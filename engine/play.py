#!/usr/bin/env python3
"""Play: keeps the SillyTavern endpoint up and runs the writers' room for each thing the player does.

  python3 engine/play.py

Leave it running while you play (Ctrl+C to stop). Nothing runs while you read. When you send something in
SillyTavern it does, in order:
  1. a short author run (your agent, headless) that decides what your move changes and writes the chapter's plan;
  2. the writer, the reader and the mender (sealed calls, no agent waiting on them);
  3. a short author run that checks the chapter, fixes it and does the bookkeeping;
  4. it sends the chapter to SillyTavern, then writes the next one ahead when no crossroads is in front of you.
Each author run starts fresh from the story's files with only what it needs, so it stays small.
"""
import contextlib, io, json, os, signal, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import providers, run, story

AUTHOR_TIMEOUT = 25 * 60     # the longest one author run may take


def ensure_server():
    """Start the SillyTavern endpoint (serve.py) unless it is already up. Returns its port and process (None when
    it was already running)."""
    port = int(story.config()['serve'].get('port', 5005))
    state = story.endpoint_state(port)
    if state == 'ours':
        return port, None
    if state == 'other':
        raise SystemExit(f'Port {port} is used by another program. Set another port under [serve] in config.toml '
                         'and use it in SillyTavern too.')
    log = open(story.run_path('logs', 'serve.log'), 'a')
    proc = subprocess.Popen([sys.executable, os.path.join(story.ROOT, 'engine', 'serve.py'), '--port', str(port)],
                            stdout=log, stderr=log, start_new_session=True, cwd=story.ROOT)
    for _ in range(50):
        if story.endpoint_state(port) == 'ours':
            return port, proc
        time.sleep(0.2)
    raise SystemExit(f'The endpoint did not start on port {port}: see .run/logs/serve.log')


def beat():
    """Tell the endpoint the author is up (it answers "the author isn't running" when this goes stale)."""
    path = story.run_path('author-alive')
    with open(path, 'a'):
        os.utime(path, None)

PLAN = """You are the author of this interactive web novel. Your brief and everything you need are below; do not
run the pack command or read these files again. Handle what the player did, as the brief says, in as few commands as
you can (usually a dice roll if needed, then one `run.py plan` command), and stop.

What the player did:
{events}

{pack}
"""
CHECK = """You are the author of this interactive web novel. Chapter {n} has just been written, read and mended. Your
brief, the chapter and the facts to hold it to are below; do not run the pack command or read these files again.
Check it, fix it with one `run.py edit` command if needed, and do the bookkeeping with one `run.py book` command, as
the brief says, then stop.

{pack}
"""


def pack(kind, n=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run.pack(kind, n)
    return buf.getvalue()


def describe(e):
    """One event in a few plain lines for the planning run."""
    kind = e.get('kind')
    lines = [f'{kind.upper()} (chapter {e.get("n")})']
    if kind == 'back':
        lines.append(f'They went back to chapter {e.get("back_to")}, then sent: '
                     + (repr(e['move']) if e.get('move') else 'Continue'))
    elif e.get('move'):
        lines.append(f'Their words: {e["move"]!r}')
    if e.get('note'):
        lines.append(f'Their note to you: {e["note"]!r}')
    for m in e.get('private') or []:
        lines.append(f'  PRIVATE [{m["role"]}] {m["text"][:1500]}')
    return '\n'.join(lines)


def agent_run(cfg, prompt, tag):
    """One short headless author run: a clean login (no personal instructions, skills or memories) and no project
    manual loaded by default; the pack command gives it what it needs. Returns usage."""
    agent = (cfg.get('author') or {}).get('agent', 'codex')
    log = story.run_path('logs', f'author-{tag}.log')
    if agent == 'claude':
        cmd = ['claude', '-p', '--setting-sources', '', '--strict-mcp-config', '--tools', 'Bash',
               '--allowedTools', 'Bash(python3:*)', 'Bash(cat:*)', 'Bash(head:*)', 'Bash(tail:*)', 'Bash(grep:*)',
               'Bash(ls:*)', '--output-format', 'stream-json', '--verbose',
               '--model', cfg['claude'].get('model') or 'opus']
        env = os.environ
    else:
        cmd = ['codex', 'exec', '-s', 'workspace-write', '-c', 'sandbox_workspace_write.network_access=true',
               '-c', 'project_doc_max_bytes=0', '-c', 'model_reasoning_effort="medium"', '--disable', 'memories',
               '--disable', 'plugins', '--disable', 'apps', '--skip-git-repo-check', '--json']
        if cfg['codex'].get('model'):
            cmd += ['-m', cfg['codex']['model']]
        cmd.append('-')
        env = {**os.environ, 'CODEX_HOME': providers.codex_home()}
    t = time.time()
    with open(log, 'w') as f:
        try:
            r = subprocess.run(cmd, input=prompt, cwd=story.ROOT, stdout=subprocess.PIPE, stderr=f, text=True,
                               env=env, timeout=AUTHOR_TIMEOUT)
        except FileNotFoundError:
            say(f'{tag}: the {agent} command was not found. Install it, or set [author] agent in config.toml.')
            return {'ok': False, 'why': f'the {agent} command is not installed on this computer'}
        except subprocess.TimeoutExpired:
            say(f'{tag}: the author run took over {AUTHOR_TIMEOUT // 60} minutes and was stopped. See {log}.')
            return {'ok': False, 'why': 'the author run took too long and was stopped'}
        f.write(r.stdout)
    usage = {}
    if agent == 'claude':
        try:
            last = [l for l in r.stdout.splitlines() if '"type":"result"' in l.replace(' ', '')][-1]
            u = json.loads(last).get('usage') or {}
            usage = {'input': u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
                     + u.get('cache_creation_input_tokens', 0), 'cached': u.get('cache_read_input_tokens', 0),
                     'output': u.get('output_tokens', 0)}
        except (ValueError, IndexError):
            pass
    else:
        for line in r.stdout.splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get('type') == 'turn.completed':
                u = d.get('usage') or {}
                usage = {'input': u.get('input_tokens', 0), 'cached': u.get('cached_input_tokens', 0),
                         'output': u.get('output_tokens', 0)}
    usage['total'] = usage.get('input', 0) + usage.get('output', 0)
    story.usage_log({'role': 'author', 'provider': agent, 'what': tag, 'seconds': int(time.time() - t),
                     'ok': r.returncode == 0, **usage})
    say(f'{tag}: {usage["total"]:,} tokens ({usage.get("cached", 0):,} cached), {int(time.time() - t)}s')
    if r.returncode:
        limit = 'usage limit' in story.read(log).lower()
        say(f'{tag}: the author run failed' + (' (usage limit reached)' if limit else '') + f'. See {log}.')
        return {**usage, 'ok': False, 'why': "your plan's usage limit was reached; send again once it resets" if limit
                else f'the author run failed (see .run/logs/author-{tag}.log)'}
    return {**usage, 'ok': True}


def say(text):
    print(time.strftime('%H:%M:%S ') + text, flush=True)


def tell_player(why):
    """Answer the request SillyTavern is waiting on, so it does not hang when something failed."""
    if story.open_event():
        with contextlib.redirect_stdout(io.StringIO()):
            run.answer(f'no chapter this time: {why}. Send your message again to retry.')


def take(name):
    path = story.run_path(name)
    data = story.read_json(path)
    if data is not None:
        os.unlink(path)
    return data


def pipeline(job):
    args = [sys.executable, os.path.join(story.ROOT, 'engine', 'run.py'), 'chapter', str(job['n'])]
    if job.get('move'):
        args += ['--move', job['move']]
    if job.get('again'):
        args += ['--again', job['again']]
    say(f'writing chapter {job["n"]} (writer, reader, mender)...')
    log = story.run_path('logs', f'ch{story.nn(job["n"])}.log')
    with open(log, 'w') as f:
        ok = subprocess.run(args, cwd=story.ROOT, stdout=f, stderr=subprocess.STDOUT).returncode == 0
    return ok, 'usage limit' in story.read(log).lower()


def write_chapter(cfg, deliver):
    """Run what the planning run queued: pipeline, check, and (when deliver) release to the waiting request.
    Returns the chapter number shelved, or None (and, when deliver, tells the player why)."""
    why = 'the author planned nothing for it'
    for _ in range(2):                       # a check run may queue the chapter once more
        job = take('queue.json')
        if not job:
            break
        ok, limit = pipeline(job)
        if not ok:
            say(f'chapter {job["n"]} failed: see .run/logs/ch{story.nn(job["n"])}.log')
            why = ("your plan's usage limit was reached; send again once it resets" if limit else
                   f'writing it failed (see .run/logs/ch{story.nn(job["n"])}.log)')
            break
        checked = agent_run(cfg, CHECK.format(n=job['n'], pack=pack('check', job['n'])),
                            f'check-ch{story.nn(job["n"])}')
        if story.stamp(story.story_dir(cfg), job['n']).get('checked'):
            if deliver and story.open_event():
                run.release(job['n'], quiet=True)
                say(f'chapter {job["n"]} sent to SillyTavern')
            return job['n']
        why = checked.get('why') or 'the author did not pass it'
    if deliver:
        tell_player(why)
    return None


def ends_at_crossroads(cfg, n):
    return bool(story.options_of(story.read(f'{story.story_dir(cfg)}/chapters/ch{story.nn(n)}.md')))


def write_ahead(cfg, n):
    """After chapter n reached the player with no crossroads at its end: plan, write and shelve chapter n+1."""
    if ends_at_crossroads(cfg, n) or story.stamp(story.story_dir(cfg), n + 1).get('checked'):
        return
    if not agent_run(cfg, PLAN.format(events=f'WRITE AHEAD (chapter {n + 1}): the player is reading chapter {n}; it ends '
                                      f'with no crossroads.', pack=pack('plan')), f'plan-ch{story.nn(n + 1)}-ahead')['ok']:
        return
    if write_chapter(cfg, deliver=False):
        say(f'chapter {n + 1} is on the shelf')


def handle(cfg, todo):
    shelf = [e for e in todo if e.get('by_shelf')]
    rest = [e for e in todo if not e.get('by_shelf')]
    last_sent = None
    if rest:
        planned = agent_run(cfg, PLAN.format(events='\n\n'.join(describe(e) for e in rest), pack=pack('plan')),
                            f'plan-{rest[-1]["id"]}')
        if planned['ok']:
            last_sent = write_chapter(cfg, deliver=True)
        else:
            take('queue.json')
            tell_player(planned['why'])
    elif shelf:
        last_sent = shelf[-1].get('n')
    review = take('review-queue.json')
    if review:
        say(f'second author on stretch {review["stretch"]}...')
        subprocess.run([sys.executable, os.path.join(story.ROOT, 'engine', 'run.py'), 'review',
                        str(review['stretch'])], cwd=story.ROOT, stdout=subprocess.DEVNULL)
    if last_sent:
        write_ahead(cfg, last_sent)


def main():
    cfg = story.config()
    if cfg.get('missing'):
        raise SystemExit('No config.toml yet: open your agent in this folder and say "start" first.')
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # `pkill -f engine/play.py` stops it like Ctrl+C
    port, server = ensure_server()
    agent = (cfg.get('author') or {}).get('agent', 'codex')
    say(f'Playing "{cfg["story"]}". SillyTavern: http://127.0.0.1:{port}/v1, model "author". Author: {agent}. '
        'Ctrl+C to stop.')
    stop = threading.Event()

    def keep_beating():                      # the endpoint knows the author is up, even during a long run
        while not stop.wait(30):
            beat()

    threading.Thread(target=keep_beating, daemon=True).start()
    try:
        while True:
            beat()
            new = story.take_new_events()
            if not new:
                time.sleep(2)
                continue
            say(', '.join(e.get('kind', '?') + (' (from the shelf)' if e.get('by_shelf') else '') for e in new))
            handle(cfg, new)
    except KeyboardInterrupt:
        print('\nStopped. Run it again to keep playing.')
    finally:
        stop.set()
        if server:
            server.terminate()


if __name__ == '__main__':
    main()
