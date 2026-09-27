---
name: media-pipeline
description: News → single-clip Instagram Reel pipeline. Collect nostalgia-relevant news, scout one strong ≤25s clip per story, render it under a branded "screenshotted post" header card, pass an evidence-based QC gate, auto-publish up to 4x/day, and feed engagement back into topic selection.
version: 5.0.0
author: Edouard Lam
platforms: [macos, linux]
tags: [reels, instagram, news, youtube, cron, publish, nostalgia]
---

# Media Pipeline

Turns current news into short-form Instagram Reels for the account configured
in `brand.json` (reference deployment: **@nostalgic.drop**, news that a Gen Z /
millennial audience connects to a childhood memory).

Scripts do the deterministic work; you (the agents) make the judgment calls.
History of how these rules came about is in `CHANGELOG.md` — this file holds
only the rules in force.

## Stages

| Stage | Job | Does | Writes |
|---|---|---|---|
| 1 | `reel-1-news-collector` (daily 11:00) | `collect_news.py`, then keep only stories with a real nostalgia bridge | `news.json` entries, status `collected` |
| 1b | `wisdom-1-collector` (Mon/Thu 09:30) | archival speeches/interviews of successful people | `news.json`, `"category": "wisdom"` |
| 2 | `reel-2-video-scout` (11:20) | find the single strongest ≤25s moment per story | `runs/<d>/moments_<HHMM>_<n>.json`, status `scouted` |
| 3 | `reel-3-producer` (12:00) | cut, write hook, render, frame QC, gate | `queue/<d>_<slug>/`, `runs/<d>/produced_<HHMM>.json`, status `produced` |
| 4 | `reel-4-auto-publish` (12:30/15:30/18:30/21:30) | publish the oldest queued reel | `posted/`, `reel_posted.json` |
| 4b | `reel-4b-share-sampler` (14/17/20/23:00) | sample shares ~60–90 min after posting | `early_shares` in `performance.json` |
| 5 | `reel-5-analytics` (21:00) | score posts, derive lessons | `performance.json`, `performance_lessons.json` |
| — | `ig-token-refresh` (Mon 03:00) | refresh the long-lived IG token (no agent) | `ig_config.json` |

Each stage gates on its predecessor's output and exits with an honest zero
when there's nothing to do.

```
sources.json → collect_news.py → runs/<d>/raw_news_1100.json
     → (agent filter) → news.json [collected]
     → yt_search.py / fetch_transcript.py → moments_<HHMM>_<n>.json [scouted]
     → cut_clip.py → reel.json → make_reel.py → reel.mp4
     → frame QC → produced_<HHMM>.json → qc_gate.py [produced]
     → publish_reel.py → posted/
     → sample_shares.py + fetch_insights.py → performance_lessons.json → Stage 1
```

## Standing rules

- **Canonical scripts only.** Call the scripts in `~/media-pipeline/scripts/`;
  never re-implement cutting, rendering, QC, or publishing inline.
- **Honest zero.** No bridgeable news, no clean footage, no strong moment →
  report zero and stop. Never relax a filter or pad to fill a slot.
- **Save as you go.** Runs have a hard tool-call budget. Write each finished
  unit of work (a moments file, a news.json status change) as soon as it's
  done — never batch all writes to the end of a run.
- **Brevity.** Reports are ≤ ~100 words.
- **JSON edits:** use `python3 -c "..."` with semicolons; heredocs are
  unreliable in the Hermes terminal. Edit only the entries you own.
- **Never commit `ig_config.json`.** It holds the live access token.

## Reel format

One reel = a screenshotted-social-post header card above ONE continuous clip.

- **Header card:** circular avatar, account name, verified badge, and handle
  from `brand.json`, set in Inter.
- **Hook = the post caption**, rendered above the clip. `*word*` marks 1–2
  words for gold emphasis; real emoji render inline (1–2, sparingly).
- **One clip**, full width, native aspect ratio. No crop, zoom, sub-shot cuts,
  badges, or before/after pairing — the clip plays close to as found.
- **Optional CTA line** below the clip (`reel.json` `cta`), rendered only when
  the clip leaves room above Instagram's bottom safe zone.
- **Audio:** the clip's original sound, baked in. There is no music library
  and no Instagram Audio API call. Do not add music.
- **Length:** ≤25s, hard-capped by `cut_clip.py`. Only the chosen moment is
  ever downloaded.
- Reels publish with `share_to_feed: false` (Reels tab/Explore, not the grid).

## Hooks

Title Case, a complete and specific curiosity-driving claim.

**Structure:** `(specific named subject) + (a loss, block, or denial) +
(a reversal word — "then"/"finally" — when there's a resolution arc) +
(a concrete, named, countable payoff)`.

- The payoff ends on a **named person, a specific number, or a countable
  thing** — never an abstract noun ("a rule," "a lesson," "a secret,"
  "everything").
- Exact numbers, dates, and dollar figures add stakes; vague time markers
  ("at 30," "years later") don't.
- Carry the three ingredients: (1) emotional charge beyond generic uplift —
  grief, nostalgia-ache, personal ownership; (2) a specific, verifiable
  cause → effect chain, not a paraphrased quote; (3) where the topic allows,
  an object or ritual the *viewer* personally had or did (optional for
  `wisdom`).
- **Proven:** "Chadwick Boseman Told Howard Grads He *Lost* A Role For
  Speaking Truth To Power — Then Explained How It Led To Jackie Robinson,
  James Brown, And T'Challa". **Dead template:** "(Famous Person) Tells
  Graduates (Inspirational Lesson)" — six attempts, all ~115–140 reach.
  The venue isn't the problem; generic uplift ending on an abstract lesson is.

## Stage rules

### Collectors (Stage 1, 1b)
- Keep only news with a genuine nostalgia bridge; discard general news
  outright. Look across categories — reboots/remasters, anniversaries,
  discontinuations and returns, early-internet culture, Y2K tech/toys/fashion,
  discontinued snacks, kids' TV reboots, 2000s pop reunions — not just games
  and movies.
- Tag every entry with an `archetype` (kebab-case story shape — **reuse an
  existing tag** when one fits; coin a new one only when none does) and a
  `subject` (the named person or franchise).
- Read `performance_lessons.json`: lean toward `signals` with weight +1, away
  from −1 and from `anti_signals`. Advisory only — never a hard exclude.
- **Variant seeking:** for each of `top_subjects`, look for ONE genuinely
  different story, clip, or fact about that subject. Dedup by story, not by
  subject.
- Prune `collected` entries older than 2 days before adding new ones.

### Scout (Stage 2)
- Work candidates in importance order and **save each one's moments file and
  status the moment it's vetted.**
- **Footage type:** real archival / documentary / POV / gameplay footage.
  Reject reaction, "explained," news-roundup, and commentary videos.
- **Subject lock:** the video must be specifically about the story's subject,
  not merely contain it. For `wisdom`, confirm it's the named person actually
  speaking.
- **Thumbnail QC:** vision-check `https://i.ytimg.com/vi/<id>/hqdefault.jpg`;
  talking heads, article screenshots, or text-covered thumbnails fail.
- Longplays: use chapters to target action sections, not dialogue boxes.
  Amateur archive footage: sample 30–70% in, never the intro.
- Score moments 0–100: 30% emotional impact, 25% surprise, 20% visual
  quality, 15% relevance, 10% source authority.

### Producer (Stage 3)
- Process unconsumed moments files newest first, up to 4 reels per run.
- **Frame QC across the whole clip,** at least every ~4s: burned-in
  subtitles, dialogue boxes, watermarks, channel logos, uploader title cards,
  and news lower-thirds fail. A frame that doesn't visibly show the subject
  fails. Native context (a game's own HUD, a sign in the scene) is fine.
  `scripts/qc_frames.py` runs a local vision model over the frames to help.
- **Record the evidence:** every sampled frame goes into
  `produced_<HHMM>.json` as `{"t", "description", "verdict"}` — what you
  actually saw, not a placeholder.
- **Run `qc_gate.py` and obey it.** It checks the evidence is complete and
  all-pass, then runs an independent pixel-level watermark check
  (`overlay_check.py`) on the clip itself. If it flags burned-in text, re-cut
  a clean window or use another source. `"overlay_override": {"reason":
  "..."}` is only for text that's genuinely part of the scene — never for
  logos, URLs, handles, or captions.
- **Grade the hook honestly** in `ingredients` / `hook_structure_ok`. The
  feedback loop compares these against results; marking everything true
  leaves it nothing to learn from (see Analytics diagnostics).
- Never run `publish_reel.py` without `--preview`/`--dry-run`; publishing is
  Stage 4's job.

### Analytics (Stage 5)
- Run `fetch_insights.py`. Exit code 2 ("nothing posted yet") is normal.
- Report the top signal, top anti-signal, and one takeaway. If
  `diagnostics` is non-empty, lead with it — it explains thin signals.

## Feedback loop

`fetch_insights.py` scores each post (reach ≥ 50) with a weighted composite,
renormalized over the metrics available:

`6·rewatch (views/reach) + 5·save (saved/reach) + 4·velocity (early_shares/reach) + 2·completion (avg watch / clip length) + 1·noise ((likes+comments)/reach)`

From posts in the last 14 days (the window *is* the decay) it writes
`performance_lessons.json`:

- `signals` — attributes whose posts score ≥ 0.5 standard deviations above
  (+1) or below (−1) the rest: each ingredient, `hook_structure_ok`, and each
  archetype with ≥ 3 posts.
- `anti_signals` — attributes over-represented in the bottom quartile.
- `diagnostics` — why signals may be empty: self-assessments marked the same
  way on ≥ 90% of posts, archetypes too fragmented to compare, or scores
  compressed into a narrow band.
- `top_subjects` — top 3 subjects by score over 30 days, for variant seeking.

`category` (`pop_culture` / `wisdom`) is a routing label only — it decides
which collector and schedule, and is never scored.

## File formats

**`news.json` entry**
```json
{"topic": "...", "importance": 8, "audience": "...", "angle": "<the nostalgia bridge>",
 "archetype": "childhood-object-nostalgia", "subject": "Mickey Mouse Club",
 "source_title": "...", "source_url": "...", "status": "collected", "added": "2026-08-31"}
```
Wisdom entries add `"category": "wisdom"` and `"person"`.

**`moments_<HHMM>_<n>.json`**
```json
{"idea": {<the news.json entry>},
 "source": {"id": "...", "url": "...", "title": "...", "channel": "...", "velocity": 225},
 "moment": {"video_id": "...", "start": 60.0, "end": 85.0, "reason": "...", "score": 72}}
```
The producer adds `"consumed_by": "<queue folder>"` once the reel clears the gate.

**`queue/<folder>/reel.json`**
```json
{"hook": "The 1990s Show That Produced Britney Spears, Justin Timberlake, And Ryan Gosling Before Vanishing Is Returning On Disney+ After *32* Years 🔥",
 "clip": "clip_01.mp4", "category": "pop_culture",
 "cta": "Share if you watched MMC before they were famous",
 "ingredients": {"emotional_charge": true, "causal_chain": true, "personal_ritual": true},
 "hook_structure_ok": true, "archetype": "childhood-object-nostalgia", "subject": "Mickey Mouse Club"}
```
Plus `caption.txt`: 1–2 sentences and 4–6 hashtags, brand hashtag first.

**`runs/<d>/produced_<HHMM>.json`**
```json
{"topic": "...", "folder": "<queue folder>", "hook": "...", "category": "pop_culture",
 "source": {"id": "...", "start": 60.0, "end": 85.0},
 "qc_frames": [{"t": 60.0, "description": "<what is visible>", "verdict": "pass"}]}
```

## Paths

- Repo: `~/media-pipeline/` (`setup.sh` rewrites this to the actual checkout)
- Config: `ig_config.json` (credentials), `brand.json` (header card), `sources.json` (news sources)
- Queue: `news.json` (collected → scouted → produced)
- Per-day audit trail: `runs/<YYYY-MM-DD>/` — raw news, transcripts, moments, produced records, QC frames. Files are run-scoped (`_<HHMM>`) and never overwritten.
- Drafts: `queue/<YYYY-MM-DD>_<slug>/` — `clip_01.mp4`, `reel.json`, `reel.mp4`, `caption.txt`
- Published: `posted/` + `reel_posted.json` (never wipe); rejected: `skipped/`
- Metrics: `performance.json`, `performance_lessons.json`

## Operations

```bash
cd ~/media-pipeline
python3 scripts/dashboard.py                      # control panel, http://127.0.0.1:8787
python3 scripts/publish_reel.py --config ig_config.json --pick <folder> --dry-run
python3 scripts/publish_reel.py --config ig_config.json --pick <folder>   # publish now
mv queue/<folder> skipped/                        # skip a reel
python3 scripts/make_reel.py queue/<folder>       # re-render after editing reel.json
python3 scripts/overlay_check.py queue/<folder>/clip_01.mp4
```

The dashboard binds to `127.0.0.1` only and logs every action to
`dashboard_audit.jsonl`. It deliberately has no QC-override button —
overriding the gate should mean re-running QC, not flipping a flag.

**Scheduling:** jobs fire only while something ticks the Hermes scheduler —
the Hermes desktop app (while open) or the profile's gateway
(`hermes -p media-pipeline gateway install --start-now --start-on-login`).
Check with `hermes -p media-pipeline cron status`.

## Technical notes

- **Apple Color Emoji only renders at fixed bitmap sizes** (20, 64, 160px).
  `make_reel.py` renders each emoji at 160px and scales the tile down; never
  request an arbitrary emoji size from `ImageFont.truetype`.
- **Inter is a variable font.** Load `Inter-Variable.ttf` once and use
  `set_variation_by_axes([weight, optical_size])` (e.g. `[700, 20]` bold).
- **Audio mux:** if the clip has no audio stream, `make_reel.py` adds a
  silent track so the container always has one.
- **Low-reach noise:** the composite is built from ratios, so posts under
  50 reach are excluded — at tiny reach a few rewatches swamp real winners.
- **Overlay check limits:** near-static shots are reported "inconclusive"
  (overlay and scene can't be separated), and without `tesseract` the check
  is skipped. Frame QC still applies in both cases.
