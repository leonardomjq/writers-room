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
  conversation open while they play.

## What the player says to you
- **"start"** (or "play", "set this up for me"): no config.toml yet → First run. Otherwise → Play.
- **"new story"**: A new story.
- Anything about how the story reads ("more danger", "the talk feels robotic", "shorter chapters"): Changing how it
  plays.
- Moves are made in SillyTavern. If the player has no SillyTavern and types a move here: Terminal play.

## First run (`python3 engine/run.py status` says NO CONFIG)
Go step by step, in plain words, and do the checks yourself.
1. **Tools.** `python3 --version` (3.11 or newer; if older, tell them to install a newer Python), and which of
   `codex --version` and `claude --version` work.
2. **Your own sandbox.** The engine calls models over the network and opens a local port for SillyTavern. In Codex, the
   project's `.codex/config.toml` allows that (workspace-write with network); if a command still fails with a network
   or "Operation not permitted" error, ask the player to restart Codex in this folder and trust it, or to approve the
   command. In Claude Code, `.claude/settings.json` allows the engine's commands; approve them if asked.
3. **What they have.** Ask once: "Which of these do you have: a ChatGPT plan with Codex, a Claude plan with Claude
   Code, an API key for OpenRouter or another OpenAI-compatible service (or a local model)?" Test each one they have:
   `python3 engine/run.py test codex`, `... test claude`, `... test openai` (for openai, first put base_url, model and
   the NAME of the key's environment variable in config.toml under [openai], and make sure that variable is exported
   in the shell they play from; never write a key into any file, and never ask them to paste a key into this chat).
4. **Write config.toml** from config.example.toml:
   - `[author] agent`: "codex" or "claude", the agent they have. With both, Codex as the author and Claude as the
     writer spreads the load over both plans.
   - writer: claude if it works, else codex, else openai. (Claude writes the strongest chapters; Codex is solid and more
     plain; a local model is the player's call.)
   - reader: a different family than the writer when one works; else the same. Either way it knows only what the
     player knows, which is what catches most mistakes.
   - mender: "writer" (one voice per chapter). second_author: like the reader.
   Tell them plainly what they got, for example: "Everything runs on Codex. The reader is the same AI as the writer, but
   it only knows what you know, which is what catches most mistakes."
5. **Who reads.** Ask two things only: which novels or kinds of stories they love, and whether English is their first
   language. Then edit briefs/player.md, changing only what the answers change: the "Novels they love" line, and the
   English line if English is their first language (then plain, clear English, but no need for the most common words).
   Keep every other line: it is the tuned default, and it is what makes the chapters good.
6. **Which story.** Ask: "Play the demo, or make your own story?" with one line about the demo: *The Seventh Noon: a
   week into the end of the world, a voice in every head names the ten strongest people in the city. You are number
   seven. Whoever kills one of the ten takes everything they carry.* Demo: `cp -R stories/seventh-noon
   stories/play-seventh-noon` and story = "play-seventh-noon" (they play the copy, so the demo itself stays clean and
   `git pull` keeps working; starting over is deleting the copy and copying again). Their own: A new story.
7. **SillyTavern.** Assume they use it (this package is made for it); do not ask. It must run on this computer: the
   endpoint listens only on 127.0.0.1, so SillyTavern in Docker or on another device can't reach it. Give these steps
   in one message:
   1. In SillyTavern, open API Connections. API: Chat Completion. Source: Custom (OpenAI-compatible).
   2. Custom endpoint: `http://127.0.0.1:5005/v1` (the port in config.toml). Leave the key empty. Model: `author`.
   3. Save this as a connection profile named "Author" (so Private can switch away and back in two clicks).
   4. In AI Response Configuration: Streaming on, and Context Size as high as it goes (tick "Unlocked" if needed):
      chapters are long, and SillyTavern drops the oldest messages to fit.
   5. Import the card: Character Management, Import, `stories/<story>/card.json`. Its chat opens on chapter 1.
   6. How to play: a number for an option, or any move in your own words; an empty message (or `c`) to continue;
      regenerate (swipe) to have a chapter written again; delete chapters and send something new to go back; a message
      in parentheses is a note to the author. A chapter takes 4 to 8 minutes unless it was written ahead. For a Private
      scene, switch the connection profile to your own model, play, then switch back to Author.
8. Then Play.

## Play
Tell them to run this in a terminal in this folder and leave it open while they play (Ctrl+C stops it):
```
python3 engine/play.py
```
It keeps the SillyTavern endpoint up, costs nothing while they read, and runs the writers' room for each move. If they
cannot open a terminal, start it for them in the background:
`mkdir -p .run/logs && nohup python3 engine/play.py > .run/logs/play.log 2>&1 &` (and `pkill -f engine/play.py` stops it). Then say that
they can play in SillyTavern now. Your part is done until they come back with a change or a new story.

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
- Their taste: briefs/player.md. A new kind of line that pulled them out: briefs/catches.md.
- How chapters read: briefs/writer.md (keep it one page). How the reader judges: briefs/reader.md.
- How the author plans and checks: briefs/author-plan.md and briefs/author-check.md.
- Which model does which job: config.toml.
GUIDE.md explains why each part exists; read it before changing one.

## Files
- `config.toml`: the story, the author agent, who does each job, the port.
- `briefs/`: author-plan, author-check, writer, reader, options, mender, second author, the reader's profile
  (player.md), catches, and the Private prompt for the card.
- `stories/<id>/`: bible.md, record.md, plans/ (the author's only); cast.md (the writer's); hero.md and
  story-so-far.md (writer and reader); chapters/ (chNN.md the final, -draft, -notes with the reader's verdict, .json
  the stamp, released.json what the player has); card.json; story.json; measures.md.
- `engine/`: play.py (play), run.py (the commands: `python3 engine/run.py` lists them), serve.py (the endpoint),
  providers.py (the sealed calls), tells.py (the counter), story.py (helpers).
- `.run/`: events, replies, logs, usage, and the snapshots Back restores (never committed).
