# writers-room

**A web novel you play as the hero, in SillyTavern. A room of AI models writes every chapter on your Claude or ChatGPT plan.**

![The Seventh Noon on a phone: the chapter's opening, a crossroads with the Play bar, and the room reading the chapter](docs/phone.png)

You read a chapter. You press Continue, type what you do, or pick one of three roads at a crossroads. A few minutes later the next chapter is there, and the world has moved on its own.

I played AI roleplay in SillyTavern every night for weeks, and every chapter or two something broke: a line nobody would say, a fact that changed, a world that did whatever I asked. I spent more time fixing than playing. This is the setup that fixed it.

## Try it

You need [SillyTavern](https://github.com/SillyTavern/SillyTavern) and [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) or [Codex](https://github.com/openai/codex), signed in with your plan. Paste this to your agent:

```
Clone https://github.com/leonardomjq/writers-room and follow its AGENTS.md to set it up for me.
```

It asks two questions about what you like to read and starts the room. Refresh SillyTavern, accept the offer to connect, and **The Seventh Noon** opens on chapter 1:

*A week into the end of the world, a voice in every head names the ten strongest people in the city. You are number seven. Whoever kills one of the ten takes everything they carry. An hour later, the tenth name is standing at your gate.*

Next time, open your agent in the folder and say **play**. For anything else (your own story, your phone, an update), ask it.

## What the room does

The author keeps a secret bible of the world (who wants what, what moves while you're away, what was planted for later) and plans a few chapters ahead. Every chapter then goes through five steps, shown on the page while it works:

1. **Plan**: what happens, who wants what, what it costs.
2. **Write**: one writer, one voice.
3. **Read as you**: a fresh model reads it knowing only what you know, and marks every line that would pull you out.
4. **Mend**: the writer fixes those lines and leaves the rest.
5. **Check**: the author holds it against the bible and every chapter before.

Step 3 is the one that matters. From a real draft:

> **Draft:** "On the fifth day two people went past you on Canal Street with a cart."
>
> **Reader:** She only sees light in living things, and a cart has no light. She was also across the river, so how does she know?

The author misses that, because the author knows everything. [More catches](examples/what-the-room-catches.md), and [two full chapters](examples/).

## Playing

| On the Play bar | What it does |
|---|---|
| **Continue** | The next chapter, usually already written |
| **1 2 3** | At a crossroads, take that road |
| Type anything | Your own move. The author bends the plan to it |
| **Note** | A question ("who is Cal again?"), a lasting change ("shorter chapters, more danger"), or **Write this chapter again** |
| **Back** | Undo the last chapter, and the story with it |
| **Private** | Step out to your own model for a scene, then step back |

SillyTavern reads like a novel site: book style, chapter headings, your place kept, a recap when you come back. It works on a phone too. Your other chats stay as they are.

**Private scenes.** Claude and ChatGPT won't write explicit scenes, so the chapter ends at the door. Tap Private and play it on your own model: GLM, a local model, anything you use in SillyTavern. When you step back, your model sums it up in plain facts, and only those reach the author. Adults only.

## Its opinions

- **Plain prose.** Common words, no idioms. Ask for richer prose if you want it.
- **You decide rarely, and big.** One crossroads every few chapters. Type anything in between.
- **A story, not a game.** No stats on screen. Power shows in what the hero can do and how the world treats them.
- **A world that pushes back.** People want things, a no stands, and danger is real.
- **One version of each chapter.** No swipes. Say what's wrong and it's written again.

The default taste is web novels and progression fantasy. Change it in a Note or by asking your agent. [GUIDE.md](GUIDE.md) explains why each part exists.

## What it isn't

- **Not a character chat.** No personas, no group chats. A novel, with you as the hero.
- **Not a new frontend.** SillyTavern, plus an extension and a small engine.
- **Not instant.** About 5 minutes a chapter, unless it was written while you read.
- **Not local.** Your own model plays Private scenes. The room needs Claude or ChatGPT.
- **Not hosted.** It runs on your computer.

## Questions

**How many chapters on a $20 plan?** A few dozen a week on ChatGPT, 10 to 20 on Claude. Claude writes the stronger prose.

**Why not a preset?** A preset changes how one model answers. It can't keep secrets from the writer, plant things for later, or have a reader who knows only what you know.

**Can I make my own story?** Ask your agent for a new story with a premise in a line or two, or hand it a SillyTavern card or lorebook.

**Where does my story go?** Nowhere. It stays on your computer, and the only prompts sent out go to your own models. No telemetry.

**What else do I need?** Python 3.11, on macOS or Linux (Windows through WSL).

---

Setup by hand, updating, removing it, phone access and the files are in [AGENTS.md](AGENTS.md). MIT licensed.
