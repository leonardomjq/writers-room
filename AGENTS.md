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

The player rarely reads anything but the README; they ask you. Do the work yourself, explain in plain words, and never
hand them a command when you can run it. If you were asked to clone this repository, clone it, work inside the clone,
and go on from here.

## What the player says to you
- **"start"**, "set this up for me", or the README's setup prompt: no config.toml yet → First run. Otherwise → Play.
- **"play"**: Play. **"stop"**: Stop.
- **"new story"**: A new story. "Switch to <story>": Changing stories.
- Anything about how the story reads ("more danger", "the talk feels robotic", "shorter chapters"): Changing how it
  plays.
- "Update", "start over", "my phone", "remove it", "something's wrong": the sections of those names below.
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
4. Then Play. Tell them to refresh SillyTavern: it offers to connect and open the story in one tap. If setup could not
   find SillyTavern, do Setup by hand with them.

## Play
Start the room in the background, unless it is already running (`pgrep -f engine/play.py`):
`mkdir -p .run/logs && nohup python3 engine/play.py > .run/logs/play.log 2>&1 &`
It keeps the SillyTavern endpoint up, costs nothing while they read, and runs the writers' room for each move. Say they
can play in SillyTavern now, and that the room keeps running until they say "stop" or restart the computer. If they
would rather watch it work, they can run `python3 engine/play.py` in a terminal themselves (Ctrl+C stops it). Your part
is done until they come back.

## Stop
`pkill -f engine/play.py`. It stops the room and the endpoint with it.

## Setup by hand (setup could not find SillyTavern)
Ask where SillyTavern is, then run setup again with `--sillytavern <folder>`. If that still fails:
1. Link `extension/` into SillyTavern as `data/default-user/extensions/writers-room`, and set `user_dir` under
   `[sillytavern]` in config.toml to that user folder.
2. Have them open API Connections → Chat Completion → Custom (OpenAI-compatible), URL `http://127.0.0.1:5005/v1` (the
   port in config.toml), model `author`, no key, and save it as a connection profile named "Author".
3. Have them import `stories/<story>/card.json` and open its chat.
Without the extension the game still plays (an empty message continues, a number picks, deleting chapters goes back),
but without the Play bar, the book style, the room's steps or the facts from Private scenes.

## Changing stories
Set `story` in config.toml, Stop, Play. In SillyTavern: Extensions → writers-room → "Connect and open the story" imports
and opens that story's card.

## Update
Stop, `git pull`, Play, and tell them to refresh SillyTavern. Their config.toml, player.md and stories are not in git,
so an update never touches them.

## Start over
For the demo: Stop, `rm -rf stories/play-seventh-noon .run`, `python3 engine/setup.py --yes` with their earlier
`--novels` and `--english` answers (player.md has them), Play, and have them open a new chat with the card. Say first
that this throws away the story they played.

## My phone
The extension already reads well on a phone; the only question is whether the phone can open their SillyTavern. That
is SillyTavern's own setup, in its `config.yaml`: on the home network, `listen: true` plus their phone's address in the
whitelist; from anywhere, something like Tailscale. Explain the choice and ask before you change their SillyTavern
config. Never turn the whitelist off without a password (basicAuth), and never forward a port to the internet. The
computer running the room has to stay on and awake while chapters are written.

## Remove it
Stop. Then delete `<SillyTavern user folder>/extensions/writers-room` and this folder (confirm first: it holds their
stories). In SillyTavern they can delete the "Author" connection profile and the story's character themselves.

## Something's wrong
`python3 engine/run.py status` says what the player has and what is waiting; `.run/logs/` has a log for every author
run (`author-*.log`), every chapter (`chNN.log`), the room (`play.log`) and the endpoint (`serve.log`). The usual
causes: the room is not running (Play), a usage limit (wait for the reset; the player got a note), the chat is from
another story (a new chat with the right card), or SillyTavern was not refreshed after an update. Fix what you can and
tell them plainly what happened.

## The plain-model experiment
If they ask to run the room on OpenRouter or a local model: it is experimental and unproven. Say so, and that it needs
a strong model with a context of at least 40,000 tokens; a small one loses track of their move and writes too little.
Then: `python3 engine/setup.py --author openai --writer openai --reader openai --openai-url <url> --openai-model <model>
--openai-key-env <NAME>` (the NAME of an environment variable holding the key; never ask them to paste a key here).

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
