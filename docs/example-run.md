# Example run: one reel, end to end

This traces one real reel, *The Mickey Mouse Club reboot* (published
2026-09-02), through each stage using the files the pipeline actually wrote.
It was the pipeline's second-best post by reach.

---

## Stage 1 — Collect → `news.json`

`collect_news.py` fetched 243 headlines that morning. The collector agent kept this
one because it has a real nostalgia angle, and tagged it with a story archetype
and a subject so the analytics stage can track what works.

```json
{
  "topic": "The Mickey Mouse Club Reboot on Disney+ — The Show That Launched Britney, Justin, and Ryan Gosling Returns",
  "importance": 8,
  "audience": "Millennials 30-45 who grew up watching MMC (1989-1994) and remember the cast that became the biggest stars of the 2000s",
  "angle": "The 1989-1994 variety show that assembled the 90s teen-idol assembly line — Britney Spears, Justin Timberlake, Christina Aguilera, and Ryan Gosling all started here — is being rebooted on Disney+",
  "archetype": "childhood-object-nostalgia",
  "subject": "Mickey Mouse Club",
  "status": "collected",
  "added": "2026-08-31"
}
```

## Stage 2 — Scout → `runs/2026-09-02/moments_1121_1.json`

The scout searched YouTube, ranked results by views per day, rejected
commentary and reaction videos, and chose a 25-second window in which all four
future stars appear together.

```json
{
  "source": {
    "id": "cFpZW9EdEI8",
    "title": "Christina, Britney, Justin, Ryan (MMC) - Note Passing (Dear Stacy)",
    "velocity": 225
  },
  "moment": {
    "start": 60.0,
    "end": 85.0,
    "reason": "MMC skit featuring all four future superstars interacting on the iconic soundstage. Real 1990s Disney Channel archival footage. Clip window centers on a moment where all four are visible in frame together.",
    "score": 72
  }
}
```

## Stage 3 — Produce → `queue/2026-09-02_mickey-mouse-club/`

`cut_clip.py` downloaded only seconds 60–85. The producer wrote the hook and
graded it honestly against the three ingredients that performance data showed
predict success:

**`reel.json`**
```json
{
  "hook": "The 1990s Show That Produced Britney Spears, Justin Timberlake, And Ryan Gosling Before Vanishing Is Returning On Disney+ After *32* Years 🔥",
  "clip": "clip_01.mp4",
  "category": "pop_culture",
  "cta": "Share if you watched MMC before they were famous",
  "ingredients": { "emotional_charge": true, "causal_chain": true, "personal_ritual": true },
  "hook_structure_ok": true,
  "archetype": "childhood-object-nostalgia",
  "subject": "Mickey Mouse Club"
}
```

`make_reel.py` rendered a 1080×1920 reel. `*32*` is shown in gold, and the
clip keeps its original audio:

<img src="examples/showcase.jpg" alt="Rendered reels" width="100%">

**QC audit trail (`runs/2026-09-02/produced_1205.json`, excerpt).** The agent
checked a frame every 3 seconds. `qc_gate.py` wouldn't let the reel be
finalized until the trail covered the whole clip and every frame passed:

```json
"qc_frames": [
  {"t": 60.0, "description": "MMC soundstage, bright colorful set, multiple cast members visible in schoolroom scene, 4:3 SD footage", "verdict": "pass"},
  {"t": 72.0, "description": "Ryan Gosling visible in frame interacting with other cast members, classroom background consistent", "verdict": "pass"},
  {"t": 78.0, "description": "Another cast reaction moment, warm studio lighting, no burned-in text or watermarks", "verdict": "pass"},
  {"t": 84.0, "description": "Final moments of clip segment, cast in classroom arrangement, clean archival Disney Channel footage", "verdict": "pass"}
]
```

**`caption.txt`**
```
The Mickey Mouse Club (1989-1994) assembled Britney Spears, Justin Timberlake,
Christina Aguilera, and Ryan Gosling on one soundstage — and now Disney+ is
rebooting the show that launched a generation of superstars, 32 years later.

#NostalgicDrop #MickeyMouseClub #BritneySpears #JustinTimberlake
```

## Stage 4 — Publish

`publish_reel.py` posted it at 20:31. The share sampler
recorded early share velocity 89 minutes after posting.

## Stage 5 — Learn → `performance.json`

```json
{
  "name": "2026-09-02_mickey-mouse-club",
  "metrics": {
    "reach": 1964,
    "views": 2575,
    "likes": 55,
    "saved": 8,
    "shares": 5,
    "total_interactions": 71,
    "ig_reels_avg_watch_time": 12432
  },
  "archetype": "childhood-object-nostalgia",
  "ingredients": { "emotional_charge": true, "causal_chain": true, "personal_ritual": true }
}
```

Viewers watched about 12.4 seconds of a 25.5-second clip on average. Because
the reel carried all three ingredients and scored well, its archetype and
subject feed `performance_lessons.json`. The next morning's collector leans
toward similar story shapes and looks for a *different* angle on the
top-scoring subjects, never a repost.

---

## Other reels from the same deployment

| Reel | Hook | Reach | Views | Likes |
|---|---|---:|---:|---:|
| Jim Carrey | Jim Carrey Wrote Himself A $10 Million Check When He Was Broke In 1990 And Post-Dated It 1995 — Then Actually Cashed It After The Cable Guy Paid Him $20 Million 🎭 | 2,011 | 2,521 | 71 |
| Mickey Mouse Club | The 1990s Show That Produced Britney Spears, Justin Timberlake, And Ryan Gosling Before Vanishing Is Returning On Disney+ After 32 Years 🔥 | 1,964 | 2,575 | 55 |
| Chadwick Boseman | Chadwick Boseman Told Howard Grads He Lost A Role For Speaking Truth To Power — Then Explained How It Led To Jackie Robinson, James Brown, And T'Challa 😱 💡 | 1,180 | 1,488 | 50 |
| Super Mario 64 | This Hidden Wing Cap Flight Let You Soar Over Peach's Castle In Super Mario 64 And It's Finally Coming Back On Switch 2 🪽 | 1,114 | 1,509 | 17 |

For contrast, the generic template the pipeline learned to avoid, "(Famous
Person) Tells Graduates (Inspirational Lesson)", topped out at around 115–140
reach with 0–2 likes across six attempts.
