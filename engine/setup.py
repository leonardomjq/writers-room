#!/usr/bin/env python3
"""First run: finds your subscription, writes config.toml, makes your reader profile, picks a story, and connects
SillyTavern. No AI needed for any of it (a story of your own is built by the author).

  python3 engine/setup.py

An agent can run it for you without questions: every answer has a flag (python3 engine/setup.py --help).
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import story

ROOT = story.ROOT
DEMO, DEMO_COPY = 'seventh-noon', 'play-seventh-noon'


def ask(args, text, default=''):
    if args.yes or not sys.stdin.isatty():
        return default
    answer = input(f'{text}' + (f' [{default}]' if default else '') + ': ').strip()
    return answer or default


def choose_providers(args):
    """Who does which job. Claude writes the strongest chapters, so it writes when it is there; the reader is best as a
    different family; with both subscriptions, Codex as the author spreads the load. A plain model (local, or an API)
    only takes jobs when asked for by flag: it is experimental, and its real place is Private scenes in SillyTavern."""
    have = [t for t in ('claude', 'codex') if shutil.which(t)]
    openai = {'base_url': args.openai_url or '', 'model': args.openai_model or '', 'api_key_env': args.openai_key_env or ''}
    if have:
        print('Found: ' + ', '.join({'claude': 'Claude Code', 'codex': 'Codex'}[t] for t in have))
    if len(have) == 2 and not (args.author or args.writer or args.reader) and not args.yes and sys.stdin.isatty():
        plans = ask(args, 'Both are installed. Which plans do you pay for? (claude, codex, or both)', 'both').lower()
        if plans in ('claude', 'codex'):
            have = [plans]                       # a tool can be signed in without a plan behind it
    usable = have + (['openai'] if openai['base_url'] and openai['model'] and args.author == 'openai' else [])
    if not usable:
        raise SystemExit('The room needs Codex or Claude Code, and neither is installed. Install one, sign in with your '
                         'plan, and run this again. To try a plain model instead (experimental), see the README.')
    writer = args.writer or usable[0]
    others = [u for u in usable if u != writer]
    reader = args.reader or (others[0] if others else writer)
    agents = [a for a in ('codex', 'claude') if a in have]
    author = args.author or agents[0]
    if 'openai' in (author, writer, reader):
        print('Note: running the room on a plain model is experimental and unproven. See the README.')
    return author, writer, reader, openai


def write_config(author, writer, reader, openai, story_id, user_dir, port, claude_model='opus'):
    q = json.dumps
    story.write(story.CONFIG, f"""# writers-room config, written by engine/setup.py. Run it again to redo this, or edit by hand.
story = {q(story_id)}

# The author: "codex" or "claude" (the agent plays the author), or "openai" (one call to the model under [openai]).
[author]
agent = {q(author)}

# Who does each job: "codex", "claude" or "openai".
[roles]
writer = {q(writer)}
reader = {q(reader)}
mender = "writer"
second_author = {q(reader)}

[codex]
model = ""

[claude]
model = {q(claude_model)}

[openai]
base_url = {q(openai['base_url'])}
api_key_env = {q(openai['api_key_env'])}
model = {q(openai['model'])}

[serve]
port = {int(port)}

[sillytavern]
user_dir = {q(user_dir)}
""")


def make_player(novels, english):
    """Your own copy of the reader's profile (never in git), changed only where your answers change it."""
    text = story.read(story.player_path())
    if novels:
        text = re.sub(r'(?s)Novels they love:.*?(?=\n\n|\Z)', f'Novels they love: {novels}', text, count=1)
    if english == 'first':
        text = re.sub(r'(?s)\s*English may be their second language,\s*so they want the most common words and no idioms; '
                      r'a rare word or an idiom pulls them out\.', ' They want plain, clear English.', text, count=1)
    story.write(f'{ROOT}/player.md', text)


def is_user_dir(path):
    """A SillyTavern user folder, even a brand-new one that hasn't made all its folders yet."""
    return os.path.isdir(path) and any(os.path.exists(os.path.join(path, f)) for f in ('settings.json', 'characters'))


def user_dirs(path):
    """The SillyTavern user folders under a path: the install, its data folder, or a user folder itself."""
    path = os.path.abspath(os.path.expanduser(path))
    if is_user_dir(path) and os.path.basename(os.path.dirname(path)) == 'data':
        return [path]
    found = sorted(p for p in glob.glob(os.path.join(path, 'data', '*')) if is_user_dir(p))
    preferred = [p for p in found if os.path.basename(p) == 'default-user']
    return preferred + [p for p in found if p not in preferred] or ([path] if is_user_dir(path) else [])


def find_sillytavern(args):
    if args.sillytavern:
        found = user_dirs(args.sillytavern)
        if not found:
            raise SystemExit(f'No SillyTavern user folder under {args.sillytavern}')
        return found[0]
    home = os.path.expanduser('~')
    for base in [home, os.path.join(home, 'Documents'), os.path.join(home, 'Workspaces')]:
        for install in glob.glob(os.path.join(base, '[Ss]illy[Tt]avern*')):
            found = user_dirs(install)
            if found:
                return found[0]
    path = ask(args, 'Where is SillyTavern? (its folder; Enter to set this up by hand later)')
    return (user_dirs(path) or [''])[0] if path else ''


def link_extension(user_dir):
    """Put the extension in SillyTavern. A link, so a git pull updates it; a copy where links are not possible."""
    src, dest = os.path.join(ROOT, 'extension'), os.path.join(user_dir, 'extensions', 'writers-room')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.islink(dest) or os.path.isfile(dest):
        os.unlink(dest)
    elif os.path.isdir(dest):
        shutil.rmtree(dest)
    try:
        os.symlink(src, dest)
    except OSError:
        shutil.copytree(src, dest)
    os.makedirs(os.path.join(user_dir, 'user', 'files'), exist_ok=True)
    return dest


def main():
    ap = argparse.ArgumentParser(description='First run of writers-room.')
    ap.add_argument('--author', choices=('codex', 'claude', 'openai'))
    ap.add_argument('--writer', choices=('codex', 'claude', 'openai'))
    ap.add_argument('--reader', choices=('codex', 'claude', 'openai'))
    ap.add_argument('--openai-url', help='experimental, with --author openai: the plain model\'s URL')
    ap.add_argument('--openai-model', help='experimental: the plain model')
    ap.add_argument('--openai-key-env', help='experimental: the NAME of the environment variable with the key, never the key')
    ap.add_argument('--novels', help='novels or kinds of stories you love')
    ap.add_argument('--english', choices=('first', 'second'))
    ap.add_argument('--story', help='"demo" (the default), or a story already in stories/')
    ap.add_argument('--title', help='experimental, plain model only: the title of a new story')
    ap.add_argument('--premise', help='experimental, plain model only: a new story\'s premise')
    ap.add_argument('--sillytavern', help='the SillyTavern folder')
    ap.add_argument('--port', type=int, default=5005)
    ap.add_argument('--no-test', action='store_true', help='do not test the models')
    ap.add_argument('--yes', action='store_true', help='ask nothing; take the defaults')
    args = ap.parse_args()

    if os.path.exists(story.CONFIG) and not args.yes and sys.stdin.isatty():
        if ask(args, 'config.toml exists. Replace it? (y/n)', 'n').lower() != 'y':
            raise SystemExit('Kept. Nothing changed.')

    author, writer, reader, openai = choose_providers(args)
    user_dir = find_sillytavern(args)
    which = args.story or 'demo'
    story_id = DEMO_COPY if which == 'demo' else which
    if which != 'demo' and not os.path.isdir(f'{ROOT}/stories/{story_id}') and author != 'openai':
        raise SystemExit(f'No story {story_id} yet. Run this with the demo, then open your agent here and say "new story".')
    live = story_id if which == 'demo' or os.path.isdir(f'{ROOT}/stories/{story_id}') else DEMO
    claude_model = 'opus'
    write_config(author, writer, reader, openai, live, user_dir, args.port)

    if not args.no_test:
        for who in sorted({author, writer, reader}):
            r = subprocess.run([sys.executable, 'engine/run.py', 'test', who], cwd=ROOT, capture_output=True, text=True)
            said = (r.stdout + r.stderr).strip()
            if who == 'claude' and 'OK' not in said.split('(')[0]:       # a plan without Opus still has Sonnet
                claude_model = 'sonnet'
                write_config(author, writer, reader, openai, live, user_dir, args.port, claude_model)
                r = subprocess.run([sys.executable, 'engine/run.py', 'test', who], cwd=ROOT, capture_output=True, text=True)
                said = (r.stdout + r.stderr).strip()
            print(said)
            if 'OK' not in said.split('(')[0]:
                raise SystemExit(f'{who} did not answer: fix that, then run this again.')

    novels = args.novels if args.novels is not None else ask(args, 'Which novels or kinds of stories do you love?')
    english = args.english or ask(args, 'Is English your first language? (first/second)', 'second')
    make_player(novels, 'first' if english.lower().startswith(('f', 'y')) else 'second')

    if which == 'demo':
        if not os.path.isdir(f'{ROOT}/stories/{DEMO_COPY}'):
            shutil.copytree(f'{ROOT}/stories/{DEMO}', f'{ROOT}/stories/{DEMO_COPY}')
    elif not os.path.isdir(f'{ROOT}/stories/{story_id}'):
        import play, run
        title = args.title or ask(args, 'The title', story_id.replace('-', ' ').title())
        premise = args.premise or ask(args, 'The premise, in a line or two (a world, a hero, a hook)')
        if not premise:
            raise SystemExit('A new story needs a premise.')
        run.new(story_id, title)
        write_config(author, writer, reader, openai, story_id, user_dir, args.port, claude_model)
        play.create_story(story.config(), premise)

    print()
    if user_dir:
        try:
            print(f'SillyTavern: extension installed in {link_extension(user_dir)}')
        except OSError as e:                     # an agent's sandbox may not write outside this folder
            print(f'Could not install the extension into SillyTavern ({e.strerror}). Run setup again where it may '
                  f'write to {user_dir}, or link extension/ there by hand.')
    story.publish()
    print('Done. For Private scenes, keep your own model as a connection profile in SillyTavern. '
          'For a story of your own, open your agent here and say "new story". Two things left:')
    print('  1. Start the room, and leave it running while you play:  python3 engine/play.py')
    print('  2. Refresh SillyTavern and follow what it offers. It connects and opens the story in one tap.' if user_dir
          else '  2. In SillyTavern: follow the README, Setup by hand.')


if __name__ == '__main__':
    main()
