#!/usr/bin/env python3
"""The whole room end to end against a scripted model (tests/fake_model.py): no AI, no cost, under a minute.

  python3 tests/room.py

It sends the requests SillyTavern sends and checks what comes back and what the room did: a move, a Continue while the
next chapter is being written ahead, a move that stops the write-ahead, a dropped request that lands later, a Back, a
note, a model that answers badly, a local server that cuts the prompt, and what the page's status may show.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
for name in ('engine', 'briefs', 'stories', 'tests'):
    shutil.copytree(os.path.join(ROOT, name), os.path.join(tmp, name), ignore=shutil.ignore_patterns('__pycache__'))


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


MODEL, PORT = free_port(), free_port()
ST = os.path.join(tmp, 'st-user')
os.makedirs(os.path.join(ST, 'user', 'files'))
open(os.path.join(tmp, 'config.toml'), 'w').write(f"""story = "seventh-noon"
[author]
agent = "openai"
[roles]
writer = "openai"
reader = "openai"
mender = "writer"
second_author = "openai"
[openai]
base_url = "http://127.0.0.1:{MODEL}/v1"
api_key_env = ""
model = "fake"
[serve]
port = {PORT}
[sillytavern]
user_dir = "{ST}"
""")
fake = subprocess.Popen([sys.executable, 'tests/fake_model.py', '--port', str(MODEL), '--delay', '0.25'], cwd=tmp,
                        stdout=subprocess.DEVNULL)
log = open(os.path.join(tmp, 'play.log'), 'w')
play = subprocess.Popen([sys.executable, 'engine/play.py'], cwd=tmp, stdout=log, stderr=log)
results = []


def ok(name, good, got=''):
    results.append(bool(good))
    print(('PASS  ' if good else 'FAIL  ') + name + ('' if good else f'   got {got}'), flush=True)


def get(path, port=MODEL):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=5) as r:
        return json.loads(r.read())


def mode(**kw):
    urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{MODEL}/mode', json.dumps(kw).encode()), timeout=5)


def calls(kind=None):
    c = get('/calls')['calls']
    return c if kind is None else c.count(kind)


PLAY = '\n\n[[writers-room:play]]'


def marked(msgs):
    return msgs[:-1] + [(msgs[-1][0], msgs[-1][1] + PLAY)]


def send(msgs, timeout=90, mark=True):
    msgs = marked(msgs) if mark else msgs
    body = {'stream': False, 'messages': [{'role': r, 'content': t} for r, t in msgs]}
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())['choices'][0]['message']['content']


def wait_for(test, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if test():
            return True
        time.sleep(0.1)
    return False


def status():
    try:
        return json.load(open(os.path.join(ST, 'user', 'files', 'writers-room.json')))
    except (OSError, ValueError):
        return {}


try:
    wait_for(lambda: status().get('beat'), 15)
    ok('the status reaches SillyTavern\'s files, and the card with it',
       status().get('story') == 'seventh-noon' and os.path.exists(os.path.join(ST, 'user', 'files', 'writers-room-card.json')))
    ch1 = open(os.path.join(tmp, 'stories/seventh-noon/chapters/ch01.md')).read().strip()

    mid_steps = set()
    import threading
    watching = threading.Event()

    def watch():
        while not watching.is_set():
            step = status().get('room', {}).get('step')
            if step:
                mid_steps.add(step)
            time.sleep(0.05)
    threading.Thread(target=watch, daemon=True).start()
    ch2 = send([('assistant', ch1), ('user', '2')], mark=False)
    ok('a pick gets a chapter through the whole room', ch2.startswith('# ') and calls()[:4] == ['plan', 'write', 'read', 'check'], calls())
    ok('the page sees the real steps', {'planning', 'writing', 'reading', 'checking'} <= mid_steps, mid_steps)
    ok('the status lists only released chapters', [c['n'] for c in status()['chapters']] == [1, 2], status()['chapters'])
    ok('the recap belongs to the released chapter', 'chapter 2' in status()['recap'], status()['recap'])

    # chapter 3 is now being written ahead; press Continue while it is
    wait_for(lambda: calls('plan') >= 2)
    ch3 = send([('assistant', ch1), ('user', '2'), ('assistant', ch2)])
    played = lambda: open(os.path.join(tmp, 'play.log')).read()
    ok('a Continue during write-ahead takes that chapter and writes nothing twice',
       ch3.startswith('# ') and ch3 != ch2 and played().count('writing chapter 3') == 1, calls())

    # the book's rhythm: chapter 4 is the first that may end at a crossroads. Continue again, once it is on the shelf.
    wait_for(lambda: 'chapter 4 is on the shelf' in played(), 30)
    ch4 = send([('assistant', ch1), ('user', '2'), ('assistant', ch2), ('assistant', ch3)])
    ok('a Continue with the chapter on the shelf comes at once, and a crossroads gets its options',
       all(o in ch4 for o in ('Go left', 'Go right', 'Stay put')), ch4[-80:])
    plans = calls('plan')
    ok('nothing is written ahead at a crossroads', not wait_for(lambda: calls('plan') > plans, 2), calls())

    chat = [('assistant', ch1), ('user', '2'), ('assistant', ch2), ('assistant', ch3), ('assistant', ch4), ('user', '1')]
    ch5 = send(chat)
    ok('a pick at the crossroads', ch5.startswith('# ') and ch5 != ch4 and 'Go left' not in ch5, ch5[:60])

    # chapter 6 is being written ahead; a typed move stops it
    wait_for(lambda: calls('plan') > plans + 1, 15)
    chat += [('assistant', ch5), ('user', 'I climb the tower')]
    ch6a = send(chat)
    stamp = json.load(open(os.path.join(tmp, 'stories/seventh-noon/chapters/ch06.json')))
    ok('a move stops the write-ahead and answers the move', ch6a.startswith('# ') and stamp.get('move') == 'I climb the tower', stamp)
    ok('the stopped run\'s process is gone', 'stopped' in played() or 'is on the shelf' in played())

    # a dropped request (a locked phone) lands when it is sent again
    chat += [('assistant', ch6a), ('user', 'I jump to the next roof')]
    body = json.dumps({'stream': False, 'messages': [{'role': r, 'content': t} for r, t in marked(chat)]}).encode()
    s = socket.create_connection(('127.0.0.1', PORT))
    s.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n'
              + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
    time.sleep(0.5)
    s.close()
    events = lambda: json.load(open(os.path.join(tmp, '.run/events.json')))
    before = len(events())
    ch6 = send(chat)
    ok('a dropped request lands when it is sent again, as the same event',
       ch6.startswith('# ') and len(events()) == before and ch6 != ch6a, len(events()) - before)
    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    writes = calls('write')
    resent = chat[:-1] + [('user', chat[-1][1] + '\n\n[[writers-room:resend]]')]
    again = send(resent, mark=False)
    ok('the extension\'s resend gets the same chapter and no new work', again == ch6 and calls('write') == writes, (len(again), calls('write')))
    redo = send(chat)
    ok('a plain Regenerate after it arrived is a Redo', redo.startswith('# ') and redo != ch6 and calls('write') > writes)
    ch6 = redo
    record = lambda: open(os.path.join(tmp, 'stories/seventh-noon/record.md')).read()
    latest = status()['chapters'][-1]['n']
    ok('a Redo takes back the replaced chapter\'s bookkeeping', record().count(f'A thing happened in chapter {latest}.') == 1,
       record()[-400:])

    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    reply = send(chat + [('assistant', ch6), ('user', '(who is Ava?)')])
    ok('a note gets an answer, out of the story', reply.startswith('*(Author:') and 'fake answer' in reply, reply[:80])
    wait_for(lambda: not status().get('room', {}).get('step'), 20)

    mode(garbage_plan=1)
    n_chats = [('assistant', ch1), ('user', 'I go somewhere new')]
    back = send(n_chats)
    ok('Back: a new move from an old chapter rewinds the story, after one bad answer and a retry',
       back.startswith('# ') and [c['n'] for c in status()['chapters']] == [1, 2], status().get('chapters'))
    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    time.sleep(1)

    mode(garbage_check=1)
    chat2 = n_chats + [('assistant', back), ('user', 'I keep going')]
    deliver = send(chat2)
    ok('a check the model botches still delivers the chapter', deliver.startswith('# ') and deliver != back, deliver[:60])
    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    time.sleep(1)

    # a chapter is on the shelf with its bookkeeping done; the player types a move instead
    n = status()['chapters'][-1]['n'] + 1
    wait_for(lambda: f'chapter {n} is on the shelf' in played(), 30)
    ok('(the chapter ahead has done its bookkeeping)', f'A thing happened in chapter {n}.' in record())
    typed = send(chat2 + [('assistant', deliver), ('user', 'I go my own way')])
    ok('a move over a written-ahead chapter takes back its bookkeeping',
       typed.startswith('# ') and record().count(f'A thing happened in chapter {n}.') == 1, record()[-400:])
    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    chat2 = chat2 + [('assistant', deliver), ('user', 'I go my own way')]
    deliver = typed
    time.sleep(1)

    mode(garbage_plan=2)
    bad = send(chat2 + [('assistant', deliver), ('user', 'Plan fails now')])
    ok('a plan that fails twice tells the player', bad.startswith('*(Author:') and 'no chapter this time' in bad, bad[:120])
    wait_for(lambda: not status().get('room', {}).get('step'), 20)

    mode(truncate=True)
    cut = send(chat2 + [('assistant', deliver), ('user', 'Plan fails again in another way')])
    ok('a local server that cuts the prompt is caught and explained', 'context' in cut and 'no chapter this time' in cut, cut[:200])
    mode(truncate=False)
    wait_for(lambda: not status().get('room', {}).get('step'), 20)

    # the player sends something else while a chapter is being written: the newer one wins, and gets its own chapter
    base = chat2 + [('assistant', deliver)]
    got = {}
    first = threading.Thread(target=lambda: got.update(a=send(base + [('user', 'First idea')])))
    writes = calls('write')
    first.start()
    wait_for(lambda: calls('write') > writes, 20)
    second = send(base + [('user', 'Second idea')])
    first.join(30)
    n = status()['chapters'][-1]['n']
    stamp = json.load(open(os.path.join(tmp, f'stories/seventh-noon/chapters/ch{n:02d}.json')))
    ok('a newer message replaces the one being written, and gets its own chapter',
       'replaced' in got.get('a', '') and second.startswith('# ') and stamp.get('move') == 'Second idea', (got.get('a', '')[:50], stamp.get('move')))
    wait_for(lambda: not status().get('room', {}).get('step'), 20)

    # something injected after the player's move (an Author's Note) must not be read as the move
    body = {'stream': False, 'messages': [{'role': 'assistant', 'content': ch1}, {'role': 'user', 'content': '(a note)' + PLAY},
                                          {'role': 'user', 'content': '[Author note: write well]'}]}
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    reply = json.loads(urllib.request.urlopen(req, timeout=60).read())['choices'][0]['message']['content']
    last = events()[-1]
    ok('anything injected after the mark is ignored', 'write well' not in json.dumps(last) and last.get('sig') is not None, last)
    wait_for(lambda: not status().get('room', {}).get('step'), 20)
    before = len(events())
    bg = send([('user', 'Summarize this chat.')], mark=False)
    ok('a background request (a summary) gets no chapter and no event', 'only writes chapters' in bg and len(events()) == before, bg[:80])
    watching.set()
finally:
    play.terminate()
    try:
        play.wait(8)
    except subprocess.TimeoutExpired:
        play.kill()
    fake.terminate()
    if not all(results):
        print('--- play.log'); print(open(os.path.join(tmp, 'play.log')).read()[-2500:])
    alive = subprocess.run(['pgrep', '-f', tmp], capture_output=True, text=True).stdout.split()
    ok('stopping the room leaves nothing running', not alive, alive)
    shutil.rmtree(tmp, ignore_errors=True)

print(f'\n{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
