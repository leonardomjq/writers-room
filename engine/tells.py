#!/usr/bin/env python3
"""The counter: a writer's machine habits, found by counting. No model, well under a second.
It runs on each draft (its hits go to the mender as lines to weigh) and on each final (printed for the author's check).

Five fixed kinds, each hit quoting the whole sentence it is in, exactly as it stands, so an edit can find it:
  COPIED  a run of 6 or more words (case and punctuation ignored) also found in an earlier chapter, a sheet or the
          plan; the voice's [bracketed] lines, the player's move and runs of almost only common words never count
  TURN    "not X. It was Y." across two sentences, "not ..., but ..." in one, and "something else", in the narration
          (people talk like that; the narrator should not)
  CAPPER  a short italic line (6 words or fewer) right after another italic line or closing an italic thought, and a
          section whose last paragraph is one sentence of 6 words or fewer
  DIDNOT  two or more sentences in a row with "did not" or "didn't" in the narration
  TRAIT   a word from a person's "Voice:" on the cast sheet used 3 or more times in the chapter
The kinds stay fixed. A hit is a candidate, never a verdict: a line that carries the hero's reaction, a fact or a blow
stays. It misses paraphrase; the reader catches that.

  python3 engine/tells.py <chapter.md>      the hits and the shape of a chapter of the live story
"""
import os, re, statistics, sys

RUN = 6          # words in a row that count as copied
SHORT = 6        # words in a capper
COMMON = set("""a an the and or but so if then than that this these those there here it its it's he him his she her
hers they them their we us our you your i me my mine of to in on at by for with from into onto over under up down out
off about as is was were be been being am are has have had do does did not no nor never just only very too also all
any some one two each every more most much many what who whom which when where why how while until again still even
back now well like can could would should will shall may might must said say says says get got go went gone come came
know knew see saw look looked want wanted way thing things something nothing anything everything time way yes okay oh
let let's don't didn't wasn't isn't can't won't couldn't i'm he's she's that's there's what's you're we're they're
i'll you'll i've you've end middle side front top bottom edge corner""".split())
STOP = COMMON | set("""head hand hands face eyes people little himself herself itself myself yourself themselves short
long good right left other another away around through before after again always never ever every once around today
tonight into then said tell told talk talks thing things someone somebody nobody everyone everybody really maybe
about make made take took give gave keep kept turn turned think thought feel felt seem seemed first last next same
very much more most mostly less least enough quite rather because though although without within loud quiet quick
fast slow soft hard sound sounds voice""".split())
WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*")
SENT_END = re.compile(r'[.!?…]+["”’\'*_)\]]*(?=\s+["“‘\'*_(\[]*[A-Z0-9]|\s*$)')
OPTIONS = re.compile(r'\n\s*\**1[.)]\**\s')
SEPARATOR = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')
DID_NOT = re.compile(r"\b(?:did not|didn['’]t)\b", re.I)
WAS_NOT = re.compile(r"\b(?:(?:was|is|were|are) not|wasn['’]t|isn['’]t|weren['’]t|aren['’]t)\b|^\W*Not\b", re.I)
IT_WAS = re.compile(r"^\W*(?:It|This)(?:\s+(?:was|is)\b|['’]s\b)")
NOT_BUT = re.compile(r"(?:\bnot\b|n['’]t\b)(?! only)[^.!?;]{1,80}?,\s+but\b", re.I)
ELSE = re.compile(r'\bsomething else\b', re.I)
LABEL = re.compile(r"(?:^|(?<=[.;]\s)|(?<=\n))[A-Z][a-z]+(?:[ ,]+[A-Za-z]+){0,3}:(?=\s)")

DESCRIBE = {'COPIED': 'said before, word for word', 'TURN': 'a not-this-but-that turn',
            'CAPPER': 'a short line capping the lines before it', 'DIDNOT': '"did not" again, sentence after sentence',
            'TRAIT': 'a word from the cast sheet, used again and again'}


def norm(w):
    return w.lower().replace('’', "'")


def stem(w):
    for suffix in ('ing', 'ed', 'es', 's', 'ly'):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[:-len(suffix)]
    return w


def prose(text):
    """The analysed part of a chapter: after its "# title" line, before its options. (start, end)."""
    start = 0
    m = re.match(r'\s*#[^\n]*\n', text)
    if m:
        start = m.end()
    o = OPTIONS.search(text, start)
    return start, (o.start() if o else len(text))


def paragraphs(text, start, end):
    """(start, end) of each paragraph between start and end, without its outer whitespace."""
    out, pos = [], start
    for m in list(re.finditer(r'\n\s*\n', text[start:end])) + [None]:
        stop = start + m.start() if m else end
        chunk = text[pos:stop]
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            out.append((pos + lead, pos + len(chunk.rstrip())))
        pos = start + m.end() if m else end
    return out


def sentences(text, start, end):
    """(start, end) of each sentence in one paragraph. A sentence ends at . ! ? (and a closing quote or *) followed by a
    capital, a digit or the paragraph's end, so '"Who?" she asked.' stays one sentence."""
    out, s, para = [], start, text[start:end]
    for m in SENT_END.finditer(para):
        e = start + m.end()
        if text[s:e].strip():
            out.append((s, e))
        s = e
        while s < end and text[s].isspace():
            s += 1
    if s < end and text[s:end].strip():
        out.append((s, end))
    return out


def quote(text, span):
    """A sentence as it stands, without an italic mark it shares with the sentences around it (so a cut of it leaves
    the paragraph's italics whole)."""
    q = text[span[0]:span[1]].strip()
    if q.count('*') % 2 and q.startswith('*'):
        q = q[1:]
    if q.count('*') % 2 and q.endswith('*'):
        q = q[:-1]
    return q.strip()


def nwords(s):
    return len(WORD.findall(s))


def is_italic(p):
    return len(p) > 2 and p.startswith('*') and p.endswith('*') and p.count('*') == 2


def layout(text):
    """The chapter as sections of paragraphs; each paragraph (start, end, kind, [sentence spans]), kind one of
    'voice', 'italic', 'speech', 'narration'."""
    start, end = prose(text)
    sections, cur = [], []
    for ps, pe in paragraphs(text, start, end):
        p = text[ps:pe]
        if SEPARATOR.match(p):
            sections.append(cur)
            cur = []
            continue
        kind = ('voice' if p.startswith('[') else 'italic' if is_italic(p)
                else 'speech' if re.search(r'["“”]', p) else 'narration')
        cur.append((ps, pe, kind, sentences(text, ps, pe)))
    sections.append(cur)
    return [s for s in sections if s]


def grams(text, n=RUN):
    w = [norm(m.group()) for m in WORD.finditer(text)]
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def strip_options(text):
    start, end = prose(text)
    return text[start:end]


def voice_words(sheet):
    """The content words of each "Voice:" part of a sheet: from "Voice:" to the next label ("What she knows:")."""
    out = set()
    for m in re.finditer(r'Voice:\s*', sheet):
        rest = sheet[m.end():]
        stop = LABEL.search(rest)
        part = rest[:stop.start()] if stop else rest
        part = part.split('\n\n')[0]
        for w in WORD.findall(part):
            if w[0].islower() and len(w) >= 4 and norm(w) not in STOP and stem(norm(w)) not in STOP:
                out.add(stem(norm(w)))
    return out


def unspoken(text, span):
    """A sentence with its quoted speech blanked out (same length), so a narrator's habit is not found in talk."""
    s = text[span[0]:span[1]]
    return re.sub(r'["“][^"“”]*(?:["”]|$)', lambda m: ' ' * len(m.group()), s)


def scan(text, earlier=(), sheets=(), plan='', move=''):
    """Every hit as (kind, quote, detail): detail is the copied run's words or the trait word, else ''."""
    secs = layout(text)
    paras = [p for s in secs for p in s]
    hits, seen = [], set()

    def hit(kind, span, detail=''):
        q = quote(text, span)
        if q and (kind, q) not in seen:
            seen.add((kind, q))
            hits.append((kind, q, detail))

    # COPIED: 6-word runs found in the sources, outside the voice's lines and the player's move
    source = set()
    for t in earlier:
        source |= grams(strip_options(t))
    for t in list(sheets) + [plan]:
        source |= grams(t)
    allowed = grams(move) if move else set()
    voice = [(ps, pe) for ps, pe, kind, _ in paras if kind == 'voice']
    voice += [(m.start(), m.end()) for m in re.finditer(r'\[[^\]\n]*\]', text)]
    start, end = prose(text)
    toks = [(norm(m.group()), m.start(), m.end()) for m in WORD.finditer(text, start, end)
            if not any(a <= m.start() < b for a, b in voice)]
    para_of = [next((k for k, p in enumerate(paras) if p[0] <= t[1] < p[1]), -1) for t in toks]
    marked = [False] * len(toks)
    for i in range(len(toks) - RUN + 1):
        g = tuple(t[0] for t in toks[i:i + RUN])
        if para_of[i] != para_of[i + RUN - 1] or toks[i + RUN - 1][2] - toks[i][1] > 200:   # a run stays in its
            continue                                                                       # paragraph and its line
        if g in source and g not in allowed and sum(w not in COMMON for w in g) >= 2:
            for k in range(i, i + RUN):
                marked[k] = True
    i, copied = 0, []
    while i < len(toks):
        if not marked[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(toks) and marked[j + 1]:
            j += 1
        while j > i and para_of[j] != para_of[i]:     # two runs touching across a break: the first one here
            j -= 1
        a, b = toks[i][1], toks[j][2]
        touched = [s for s in paras[para_of[i]][3] if s[1] > a and s[0] < b]
        span = (touched[0][0], touched[-1][1])
        if copied and copied[-1][0][1] > span[0]:     # two runs in the same sentence: one hit
            copied[-1] = ((copied[-1][0][0], span[1]), copied[-1][1] + ' / ' + text[a:b])
        else:
            copied.append((span, text[a:b]))
        i = j + 1
    for span, run in copied:
        hit('COPIED', span, run)

    # TURN, in the narration
    for ps, pe, kind, ss in paras:
        for k, s in enumerate(ss):
            body = unspoken(text, s)
            if k + 1 < len(ss) and WAS_NOT.search(body):
                nxt = unspoken(text, ss[k + 1]).lstrip('* ')
                first, other = body.lstrip('* ').split(' ')[0], nxt.split(' ')[0]
                if IT_WAS.match(nxt) or (first in ('He', 'She', 'They') and other == first
                                         and re.match(r'\w+ (?:was|is|were)\b', nxt)):
                    hit('TURN', (s[0], ss[k + 1][1]))
            if NOT_BUT.search(body) or ELSE.search(body):
                hit('TURN', s)

    # CAPPER: a short italic line after another italic line, or closing an italic thought after a full sentence; and
    # a section that ends on one short sentence
    for idx, (ps, pe, kind, ss) in enumerate(paras):
        if kind != 'italic' or not ss or nwords(text[ss[-1][0]:ss[-1][1]]) > SHORT:
            continue
        if (len(ss) == 1 and idx > 0 and paras[idx - 1][2] == 'italic') or \
                (len(ss) > 1 and nwords(text[ss[-2][0]:ss[-2][1]]) >= 4):
            hit('CAPPER', ss[-1])
    for sec in secs:
        ps, pe, kind, ss = sec[-1]
        if kind != 'voice' and len(ss) == 1 and nwords(text[ps:pe]) <= SHORT:
            hit('CAPPER', ss[0])

    # DIDNOT: narration sentences in a row, in reading order within a section
    for sec in secs:
        flat = [s for p in sec if p[2] != 'voice' for s in p[3]]
        k = 0
        while k < len(flat):
            j = k
            while j < len(flat) and DID_NOT.search(unspoken(text, flat[j])):
                j += 1
            if j - k >= 2:
                for s in flat[k:j]:
                    hit('DIDNOT', s)
            k = max(j, k + 1)

    sents = [s for p in paras if p[2] != 'voice' for s in p[3]]
    # TRAIT: a word of a person's Voice used 3 or more times (a word the plan itself uses is the story's, not a tic)
    traits = set()
    for sheet in sheets:
        traits |= voice_words(sheet)
    traits -= {stem(norm(w)) for w in WORD.findall(plan)}
    counts = {}
    for w, a, b in toks:
        st = stem(w)
        if st in traits:
            counts.setdefault(st, []).append(a)
    for word, places in sorted(counts.items()):
        if len(places) >= 3:
            for s in sents:
                if any(s[0] <= a < s[1] for a in places):
                    hit('TRAIT', s, f'{word}, {len(places)} times')
    return hits


def find(text, earlier=[], sheets=[], plan='', move=''):
    """[(kind, quote)]: every hit, in the order of the kinds above."""
    return [(k, q) for k, q, _ in scan(text, earlier, sheets, plan, move)]


def lines(hits):
    """Hits as plain lines for a prompt or the printout; takes scan()'s or find()'s tuples."""
    out = []
    for h in hits:
        kind, q, detail = (h + ('',))[:3]
        extra = f': "{detail}"' if kind == 'COPIED' else f': {detail}' if detail else ''
        out.append(f'{kind} ({DESCRIBE[kind]}{extra}): "{q}"')
    return out


def shape(text):
    """The narration's shape (paragraphs with no quoted speech, and not the voice's lines): the median sentence length
    in words, the share of sentences of 4 words or fewer, the share of one-sentence paragraphs."""
    paras = [p for s in layout(text) for p in s if p[2] in ('narration', 'italic')]
    lens = [nwords(text[a:b]) for p in paras for a, b in p[3]]
    lens = [n for n in lens if n]
    if not lens:
        return {'median_words': 0, 'short_share': 0, 'one_sentence_paragraphs': 0, 'sentences': 0}
    return {'median_words': statistics.median(lens),
            'short_share': round(100 * sum(n <= 4 for n in lens) / len(lens)),
            'one_sentence_paragraphs': round(100 * sum(len(p[3]) == 1 for p in paras) / len(paras)),
            'sentences': len(lens)}


def shape_line(sh):
    return (f"median {sh['median_words']} words a sentence, {sh['short_share']}% of sentences 4 words or fewer, "
            f"{sh['one_sentence_paragraphs']}% one-sentence paragraphs ({sh['sentences']} sentences of narration)")


BASELINE = 'human serials: median 15 to 16 words, 2 to 16% of sentences 4 words or fewer'


def number(name):
    """The chapter number at the front of a file name ("ch104-draft.md" is 104), or None."""
    m = re.match(r'ch(\d+)', os.path.basename(name))
    return int(m.group(1)) if m else None


if __name__ == '__main__':
    import story
    if len(sys.argv) != 2 or not os.path.isfile(sys.argv[1]):
        raise SystemExit(__doc__)
    sdir = story.story_dir()
    path = sys.argv[1]
    n = number(path)
    text = open(path, encoding='utf-8').read()
    finals = sorted((number(f), f) for f in os.listdir(f'{sdir}/chapters') if re.fullmatch(r'ch\d+\.md', f))
    earlier = [story.read(f'{sdir}/chapters/{f}') for k, f in finals if n is not None and k < n]
    plan = story.read(f'{sdir}/plans/ch{n:02d}.md') if n is not None else ''
    sheets = ['## ' + s for s in re.split(r'(?m)^## ', story.read(f'{sdir}/cast.md'))[1:]] + [story.read(f'{sdir}/hero.md')]
    found = scan(text, earlier, sheets, plan)
    print(f'{len(found)} hits in {os.path.basename(path)}:')
    for line in lines(found):
        print('  ' + line)
    print('shape: ' + shape_line(shape(text)))
    print(BASELINE)
