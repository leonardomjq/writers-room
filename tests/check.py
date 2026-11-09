#!/usr/bin/env python3
"""Offline self-check: no model calls, no cost, about a second. Run it after changing the engine:

  python3 tests/check.py

It copies the engine and the demo story into a temporary folder and checks how the endpoint reads each SillyTavern
action (pick, Continue, typed move, note, Private, Redo, Back), that Back restores the story, the counter, the pack
size, and that the author's write commands stay inside the story.
"""
import contextlib, io, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
for name in ('engine', 'briefs', 'stories'):
    shutil.copytree(os.path.join(ROOT, name), os.path.join(tmp, name), ignore=shutil.ignore_patterns('__pycache__'))
shutil.copy(os.path.join(ROOT, 'config.example.toml'), os.path.join(tmp, 'config.toml'))
sys.path.insert(0, os.path.join(tmp, 'engine'))
sys.dont_write_bytecode = True
import story, serve, run, tells

results = []


def check(name, got, want):
    good = all(got.get(k) == v for k, v in want.items())
    results.append(good)
    print(('PASS  ' if good else 'FAIL  ') + name + ('' if good else f'   got {got}'))


sdir = story.story_dir()
ch1 = story.read(f'{sdir}/chapters/ch01.md')
A = lambda t: {'role': 'assistant', 'text': t}
U = lambda t: {'role': 'user', 'text': t}

check('a pick becomes the option text', serve.classify([A(ch1), U('2')]),
      {'kind': 'move', 'n': 2, 'move': story.options_of(ch1)[1]})
check('an empty send is Continue', serve.classify([A(ch1)]), {'kind': 'continue', 'n': 2})
check('"c" is Continue', serve.classify([A(ch1), U('c')]), {'kind': 'continue'})
check('a typed move with a note', serve.classify([A(ch1), U('I wave at her (note: keep it short)')]),
      {'kind': 'move', 'move': 'I wave at her', 'note': 'keep it short'})
check('a message in parentheses is a note', serve.classify([A(ch1), U('(who is Ava?)')]),
      {'kind': 'note', 'note': 'who is Ava?'})
p = serve.classify([A(ch1), U('I open the gate'), A('She smiles and steps in.'), U('c')])
check('another model\'s messages are a Private stretch', {'kind': p['kind'], 'n': len(p['private'])},
      {'kind': 'continue', 'n': 2})
check('a chat from another story is refused', {'reply': 'reply' in serve.classify([A('# X\n\nother'), U('hi')])},
      {'reply': True})

with contextlib.redirect_stdout(io.StringIO()):
    ch2 = '# Two\n\n' + 'Evan talked to her. ' * 300 + '\n\n1. Stay\n2. Go\n3. Run'
    story.write(f'{sdir}/chapters/ch02.md', ch2)
    story.write(f'{sdir}/plans/ch02.md', '# Chapter 2\nCAST: Ava Torres\nCROSSROADS: yes\n- beat')
    story.write_json(f'{sdir}/chapters/ch02.json', {'n': 2, 'move': 'I wave at her', 'follows': 1})
    record_before = story.read(f'{sdir}/record.md')
    run.shelve(2)
    run.release(2, quiet=True)
check('regenerate is Redo', serve.classify([A(ch1), U('I wave at her')]), {'kind': 'redo', 'n': 2})
check('edit + regenerate is Redo with a note', serve.classify([A(ch1), U('I wave at her (note: colder)')]),
      {'kind': 'redo', 'note': 'colder'})
check('delete + new move is Back', serve.classify([A(ch1), U('I run inside')]),
      {'kind': 'back', 'back_to': 1, 'n': 2, 'move': 'I run inside'})
check('a pick after chapter 2', serve.classify([A(ch1), U('x'), A(ch2), U('3')]), {'kind': 'move', 'n': 3, 'move': 'Run'})
with contextlib.redirect_stdout(io.StringIO()):
    run.record_add(2, 'Evan waved.\nNOW: at the gate')
    run.back(1)
check('Back restores the record and what the player has',
      {'record': story.read(f'{sdir}/record.md') == record_before,
       'chapters': len([r for r in story.released(sdir) if r.get('nn')])}, {'record': True, 'chapters': 1})
hits = tells.find('# T\n\nIt was not fear. It was hunger.\n\nHe did not move. He did not breathe.')
check('the counter finds its habits', {'kinds': sorted({k for k, q in hits})}, {'kinds': ['DIDNOT', 'TURN']})
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run.pack('plan')
check('the plan pack fits in one prompt', {'small': len(buf.getvalue()) < 60000}, {'small': True})
try:
    run.append('../../outside', 'no')
    results.append(False)
    print('FAIL  writes stay inside the story')
except SystemExit:
    results.append(True)
    print('PASS  writes stay inside the story')

shutil.rmtree(tmp)
print(f'\n{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
