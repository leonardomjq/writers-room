#!/usr/bin/env python3
"""The author on any OpenAI-compatible model (a local one, or an API): plain model calls, no agent, no tools.

  python3 engine/author.py    (a job as JSON on stdin; play.py starts it)

An agent reads the story and runs commands. A plain model only writes: this works out what the player's action needs,
does everything it can without a model (a Redo, a Back, a Continue with its plan ready), and asks the model only for the
creative parts, in labeled sections. A model can't run anything here. The last line printed is a JSON result for play.py.
"""
import contextlib, io, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import providers, run, story
from story import nn, read

LAYOUT = """

Answer in exactly this layout, with these section lines as written and nothing before the first one. No code, no
commands, no notes about what you are doing.
"""
SECTION = re.compile(r'^\W*=+\s*([A-Za-z][A-Za-z .-]*?)\s*=+\W*$')


def sections(reply):
    """A reply's labeled sections, as {NAME: text}."""
    found, name, lines = {}, None, []
    for line in reply.splitlines():
        m = SECTION.match(line)
        if m:
            if name:
                found[name] = '\n'.join(lines).strip()
            name, lines = m.group(1).upper(), []
        elif name and not line.strip().startswith('```'):
            lines.append(line)
    if name:
        found[name] = '\n'.join(lines).strip()
    return found


def captured(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        fn(*args)
    return out.getvalue()


def ask(cfg, prompt, what):
    cfg = {**cfg, 'roles': {**cfg['roles'], 'author': 'openai'}}
    reply, _ = providers.call('author', prompt, 'medium', cfg, what)
    print(reply)
    if reply.startswith('ERROR'):
        raise Failed(reply[7:400].strip())
    return reply


class Failed(Exception):
    pass


def the_world():
    """How the story is planned and how the world behaves, from the planning brief, without an agent's commands."""
    brief = story.body(read(f'{story.BRIEFS}/author-plan.md'))
    keep = brief[brief.index('## The plan'):brief.index("## Writing to the story's files")]
    keep = re.sub(r'\s*\(written with `run\.py plan N`; stdin is the plan\)', '', keep)
    keep = re.sub(r'`python3 engine/run\.py dice`', 'take the next number from the dice list', keep)
    keep = re.sub(r'[,:]?\s*`run\.py [^`]*`', '', keep)
    return keep


def the_pack(kind, n=None):
    """The story's facts as an agent gets them, without its brief."""
    return re.sub(r'(?s)^\s*===== briefs/[^\n]*\n.*?(?=\n===== )', '', captured(run.pack, kind, n), count=1).strip()


def since_crossroads(sdir, n):
    k = 1
    while n - k >= 1 and not story.options_of(read(f'{sdir}/chapters/ch{nn(n - k)}.md')):
        k += 1
    return k


def write_plan(cfg, n, move, note, what):
    """Ask for chapter n's plan and queue the chapter."""
    sdir = story.story_dir(cfg)
    since = since_crossroads(sdir, n)
    dice = ', '.join(str(random.SystemRandom().randint(1, 100)) for _ in range(5))
    must = (f"\nRemember: the player's move is {move!r}. It happens, as they said it, at the start of this chapter. Plan what "
            'it changes. Never replace it with something else.' if move else '')
    road = ('CROSSROADS: no' if since < 3 else 'CROSSROADS: yes' if since >= 5 else
            'CROSSROADS: yes only if this chapter ends a stretch of the story, otherwise no')
    prompt = f"""You are the author of an interactive web novel, and you keep its secrets. Write the plan for chapter {n}, the next
chapter the player reads, from what the player just did. One plan, for this one chapter only.

What the player did:
{what}

{the_world()}

Dice list, to use in order only where an outcome is truly uncertain: {dice}.

{the_pack('plan')}
{LAYOUT}
=== PLAN ===
# Chapter {n}: <a working title>
WHEN: <story day and time>
CAST: <names, comma separated>
{road}
- <a beat: what happens, who wants what, the hard or costly part>
- <more beats, in order, up to how the chapter ends>
- <what to plant, in a plain line>
=== NEW PEOPLE ===
<only if someone on the CAST line has no section in cast.md: ## Name, then their look, voice, and what they know, want and hide. Otherwise leave this empty>
=== PRIVATE FACTS ===
<only if the player played a Private scene: plain facts of where, when, who and what was agreed or done, never quoted. Otherwise leave this empty>
{must}"""
    plan, parts, why = None, {}, ''
    for _ in range(2):
        parts = sections(ask(cfg, prompt + why, f'author plan ch{nn(n)}'))
        plan = parts.get('PLAN', '')
        if re.search(r'(?m)^\s*-\s+\S', plan):
            break
        plan = None
        why = '\n\nYour last answer had no === PLAN === section with beats. Follow the layout exactly.'
    if not plan:
        raise Failed('the model wrote no plan a chapter can be written from')
    if not plan.lstrip().startswith('#'):
        plan = f'# Chapter {n}\n{plan}'
    plan = re.sub(r'^\s*#[^\n]*?Chapter\s+\S+', f'# Chapter {n}', plan, count=1)
    forced = 'no' if since < 3 else 'yes' if since >= 5 else None        # the book's rhythm is not left to chance
    if forced:
        if re.search(r'(?mi)^CROSSROADS:', plan):
            plan = re.sub(r'(?mi)^CROSSROADS:.*$', f'CROSSROADS: {forced}', plan)
        else:
            plan = plan.replace('\n', f'\nCROSSROADS: {forced}\n', 1)
    people = parts.get('NEW PEOPLE', '')
    if '## ' in people:
        captured(run.append, 'cast.md', people)
    facts = parts.get('PRIVATE FACTS', '')
    if facts and len(facts) > 8 and 'Private' in what.split('\n')[0] + what:
        captured(run.private_note, facts)
    captured(run.plan_and_queue, n, plan, move, note)


def note_job(cfg, e, what):
    prompt = f"""You are the author of an interactive web novel. The player wrote to you, out of the story. Answer from what they have
read only; never name anything still to come. If they clearly ask for a change in how the story reads from now on (like
"shorter chapters"), say what you will change, and list everything they have asked for so far under TASTE (keep their
earlier asks, at the end of the reader's profile below, unless this replaces one). One chapter's slip is not an ask.

Their words: {e.get('note')!r}

{the_pack('plan')}
{LAYOUT}
=== ANSWER ===
<your plain answer, a few sentences>
=== TASTE ===
<only if they asked for a change: the whole list, at most five short lines. Otherwise leave this empty>"""
    parts = sections(ask(cfg, prompt, 'author note'))
    answer = parts.get('ANSWER') or 'Noted.'
    if parts.get('TASTE'):
        captured(run.taste, parts['TASTE'])
    captured(run.answer, answer)


def plan_job(cfg, job):
    """What one thing the player did needs. Only the parts that need writing reach the model."""
    e = job['events'][-1]
    kind, n, move, note = e.get('kind'), e.get('n'), e.get('move'), e.get('note')
    sdir = story.story_dir(cfg)
    if kind == 'note':
        return note_job(cfg, e, job['what'])
    if kind == 'back':
        captured(run.back, e['back_to'])
        n = e['back_to'] + 1
    has_plan = bool(read(f'{sdir}/plans/ch{nn(n)}.md'))
    if kind == 'redo' and has_plan:
        return captured(run.queue, n, move, note or 'write it fresh')
    if not move and not note and not e.get('private'):
        rel = [r['nn'] for r in story.released(sdir) if r.get('nn') and not r.get('kind')]
        if rel and story.options_of(read(f'{sdir}/chapters/ch{nn(rel[-1])}.md')):
            return captured(run.answer, 'Pick 1, 2 or 3, or type what you do.')
        if has_plan:
            return captured(run.queue, n)
    write_plan(cfg, n, move, note, job['what'])


def check_job(cfg, n):
    """The check and the bookkeeping. Whatever the model gives is used; the chapter is shelved either way."""
    brief = story.body(read(f'{story.BRIEFS}/author-check.md'))
    questions = brief[:brief.index('Fix by the smallest')].strip()
    prompt = f"""{questions}

{the_pack('check', n)}
{LAYOUT}
=== FIXES ===
<only real mistakes, the smallest cut or swap, words quoted exactly from the chapter; leave empty if there are none>
SWAP: "<exact words>"
TO: "<new words>"
CUT: "<exact words>"
=== FACTS ===
<one fact per line that became true in this chapter: a kill, a wound, a deal, a name learned, who saw what>
=== NOW ===
<where and when the story stands, one line>
=== LAST TIME ===
<one or two plain sentences for someone coming back a day later, only what this chapter showed>
=== SO FAR ===
<the whole story so far as the player has now seen it, under 400 words, older events compressed>"""
    parts = sections(ask(cfg, prompt, f'author check ch{nn(n)}'))
    if re.search(r'(?m)^\s*(SWAP|CUT):', parts.get('FIXES', '')):
        print(captured(run.edit, str(n), parts['FIXES']))
    book = parts.get('FACTS', '')
    book = re.sub(r'(?mi)^\s*(NOW|LAST TIME|SO FAR):.*$', '', book).strip()
    if parts.get('NOW'):
        book += f'\nNOW: {" ".join(parts["NOW"].split())}'
    if parts.get('LAST TIME'):
        book += f'\nLAST TIME: {" ".join(parts["LAST TIME"].split())}'
    if parts.get('SO FAR'):
        book += f'\nSO FAR:\n{parts["SO FAR"]}'
    captured(run.book, n, book or 'The chapter happened as written.')


def new_job(cfg, premise):
    """A new story from a premise: the files, then chapter 1's plan."""
    sdir = story.story_dir(cfg)
    files = ('bible.md', 'cast.md', 'hero.md', 'story-so-far.md', 'record.md')
    layout = '\n'.join(f'=== {f} ===\n{read(f"{sdir}/{f}")}' for f in files)
    brief = story.body(read(f'{story.BRIEFS}/new-story.md'))
    prompt = f"""You are the author of a new interactive web novel. Build it from the player's premise, deciding everything they did not
say. Their words are a lean, not a spec.

The player's premise: {premise}

{brief[:brief.index('Write these,')].strip()}

{the_world()}

The reader: {run.player()}

Chapter 1 opens already in motion, with a hook in its first lines, and ends on a real choice.
{LAYOUT}
{layout}
=== stretch-01.md ===
<what this stretch is about, who wants what, plants, the twist, the crossroads at its end>
=== PLAN ===
# Chapter 1: <a working title>
WHEN: <story day and time>
CAST: <names on cast.md>
CROSSROADS: yes
- <a beat: what happens, who wants what, the hard or costly part>
- <more beats, in order, up to the choice>"""
    parts = {}
    for _ in range(2):
        parts = sections(ask(cfg, prompt, 'author new story'))
        if re.search(r'(?m)^\s*-\s+\S', parts.get('PLAN', '')) and parts.get('BIBLE.MD'):
            break
    if not parts.get('PLAN') or not parts.get('BIBLE.MD'):
        raise Failed('the model did not write the story in the layout asked for')
    for f in files:
        if parts.get(f.upper()):
            story.write(f'{sdir}/{f}', parts[f.upper()])
    if parts.get('STRETCH-01.MD'):
        story.write(f'{sdir}/plans/stretch-01.md', parts['STRETCH-01.MD'])
    captured(run.plan_and_queue, 1, parts['PLAN'])


def main():
    job = json.loads(sys.stdin.read())
    cfg = story.config()
    kind = job['kind']
    if kind == 'plan':
        plan_job(cfg, job)
    elif kind == 'ahead':
        write_plan(cfg, job['n'], None, None, f'They are reading chapter {job["n"] - 1}, and will turn the page.')
    elif kind == 'check':
        check_job(cfg, job['n'])
    elif kind == 'new':
        new_job(cfg, job['premise'])
    return {'ok': True}


if __name__ == '__main__':
    try:
        result = main()
    except Failed as e:
        result = {'ok': False, 'why': str(e)}
    except SystemExit as e:
        result = {'ok': False, 'why': str(e)[:300]}
    print(json.dumps({'type': 'author_result', **result}))
