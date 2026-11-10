#!/usr/bin/env python3
"""Play: keeps the SillyTavern endpoint up and runs the writers' room for each thing the player does.

  python3 engine/play.py                 (in a terminal; Ctrl+C stops it)
  python3 engine/play.py --background    (keeps running on its own; for an agent to start it)
  python3 engine/play.py --stop

Leave it running while you play. Nothing runs while you read. When you send something in
SillyTavern it does, in order:
  1. a short author run (your agent, headless) that decides what your move changes and writes the chapter's plan;
  2. the writer, the reader and the mender (sealed calls, no agent waiting on them);
  3. a short author run that checks the chapter, fixes it and does the bookkeeping;
  4. it sends the chapter to SillyTavern, then writes the next one ahead when no crossroads is in front of you.
Each author run starts fresh from the story's files with only what it needs, so it stays small.
"""
import contextlib, io, json, os, signal, subprocess, sys, threading, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import providers, run, story

AUTHOR_TIMEOUT = 25 * 60     # the longest one author run may take
child = None                 # the process running now, so a stop can end it and everything it started


class Interrupted(Exception):
    """The player sent a move that voids the work being done."""


def stop_child(p):
    with contextlib.suppress(OSError):
        os.killpg(p.pid, signal.SIGTERM)
    try:
        p.wait(3)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(p.pid, signal.SIGKILL)
        p.wait()


def run_child(cmd, text_in=None, stop=None, timeout=None, **kw):
    """Like subprocess.run, in its own process group, and `stop()` can end it early. Returns (exit code, its stdout)."""
    global child
    p = child = subprocess.Popen(cmd, start_new_session=True, text=True, cwd=story.ROOT,
                                 stdin=subprocess.PIPE if text_in is not None else None, **kw)
    end = time.time() + timeout if timeout else None
    try:
        while True:
            try:
                out = p.communicate(text_in, timeout=2)[0]
                return p.returncode, out
            except subprocess.TimeoutExpired:
                text_in = None               # it has its input already; a second try must not send it again
                if stop and stop():
                    stop_child(p)
                    raise Interrupted()
                if end and time.time() > end:
                    stop_child(p)
                    raise
    finally:
        child = None


def move_waiting():
    """An unhandled move, Redo or Back (or a Private stretch) makes the chapter being written ahead useless."""
    return any(not e.get('seen') and (e.get('kind') in ('move', 'redo', 'back') or e.get('private'))
               for e in story.events())


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
    story.publish()

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


def agent_run(cfg, prompt, tag, job, stop=None):
    """One short headless author run: a clean login (no personal instructions, skills or memories) and no project
    manual loaded by default; the prompt holds what it needs. On a plain model (agent "openai") engine/author.py takes
    the job instead of the prompt and asks the model only for what needs writing. Returns usage, with ok and, when not
    ok, why."""
    agent = (cfg.get('author') or {}).get('agent', 'codex')
    log = story.run_path('logs', f'author-{tag}.log')
    if agent == 'claude':
        cmd = ['claude', '-p', '--setting-sources', '', '--strict-mcp-config', '--tools', 'Bash',
               '--allowedTools', 'Bash(python3 engine/run.py:*)', 'Bash(cat:*)', 'Bash(head:*)', 'Bash(tail:*)', 'Bash(grep:*)',
               'Bash(ls:*)', '--output-format', 'stream-json', '--verbose',
               '--model', cfg['claude'].get('model') or 'opus']
        env = os.environ
    elif agent == 'openai':
        cmd = [sys.executable, os.path.join(story.ROOT, 'engine', 'author.py')]
        prompt = json.dumps(job)
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
            code, out = run_child(cmd, prompt, stop, AUTHOR_TIMEOUT, stdout=subprocess.PIPE, stderr=f, env=env)
        except FileNotFoundError:
            say(f'{tag}: the {agent} command was not found. Install it, or set [author] agent in config.toml.')
            return {'ok': False, 'why': f'the {agent} command is not installed on this computer'}
        except subprocess.TimeoutExpired:
            say(f'{tag}: the author run took over {AUTHOR_TIMEOUT // 60} minutes and was stopped. See {log}.')
            return {'ok': False, 'why': 'the author run took too long and was stopped'}
        f.write(out or '')
    out = out or ''
    usage = {}
    if agent == 'openai':                         # its calls log their own usage
        try:
            result = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {'ok': False, 'why': f'the author run failed (see .run/logs/author-{tag}.log)'}
        if not result.get('ok'):
            say(f'{tag}: {result.get("why")}')
        return {'ok': bool(result.get('ok')), 'why': result.get('why', '')}
    if agent == 'claude':
        try:
            last = [l for l in out.splitlines() if '"type":"result"' in l.replace(' ', '')][-1]
            u = json.loads(last).get('usage') or {}
            usage = {'input': u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
                     + u.get('cache_creation_input_tokens', 0), 'cached': u.get('cache_read_input_tokens', 0),
                     'output': u.get('output_tokens', 0)}
        except (ValueError, IndexError):
            pass
    else:
        for line in out.splitlines():
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
                     'ok': code == 0, **usage})
    say(f'{tag}: {usage["total"]:,} tokens ({usage.get("cached", 0):,} cached), {int(time.time() - t)}s')
    if code:
        limit = bool(providers.LIMIT.search(story.read(log)[-1500:]))
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


def pipeline(job, stop=None):
    args = [sys.executable, os.path.join(story.ROOT, 'engine', 'run.py'), 'chapter', str(job['n'])]
    if job.get('move'):
        args += ['--move', job['move']]
    if job.get('again'):
        args += ['--again', job['again']]
    say(f'writing chapter {job["n"]} (writer, reader, mender)...')
    log = story.run_path('logs', f'ch{story.nn(job["n"])}.log')
    with open(log, 'w') as f:
        code, _ = run_child(args, stop=stop, stdout=f, stderr=subprocess.STDOUT)
    return code == 0, bool(providers.LIMIT.search(story.read(log)[-1500:]))


def write_chapter(cfg, deliver, stop=None):
    """Run what the planning run queued: pipeline, check, and (when deliver) release to the waiting request.
    Returns the chapter number shelved, or None (and, when deliver, tells the player why)."""
    why = 'the author planned nothing for it'
    for _ in range(2):                       # a check run may queue the chapter once more
        job = take('queue.json')
        if not job:
            break
        ok, limit = pipeline(job, stop)
        if not ok:
            say(f'chapter {job["n"]} failed: see .run/logs/ch{story.nn(job["n"])}.log')
            why = ("your plan's usage limit was reached; send again once it resets" if limit else
                   f'writing it failed (see .run/logs/ch{story.nn(job["n"])}.log)')
            break
        if stop and stop():
            raise Interrupted()
        story.room('checking')
        checked = agent_run(cfg, CHECK.format(n=job['n'], pack=pack('check', job['n'])),
                            f'check-ch{story.nn(job["n"])}', {'kind': 'check', 'n': job['n']}, stop)
        if checked['ok'] and not story.stamp(story.story_dir(cfg), job['n']).get('checked') \
                and not os.path.exists(story.run_path('queue.json')):
            say(f'chapter {job["n"]}: the check left no bookkeeping; shelving the chapter as it is')   # never block reading
            with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):
                run.shelve(job['n'])
        if story.stamp(story.story_dir(cfg), job['n']).get('checked'):
            if stop and stop():                  # never hand this chapter to a message it wasn't written for
                raise Interrupted()
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
    if ends_at_crossroads(cfg, n) or story.stamp(story.story_dir(cfg), n + 1).get('checked') or move_waiting():
        return
    story.room('planning')
    try:
        if not agent_run(cfg, PLAN.format(events=f'WRITE AHEAD (chapter {n + 1}): the player is reading chapter {n}; it '
                                          f'ends with no crossroads.', pack=pack('plan')),
                         f'plan-ch{story.nn(n + 1)}-ahead', {'kind': 'ahead', 'n': n + 1}, move_waiting)['ok']:
            return
        if write_chapter(cfg, deliver=False, stop=move_waiting):
            say(f'chapter {n + 1} is on the shelf')
    except Interrupted:
        take('queue.json')
        say(f'chapter {n + 1} stopped: the player sent something that changes it')


def newer_waiting():
    """The player sent something else while this was being written: what it was for is void."""
    return any(not e.get('seen') for e in story.events())


def settle(cfg, e):
    """The story's files must say only what the player has read. A Redo takes back the bookkeeping of the chapter it
    replaces; anything else that doesn't take the chapter written ahead takes back that chapter's bookkeeping."""
    sdir = story.story_dir(cfg)
    kind, n = e.get('kind'), e.get('n')
    if kind == 'redo':
        with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            run.back(n - 1)
    elif kind not in ('back', 'note'):
        s = story.stamp(sdir, n)
        if s.get('checked') and not s.get('released') and s.get('before'):
            story.restore(sdir, s['before'])
            story.publish(cfg)


def handle(cfg, todo):
    shelf = [e for e in todo if e.get('by_shelf')]
    rest = [e for e in todo if not e.get('by_shelf') and not e.get('done')]
    last_sent = None
    if rest and all(e.get('kind') == 'continue' and not e.get('private') and not e.get('note') for e in rest):
        latest = rest[-1]                     # a Continue that came while this chapter was being written ahead
        if story.shelf_chapter(story.story_dir(cfg), latest['n']):
            run.release(latest['n'], latest, quiet=True)
            story.update_event(latest['id'], by_shelf=True)
            say(f'chapter {latest["n"]} sent to SillyTavern from the shelf')
            last_sent, rest = latest['n'], []
    if rest:
        settle(cfg, rest[-1])
        story.room('planning')
        what = '\n\n'.join(describe(e) for e in rest)
        try:
            planned = agent_run(cfg, PLAN.format(events=what, pack=pack('plan')), f'plan-{rest[-1]["id"]}',
                                {'kind': 'plan', 'events': rest, 'what': what}, newer_waiting)
            if planned['ok']:
                last_sent = write_chapter(cfg, deliver=True, stop=newer_waiting)
            else:
                take('queue.json')
                tell_player(planned['why'])
        except Interrupted:
            take('queue.json')
            story.room(None)
            say('stopped: the player sent something newer')
            return
    elif shelf:
        last_sent = shelf[-1].get('n')
    review = take('review-queue.json')
    if review:
        say(f'second author on stretch {review["stretch"]}...')
        subprocess.run([sys.executable, os.path.join(story.ROOT, 'engine', 'run.py'), 'review',
                        str(review['stretch'])], cwd=story.ROOT, stdout=subprocess.DEVNULL)
    story.room(None)
    if last_sent:
        write_ahead(cfg, last_sent)
        story.room(None)


def create_story(cfg, premise):
    """Experimental: build the live (empty) story from a premise on a plain model. With an agent, the manual's "A new
    story" does this instead."""
    say('the author is building the story...')
    built = agent_run(cfg, '', 'new-story', {'kind': 'new', 'premise': premise})
    if not built['ok'] or not write_chapter(cfg, deliver=False):
        raise SystemExit(f'the story was not built: {built.get("why") or "see .run/logs/"}')
    run.card()


PID = 'play.pid'


def running_pid():
    """The pid of a room already running in this folder, or None."""
    pid = story.read_json(story.run_path(PID))
    try:
        os.kill(int(pid), 0)
        return int(pid)
    except (TypeError, ValueError, OSError):
        return None


def background():
    """Start the room on its own, with its log in .run/logs/play.log, and return."""
    if running_pid():
        raise SystemExit(f'The room is already running (pid {running_pid()}).')
    log = open(story.run_path('logs', 'play.log'), 'a')
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=story.ROOT, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    for _ in range(30):
        time.sleep(0.3)
        if p.poll() is not None:
            raise SystemExit('The room stopped right away: see .run/logs/play.log')
        if running_pid():
            break
    print(f'The room is running (pid {p.pid}). It keeps going until python3 engine/play.py --stop. '
          'Log: .run/logs/play.log')


def stop_room():
    pid = running_pid()
    if not pid:
        print('The room is not running.')
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        time.sleep(0.3)
        if not running_pid():
            break
    print('The room is stopped.')


IN_SANDBOX = ('The room cannot run inside Codex\'s sandbox: it runs Codex itself for every chapter, and a sandbox '
              'cannot open another one. Start it outside the sandbox: approve running `python3 engine/play.py '
              '--background` outside it when Codex asks, or run `python3 engine/play.py` in a terminal.')


def main():
    if os.environ.get('CODEX_SANDBOX') and '--stop' not in sys.argv:
        raise SystemExit(IN_SANDBOX)
    if '--background' in sys.argv:
        return background()
    if '--stop' in sys.argv:
        return stop_room()
    cfg = story.config()
    if cfg.get('missing'):
        raise SystemExit('No config.toml yet: run python3 engine/setup.py first.')
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # --stop (or pkill) stops it like Ctrl+C
    story.write_json(story.run_path(PID), os.getpid())
    story.retry_open_events()
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
            try:
                handle(cfg, new)
            except (Exception, SystemExit) as e:     # one bad move must never take the room down
                traceback.print_exc()
                story.room(None)
                take('queue.json')
                tell_player(f'the room hit an error ({str(e)[:120]}; see the terminal)')
    except KeyboardInterrupt:
        print('\nStopped. Run it again to keep playing.')
    finally:
        stop.set()
        story.room(None)
        if child:
            stop_child(child)
        with contextlib.suppress(OSError):
            if story.read_json(story.run_path(PID)) == os.getpid():
                os.unlink(story.run_path(PID))
        if server:
            server.terminate()


if __name__ == '__main__':
    main()
