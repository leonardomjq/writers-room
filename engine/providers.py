"""The models behind each role: the codex CLI, the claude CLI, or any OpenAI-compatible API.

Every call is sealed: it runs from an empty folder outside the project, with tools off and none of the user's plugins,
memories or project instructions, so a model answers from its prompt alone and never sees a file its role must not see.
A call returns (text, usage); a failure returns ('ERROR: ...', usage).
"""
import json, os, re, subprocess, tempfile, time, urllib.error, urllib.request

import story

SEALED = os.path.join(tempfile.gettempdir(), 'writers-room-sealed')
LIMIT = re.compile(r'usage limit|rate limit|limit reached|\bresets? (?:at|in)\b|out of (?:extra )?usage|quota', re.I)
EFFORTS = ('low', 'medium', 'high')


def sealed_dir():
    os.makedirs(SEALED, exist_ok=True)
    for f in os.listdir(SEALED):                      # nothing a model could pick up
        p = os.path.join(SEALED, f)
        if os.path.isfile(p) and not f.startswith('codex-'):
            os.unlink(p)
    return SEALED


def codex_login_file():
    """The user's Codex login (auth.json), or None when Codex keeps it somewhere else, like the system keyring."""
    path = os.path.join(os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex'), 'auth.json')
    return path if os.path.exists(path) else None


def codex_home():
    """A plain CODEX_HOME: the user's login and nothing else (no plugins, MCP servers, memories or global AGENTS.md),
    so what one sealed call saw can never reach another."""
    home = os.path.join(story.RUN, 'codex-home')
    os.makedirs(home, exist_ok=True)
    login = codex_login_file()
    link = os.path.join(home, 'auth.json')
    if login and not os.path.lexists(link):
        os.symlink(login, link)
    cfg = os.path.join(home, 'config.toml')
    if not os.path.exists(cfg):
        story.write(cfg, '# writers-room: a plain home for sealed calls (login only)')
    return home


def by_codex(prompt, effort='medium', model='', timeout=1500):
    out = os.path.join(sealed_dir(), f'codex-{os.getpid()}-{time.time_ns()}.md')
    cmd = ['codex', 'exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only',
           '--disable', 'shell_tool', '--disable', 'unified_exec', '--disable', 'memories', '--disable', 'plugins',
           '--disable', 'apps', '-c', f'model_reasoning_effort="{effort}"', '-o', out]
    if model:
        cmd += ['-m', model]
    cmd.append('-')
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=SEALED,
                           env={**os.environ, 'CODEX_HOME': codex_home()})
    except subprocess.TimeoutExpired:
        return f'ERROR: codex timed out after {timeout}s', {}
    except OSError as e:
        return f'ERROR: codex could not start ({e})', {}
    err = (r.stderr or '') + (r.stdout or '')
    m = re.search(r'tokens used\s*\n?\s*([\d,]+)', err)
    usage = {'total': int(m.group(1).replace(',', ''))} if m else {}
    text = story.read(out)
    if os.path.exists(out):
        os.unlink(out)
    if r.returncode or not text:
        return 'ERROR: ' + err.strip()[-600:], usage
    return text, usage


def by_claude(prompt, effort='medium', model='opus', timeout=1500):
    cmd = ['claude', '-p', '--model', model or 'opus', '--effort', effort, '--tools', '', '--strict-mcp-config',
           '--setting-sources', '', '--output-format', 'json', '--no-session-persistence']
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=sealed_dir())
    except subprocess.TimeoutExpired:
        return f'ERROR: claude timed out after {timeout}s', {}
    except OSError as e:
        return f'ERROR: claude could not start ({e})', {}
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return 'ERROR: ' + ((r.stdout or '') + (r.stderr or '')).strip()[-600:], {}
    u = data.get('usage') or {}
    usage = {'input': (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0)
             + (u.get('cache_creation_input_tokens') or 0), 'output': u.get('output_tokens') or 0}
    usage['total'] = usage['input'] + usage['output']
    if data.get('total_cost_usd') is not None:
        usage['cost_usd_if_api'] = round(data['total_cost_usd'], 4)
    text = (data.get('result') or '').strip()
    if data.get('is_error') or r.returncode or not text:
        return 'ERROR: ' + (text or r.stderr or 'no answer')[-600:], usage
    return text, usage


def by_openai(prompt, effort='medium', base_url='', api_key_env='', model='', timeout=1500):
    key = os.environ.get(api_key_env or '', '')
    if not base_url or not model:
        return 'ERROR: [openai] needs base_url and model in config.toml', {}
    if not key and 'localhost' not in base_url and '127.0.0.1' not in base_url:
        return f'ERROR: the environment variable {api_key_env} is empty (export it before starting the author)', {}
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 16000}
    req = urllib.request.Request(base_url.rstrip('/') + '/chat/completions', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          **({'Authorization': f'Bearer {key}'} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return f'ERROR: HTTP {e.code}: {e.read().decode(errors="ignore")[:400]}', {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f'ERROR: {e}', {}
    u = data.get('usage') or {}
    usage = {'input': u.get('prompt_tokens') or 0, 'output': u.get('completion_tokens') or 0}
    usage['total'] = usage['input'] + usage['output']
    if u.get('cost') is not None:
        usage['cost_usd'] = u['cost']
    try:
        text = (data['choices'][0]['message']['content'] or '').strip()
    except (KeyError, IndexError, TypeError):
        return f'ERROR: unexpected answer: {str(data)[:400]}', usage
    text = re.sub(r'(?s)^\s*<think>.*?</think>\s*', '', text)     # a reasoning model's thinking, if it leaks
    return (text or 'ERROR: empty answer'), usage


def provider_for(role, cfg):
    roles = cfg['roles']
    who = roles.get(role) or 'codex'
    if who == 'writer':                               # the mender is the writer by default: one voice per chapter
        who = roles.get('writer') or 'codex'
    return who


def call(role, prompt, effort='medium', cfg=None, what=''):
    """One sealed call for a role (writer, reader, mender, second_author); logs its usage."""
    cfg = cfg or story.config()
    who = provider_for(role, cfg)
    t = time.time()
    if who == 'codex':
        text, usage = by_codex(prompt, effort, cfg['codex'].get('model', ''))
    elif who == 'claude':
        text, usage = by_claude(prompt, effort, cfg['claude'].get('model', 'opus'))
    elif who == 'openai':
        o = cfg['openai']
        text, usage = by_openai(prompt, effort, o.get('base_url', ''), o.get('api_key_env', ''), o.get('model', ''))
    else:
        text, usage = f'ERROR: unknown provider "{who}" for {role} (use codex, claude or openai)', {}
    story.usage_log({'role': role, 'provider': who, 'what': what, 'seconds': int(time.time() - t),
                     'ok': not text.startswith('ERROR'), 'limit': bool(text.startswith('ERROR') and LIMIT.search(text)),
                     **usage})
    return text, who
