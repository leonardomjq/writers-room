#!/usr/bin/env python3
"""A scripted OpenAI-compatible model: it answers each job in the writers' room by reading the prompt, instantly and for
free. tests/room.py uses it, and it lets you try the whole game (and the SillyTavern extension) without any AI:

  python3 tests/fake_model.py [--port 5099] [--delay 2]

Point config.toml's [openai] at http://127.0.0.1:5099/v1, model "fake", agent and roles "openai".
"""
import json, random, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELAY = float(sys.argv[sys.argv.index('--delay') + 1]) if '--delay' in sys.argv else 0
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 5099
CALLS, LOCK = [], threading.Lock()
MODE = {'garbage_plan': 0, 'garbage_check': 0, 'truncate': False, 'cut_off': False}
WORDS = 'river gate window market roof ladder engine street lantern harbor bridge tower cellar yard door'.split()


def chapter(crossroads):
    seed = ''.join(random.choices('abcdefghij', k=12))
    lines = [f'The morning started with {seed} on every wall.']
    for i in range(330):
        lines.append(f'Evan passed the {random.choice(WORDS)} number {i} and kept going toward the {random.choice(WORDS)}.')
    return f'# The {random.choice(WORDS).title()} {seed[:4]}\n\n' + '\n\n'.join(' '.join(lines[i:i + 6]) for i in range(0, 330, 6))


def author(p):
    m = re.search(r'=== FACTS ===', p)
    if m:
        if MODE['garbage_check'] > 0:
            MODE['garbage_check'] -= 1
            return 'kind', 'I think this chapter is lovely, well done.'
        n = re.search(r'chapters/ch(\d+)\.md \(THE CHAPTER TO CHECK', p).group(1)
        n = int(n)
        return 'check', (f'=== FIXES ===\n\n=== FACTS ===\nA thing happened in chapter {n}.\n=== NOW ===\nat the gate\n'
                         f'=== LAST TIME ===\nYou were at the gate after chapter {n}.\n=== SO FAR ===\n'
                         f'Things happened up to chapter {n}.')
    if MODE['garbage_plan'] > 0:
        MODE['garbage_plan'] -= 1
        return 'kind', 'Sure! Here is my plan: something exciting happens.'
    if "player's premise" in p:
        return 'new', ('=== bible.md ===\nThe world.\n=== cast.md ===\n## Ava Torres\nA woman.\n=== hero.md ===\nA hero.\n'
                       '=== story-so-far.md ===\nIt begins.\n=== record.md ===\n## Now\n- here\n\n## What happened\n'
                       '=== stretch-01.md ===\nA stretch.\n=== PLAN ===\n# Chapter 1: Start\nWHEN: Day 1\nCAST: Ava Torres\n'
                       'CROSSROADS: yes\n- it begins')
    if '=== ANSWER ===' in p:
        return 'plan', '=== ANSWER ===\nA fake answer to your note.\n=== TASTE ===\n'
    n = int(re.search(r'Write the plan for chapter (\d+)', p).group(1))
    return 'plan', (f'=== PLAN ===\n# Chapter {n}: A test\nWHEN: Day 8\nCAST: Ava Torres\nCROSSROADS: yes\n- something happens\n'
                    '=== NEW PEOPLE ===\n\n=== PRIVATE FACTS ===\n')


def answer(p):
    if 'Answer in exactly this layout' in p:
        return author(p)
    if 'Write the chapter now.' in p:
        return 'write', chapter(False)
    if 'You are the reader this chapter is written for' in p:
        options = '\nOPTIONS:\n1. Go left\n2. Go right\n3. Stay put' if 'OPTIONS' in p else ''
        return 'read', 'SENSE: yes\nNEXT: more\nFRESH: yes\nPROSE: yes\nCLEAN' + options
    if 'give only the facts of this scene' in p:
        return 'facts', 'They met at the gate and made a deal.'
    if 'READY' in p and len(p) < 200:
        return 'test', 'READY'
    if 'CUT' in p and 'SWAP' in p:
        return 'mend', 'END'
    return 'other', 'Nothing to add.'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, data):
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.send({'calls': CALLS} if self.path == '/calls' else {'data': [{'id': 'fake', 'object': 'model'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        if self.path == '/mode':
            MODE.update(body)
            return self.send(MODE)
        prompt = body['messages'][-1]['content']
        kind, text = answer(prompt)
        with LOCK:
            CALLS.append(kind)
        time.sleep(DELAY)
        tokens = 10 if MODE['truncate'] else len(prompt) // 4
        finish = 'length' if MODE['cut_off'] else 'stop'
        self.send({'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': finish}],
                   'usage': {'prompt_tokens': tokens, 'completion_tokens': len(text) // 4}})


if __name__ == '__main__':
    print(f'fake model on http://127.0.0.1:{PORT}/v1', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
