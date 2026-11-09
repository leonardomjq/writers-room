"""Shared helpers: the config, the live story's files, the released chapters, and the run folder.

Every other script imports this. Standard library only (Python 3.11 or newer, for tomllib).
"""
import contextlib, fcntl, hashlib, json, os, re, sys, time, urllib.error, urllib.request

if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11 or newer is needed (for tomllib). Install a newer python3 and try again.')
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFS = f'{ROOT}/briefs'
RUN = f'{ROOT}/.run'                 # events, replies, locks, logs; never committed
CONFIG = f'{ROOT}/config.toml'
OPTION_SPLIT = r'\n\s*\**1[.)]\**\s'


# ---- files ----

def read(path, default=''):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return default


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text.rstrip() + '\n')
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=1))


def body(text):
    """A file without its leading "# ..." comment lines (notes for the author, not for a model)."""
    lines = text.split('\n')
    while lines and (lines[0].startswith('#') or not lines[0].strip()):
        lines.pop(0)
    return '\n'.join(lines).strip()


# ---- the config ----

DEFAULTS = {
    'story': 'seventh-noon',
    'author': {'agent': 'codex'},
    'roles': {'writer': 'codex', 'reader': 'codex', 'mender': 'writer', 'second_author': 'codex'},
    'codex': {'model': ''},
    'claude': {'model': 'opus'},
    'openai': {'base_url': 'https://openrouter.ai/api/v1', 'api_key_env': 'OPENROUTER_API_KEY', 'model': ''},
    'serve': {'port': 5005},
    'sillytavern': {'user_dir': ''},
}


def config():
    """config.toml over the defaults. No config yet: the defaults, with 'missing' set."""
    cfg = json.loads(json.dumps(DEFAULTS))
    if not os.path.exists(CONFIG):
        cfg['missing'] = True
        return cfg
    try:
        with open(CONFIG, 'rb') as f:
            mine = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f'config.toml has a mistake: {e}. Fix that line, or ask your agent to.')
    for k, v in mine.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def story_dir(cfg=None):
    cfg = cfg or config()
    path = f'{ROOT}/stories/{cfg["story"]}'
    if not os.path.isdir(path):
        raise SystemExit(f'no story folder: stories/{cfg["story"]} (set story = "..." in config.toml)')
    return path


# ---- chapters ----

def strip_title(text):
    return re.sub(r'^\s*#\s+[^\n]*\n', '', text.strip(), count=1).strip()


def title_of(text):
    m = re.match(r'\s*#\s+([^\n]*)', text or '')
    return m.group(1).strip() if m else ''


def prose_of(text):
    """A chapter's prose: no title line, no options under it."""
    return re.split(OPTION_SPLIT, '\n' + strip_title(text))[0].strip()


def options_of(text):
    m = re.search(OPTION_SPLIT + r'.*', '\n' + strip_title(text), re.S)
    if not m:
        return []
    return [re.sub(r'^\s*\**[1-9][.)]\**\s*', '', l).strip() for l in m.group(0).strip().splitlines()
            if re.match(r'^\s*\**[1-9][.)]', l)]


def key(text):
    """A chapter's fingerprint as SillyTavern shows it: its prose (no title, no options), letters and digits only,
    first 400. Survives markdown, quote styles and whitespace that a frontend may change."""
    t = prose_of(text) if text.lstrip().startswith('#') else re.split(OPTION_SPLIT, '\n' + text.strip())[0]
    t = re.sub(r'[^a-z0-9]+', '', t.lower())
    return hashlib.sha1(t[:400].encode()).hexdigest()[:16] if t else ''


def head(text):
    """The start of a chapter's prose, letters and digits only: how the SillyTavern extension recognizes a chapter."""
    return re.sub(r'[^a-z0-9]+', '', prose_of(text).lower())[:60]


def shelf_chapter(sdir, n, cfg=None):
    """Chapter n's text if it is checked, written ahead for a Continue and still follows what the player has."""
    s = stamp(sdir, n)
    text = read(f'{sdir}/chapters/ch{nn(n)}.md')
    if s.get('checked') and not s.get('released') and not s.get('move') and s.get('follows') == n - 1 \
            and s.get('checked_sha') == text_sha(text):
        return text
    return None


def number(name):
    m = re.search(r'(\d+)', name)
    return int(m.group(1)) if m else None


def nn(n):
    return f'{int(n):02d}'


def released(sdir):
    """chapters/released.json: every chapter the player has received, in order:
    {nn, key, title, move, event, commit, at}. Chapter 1 is the card's first message."""
    return read_json(f'{sdir}/chapters/released.json', []) or []


def save_released(sdir, items):
    write_json(f'{sdir}/chapters/released.json', items)


def stamp(sdir, n):
    return read_json(f'{sdir}/chapters/ch{nn(n)}.json', {}) or {}


def text_sha(text):
    return hashlib.sha1((text or '').strip().encode()).hexdigest()[:16]


# ---- snapshots, for Back ----

def snapshot(sdir, label):
    """A copy of the story folder as it is now, in .run/snapshots/<story>/<label>, so Back can restore it. Plain files
    (no git), so it works inside any agent's sandbox. Returns the label."""
    import shutil
    dest = run_path('snapshots', os.path.basename(sdir), label)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(sdir, dest)
    return label


def restore(sdir, label):
    import shutil
    src = os.path.join(RUN, 'snapshots', os.path.basename(sdir), label)
    if not os.path.isdir(src):
        raise SystemExit(f'no snapshot {label} for this story')
    for name in os.listdir(sdir):
        path = os.path.join(sdir, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
    shutil.copytree(src, sdir, dirs_exist_ok=True)


# ---- the run folder: events from the page, replies to it ----

def run_path(*parts):
    path = os.path.join(RUN, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


@contextlib.contextmanager
def events_lock():
    """Held around every read-modify-write of events.json: the endpoint, play.py and run.py all change it."""
    with open(run_path('events.lock'), 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def events():
    return read_json(run_path('events.json'), []) or []


def save_events(items):
    write_json(run_path('events.json'), items[-200:])


def add_event(ev):
    with events_lock():
        items = events()
        ev = {'id': f'{int(time.time() * 1000)}', 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'seen': False,
              'done': False, **ev}
        items.append(ev)
        save_events(items)
    return ev


def update_event(eid, **changes):
    with events_lock():
        items = events()
        for e in items:
            if e['id'] == eid:
                e.update(changes)
        save_events(items)


def take_new_events():
    """The events play.py has not handled yet, marked as seen."""
    with events_lock():
        items = events()
        new = [e for e in items if not e.get('seen')]
        if new:
            for e in items:
                e['seen'] = True
            save_events(items)
    return new


def retry_open_events():
    """At start: a move the last run took but never answered (it crashed, or was stopped) is handled again."""
    with events_lock():
        items = events()
        for e in items:
            if not e.get('done'):
                e['seen'] = False
        save_events(items)


def endpoint_state(port):
    """'ours' (the writers-room endpoint answers on the port), 'other' (something else does) or 'free'."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as r:
            return 'ours' if b'writers-room' in r.read(500) else 'other'
    except urllib.error.HTTPError:
        return 'other'
    except (OSError, ValueError):
        return 'free'


def open_event():
    """The newest event still waiting for an answer (a chapter or a reply), or None."""
    for e in reversed(events()):
        if not e.get('done'):
            return e
    return None


def reply_path(eid):
    return run_path('replies', f'{eid}.md')


# ---- the public status: what the page may know (room steps and released chapters, never anything unreleased) ----

def room(step):
    """The step the writers' room is on: planning, writing, reading, mending, checking, or None."""
    write_json(run_path('room.json'), {'step': step, 'since': int(time.time())} if step else {})
    publish()


def st_files(cfg=None):
    """SillyTavern's user/files folder (the page reads our status from it), or None when it is not set up."""
    user_dir = (cfg or config()).get('sillytavern', {}).get('user_dir', '')
    path = os.path.join(os.path.expanduser(user_dir), 'user', 'files') if user_dir else ''
    return path if path and os.path.isdir(os.path.dirname(path)) else None


def publish(cfg=None):
    """Write the public status where the page can read it. Never raises: the game runs without the extension."""
    try:
        cfg = cfg or config()
        sdir = story_dir(cfg)
        chs = [r for r in released(sdir) if r.get('nn') and not r.get('kind')]
        last = chs[-1] if chs else None
        items = []
        for r in chs:
            items.append({'n': r['nn'], 'title': r.get('title', ''),
                          'head': head(read(f'{sdir}/chapters/ch{nn(r["nn"])}.md'))})
        try:
            last_at = int(time.mktime(time.strptime(last['at'], '%Y-%m-%d %H:%M:%S'))) if last else 0
        except (ValueError, KeyError):
            last_at = 0
        beat = os.path.getmtime(run_path('author-alive')) if os.path.exists(run_path('author-alive')) else 0
        meta = read_json(f'{sdir}/story.json', {}) or {}
        data = {'v': 1, 'story': cfg['story'], 'title': meta.get('title', ''), 'port': cfg['serve'].get('port', 5005),
                'beat': int(beat), 'room': read_json(run_path('room.json'), {}) or {}, 'chapters': items,
                'recap': stamp(sdir, last['nn']).get('recap', '') if last else '', 'last_at': last_at}
        write_json(run_path('status.json'), data)
        files = st_files(cfg)
        if files:
            write_json(os.path.join(files, 'writers-room.json'), data)
            card = read(f'{sdir}/card.json')
            if card:
                write(os.path.join(files, 'writers-room-card.json'), card)
    except (OSError, SystemExit, ValueError) as e:
        print(f'status not published: {e}', file=sys.stderr)


# ---- the reader's profile: your copy (made at setup, never in git) over the default ----

def player_path():
    mine = f'{ROOT}/player.md'
    return mine if os.path.exists(mine) else f'{BRIEFS}/player.md'


def usage_log(entry):
    with open(run_path('usage.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps({'at': time.strftime('%Y-%m-%d %H:%M:%S'), **entry}) + '\n')
