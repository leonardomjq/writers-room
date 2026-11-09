# The manual

This folder is a writers' room for an interactive web novel that the player reads in SillyTavern and is the hero of.
An AI author keeps the story's truth, plans it a few chapters at a time, has each chapter written, read as the player
and mended by sealed model calls, checks it, and sends it to SillyTavern. The goal: a web novel that grips (power the
player can feel climbing, a world that pushes back, people who act like people, surprise, real danger), where they
never find a mix-up that breaks it.

There are two ways an agent works here:
- **You, in this conversation**: setup, new stories, and changes to how it plays. This file is for you.
- **During play**, `engine/play.py` starts a short, fresh author run for each thing the player does, with
  `briefs/author-plan.md` (decide what the move changes, write the plan) and `briefs/author-check.md` (check the
  written chapter, do the bookkeeping). You do not run the play loop yourself, and the player does not need this
  conversation open while they play. Experimental: on a plain model (`[author] agent = "openai"`), `engine/author.py`
  asks the model only for what needs writing, and no agent is involved. It is unproven; don't offer it unless they ask,
  and if they do, say so plainly and point them to the README. Their own model's real job is Private scenes.

## What the player says to you
- **"start"** (or "play", "set this up for me"): no config.toml yet → First run. Otherwise → Play.
- **"new story"**: A new story.
- Anything about how the story reads ("more danger", "the talk feels robotic", "shorter chapters"): Changing how it
  plays.
- Moves are made in SillyTavern, on the Play bar. If the player has no SillyTavern and types a move here: Terminal play.

## First run (`python3 engine/run.py status` says NO CONFIG)
`engine/setup.py` does the work; your part is asking and running it. Go step by step, in plain words.
1. **Your own sandbox.** The engine calls models over the network and opens a local port for SillyTavern. In Codex, the
   project's `.codex/config.toml` allows that (workspace-write with network); if a command fails with a network or
   "Operation not permitted" error, ask the player to restart Codex in this folder and trust it, or to approve the
   command. In Claude Code, `.claude/settings.json` allows the engine's commands; approve them if asked.
2. **Ask once, together:** which novels or kinds of stories they love; whether English is their first language; the demo or
   their own story (one line on the demo: *The Seventh Noon: a week into the end of the world, a voice in every head
   names the ten strongest people in the city. You are number seven. Whoever kills one of the ten takes everything they
   carry.*). Their own: a premise in a line or two. Never ask them to paste a key into this chat; a key lives in an
   environment variable, exported in the shell they play from.
3. **Run it**, with what you learned (`--help` lists everything; it finds Claude, Codex and SillyTavern by itself, and
   tests each model):
   `python3 engine/setup.py --yes --novels "..." --english first|second --story demo`
   Add `--author`, `--writer`, `--reader` to override a choice, and `--sillytavern <folder>` if it is not found. Their own story: run it with the demo, then A new story.
4. Then Play. Tell them to refresh SillyTavern: it offers to connect and open the story in one tap. If it cannot, or
   SillyTavern is elsewhere, give them Setup by hand from the README.

## Play
Tell them to run this in a terminal in this folder and leave it open while they play (Ctrl+C stops it):
```
python3 engine/play.py
```
It keeps the SillyTavern endpoint up, costs nothing while they read, and runs the writers' room for each move. If they
cannot open a terminal, start it for them in the background:
`mkdir -p .run/logs && nohup python3 engine/play.py > .run/logs/play.log 2>&1 &` (and `pkill -f engine/play.py` stops
it). Then say that they can play in SillyTavern now. Your part is done until they come back with a change or a new story.

If something goes wrong in play, `.run/logs/` has a log for every author run and every chapter, and
`python3 engine/run.py status` shows what the player has and what is waiting.

## A new story
Read briefs/author-plan.md first: it holds how a story is planned and how the world behaves.
1. `python3 engine/run.py new <id> "<Title>"`, set story = "<id>" in config.toml, and a one-line blurb in story.json.
2. Ask for the premise in a line or two (a world, a hero, a hook) and anything they already know they want. Do not hand
   them menus: choosing from lists is hard and their picks are a lean, not a spec. Decide the rest yourself.
3. If they bring a SillyTavern character card or lorebook (JSON or PNG in this folder), read it and build from it.
4. Write, in this order: bible.md (the world's rules, the hero's power and what comes next, the people who move the
   world with their wants and plans, places, clocks, the course), cast.md, hero.md, story-so-far.md (what the opening
   will show), record.md, plans/stretch-01.md and plans/ch01.md (CROSSROADS: yes, so chapter 1 ends on a real choice).
5. `python3 engine/run.py review 1`, take its catches. Then `python3 engine/run.py chapter 1`, check it as
   briefs/author-check.md says (`run.py edit 1`, then `run.py book 1`), and `python3 engine/run.py card` (it makes
   card.json with chapter 1 as its first message and marks chapter 1 as released).
6. Tell them to import the card, start Play, and read. Reacting to a page works; ask what they felt after they read it,
   and adjust the bible and the next plans from that.

## Terminal play (no SillyTavern)
The player types moves here. For each one: follow briefs/author-plan.md (it ends with `run.py plan` or `run.py
queue`), then run `python3 engine/run.py chapter N [--move "..."]` yourself, follow briefs/author-check.md, then
`python3 engine/run.py release N` and tell them only: "Chapter ready: <title>, in stories/<story>/chapters/chNN.md".

## Changing how it plays
This package is opinionated: it ships one way of playing, tuned over weeks of real play. If the player wants it
different, change it with them one thing at a time, replacing rather than adding: a pile of rules
makes flat chapters. A slip in one chapter is fixed in that chapter or its plan, never with a new rule.
- Their taste: `player.md` (their own copy, made at setup, never in git; the default is briefs/player.md). The player
  can also ask from the page: Note, "shorter chapters", and the author keeps it with `run.py taste`. A new kind of line
  that pulled them out: briefs/catches.md.
- How chapters read: briefs/writer.md (keep it one page). How the reader judges: briefs/reader.md.
- How the author plans and checks: briefs/author-plan.md and briefs/author-check.md.
- Which model does which job: config.toml.
GUIDE.md explains why each part exists; read it before changing one.

## Files
- `config.toml`: the story, the author, who does each job, the port, SillyTavern's folder. `player.md`: the player's taste.
- `briefs/`: author-plan, author-check, new-story, writer, reader, options, mender, second author, the default reader's
  profile (player.md), catches, and the Private prompt for the card.
- `extension/`: the SillyTavern extension (Play bar, reading style, the room's steps). Setup links it into SillyTavern.
- `stories/<id>/`: bible.md, record.md, plans/ (the author's only); cast.md (the writer's); hero.md and
  story-so-far.md (writer and reader); chapters/ (chNN.md the final, -draft, -notes with the reader's verdict, .json
  the stamp, released.json what the player has); card.json; story.json; measures.md.
- `engine/`: setup.py (first run), play.py (play), author.py (the author on a plain model), run.py (the commands:
  `python3 engine/run.py` lists them), serve.py (the endpoint), providers.py (the sealed calls), tells.py (the counter),
  story.py (helpers).
- `.run/`: events, replies, logs, usage, and the snapshots Back restores (never committed).
