# writers-room

**A web novel you play as the hero, in SillyTavern. A room of AI models writes every chapter on your Claude or ChatGPT plan.**

![The Seventh Noon on a phone: the chapter's opening, a crossroads with the Play bar, and the room reading the chapter](docs/phone.png)

You read a chapter. You press Continue, type what you do, or pick one of three roads at a crossroads. A few minutes later the next chapter is there, and the world has moved on its own.

It's one opinionated way of playing, tuned over weeks of real play. You change it by asking, not through settings.

## What you get

- **An author, not a chatbot.** It keeps a secret bible of the world (who wants what, what moves while you're not looking, what was planted for later) and plans a few chapters ahead.
- **A writers' room on every chapter.** You watch these steps on the page while it works:
  1. **Plan**: what happens, who wants what, what it costs.
  2. **Write**: one writer, one voice.
  3. **Read as you**: a fresh model reads it knowing only what you know, and marks every line that would pull you out.
  4. **Mend**: the writer fixes exactly those lines. The rest stays its words.
  5. **Check**: the author holds it against the bible and every chapter before.
- **SillyTavern that reads like a novel site.** A book style, chapter headings, a Play bar, your place kept, and a recap when you come back after a while. Only on writers-room stories. Your other chats stay as they are.
- **Your own model for what the plans won't write.** See [Private scenes](#private-scenes).

## What it isn't

- **Not a character chat.** No personas and no group chats. It's a novel, with you as the hero.
- **Not a new frontend.** It's SillyTavern, plus an extension and a small engine.
- **Not instant.** A chapter takes about 5 to 9 minutes, unless it was written ahead while you read.
- **Not free.** It needs a Claude or ChatGPT plan, and it uses a lot of it ([Usage](#usage)). Don't buy a plan just for this before you've read the [example chapters](examples/).
- **Not local.** Your own model plays Private scenes, but it can't run the room ([Experiments](#experiments)).
- **Not hosted.** It runs on your computer, which has to stay on while chapters are written.

## What you need

- **SillyTavern**, on the computer that runs this (tested on 1.19).
- **Claude Code or Codex CLI**, signed in with your plan. One is enough. Claude writes the strongest chapters, on Opus; on a plan without it, setup falls back to Sonnet. Codex is solid and more plain. With both, setup spreads the jobs.
- **Python 3.11 or newer**, on macOS or Linux (on Windows, run this and SillyTavern in WSL).
- Optional: **your own model** in SillyTavern, for Private scenes.

## Try it

```bash
git clone https://github.com/leonardomjq/writers-room.git
cd writers-room
python3 engine/setup.py
```

Setup finds your plan, tests it, asks two questions about your taste, and installs the extension. Or open Claude Code or Codex in the folder and say **`start`**.

Start the room, and leave it running while you play:

```bash
python3 engine/play.py
```

Refresh SillyTavern and accept its offer to connect. **The Seventh Noon** opens on chapter 1: a week into the end of the world, a voice in every head names the ten strongest people in the city. You are number seven. Whoever kills one of the ten takes everything they carry. An hour later, the tenth name is standing at your gate.

Reading chapter 1 costs nothing. Your first move starts the room.

<details>
<summary>Setup by hand, if setup can't find SillyTavern</summary>

1. Link the `extension` folder into SillyTavern as `data/default-user/extensions/writers-room`, and set `user_dir` under `[sillytavern]` in `config.toml`.
2. **API Connections** → Chat Completion → **Custom (OpenAI-compatible)**, URL `http://127.0.0.1:5005/v1`, model `author`, no key. Save it as a connection profile named "Author".
3. **Import** `stories/<your story>/card.json` and open its chat.

Without the extension the game still plays: send an empty message to continue, a number to pick, delete chapters to go back. You miss the Play bar, the book style, the room's steps and the facts from Private scenes.
</details>

## Playing

| On the Play bar | What it does |
|---|---|
| **Continue** | The next chapter, usually already written |
| **1 2 3** | At a crossroads, take that road |
| Type anything | Your own move, any time. The author bends the plan to it |
| **Note** | A word to the author: a question ("who is Cal again?"), or a change ("shorter chapters, more danger") that holds from then on. Or **Write this chapter again**, with your note |
| **Back** | Undo the last chapter. The story goes back with it |
| **Private** | Step out to your own model for a scene, then step back |

## Private scenes

Claude and Codex won't write explicit scenes, so a chapter that reaches one ends at the door. Tap **Private** and play it on your own model: GLM, a local model, anything you use in SillyTavern. Adults only.

Private plays on one of your SillyTavern connection profiles. Choose which under **Extensions → writers-room**.

When you tap **Back to the story**, your own model sums the scene up in plain, non-graphic facts, and only those reach the author. The scene itself never goes to Claude or Codex, with or without the extension.

## Reading on your phone

On a phone, the extension switches to a reading mode like a web-novel site: the page itself scrolls, and the bars slide away as you read. You can send a move, lock the phone, and find the chapter there when you come back. It lands on the device that sent the move, so play on one device at a time.

writers-room doesn't connect your phone to your computer. That's SillyTavern's own setup: your phone has to be able to open your SillyTavern, on your home network (`listen: true` and the whitelist in its `config.yaml`) or from anywhere through something like Tailscale. Never expose SillyTavern to the open internet. If you only play on the computer, you can skip all of this.

## Your own story

Open Claude Code or Codex in the folder, say **`new story`**, and give it a premise in a line or two. It builds the world and writes chapter 1. You can also drop a SillyTavern card or lorebook in the folder and say "use this".

To change stories, set `story` in `config.toml`, restart the room, and import that story's `card.json`.

## Day to day

```bash
python3 engine/play.py
```

That's all you run: then open SillyTavern and read. Ctrl+C stops it. To update:

```bash
git pull
```

Then restart the room and refresh SillyTavern. To start the demo over, delete your copy and run setup again, then open a new chat with the card:

```bash
rm -rf stories/play-seventh-noon .run
```

To remove everything, delete this folder, `data/default-user/extensions/writers-room` in SillyTavern, and the "Author" connection profile.

## Usage

A chapter uses roughly 250 to 350k tokens on your plan: most of it on the author's planning and checking, under 80k for the writer, reader and mender. At your plan's limit, SillyTavern gets a short note instead of a chapter; send again once it resets. A chapter written ahead is thrown away if you type a move instead, and its tokens with it. `python3 engine/run.py usage` adds up what's been used so far.

It runs the official CLIs under your own login, so your provider's terms and limits apply.

## When something's off

| You see | What to do |
|---|---|
| "The writers' room isn't running" | Run `python3 engine/play.py` and leave it open |
| "This chat doesn't match the story I'm running" | Start a new chat with the story's card, or check `story` in `config.toml` |
| "No chapter this time" | It says why. For a usage limit, send again once it resets |
| No Play bar | Refresh SillyTavern, and check you're on a writers-room card |
| Anything else | `.run/logs/` has a log for every step. Or ask your agent in this folder what happened |

## Make it yours

Say it in a Note, or tell your agent ("more romance, less fighting", "my English is fluent, use richer words"). [GUIDE.md](GUIDE.md) explains why each part exists, so you can change the briefs without breaking what works.

## Experiments

**The whole room on a plain model.** `[author] agent = "openai"` runs every job on an OpenAI-compatible model, with no agent. It's unproven, and it needs a strong model with a context of at least 40,000 tokens: a small model on a laptop loses track of the player's move, writes too little, and takes the machine over while it works.

## What's in here

- `extension/`: the SillyTavern extension.
- `engine/`: `setup.py` (first run), `play.py` (the room), `run.py` (the author's commands), `serve.py` (the endpoint SillyTavern talks to), `providers.py` (model calls), `tells.py` (the counter), `author.py` (the experiment above), `story.py`. Python standard library only.
- `briefs/`: the instructions for the author, writer, reader, mender and second author, and the default reader.
- `stories/`: the demo, and a template for your own.
- `examples/`: two chapters, not edited by hand, one by Claude and one by Codex.
- `AGENTS.md` (`CLAUDE.md` links to it): the manual your agent follows.
- `tests/`: `check.py` and `room.py` run everything against a scripted model (`fake_model.py`), with no AI and no tokens.

MIT licensed.
