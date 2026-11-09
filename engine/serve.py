#!/usr/bin/env python3
"""The local endpoint SillyTavern talks to, as if it were any OpenAI-compatible API.

  python3 engine/serve.py [--port 5005]    (play.py starts it by itself; you rarely run it by hand)

In SillyTavern: API "Chat Completion", source "Custom (OpenAI-compatible)", URL http://127.0.0.1:5005/v1, model
"author". Each request is the whole chat. The endpoint compares it with the chapters the player has received
(chapters/released.json) and turns it into one event for the author:

  continue  an empty send, or "c" / "continue" / "next"
  move      anything else typed after the latest chapter (a pick "2", or a move in the player's words)
  redo      regenerate/swipe of the latest chapter (same move as before), with a "(note: ...)" if the player added one
  back      the player deleted chapters and sent something new: the story goes back to the last chapter still shown
  note      a whole message in parentheses, or starting with "note:": a word to the author, out of the story
  private   (on any of the above) messages written by another model after the latest chapter: a Private stretch

The request is held open (keep-alive) until the author releases a chapter or answers; a Continue with a checked
chapter on the shelf is answered at once.
"""
import hashlib, json, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import story

HOLD_MINUTES = 40          # the longest a request waits for the author
KEEPALIVE = 10             # seconds between keep-alive bytes
STALE_MINUTES = 2          # no sign of play.py for this long (it beats every 30s): say so instead of waiting
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
RESEND = '[[writers-room:resend]]'     # the extension's mark: "I lost the answer to this request, send it again"
PLAY = '[[writers-room:play]]'         # the extension's mark on a move. Once it has been seen, unmarked requests are
                                       # SillyTavern's background features (summaries, expressions), not the player
FACTS = '[[writers-room:facts]]'       # marks what the player's own model said about a Private scene
NO_FACTS = 'A Private scene happened. Its details stay private.'
NOT_PLAY = "(writers-room only writes chapters. If you removed its extension, delete .run/extension-seen and send again.)"
LOCK = threading.Lock()


def text_of(m):
    c = m.get('content')
    if isinstance(c, list):
        c = '\n'.join(p.get('text', '') for p in c if isinstance(p, dict))
    return (c or '').strip()


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def is_continue(s):
    return norm(s) in ('', 'c', 'continue', 'next', 'go on', 'go', 'more')


NOTE = re.compile(r'\(\s*note\s*:\s*(.*?)\)\s*$', re.I | re.S)


def is_ooc(s):
    s = (s or '').strip()
    return bool(s) and ((s.startswith('(') and s.endswith(')')) or bool(re.match(r'(?i)note\s*:', s)))


def split_note(s):
    """(the move without its note, the note)."""
    m = NOTE.search(s or '')
    if m:
        return s[:m.start()].strip(), m.group(1).strip()
    if re.match(r'(?i)\s*note\s*:', s or ''):
        return '', re.sub(r'(?i)^\s*note\s*:\s*', '', s).strip()
    return (s or '').strip(), ''


def strip_name(s, names):
    """SillyTavern can prefix messages with a speaker name ("Evan: ..."): drop it."""
    for n in names:
        if n and s.startswith(n + ':'):
            return s[len(n) + 1:].strip()
    return s


def heartbeat_age():
    try:
        return (time.time() - os.path.getmtime(story.run_path('author-alive'))) / 60
    except OSError:
        return 1e9


def classify(msgs):
    """The event a chat request stands for, or {'reply': text} when the endpoint can answer by itself."""
    sdir = story.story_dir()
    rel = story.released(sdir)
    chaps = [r for r in rel if r.get('nn') and not r.get('kind')]
    if not chaps:
        return {'reply': '*(Author: this story has no chapter 1 yet. Ask the author to finish setting it up.)*'}
    by_key = {r['key']: r for r in chaps}
    ooc_keys = {r['key'] for r in rel if r.get('kind') == 'ooc'}
    anchor_i = None
    for i, m in enumerate(msgs):
        if m['role'] == 'assistant' and story.key(m['text']) in by_key:
            anchor_i = i
    if anchor_i is None:
        return {'reply': "*(Author: this chat doesn't match the story I'm running. Start a new chat with the story's "
                         "card, or tell the author which story you are playing.)*"}
    anchor = by_key[story.key(msgs[anchor_i]['text'])]
    latest = chaps[-1]
    after = msgs[anchor_i + 1:]
    last = msgs[-1]
    move = '' if last['role'] == 'assistant' else last['text']
    between = after if last['role'] == 'assistant' else after[:-1]
    private = [m for m in between if not (m['role'] == 'assistant' and story.key(m['text']) in ooc_keys)
               and not (m['role'] == 'user' and is_ooc(m['text']))]
    if not any(m['role'] == 'assistant' for m in private):
        private = []
    if last['role'] == 'assistant' and story.key(last['text']) in ooc_keys:
        move = ''
    # A Private scene itself never goes on: only the plain facts the player's own model gave, or that it happened.
    facts = [m['text'][len(FACTS):].strip() for m in private if m['text'].startswith(FACTS)]
    ev = {'private': [{'role': 'assistant', 'text': t} for t in (facts or [NO_FACTS])] if private else []}
    chapter = msgs[anchor_i]['text']
    if not chapter.lstrip().startswith('#'):
        chapter = '# (untitled)\n\n' + chapter          # options_of expects a chapter with its title line

    def pick(s):
        """A bare option number ("2", "2.") becomes that option's words, as the chapter showed them."""
        m = re.fullmatch(r'\s*\**([1-9])[.)]?\**\s*', s or '')
        opts = story.options_of(chapter)
        return opts[int(m.group(1)) - 1] if m and int(m.group(1)) <= len(opts) else s

    if anchor['nn'] == latest['nn']:
        if is_ooc(move):
            return {**ev, 'kind': 'note', 'n': latest['nn'], 'note': split_note(move)[1] or move.strip('() ')}
        clean, note = split_note(move)
        kind = 'continue' if is_continue(clean) else 'move'
        return {**ev, 'kind': kind, 'n': latest['nn'] + 1, 'move': None if kind == 'continue' else pick(clean),
                'note': note or None}
    clean, note = split_note(move)
    clean = pick(clean)
    if anchor['nn'] == latest['nn'] - 1 and (norm(clean) == norm(latest.get('move') or '')
                                             or (is_continue(clean) and not latest.get('move'))):
        return {**ev, 'kind': 'redo', 'n': latest['nn'], 'move': latest.get('move'), 'note': note or None}
    return {**ev, 'kind': 'back', 'back_to': anchor['nn'], 'n': anchor['nn'] + 1,
            'move': None if is_continue(clean) else clean, 'note': note or None}


def from_shelf(ev):
    """A Continue with a checked chapter waiting that follows the latest one: release it now."""
    if ev['kind'] != 'continue' or ev.get('private') or ev.get('note'):
        return None
    text = story.shelf_chapter(story.story_dir(), ev['n'])
    if text:
        import run
        run.release(ev['n'], ev, quiet=True)
        story.update_event(ev['id'], by_shelf=True)
        return text
    return None


def handle(msgs, resend=False):
    """(an immediate reply or None, the event it answers or to wait on). The same request again is the same event while
    its chapter is being written, or when the answer never arrived. Once it arrived, a plain Regenerate sends the very
    same request and means a Redo, so only the extension's resend mark gets the stored answer again."""
    with LOCK:
        sig = hashlib.sha1(json.dumps(msgs, sort_keys=True).encode()).hexdigest()[:16]
        for e in reversed(story.events()):
            if e.get('sig') == sig:
                reply = story.read(story.reply_path(e['id']))
                if reply and (resend or not e.get('delivered')):
                    return reply, e
                if not reply and not e.get('done'):
                    return None, e
                break
        ev = classify(msgs)
        if 'reply' in ev:
            return ev['reply'], None
        if heartbeat_age() > STALE_MINUTES:
            return ("*(Author: the writers' room isn't running. In a terminal in the writers-room folder, run "
                    "`python3 engine/play.py`, then send this again.)*"), None
        open_ev = story.open_event()
        if open_ev:                                              # a newer request replaces one still waiting
            story.update_event(open_ev['id'], done=True, answered_with='replaced by a newer request')
            story.write(story.reply_path(open_ev['id']), '*(Author: replaced by your newer message.)*')
        ev = story.add_event({**ev, 'sig': sig})
        shelf = from_shelf(ev)
        return (shelf, ev) if shelf else (None, ev)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write(time.strftime('%H:%M:%S ') + (fmt % args) + '\n')

    def send_json(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.rstrip('/') == '/card.json':                 # the live story's card, for a quick import
            card = story.read(f'{story.story_dir()}/card.json')
            raw = card.encode()
            self.send_response(200 if card else 404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Disposition', 'attachment; filename="card.json"')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.rstrip('/').endswith('/models'):
            self.send_json(200, {'object': 'list', 'data': [{'id': 'author', 'object': 'model', 'owned_by': 'you'}]})
        else:
            self.send_json(200, {'ok': True, 'what': 'writers-room author endpoint', 'models': ['author']})

    def local_json(self):
        """Only a local program sending JSON (SillyTavern's server) may post. A web page can't: it can't send
        application/json to another origin without a CORS preflight, which this endpoint never grants, and a page
        reaching it through DNS rebinding arrives with its own host name."""
        try:
            host = urlsplit('//' + (self.headers.get('Host') or '')).hostname
        except ValueError:
            host = None
        ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        return host in LOCAL_HOSTS and ctype == 'application/json'

    def do_POST(self):
        if not self.local_json():
            self.send_json(403, {'error': {'message': 'only local JSON requests are accepted'}})
            return
        if not self.path.rstrip('/').endswith('/chat/completions'):
            self.send_json(404, {'error': {'message': 'use /v1/chat/completions'}})
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        except ValueError:
            self.send_json(400, {'error': {'message': 'bad JSON'}})
            return
        story.write_json(story.run_path('last-request.json'), req)    # for troubleshooting what the frontend sends
        names = [n for n in (req.get('user_name'), req.get('char_name')) if n]
        msgs = [{'role': m['role'], 'text': strip_name(text_of(m), names)} for m in req.get('messages', [])
                if m.get('role') in ('user', 'assistant')]
        msgs = [m for m in msgs if m['text'] or m['role'] == 'user']
        at = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i]['text'].endswith((RESEND, PLAY))), None)
        resend = False
        if at is not None:
            msgs = msgs[:at + 1]                                 # anything after the mark was injected (an Author's Note)
            resend = msgs[-1]['text'].endswith(RESEND)
            msgs[-1]['text'] = msgs[-1]['text'][:-len(RESEND if resend else PLAY)].rstrip()
            story.write(story.run_path('extension-seen'), 'yes')
        elif os.path.exists(story.run_path('extension-seen')):
            stream = bool(req.get('stream'))
            self.begin(stream)
            self.finish_reply(NOT_PLAY, stream)
            return
        if not msgs:
            self.send_json(400, {'error': {'message': 'no messages'}})
            return
        try:
            reply, ev = handle(msgs, resend)
        except SystemExit as e:
            reply, ev = f'*(Author: {e})*', None
        stream = bool(req.get('stream'))
        self.begin(stream)
        if reply is None:
            reply = self.hold(ev, stream)
            if reply is None:
                return                                           # the client went away; the event stays open
        if self.finish_reply(reply, stream) and ev is not None:
            story.update_event(ev['id'], delivered=True)

    # -- a held response: headers now, keep-alive bytes while the author works, the text at the end --

    def begin(self, stream):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if stream else 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

    def chunk(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.wfile.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
        self.wfile.flush()

    def hold(self, ev, stream):
        path = story.reply_path(ev['id'])
        start = last = time.time()
        while time.time() - start < HOLD_MINUTES * 60:
            if os.path.exists(path):
                return story.read(path)
            if time.time() - last >= KEEPALIVE:
                try:
                    self.chunk(': writing\n\n' if stream else ' ')
                except (BrokenPipeError, ConnectionResetError):
                    return None
                last = time.time()
            time.sleep(1)
        return (f'*(Author: still no chapter after {HOLD_MINUTES} minutes. Check the terminal running '
                '`python3 engine/play.py`, then send again.)*')

    def finish_reply(self, text, stream):
        base = {'id': f'chatcmpl-{int(time.time())}', 'created': int(time.time()), 'model': 'author'}
        try:
            if stream:
                self.chunk('data: ' + json.dumps({**base, 'object': 'chat.completion.chunk', 'choices': [
                    {'index': 0, 'delta': {'role': 'assistant', 'content': text}, 'finish_reason': None}]}) + '\n\n')
                self.chunk('data: ' + json.dumps({**base, 'object': 'chat.completion.chunk', 'choices': [
                    {'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n')
                self.chunk('data: [DONE]\n\n')
            else:
                self.chunk(json.dumps({**base, 'object': 'chat.completion', 'choices': [
                    {'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}))
            self.chunk(b'')
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


def main():
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else \
        int(story.config()['serve'].get('port', 5005))
    if story.endpoint_state(port) != 'free':
        raise SystemExit(f'port {port} is already in use (the endpoint may already be running)')
    story.write(story.run_path('serve.json'), json.dumps({'pid': os.getpid(), 'port': port}))
    print(f'writers-room endpoint on http://127.0.0.1:{port}/v1 (model "author")', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
