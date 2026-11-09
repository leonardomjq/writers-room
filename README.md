# writers-room

**An AI author for SillyTavern. It plans a web novel you play as the hero, and every chapter is written, read, fixed
and checked before it reaches you.**

Not a character to chat with: a story that grips. The author keeps a secret bible of the world (who wants what, what
moves while you're not looking, what was planted for later), plans a few chapters ahead, and runs a small writers'
room on every chapter:

1. **Plan**: what happens, who wants what, what it costs. No small details: a writer narrates every detail it is
   given, and that is what reads as "AI".
2. **Write**: one writer, one voice, from a one-page brief.
3. **Read**: a fresh model reads the chapter *as you*, knowing only what you know, and marks every line that would
   pull you out. A plain counter (no AI) flags the writer's machine habits.
4. **Mend**: the writer fixes exactly those lines with small edits. The rest stays its words.
5. **Check**: the author holds the final against the bible and every chapter before, then sends it to SillyTavern.

You make the big calls at crossroads, type anything you like at any time, and press Continue in between. The next
chapter is often written while you read.

It runs on what you already have: **Codex** (ChatGPT plan), **Claude Code** (Claude plan), or any
**OpenAI-compatible API** (OpenRouter, a local model), and each job can use a different one.

## Requirements

- SillyTavern, on the same computer (the endpoint listens only on 127.0.0.1, so SillyTavern in Docker or on
  another device can't reach it)
- Python 3.11 or newer
- Codex CLI or Claude Code (the author runs on it)
- macOS or Linux (on Windows, use WSL)

## Setup

```bash
git clone https://github.com/leonardomjq/writers-room.git
cd writers-room
```

Open your agent in the folder (`codex` or `claude`) and say **`start`**. It checks your tools, asks what you have,
writes your config, asks two questions about your taste, and gives you the SillyTavern steps:

1. **API Connections** → Chat Completion → **Custom (OpenAI-compatible)**, URL `http://127.0.0.1:5005/v1`, model
   `author`, no key. Save it as a connection profile named "Author".
2. **AI Response Configuration**: Streaming on, **Context Size** as high as it goes.
3. **Import** `stories/seventh-noon/card.json` and open its chat. Chapter 1 is the first message.

In Codex, trust the folder when asked: its `.codex/config.toml` gives the engine the network access it needs. In
Claude Code, approve the engine's commands the first time.

## Playing

Start the writers' room and leave it running while you play (Ctrl+C stops it):

```bash
python3 engine/play.py
```

| In SillyTavern you… | The author… |
|---|---|
| type `1`, `2`, `3` at a crossroads, or any move in your own words | bends the plan to it and writes the chapter (4 to 8 min) |
| send an empty message (or `c`) | gives you the next chapter, usually already written |
| regenerate / swipe | writes that chapter again |
| edit your move to add `(note: less talking)`, then regenerate | rewrites it with your note |
| delete chapters and send something new | goes back to that point, story and all |
| write a message in parentheses, like `(who is Cal again?)` | answers out of the story, without spoilers |
| switch your connection profile to your own model | steps out: you play a **Private** scene with that model |
| switch back to "Author" and send | reads what happened for facts only, and carries on |

Nothing runs while you read. Each move starts a short author run that decides what the move changes, then the
writer, reader and mender, then a second short run that checks the chapter and updates the story's record.

**Private scenes.** Claude and Codex won't write explicit scenes, so a chapter that reaches one ends at the door.
Switch SillyTavern to your usual API, play the scene, then switch back. The card carries a short narrator prompt for
it. Adults only.

## Stories

**The Seventh Noon** ships as a demo: a week into the end of the world, a voice in every head names the ten
strongest people in the city. You are number seven. Whoever kills one of the ten takes everything they carry. An hour
later, the tenth name is standing at your gate.

For your own, say **`new story`** to your agent and give it a premise in a line or two. It writes chapter 1 and builds
the world behind it. You can also drop a SillyTavern card or lorebook in the folder and say "use this".

[`examples/`](examples/) has two chapters, not edited by hand, one written by Claude and one by Codex.

## Usage and models

A chapter uses roughly 250 to 400k tokens: most of it on your agent's plan for the author's planning and checking,
about 55k for the writer, reader and mender. On a subscription that counts toward your plan's usage limit. When the
limit is reached, SillyTavern gets a short note instead of a chapter; send again once it resets.
`python3 engine/run.py usage` adds up the tokens used so far, per job.

- Claude writes the strongest chapters; Codex is solid and more plain.
- The reader works best as a different model than the writer, when you have two.
- With both Claude and Codex, put the author on Codex (`[author] agent = "codex"` in `config.toml`) and the writing
  on Claude to spread the load.
- Any OpenAI-compatible API (OpenRouter, LM Studio, Ollama) can take the writer, reader or mender roles; see
  `config.example.toml`.

## Make it yours

It is opinionated on purpose: one way of playing, tuned over weeks of real play. To change it, tell your agent
("shorter chapters", "more romance, less fighting", "my English is fluent, use richer words") and it edits
`briefs/player.md` or the briefs. [GUIDE.md](GUIDE.md) explains why each part exists, so you can change it without
breaking what works.

## Files

- `AGENTS.md` (`CLAUDE.md` links to it): the manual your agent follows for setup and new stories.
- `briefs/`: how the author plans and checks, and the writer's, reader's, mender's and second author's instructions,
  your reader profile, and lines that pulled readers out before.
- `engine/`: `play.py` (play), `run.py` (the author's commands), `serve.py` (the endpoint SillyTavern talks to),
  `providers.py` (model calls), `tells.py` (the counter), `story.py`. Python standard library only.
- `stories/`: the demo, and a template for your own.
- `tests/check.py`: an offline self-check (no model calls) to run after changing the engine.

MIT licensed.
