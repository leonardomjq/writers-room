#!/usr/bin/env python3
"""The author's tools. The author runs these (the fresh runs play.py starts, or your agent during setup); the player
never needs to.

  python3 engine/run.py test <codex|claude|openai>   one tiny sealed call: does this provider answer from here?
  python3 engine/run.py status                       the story, what the player has, the shelf, the open event
  python3 engine/run.py chapter <N> [--move "<the player's words>"] [--again "<what to change>"] [--reread]
      The pipeline for chapter N from plans/chNN.md: write, read as the player, count, mend. Writes chapters/chNN.md
      (the final), chNN-draft.md, chNN-notes.md (the reader's verdict, the edits, the counter on the final) and
      chNN.json (the stamp). Prints the reader's verdict for the author's check. About 3 to 6 minutes.
      --move   the move this chapter answers (a pick's words, or what the player typed); none for Continue
      --again  a Redo: the chapter written fresh with this note (the plan stands)
      --reread read and mend the chapter on file again, without writing it anew
  python3 engine/run.py prompt <N> [--move ...]      print the writer's prompt only (to see what the writer sees)
  python3 engine/run.py review <stretch>             the second author on plans/stretch-NN.md and the unwritten plans
  python3 engine/run.py shelve <N>                   after the author's check: mark chapter N checked
  python3 engine/run.py release <N>                  send chapter N to the player (answers the open event)
  python3 engine/run.py answer "<text>"              an out-of-character reply to the open event (a note, a question)
  python3 engine/run.py back <N>                     the story's files as they were when chapter N was the last
  python3 engine/run.py private-note "<plain facts>" what a Private stretch left, for the writer and reader
  python3 engine/run.py card                         write the story's SillyTavern card (card.json) from chapter 1
  python3 engine/run.py new <id> "<Title>"           a new story folder from stories/_new
  python3 engine/run.py usage                        tokens used, per chapter and in total
  python3 engine/run.py pack [plan | check N]        what one author run needs, in one read
  python3 engine/run.py queue N [--move ...] [--again ...]   ask play.py to write chapter N after this run
  python3 engine/run.py queue-review NN              ask play.py to run the second author on stretch NN
  python3 engine/run.py plan N [--move ...]  (stdin) write the chapter's plan and queue it, in one step
  python3 engine/run.py book N  (stdin)              shelve + record facts + story so far, in one step
  python3 engine/run.py edit N|FILE  (stdin)         fixes to a chapter or story file, as CUT / SWAP+TO lines
  python3 engine/run.py append FILE  (stdin)         add to a story file (bible.md, cast.md, hero.md, record.md, ...)
  python3 engine/run.py record N  (stdin)            facts that became true in chapter N (a NOW: line sets Now)
  python3 engine/run.py sofar  (stdin)               replace the story so far
"""
import json, os, random, re, shutil, signal, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import providers, story, tells
from story import body, nn, read, read_json, write, write_json

KEEP = 3          # chapters the reader and the second author see before the new one
KEEP_WRITER = 1   # the writer sees only the last one: with three it copies its own sentences
MIN_WORDS = 1200  # a draft shorter than this failed


# ---- what the player has read ----

def blocks(sdir, keep, before):
    """The last `keep` chapters the player received before chapter `before`, oldest first, each followed by the move
    that answered it; a Private stretch is one plain line."""
    found = []
    for r in story.released(sdir):
        if r.get('kind') == 'private':
            found.append(['PRIVATE', r.get('note') or 'A private scene played here.'])
            continue
        if r.get('kind') or not r.get('nn') or r['nn'] >= before:
            continue
        if r.get('move'):
            found.append(["THE PLAYER'S MOVE", r['move']])
        found.append(['CHAPTER', story.prose_of(read(f'{sdir}/chapters/ch{nn(r["nn"])}.md'))])
    out, n = [], 0
    for kind, text in reversed(found):
        if kind == 'CHAPTER':
            n += 1
            if n > keep:
                break
        out.append([kind, text])
    out.reverse()
    while out and out[0][0] != 'CHAPTER':           # start on a chapter
        out.pop(0)
    return out


def tail(sdir, keep, before):
    return '\n\n'.join(f'{k}:\n{t}' for k, t in blocks(sdir, keep, before)) or '(none: this is the first chapter)'


def seen_chapters(sdir, keep, before):
    return [t for k, t in blocks(sdir, keep, before) if k == 'CHAPTER']


# ---- the plan and the people ----

def plan(sdir, n):
    text = read(f'{sdir}/plans/ch{nn(n)}.md')
    if not text:
        raise SystemExit(f'no plan: plans/ch{nn(n)}.md (write it first)')
    return text


def plan_body(p):
    return re.sub(r'(?m)^(CAST|CROSSROADS|WHEN):.*\n?', '', p).strip()


def crossroads(p):
    return bool(re.search(r'(?mi)^CROSSROADS:\s*yes\b', p))


def cast_sections(sdir, p):
    """[(name, section)]: the hero (the first section of cast.md), then the people on the plan's CAST line."""
    sections = {}
    for chunk in re.split(r'(?m)^## ', read(f'{sdir}/cast.md'))[1:]:
        name, _, rest = chunk.partition('\n')
        sections[name.strip()] = rest.strip()
    m = re.search(r'(?m)^CAST:\s*(.+)$', p)
    wanted = [w.strip() for w in (m.group(1).split(',') if m else []) if w.strip()]
    hero = next(iter(sections), None)
    names = ([hero] if hero else []) + [w for w in wanted if w != hero]
    missing = [w for w in names if w not in sections]
    if missing:
        raise SystemExit(f'cast.md has no "## {missing[0]}" section (the plan names it on its CAST line)')
    return [(w, sections[w]) for w in names]


def cast_for(sdir, p):
    return '\n\n'.join(f'{w}:\n{s}' for w, s in cast_sections(sdir, p))


def writer_hero(sdir):
    """The hero sheet without its "What he has:" paragraph: every thing the writer sees, it narrates."""
    return re.sub(r'(?ims)^What (?:he|she|they|the hero) ha(?:s|ve):.*?(?:\n\s*\n|\Z)', '',
                  body(read(f'{sdir}/hero.md'))).strip()


def player():
    return body(read(f'{story.BRIEFS}/player.md'))


def writer_prompt(sdir, n, move=None, again=None):
    p = plan(sdir, n)
    parts = [body(read(f'{story.BRIEFS}/writer.md')),
             '=== THE READER YOU WRITE FOR ===\n' + player(),
             '=== THE STORY SO FAR ===\n' + body(read(f'{sdir}/story-so-far.md')),
             '=== THE LAST CHAPTER, AS THE PLAYER READ IT ===\n' + tail(sdir, KEEP_WRITER, n),
             '=== THE HERO SHEET (the hero\'s power exactly, and what the voice of the world has said) ===\n'
             + writer_hero(sdir),
             '=== THE PEOPLE (and what each one knows) ===\n' + cast_for(sdir, p),
             f'=== THE PLAN FOR CHAPTER {n} ===\n' + plan_body(p)]
    if move:
        parts.append("=== THE PLAYER'S MOVE (what the player told the hero to do; the chapter opens on it) ===\n"
                     + move.strip())
    if again:
        parts.append('=== WRITE IT AGAIN ===\nThe player asked for this chapter again. Keep the plan; change this: '
                     + again.strip())
    if crossroads(p):
        parts.append('=== THE END ===\nThis chapter ends at a crossroads: stop the moment the choice is in front of the '
                     'hero, before the hero makes it. No options; they come after.')
    return '\n\n'.join(parts) + '\n\nWrite the chapter now.'


def reader_prompt(sdir, n, chapter, move=None, ask_options=False):
    parts = [body(read(f'{story.BRIEFS}/reader.md')),
             '=== WHO YOU ARE AS A READER ===\n' + player(),
             '=== WHO YOU PLAY: THE HERO SHEET (exactly) ===\n' + body(read(f'{sdir}/hero.md')),
             '=== WHAT YOU KNOW SO FAR ===\n' + body(read(f'{sdir}/story-so-far.md')),
             '=== WHAT YOU READ BEFORE (the last chapters and your moves, oldest first) ===\n' + tail(sdir, KEEP, n),
             '=== YOUR MOVE ===\n' + (move.strip() if move else '(you turned the page)'),
             '=== THE CHAPTER ===\n' + story.strip_title(chapter),
             '=== LINES READERS STRUCK BEFORE (what pulls a reader out) ===\n'
             + body(read(f'{story.BRIEFS}/catches.md'))]
    if ask_options:
        parts.append(body(read(f'{story.BRIEFS}/options.md')))
    return '\n\n'.join(parts)


def mender_prompt(sdir, n, move, draft, notes, hits, p):
    parts = [body(read(f'{story.BRIEFS}/writer.md')),
             '=== THE READER YOU WRITE FOR ===\n' + player(),
             '=== THE HERO SHEET ===\n' + writer_hero(sdir),
             '=== THE PEOPLE (and what each one knows) ===\n' + cast_for(sdir, p),
             f'=== THE PLAN FOR CHAPTER {n} ===\n' + plan_body(p)]
    if move:
        parts.append("=== THE PLAYER'S MOVE ===\n" + move.strip())
    parts += ['=== YOUR CHAPTER ===\n' + draft,
              "=== THE READER'S NOTES ===\n" + (for_mender(notes) or '(none)'),
              "=== THE COUNTER'S LINES (candidates: each stays if it carries the hero's reaction, a fact, or a blow) "
              "===\n" + ('\n'.join(tells.lines(hits)) or '(none)'),
              body(read(f'{story.BRIEFS}/mender.md'))]
    return '\n\n'.join(parts)


# ---- the reader's answer and the mending ----

VERDICT_KEY = re.compile(r'^[*\s]*(SENSE|NEXT|FRESH|PROSE|STOP|WHY|FIX|CLEAN|OPTIONS)\b')


def parse_reader(out):
    notes = re.search(r'((?:\**SENSE|\**STOP|\**CLEAN).*?)\s*(?=\**OPTIONS:|$)', out, re.S)
    o = re.search(r'OPTIONS:\**\s*\n(.*)', out, re.S)
    options = [re.sub(r'^\s*\**[1-3][.)]\**\s*', '', l).strip() for l in (o.group(1) if o else '').splitlines()
               if re.match(r'^\s*\**[1-3][.)]', l)][:3]
    return (notes.group(1).strip() if notes else out.strip()), options


def verdict_yes(notes, k):
    return bool(re.search(rf'(?m)^[*\s]*{k}[*\s]*:[*\s]*yes\b', notes, re.I))


def needs_mending(notes, hits):
    return 'STOP:' in notes or not (verdict_yes(notes, 'SENSE') and verdict_yes(notes, 'PROSE')) or bool(hits)


def for_mender(notes):
    """The reader's notes without NEXT and FRESH: those are the author's, for the plan or a rewrite."""
    out, drop = [], False
    for line in notes.split('\n'):
        m = VERDICT_KEY.match(line)
        if m:
            drop = m.group(1) in ('NEXT', 'FRESH')
        if not drop:
            out.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip()


EDIT = re.compile(r'(?m)^[ \t]*(?:[-*][ \t]+|\d+[.)][ \t]+)?\**(CUT|SWAP|TO)\**[ \t]*:\**[ \t]*')


def unquote(s):
    s = s.strip()
    if s[:1] in ('"', '“'):
        m = re.match(r'^(["“].*["”])', s, re.S)
        if m and len(m.group(1)) >= 2:
            s = m.group(1)[1:-1]
    return s.replace('\\"', '"').replace("\\'", "'")


def parse_edits(reply):
    parts = EDIT.split(reply)
    items = [(parts[k], parts[k + 1]) for k in range(1, len(parts) - 1, 2)]
    edits = []
    for k, (kind, content) in enumerate(items):
        if kind == 'CUT':
            edits.append(('CUT', unquote(content), ''))
        elif kind == 'SWAP':
            same = re.match(r'^(.*["”])[ \t]+TO[ \t]*:[ \t]*(.*)$', content.strip(), re.S)
            if same:
                edits.append(('SWAP', unquote(same.group(1)), unquote(same.group(2))))
            else:
                nxt = items[k + 1] if k + 1 < len(items) else None
                edits.append(('SWAP', unquote(content), unquote(nxt[1]) if nxt and nxt[0] == 'TO' else None))
    return edits


def loosen(text):
    chars, where = [], []
    for i, c in enumerate(text):
        c = {'‘': "'", '’': "'", '“': '"', '”': '"'}.get(c, c)
        if c.isspace():
            if chars and chars[-1] == ' ':
                continue
            c = ' '
        chars.append(c)
        where.append(i)
    return ''.join(chars), where


def locate(text, q):
    if not q.strip():
        return None, 'empty'
    n = text.count(q)
    if n == 1:
        i = text.index(q)
        return (i, i + len(q)), None
    if n > 1:
        return None, f'found {n} times'
    loose, where = loosen(text)
    lq = loosen(q.strip())[0]
    found = [m.start() for m in re.finditer(re.escape(lq), loose)]
    if len(found) == 1:
        return (where[found[0]], where[found[0] + len(lq) - 1] + 1), None
    return None, 'not found' if not found else f'found {len(found)} times'


def tidy_cut(text, s, e):
    left, right = text[:s], text[e:]
    ps = left.rfind('\n\n') + 2 if '\n\n' in left else 0
    pe = right.find('\n\n')
    pe = len(right) if pe < 0 else pe
    para = left[ps:] + right[:pe]
    j = len(left) - ps
    a, b = para[:j], para[j:]
    if a.endswith((' ', '\t')) and (b[:1] in (' ', '\t', '') or re.match(r'[.,;:!?…*"”’)]', b)):
        a = a.rstrip(' \t')
    if not a.strip() or a.endswith('\n'):
        b = b.lstrip(' \t')
    para = a + b
    para = re.sub(r'^([*"“‘]+)[ \t]+', r'\1', para)
    para = re.sub(r'[ \t]+([*"”’]+)$', r'\1', para.rstrip())
    para = para.strip(' \t')
    if not re.sub(r'[\s*_"“”\'‘’]', '', para):
        joined = left[:ps].rstrip('\n') + '\n\n' + right[pe:].lstrip('\n')
        return joined.strip('\n') if joined.strip() else ''
    return left[:ps] + para + right[pe:]


def apply_reply(draft, reply):
    """(text, how, applied, not applied): the CUT and SWAP edits applied in order, each quote found once or skipped."""
    text, applied, skipped = draft, 0, []
    edits = parse_edits(reply)
    for kind, q, new in edits:
        if kind == 'SWAP' and new is None:
            skipped.append(f'NOT APPLIED (a SWAP with no TO): "{q[:200]}"')
            continue
        span, why = locate(text, q)
        if not span:
            skipped.append(f'NOT APPLIED ({why}): {kind} "{q[:200]}"')
            continue
        text = text[:span[0]] + new.strip() + text[span[1]:] if new and new.strip() else tidy_cut(text, *span)
        applied += 1
    title = draft.split('\n', 1)[0]
    if not text.startswith('# '):
        text = title + '\n\n' + text.lstrip()
    if not edits:
        skipped.append(f'NO EDITS in the reply: {reply.strip()[:300]}')
    return text.strip(), ('patches' if applied else 'failed'), applied, skipped


def good_chapter(text, words=MIN_WORDS):
    return bool(text) and not text.startswith('ERROR') and text.lstrip().startswith('# ') and len(text.split()) >= words


# ---- one run at a time ----

LOCK = 'author.lock'


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def take_lock(n):
    path = story.run_path(LOCK)
    old = read_json(path)
    if old and alive(int(old.get('pid', 0))) and old.get('pid') != os.getpid():
        raise SystemExit(f'another run is writing chapter {old.get("n")} (pid {old["pid"]}): wait for it, '
                         f'or stop it: kill -- -{old.get("pgid", old["pid"])}')
    write_json(path, {'pid': os.getpid(), 'pgid': os.getpgid(0), 'n': n, 'at': time.strftime('%H:%M:%S')})


def drop_lock():
    path = story.run_path(LOCK)
    if (read_json(path) or {}).get('pid') == os.getpid():
        os.unlink(path)


# ---- the pipeline ----

def pipeline(n, move=None, again=None, reread=False):
    cfg = story.config()
    sdir = story.story_dir(cfg)
    out = f'{sdir}/chapters/ch{nn(n)}'
    p = plan(sdir, n)
    rel = [r for r in story.released(sdir) if r.get('nn') and not r.get('kind')]
    follows = next((r for r in reversed(rel) if r['nn'] < n), None)
    old = story.stamp(sdir, n)
    if old.get('checked') and not old.get('released'):      # a new run voids the one on the shelf at once
        old['checked'] = False
        write_json(f'{out}.json', old)
    t0, log = time.time(), []
    if reread:
        draft = re.split(story.OPTION_SPLIT, '\n' + read(f'{out}.md'))[0].strip()
        writer = old.get('writer') or providers.provider_for('writer', cfg)
        if not good_chapter(draft):
            raise SystemExit(f'no chapter to read again at chapters/ch{nn(n)}.md')
    else:
        draft, writer = providers.call('writer', writer_prompt(sdir, n, move, again), 'medium', cfg, f'ch{nn(n)} write')
        if draft.startswith('ERROR') and not providers.LIMIT.search(draft):
            log.append(f'the writer failed once ({draft[7:160].strip()}); trying again')
            draft, writer = providers.call('writer', writer_prompt(sdir, n, move, again), 'medium', cfg,
                                           f'ch{nn(n)} write')
        if draft.startswith('ERROR'):
            raise SystemExit(('USAGE LIMIT: ' if providers.LIMIT.search(draft) else 'the writer failed: ') + draft[:600])
        draft = re.sub(r'^```\w*\n|\n```\s*$', '', draft.strip())
        if not draft.lstrip().startswith('# '):
            draft = '# ' + draft.lstrip()
        draft = re.sub(r'^#\s+Chapter\s+\d+\s*[:.-]\s*', '# ', draft)    # a title copied from the plan's heading
        if not good_chapter(draft):
            raise SystemExit(f'the writer returned something too short to be a chapter: {draft[:400]}')
        write(f'{out}-draft.md', draft)
    t1 = time.time()
    reply, reader = providers.call('reader', reader_prompt(sdir, n, draft, move, crossroads(p)), 'medium', cfg,
                                   f'ch{nn(n)} read')
    reader_ok = not reply.startswith('ERROR')
    notes, options = parse_reader(reply) if reader_ok else (f'READER FAILED: {reply[:400]}', [])
    earlier = seen_chapters(sdir, KEEP, n)
    sheets = [f'{w}:\n{s}' for w, s in cast_sections(sdir, p)] + [body(read(f'{sdir}/hero.md'))]
    hits = tells.scan(draft, earlier, sheets, p, move or '')
    t2 = time.time()
    final, how, mender, applied, skipped = draft, 'none', None, 0, []
    if reader_ok and needs_mending(notes, hits):
        mreply, mender = providers.call('mender', mender_prompt(sdir, n, move, draft, notes, hits, p), 'medium', cfg,
                                        f'ch{nn(n)} mend')
        if mreply.startswith('ERROR'):
            how, skipped = 'failed', [f'MENDING FAILED, the draft stands: {mreply[:300]}']
        else:
            final, how, applied, skipped = apply_reply(draft, mreply)
            if not good_chapter(final, 1):
                final, how = draft, 'failed'
    t3 = time.time()
    shown = []
    if crossroads(p) and len(options) == 3:
        random.SystemRandom().shuffle(options)       # the main road is not always 1
        shown = options
        final += '\n\n' + '\n'.join(f'{i}. {o}' for i, o in enumerate(options, 1))
    elif crossroads(p):
        notes += '\n\n(NO OPTIONS from the reader: the author writes three as the player before release)'
    write(f'{out}.md', final)
    found = tells.scan(final, earlier, sheets, p, move or '')
    counter = ['COUNTER ON THE FINAL:'] + (tells.lines(found) or ['(no hits)']) + \
              ['shape: ' + tells.shape_line(tells.shape(final)), tells.BASELINE]
    mending = ('MENDING: not run (the reader failed; --reread runs both again)' if not reader_ok else
               'MENDING: none needed' if how == 'none' else
               f'MENDING ({mender}): {how}, {applied} edits applied, '
               f'{sum(1 for s in skipped if s.startswith("NOT APPLIED"))} not applied')
    sections = [notes, mending + ('\n' + '\n'.join(skipped) if skipped else '')]
    if hits:
        sections.append('THE COUNTER ON THE DRAFT (given to the mender):\n' + '\n'.join(tells.lines(hits)))
    sections.append('\n'.join(counter))
    write(f'{out}-notes.md', '\n\n'.join(sections))
    write_json(f'{out}.json', {
        'n': n, 'plan_sha': story.text_sha(p), 'move': move or None, 'again': again or None,
        'follows': follows['nn'] if follows else None, 'follows_key': follows['key'] if follows else None,
        'writer': writer, 'reader': reader if reader_ok else 'failed', 'mender': mender, 'mending': how,
        'options': shown, 'counter_final': len(found), 'chapter_sha': story.text_sha(read(f'{out}.md')),
        'checked': False, 'released': False, 'finished': time.strftime('%Y-%m-%d %H:%M:%S')})
    words = len(story.strip_title(final).split())
    print(f'chapter {n}: {words} words | write {int(t1 - t0)}s, read {int(t2 - t1)}s, mend {int(t3 - t2)}s | '
          f'chapters/ch{nn(n)}.md')
    print(f'title: {story.title_of(final)}')
    for line in log:
        print(line)
    print(f'written by {writer}; ' + (f'mended by {mender} ({how})' if mender else 'not mended'))
    if reader_ok and not verdict_yes(notes, 'FRESH'):
        print('FRESH FAILED: the author decides: the next plan, or --again')
    print("THE READER:\n" + notes)
    print(mending)
    for line in skipped:
        print(line)
    if shown:
        print('OPTIONS:\n' + '\n'.join(f'{i}. {o}' for i, o in enumerate(shown, 1)))
    print('\n'.join(counter))
    print(f'next: the check (briefs/author-check.md) on chapters/ch{nn(n)}.md')


def review(stretch):
    cfg = story.config()
    sdir = story.story_dir(cfg)
    rel = [r['nn'] for r in story.released(sdir) if r.get('nn') and not r.get('kind')]
    last = max(rel or [0])
    pending = [f for f in sorted(os.listdir(f'{sdir}/plans')) if re.match(r'ch\d+.*\.md$', f)
               and (story.number(f) or 0) > last]
    parts = [body(read(f'{story.BRIEFS}/second-author.md')),
             '=== THE READER (and player) ===\n' + player()]
    for name, path in [('THE BIBLE', 'bible.md'), ('THE CAST SHEET', 'cast.md'), ('THE HERO SHEET', 'hero.md'),
                       ('WHAT THE PLAYER HAS SEEN SO FAR', 'story-so-far.md')]:
        parts.append(f'=== {name} ===\n' + body(read(f'{sdir}/{path}')))
    parts.append('=== THE LAST CHAPTERS THE PLAYER READ (oldest first) ===\n' + tail(sdir, KEEP, last + 1))
    parts.append('=== THE STRETCH PLAN ===\n' + read(f'{sdir}/plans/stretch-{nn(stretch)}.md'))
    for f in pending:
        parts.append(f'=== CHAPTER PLAN {f} ===\n' + read(f'{sdir}/plans/{f}'))
    t = time.time()
    out, who = providers.call('second_author', '\n\n'.join(parts), 'high', cfg, f'stretch {nn(stretch)} review')
    if out.startswith('ERROR'):
        raise SystemExit(f'the review failed: {out[:400]}')
    path = f'{sdir}/plans/stretch-{nn(stretch)}-review.md'
    write(path, f'# The second author ({who}) on stretch {stretch} ({time.strftime("%Y-%m-%d %H:%M")})\n\n{out}')
    print(f'review of stretch {stretch} in {int(time.time() - t)}s: plans/stretch-{nn(stretch)}-review.md\n\n{out}')


# ---- the shelf, release, back ----

def shelve(n):
    sdir = story.story_dir()
    s = story.stamp(sdir, n)
    if not s:
        raise SystemExit(f'chapter {n} has no stamp: run the pipeline first')
    text = read(f'{sdir}/chapters/ch{nn(n)}.md')
    if not good_chapter(text, 600):
        raise SystemExit(f'chapters/ch{nn(n)}.md is not a chapter')
    if crossroads(read(f'{sdir}/plans/ch{nn(n)}.md')) and len(story.options_of(text)) < 2:
        raise SystemExit(f'chapter {n} ends at a crossroads but has no options under it: add three, then shelve')
    s.update(checked=True, checked_sha=story.text_sha(text), checked_at=time.strftime('%Y-%m-%d %H:%M:%S'))
    write_json(f'{sdir}/chapters/ch{nn(n)}.json', s)
    s['before'] = story.snapshot(sdir, f'before-ch{nn(n)}')       # before this chapter's bookkeeping, for Back
    write_json(f'{sdir}/chapters/ch{nn(n)}.json', s)
    print(f'chapter {n} checked: "{story.title_of(text)}"')


def release(n, event=None, quiet=False):
    """Send chapter n to the player: it answers the open event (or `event`). Snapshots the story first, for Back."""
    sdir = story.story_dir()
    s = story.stamp(sdir, n)
    text = read(f'{sdir}/chapters/ch{nn(n)}.md')
    if not s.get('checked') or s.get('checked_sha') != story.text_sha(text):
        raise SystemExit(f'chapter {n} is not checked (or was edited after): read it, then `run.py shelve {n}`')
    ev = event or story.open_event()
    rel = story.released(sdir)
    before = s.get('before') or story.snapshot(sdir, f'before-ch{nn(n)}')
    rel = [r for r in rel if r.get('kind') or not r.get('nn') or r['nn'] < n]     # a Redo replaces its chapter
    rel.append({'nn': n, 'key': story.key(text), 'title': story.title_of(text), 'move': s.get('move'),
                'event': ev['id'] if ev else None, 'before': before, 'at': time.strftime('%Y-%m-%d %H:%M:%S')})
    story.save_released(sdir, rel)
    s.update(released=True)
    write_json(f'{sdir}/chapters/ch{nn(n)}.json', s)
    if ev:
        write(story.reply_path(ev['id']), text)
        story.update_event(ev['id'], done=True, answered_with=f'chapter {n}')
    if not quiet:
        print(f'released chapter {n} "{story.title_of(text)}"' + (f' (answers {ev["kind"]} {ev["id"]})' if ev else
              ' (no open event: it waits for the next request)'))


def answer(text):
    ev = story.open_event()
    if not ev:
        raise SystemExit('no open event to answer')
    sdir = story.story_dir()
    reply = f'*(Author: {text.strip()})*'
    rel = story.released(sdir)
    rel.append({'kind': 'ooc', 'key': story.key(reply), 'at': time.strftime('%Y-%m-%d %H:%M:%S')})
    story.save_released(sdir, rel)
    write(story.reply_path(ev['id']), reply)
    story.update_event(ev['id'], done=True, answered_with='answer')
    print(f'answered {ev["kind"]} {ev["id"]}')


def back(n):
    """The story's files as they were while chapter n was the last one the player had."""
    sdir = story.story_dir()
    rel = story.released(sdir)
    nxt = next((r for r in rel if r.get('nn') and not r.get('kind') and r['nn'] == n + 1), None)
    if not nxt or not nxt.get('before'):
        raise SystemExit(f'no snapshot from before chapter {n + 1} (was chapter {n + 1} released?)')
    story.restore(sdir, nxt['before'])
    print(f'the story is back to after chapter {n}: plans, record, sheets and released list as they were then. '
          f'Chapters written after it are void.')


def private_note(text):
    sdir = story.story_dir()
    rel = story.released(sdir)
    rel.append({'kind': 'private', 'note': text.strip(), 'at': time.strftime('%Y-%m-%d %H:%M:%S')})
    story.save_released(sdir, rel)
    print('private note kept')


def card():
    sdir = story.story_dir()
    meta = read_json(f'{sdir}/story.json', {}) or {}
    first = read(f'{sdir}/chapters/ch01.md')
    if not first:
        raise SystemExit('no chapters/ch01.md yet')
    name = meta.get('title') or story.title_of(first)
    private = body(read(f'{story.BRIEFS}/private.md'))
    port = story.config()['serve'].get('port', 5005)
    data = {'name': name, 'description': meta.get('blurb', ''), 'personality': '', 'scenario': '',
            'first_mes': first, 'mes_example': '', 'creator_notes': (
                'Play with the writers-room author: connect SillyTavern to its local endpoint (Chat Completion, '
                f'Custom OpenAI-compatible, http://127.0.0.1:{port}/v1, model "author"). For Private scenes, switch '
                'to your usual API; switch back to continue the story.'),
            'system_prompt': private, 'post_history_instructions': '', 'alternate_greetings': [],
            'tags': ['writers-room', 'web novel'], 'creator': 'writers-room', 'character_version': '1',
            'extensions': {}}
    write_json(f'{sdir}/card.json', {'spec': 'chara_card_v2', 'spec_version': '2.0', 'data': data})
    rel = story.released(sdir)
    if not any(r.get('nn') == 1 for r in rel):
        rel.insert(0, {'nn': 1, 'key': story.key(first), 'title': story.title_of(first), 'move': None,
                       'event': None, 'before': '', 'at': time.strftime('%Y-%m-%d %H:%M:%S')})
        story.save_released(sdir, rel)
        s = story.stamp(sdir, 1) or {'n': 1}
        s.update(checked=True, released=True, checked_sha=story.text_sha(first))
        write_json(f'{sdir}/chapters/ch01.json', s)
    print(f'card written: stories/{os.path.basename(sdir)}/card.json ("{name}"); chapter 1 is its first message')


def new(sid, title):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', sid):
        raise SystemExit('a story id is lowercase letters, digits and dashes, like "harbor-city"')
    dest = f'{story.ROOT}/stories/{sid}'
    if os.path.exists(dest):
        raise SystemExit(f'stories/{sid} already exists')
    shutil.copytree(f'{story.ROOT}/stories/_new', dest)
    write_json(f'{dest}/story.json', {'title': title, 'blurb': ''})
    print(f'stories/{sid} created. Set story = "{sid}" in config.toml, then fill it (AGENTS.md, A new story).')


def status():
    cfg = story.config()
    if cfg.get('missing'):
        print('NO CONFIG: first run. Follow AGENTS.md, First run.')
        return
    sdir = story.story_dir(cfg)
    rel = story.released(sdir)
    chs = [r for r in rel if r.get('nn') and not r.get('kind')]
    last = chs[-1] if chs else None
    print(f'story: {cfg["story"]} | roles: ' + ', '.join(f'{k}={providers.provider_for(k, cfg)}' for k in cfg['roles']))
    print(f'the player has: chapter {last["nn"]} "{last["title"]}"' if last else 'the player has: nothing yet')
    for f in sorted(os.listdir(f'{sdir}/chapters')):
        if re.fullmatch(r'ch\d+\.json', f):
            s = read_json(f'{sdir}/chapters/{f}', {})
            if not s.get('released'):
                print(f'written, not released: chapter {s.get("n")} (checked: {s.get("checked")}, move: '
                      f'{s.get("move")!r}, follows: {s.get("follows")})')
    lock = read_json(story.run_path(LOCK))
    if lock and alive(int(lock.get('pid', 0))):
        print(f'a pipeline is running: chapter {lock.get("n")} since {lock.get("at")}')
    ev = story.open_event()
    print(f'open event: {ev["kind"]} {ev["id"]} {json.dumps({k: ev[k] for k in ev if k in ("move", "note", "back_to")})}'
          if ev else 'open event: none')


def pack(kind='plan', n=None):
    """Everything one author run needs, in one read. plan: the planning brief, status, record, bible, current stretch
    plan (and its review if any), sheets, story so far, the last chapter the player has. check N: the checking brief,
    the chapter, the reader's notes, its plan, and the facts to hold it to."""
    sdir = story.story_dir()
    rel = [r for r in story.released(sdir) if r.get('nn') and not r.get('kind')]
    last = rel[-1]['nn'] if rel else None
    out = []

    def add(title, text):
        out.append(f'\n===== {title} =====\n{text}')
    if kind == 'check':
        p = read(f'{sdir}/plans/ch{nn(n)}.md')
        add('briefs/author-check.md', body(read(f'{story.BRIEFS}/author-check.md')))
        add(f'plans/ch{nn(n)}.md (the plan it was written from)', p)
        add(f'chapters/ch{nn(n)}.md (THE CHAPTER TO CHECK; fix it with run.py edit)', read(f'{sdir}/chapters/ch{nn(n)}.md'))
        add(f'chapters/ch{nn(n)}-notes.md (the reader, the mending, the counter)', read(f'{sdir}/chapters/ch{nn(n)}-notes.md'))
        prev = [r['nn'] for r in rel if r['nn'] < n]
        if prev:
            add(f'chapters/ch{nn(prev[-1])}.md (the chapter before)', story.prose_of(read(f'{sdir}/chapters/ch{nn(prev[-1])}.md')))
        add('the people in it (cast.md)', cast_for(sdir, p) if p else read(f'{sdir}/cast.md'))
        for f in ('hero.md', 'record.md', 'bible.md'):
            add(f, read(f'{sdir}/{f}'))
    else:
        add('briefs/author-plan.md', body(read(f'{story.BRIEFS}/author-plan.md')))
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status()
        add('status', buf.getvalue().strip())
        plans = sorted(f for f in os.listdir(f'{sdir}/plans') if re.fullmatch(r'stretch-\d+\.md', f))
        for f in ('record.md', 'bible.md'):
            add(f, read(f'{sdir}/{f}'))
        if plans:
            add(f'plans/{plans[-1]}', read(f'{sdir}/plans/{plans[-1]}'))
            review = f'{sdir}/plans/{plans[-1][:-3]}-review.md'
            if os.path.exists(review):
                add(f'plans/{plans[-1][:-3]}-review.md (the second author)', read(review))
        add('hero.md', read(f'{sdir}/hero.md'))
        add('story-so-far.md', read(f'{sdir}/story-so-far.md'))
        add('people on cast.md (sections exist for these)', ', '.join(re.findall(r'(?m)^## (.+)$', read(f'{sdir}/cast.md'))))
        if last:
            add(f'chapters/ch{nn(last)}.md (the last chapter the player has)', read(f'{sdir}/chapters/ch{nn(last)}.md'))
        written = sorted(f for f in os.listdir(f'{sdir}/plans') if re.fullmatch(r'ch\d+.*\.md', f))
        add('chapter plans on file', ', '.join(written) or '(none)')
    print('\n'.join(out))


STORY_FILES = ('bible.md', 'cast.md', 'hero.md', 'record.md', 'story-so-far.md', 'measures.md')


def story_file(target):
    """A chapter number or a story file name (bible.md, cast.md, ...) as a path inside the live story."""
    sdir = story.story_dir()
    if re.fullmatch(r'\d+', str(target)):
        return f'{sdir}/chapters/ch{nn(int(target))}.md'
    name = os.path.basename(str(target))
    if name not in STORY_FILES and not re.fullmatch(r'(ch\d+|stretch-\d+)\.md', name):
        raise SystemExit(f'not a story file: {target} (one of {", ".join(STORY_FILES)}, a plan, or a chapter number)')
    return f'{sdir}/plans/{name}' if name.startswith(('ch', 'stretch')) else f'{sdir}/{name}'


def edit(target, text):
    """Fixes to a chapter or a story file, all at once: CUT / SWAP+TO lines, applied by code."""
    path = story_file(target)
    original = read(path)
    if not original:
        raise SystemExit(f'nothing to edit at {os.path.relpath(path, story.ROOT)}')
    if original.lstrip().startswith('# '):
        final, how, applied, skipped = apply_reply(original, text)
    else:                                              # a file without a title line: apply the edits directly
        final, applied, skipped = original, 0, []
        for kind, q, new in parse_edits(text):
            span, why = locate(final, q)
            if not span or (kind == 'SWAP' and new is None):
                skipped.append(f'NOT APPLIED ({why or "no TO"}): {kind} "{q[:200]}"')
                continue
            final = final[:span[0]] + (new.strip() if new else '') + final[span[1]:]
            applied += 1
    if applied:
        write(path, final)
    print(f'{applied} edits applied to {os.path.relpath(path, story.ROOT)}' + ''.join('\n' + s for s in skipped))


def append(target, text):
    """Add text to the end of a story file (a dice log line in bible.md, a new ## Name section in cast.md, ...)."""
    path = story_file(target)
    write(path, read(path).rstrip() + '\n\n' + text.strip())
    print(f'appended {len(text.split())} words to {os.path.relpath(path, story.ROOT)}')


def record_add(n, text):
    """Append what became true in chapter n to record.md (under "## What happened"); a line starting with NOW: sets
    "## Now"."""
    sdir = story.story_dir()
    rec = read(f'{sdir}/record.md')
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    now = [l[4:].strip() for l in lines if l.upper().startswith('NOW:')]
    facts = [l if l.startswith('- ') else f'- {l}' for l in lines if not l.upper().startswith('NOW:')]
    if now:
        rec = re.sub(r'(?s)(## Now\n).*?(?=\n## )', lambda m: m.group(1) + f'- {now[0]} (ch{n})\n', rec, count=1)
    block = '\n'.join(f if f.rstrip().endswith(')') else f'{f} (ch{n})' for f in facts)
    if '## What happened' in rec:
        rec = re.sub(r'(?s)(## What happened\n.*?)(?=\n## |\Z)', lambda m: m.group(1).rstrip() + '\n' + block + '\n',
                     rec, count=1)
    else:
        rec += '\n\n## What happened\n' + block
    write(f'{sdir}/record.md', rec)
    print(f'record.md: {len(facts)} facts added' + (', Now updated' if now else ''))


def sofar(text):
    """Replace story-so-far.md (keeping its header comment) with this text."""
    path = f'{story.story_dir()}/story-so-far.md'
    head = ''.join(l + '\n' for l in read(path).splitlines() if l.startswith('#'))
    write(path, head + '\n' + text.strip())
    print(f'story-so-far.md: {len(text.split())} words')


def queue(n, move=None, again=None):
    """Ask engine/play.py to run the pipeline for chapter n after this author run ends."""
    if not read(f'{story.story_dir()}/plans/ch{nn(n)}.md'):
        raise SystemExit(f'write plans/ch{nn(n)}.md first')
    write_json(story.run_path('queue.json'), {'n': n, 'move': move, 'again': again})
    print(f'queued chapter {n}' + (f' (move: {move!r})' if move else '') + (f' (again: {again!r})' if again else ''))


def plan_and_queue(n, text, move=None, again=None):
    """Write plans/chNN.md from this text and queue the chapter, in one step."""
    path = f'{story.story_dir()}/plans/ch{nn(n)}.md'
    write(path, text.strip())
    print(f'plans/ch{nn(n)}.md written')
    queue(n, move, again)


def book(n, text):
    """After the check, in one step: shelve chapter n (with the Back snapshot), then the bookkeeping. The text holds
    one fact per line, a NOW: line, then a line SO FAR: followed by the whole story so far."""
    shelve(n)
    head, _, so_far = text.partition('SO FAR:')
    record_add(n, head)
    if so_far.strip():
        sofar(so_far)


def queue_review(stretch):
    write_json(story.run_path('review-queue.json'), {'stretch': stretch})
    print(f'queued the second author on stretch {stretch}')


def usage():
    rows = [json.loads(l) for l in open(story.run_path('usage.jsonl'))] if os.path.exists(
        story.run_path('usage.jsonl')) else []
    per = {}
    for r in rows:
        k = (r.get('what') or '').split(' ')[0]
        per.setdefault(k, [0, 0])
        per[k][0] += r.get('total') or 0
        per[k][1] += 1
    for k, (t, c) in per.items():
        print(f'{k or "(other)"}: {t:,} tokens in {c} calls')
    print(f'total: {sum(r.get("total") or 0 for r in rows):,} tokens in {len(rows)} calls, since this folder was set up '
          '(author runs, the writer, reader, mender and second author)')


def drop_pick_number(move):
    """'2. Run for the gate' -> 'Run for the gate': a pick's words without the option number."""
    return re.sub(r'^\s*\**[1-3][.)]\**\s*', '', move) if move else None


def flag(args, name):
    if name not in args:
        return None
    i = args.index(name)
    return args[i + 1] if i + 1 < len(args) else ''


def main(args):
    if not args:
        raise SystemExit(__doc__)
    cmd = args[0]
    if cmd == 'test' and len(args) == 2:
        cfg = story.config()
        cfg['roles'] = {'writer': args[1]}
        text, who = providers.call('writer', 'Reply with exactly one word: READY', 'low', cfg, 'test')
        ok = not text.startswith('ERROR') and 'READY' in text.upper()
        print(f'{who}: ' + ('OK' if ok else 'FAILED') + f' ({text.strip()[:300]})')
        if not ok and args[1] == 'codex' and not providers.codex_login_file():
            print('No Codex login file was found (~/.codex/auth.json). The engine needs Codex to keep its login in a '
                  'file: set cli_auth_credentials_store = "file" in ~/.codex/config.toml, then run `codex login`.')
    elif cmd == 'status':
        status()
    elif cmd == 'pack':
        pack(args[1] if len(args) > 1 else 'plan', int(args[2]) if len(args) > 2 else None)
    elif cmd == 'queue' and len(args) >= 2:
        queue(int(args[1]), drop_pick_number(flag(args, '--move')), flag(args, '--again'))
    elif cmd == 'plan' and len(args) >= 2:
        plan_and_queue(int(args[1]), sys.stdin.read(), drop_pick_number(flag(args, '--move')), flag(args, '--again'))
    elif cmd == 'book' and len(args) == 2:
        book(int(args[1]), sys.stdin.read())
    elif cmd == 'edit' and len(args) == 2:
        edit(args[1], sys.stdin.read())
    elif cmd == 'append' and len(args) == 2:
        append(args[1], sys.stdin.read())
    elif cmd == 'record' and len(args) == 2:
        record_add(int(args[1]), sys.stdin.read())
    elif cmd == 'sofar':
        sofar(sys.stdin.read())
    elif cmd == 'queue-review' and len(args) == 2:
        queue_review(int(args[1]))
    elif cmd in ('chapter', 'prompt') and len(args) >= 2:
        n = int(args[1])
        move = drop_pick_number(flag(args, '--move'))
        if cmd == 'prompt':
            print(writer_prompt(story.story_dir(), n, move, flag(args, '--again')))
            return
        take_lock(n)
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(143))
        try:
            pipeline(n, move, flag(args, '--again'), '--reread' in args)
        finally:
            drop_lock()
    elif cmd == 'review' and len(args) == 2:
        review(int(args[1]))
    elif cmd == 'shelve' and len(args) == 2:
        shelve(int(args[1]))
    elif cmd == 'release' and len(args) == 2:
        release(int(args[1]))
    elif cmd == 'answer' and len(args) == 2:
        answer(args[1])
    elif cmd == 'back' and len(args) == 2:
        back(int(args[1]))
    elif cmd == 'private-note' and len(args) == 2:
        private_note(args[1])
    elif cmd == 'card':
        card()
    elif cmd == 'new' and len(args) == 3:
        new(args[1], args[2])
    elif cmd == 'usage':
        usage()
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
