# The new-story brief: how the author builds a story from a premise. engine/play.py sends it to one author run with
# the planning brief above it; run.py commands are the only way to write.

Build a new story from the player's premise. Decide everything they did not say; their words are a lean, not a spec.
Write these, in this order, each with `python3 engine/run.py append <file> <<'END'`:
- bible.md: the world's rules; the hero's power and what comes next for it; the people who move the world, with their
  wants and plans; places; clocks (what happens when, whether the hero looks or not); the course of the whole story.
- cast.md: a `## Name` section for each person the opening needs (look, voice, what they know, want and hide).
- hero.md: who the hero is and what they can do, as plain facts.
- story-so-far.md: what the opening will show, in a few lines.
- record.md: facts true at the start, and where and when the story stands.
- stretch-01.md: what this stretch is about, who wants what, plants, the twist, the crossroads at its end.

Then write and queue chapter 1 with `python3 engine/run.py plan 1 <<'END'`. Its plan has CROSSROADS: yes, so chapter 1
ends on a real choice. Chapter 1 should open already in motion, with a hook in its first lines. Then stop.
