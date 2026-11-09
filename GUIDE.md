# Why it works this way

This setup came out of long play, asking after every chapter: is this good writing, does it make sense, is it
boring? Most of what is here exists because something else failed first. Read this before
you change a part, so you know what it was protecting.

## The author is a live agent, not a script
The single biggest gain came from having one mind that *is the author*: it keeps the world's truth, plans ahead,
plants things that pay off later, decides what a move changes, and reads every chapter before the player does.

Before that, the model only answered each move. Nothing was planted, so nothing paid off, so nothing surprised.
A rule pile can't replace that judgment. Fixed checklists catch only literal cases; "would a 67-year-old really say
this here?" needs a mind that has read the whole story.

So the author is an agent (Codex or Claude Code) with tools: it reads the files, runs the pipeline, edits the
chapter, keeps the record. The code only does what a model can't hold: retrieval, sealing, counting, the endpoint.

## But not one long chat
The first version kept the author alive as one chat for the whole session. Measured, that chat was about 95% of all
the usage: every command it ran re-sent its whole growing history, and so did every "nothing happened yet" check while
the player read. The writer, reader and mender together were the small part.

So the author now runs fresh for each move, in two short runs: one decides what the move changes and writes the plan,
one checks the written chapter and does the bookkeeping. Each run gets everything it needs in its first message (the
brief, the bible, the record, the plan, the chapter) instead of reading files step by step, and does its work in a few
single commands. Nobody waits on the four-minute pipeline. About 5.6 times fewer tokens per chapter, and a blind
comparison on the same move found no clear quality difference. The story's state lives in files, so nothing is lost
between runs.

## Why local models play Private, not the author
A cheap model wrote the Private scenes from the start, and a strong one did everything else. That split isn't about price:
the author has to hold the whole bible and judge what a move changes, and a small model loses that in a long prompt. One
ignored the player's move outright, and a room of five long calls in a row took over a 16 GB laptop. A short
scene is a far simpler job, and it's the one the subscriptions won't do.

`engine/author.py` runs the room on a plain model anyway, as an experiment for anyone with a strong one. A model there
can't run anything: the engine does what it can alone (a Redo, a Back, a Continue with its plan ready) and asks the model
only for the creative parts, in labeled sections.

## The author never reads a Private scene
Explicit text has no place on a subscription account. When the player steps back, their own model writes a few plain,
non-graphic facts, and that's all the author gets. The extension swaps the scene for those facts inside the request itself,
and the endpoint drops any Private text that isn't marked as those facts, so the scene can't slip through another way.

## The files say only what the player has read
A chapter written ahead has already done its bookkeeping. If the player types a move instead, or asks for a Redo, those
facts never happened, and leaving them in is how a story contradicts itself. So the room restores the snapshot first.

## One writer's voice
At one point four models touched every page: a narrator, a translator, an editor and a reader. Each pass sanded
the voice flatter. A strong writer writing directly read far better than a weak draft rewritten by a stronger
one. So one model writes the whole book. The mender is the same model, and the author's own edits stay small.

## Plans say what happens, never how
Whatever concrete detail a writer is given, it narrates. If the notes say the hero apologizes too much, the chapter
gets four apologies. If the plan says "bright sun, no shade", that comes back nearly word for word. The result reads
like a list: the gun, then the sun, then the skill. That was the exact complaint ("I can see it's AI written") that
led to lean plans.

So a plan holds the beats, who wants what, the cost, and what to plant. The writer decides the rooms, the talk and
how a fight goes. A cast sheet gives each trait together with its trigger. A hero's inventory never reaches the writer.

## A chapter is won or lost before it is written
The weakest chapters had only helpers and prices in the room. The best had someone who wanted something against the
hero, and a real cost. No edit saves a chapter with nothing at stake. That's why the plan format asks for wants and
costs, and the author's manual insists on resistance from the world's own clock, not a fight every chapter.

## Decide rarely, and big
When the player decided every chapter, every decision was small and every chapter ended in homework. Now each
stretch of 3 to 5 chapters ends on one crossroads, where each road wins something no other road can. In between the
player presses Continue, or types anything at all, whenever they want. Typed moves are how players actually like to
play: loose directions like "show off, tell them the world changed, ask who's in".

## The reader knows only what the player knows
A model reading the chapter as the player, sealed off from the secrets, catches sense errors very well: a person
acting unlike themselves, a fact that changed, someone knowing a name they couldn't. The author can't catch these
alone, because the author knows the secrets, so everything makes sense to it.

The same reader is poor at catching prose habits: it noted only a handful of the ones a count found. So a plain counter with no model
(`engine/tells.py`) does that job: copied runs, "not X, it was Y" turns, short italic cappers, runs of "did not",
a trait word repeated. A hit is a candidate, never a verdict.

## Mend with patches, never regenerate
Regenerating a chapter to fix five flagged lines trades them for five new ones. The writer answers with exact CUT
and SWAP edits, code applies them, and every other word stays.

## The writer sees only the last chapter
When the writer got its last three chapters, they made up 75% of its prompt and it copied itself: a sentence from
chapter 1 came back in chapter 4. Now it gets the story so far (a short summary), the last chapter as the player read
it, and the sheets. The reader still sees three chapters, for continuity.

## A rule pile flattens the writing
Every rule fixed one bad line. Together they made flat, safe chapters, and any count in a brief becomes a quota
the reader can feel ("if there's a rule like 1 or 2, I'll always see 1 or 2"). The writer's brief stays one page. A
slip in one chapter gets fixed in that chapter or its plan, never with a new rule. Changes to how the game runs
happen between sessions, one at a time, and replace something rather than add to it.

## Don't trust a model's score
Given published chapters of known quality, AI judges did not pick the better one. They reward an instant power
hook. The only verdict that counts is the player's: how many chapters they read before they stop to say something
is off. `measures.md` is where the author notes what the player said.

## The usual failure of an AI author
People are too polite, and every ask is simply granted. The second author (a different run, ideally a different
model) reads every stretch's plans before they're written, specifically to find this. It also catches plotting that's
too tidy, chapters that all have the same shape, and decisions taken away from the player.

## Power the player can feel
Power shows as new things the hero can do, and as how the world starts treating them. When the hero grows, an old
threat becomes easy on the page. Never a perfectly scaled new enemy, never a price after every gain, never numbers
on a screen. It is a story, not a game; the only game part is that the player makes the decisions.

## Spoilers come from the author's mouth
Status updates that named a coming beat spoiled the story several times. During play the author says nothing in
the terminal; everything the player sees arrives in SillyTavern as a chapter or an out-of-character answer. The page's
status holds only room steps and released chapters: a chapter written ahead doesn't exist for the page until it's yours.

## Every screen is a page of the book
Any panel or bar that looks like a game screen breaks the book. It's a story; the only game part is that the player
decides. So the extension draws in the reading serif, shows steps as plain words, and adds nothing to the chat or to a
prompt: headings and the recap live on the page only.

## Show the room at work
A chapter takes minutes. A spinner makes that a wait; the real steps (plan, write, read as you, mend, check) make it the
reason the chapter is good. They cost nothing: the room publishes which step it's on.

## Send and leave
On a phone, people lock the screen after sending, and the browser may kill the request. So play must never need the page
awake: the room keeps working, keeps its answer, and when the page wakes up it sends the same request again and gets the
chapter as SillyTavern's own reply. The extension never writes a chapter into the chat, so it can't overwrite anything.

## Change it by asking, within limits
The player can ask from the page ("shorter chapters"). The author keeps those asks in five short lines at the end of the
player's profile, replaced whole each time. One chapter's slip is never an ask: that would grow the rule pile back.
