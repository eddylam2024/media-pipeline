---
name: media-pipeline
description: News → single-clip nostalgia reel pipeline for @nostalgic.drop. Collect nostalgia-relevant news/topics, scout up to 3 compelling clips, render each under a branded "screenshotted post" header card, auto-publish daily (4x/day), analyze.
version: 4.3.0
author: Edouard Lam
platforms: [macos]
tags: [nostalgia, reels, instagram, news, youtube, cron, publish]
---

# Media Pipeline — Single-Clip Nostalgia Reel Pipeline

Converts nostalgia-relevant news/topics into reels for **@nostalgic.drop**
(same account/brand as the carousel pipeline in the `nostalgia` profile).

## FORMAT v4 (locked 2026-08-02 — full rebuild, replaces v1-v3 entirely)

Modeled on @Wealth-style IG reels: a screenshotted-social-post header card
above ONE continuous, minimally-touched video clip.

- **Header card:** circular Nostalgic Drop avatar + "Nostalgic Drop" + gold
  verified checkmark + "@nostalgic.drop" handle, plain UI sans-serif (Inter
  — NOT the old Anton condensed poster font).
- **Hook = the post caption.** Title Case (not ALL CAPS), a complete,
  specific, curiosity-driving claim about the subject — e.g. "The Button
  That Started The Chernobyl Disaster Disappeared From This Control Room
  And Has Never Been Officially Found 😱 💡". `*word*` = gold emphasis.
  Real emoji render natively (see Pitfalls — Apple Color Emoji strike sizes).
  - **Winning hook structure (locked 2026-08-18):** `(specific named
    subject) + (a loss, block, or denial) + (a reversal word — "then"/
    "finally" — when there's a redemption/resolution arc) + (a concrete,
    named, countable payoff)`. The payoff MUST end on a named person, a
    specific number, or a countable thing — **NEVER an abstract noun**
    ("a rule," "a lesson," "a truth," "a secret," "everything"). Exact
    numbers/dates/dollar figures add stakes; vague time markers ("at 30,"
    "two years before") do not. The hook must also carry three ingredients:
    (1) emotional charge beyond generic inspiration (grief / nostalgia-ache
    / personal ownership); (2) a hyper-specific verifiable causal chain,
    not a paraphrased quote; (3) where the topic allows, a ritual/object
    the VIEWER personally had or did (optional for `wisdom` — require 1+2 +
    the concrete payoff there).
  - **Proven vs. flat:** the account's single best post (Chadwick Boseman,
    Howard speech — 50 likes, 6 saves, 8 profile visits, 1 follow, 2 shares)
    is a commencement speech that won on a specific causal chain + real
    grief. The flat performers (Elon Musk, Arnold, Bill Gates, Denzel, JK
    Rowling, Oprah — all ~115-140 reach, 0-2 likes) were also commencement
    speeches but used the dead template "(Person) Tells Graduates
    (Inspirational Lesson)." **Category/venue is not the predictor — the
    hook shape is.** Don't ban commencement speeches; ban generic uplift
    ending on an abstract lesson.
  - **Archetype + subject tracking, and variant-seeking (added 2026-08-18
    — "obsess over what worked"):** every `news.json`/`reel.json` entry now
    carries an `archetype` tag (freeform kebab-case story-shape label, e.g.
    `denied-then-triumphant`, `childhood-object-nostalgia`,
    `discontinued-return`, `hidden-mystery-fact`, `grief-loss`,
    `gen-defining-tech-shift` — coin a new one if nothing fits) and a
    `subject` (the specific named person or franchise/IP). Unlike
    `category`, **archetype IS a live scoring dimension** —
    `fetch_insights.py` computes per-archetype average composite score
    (n≥3, 14-day decay) and emits `archetype:<tag> +1/-1` signals the
    collectors read alongside the ingredient signals. Separately,
    `performance_lessons.json`'s `top_subjects` list (top 3 by composite
    score, 30-day window) drives an explicit **variant-seeking step**: both
    collectors actively search for ONE new, genuinely different moment
    about each top subject (different clip/fact/angle — never a repost of
    the same footage or story) each run. Dedup stays story-level, not
    subject-level — the same subject can recur as often as real new
    angles exist; only the exact same story is blocked.
- **ONE video clip below, full-bleed width, fit-to-width preserving its
  native aspect ratio.** NO crop, NO zoom, NO sub-shot cuts, NO THEN/NOW
  pairing, NO graphic badges/CTA cards. "No more big video edits" is Eddy's
  explicit standing instruction (2026-08-02) — the clip plays close to as
  found, letterboxed by its own aspect ratio, nothing else.
- **Optional CTA text line below the clip (added 2026-08-11, deliberate
  scoped exception to the rule above)** — a short, topic-relevant,
  take-a-side share-prompt written by the producer into `reel.json`'s
  `cta` field (e.g. "Share if old games beat anything releasing today").
  Still no graphic badge/card — plain Inter gold text, same style system
  as the hook, smaller. `make_reel.py` only renders it when the clip's own
  height leaves real room above Instagram's bottom safe zone; automatically
  and silently skipped otherwise (logged to stderr) — never allowed to
  encroach on IG's reserved UI area. See `render_cta()` / the `CTA_*`
  constants near the top of `make_reel.py`.
- **Audio is baked in from the source clip (changed 2026-08-02).** `make_reel.py`
  renders reel.mp4 with the clip's ORIGINAL source audio muxed in — no more
  silent render + live Instagram Audio API pick. `publish_reel.py` no longer
  calls the IG Audio API or sets `audio_configuration`; it just publishes the
  video as rendered. If a source clip has no audio stream, a silent track is
  still muxed in (Reels containers expect a stream to exist).

### Content scope (broadened 2026-08-02)
Not strictly "current news → nostalgia bridge" anymore. Also covers: cool
things that recently came back to life (revivals, restocks, remakes,
reunions), and standalone 90s-2000s curiosity/rediscovery content in the
style of urban-exploration or declassified-footage pages. The news
collector (Stage 1) still supplies most candidates since revival/remake/
anniversary stories fit this well, but the scout (Stage 2) is not required
to find a THEN+NOW pair anymore — just the single strongest clip.

## Key Rules (user preferences)
- **Auto-publish (approved 2026-08-11, updated 2026-09-05 to 4x/day):** Stage 4 publishes the oldest queued reel automatically at 12:30 / 15:30 / 18:30 / 21:30 daily via `publish_reel.py --pick oldest`. No manual approval required. Stage 3 (producer) produces up to 4 reels per run to match the 4 daily slots. Dedup is handled by `reel_posted.json`. `share_to_feed: "false"` retained.
- **Honest zero:** no bridgeable news / no usable video / no strong moment → report zero and stop. Never relax filters or pad.
- **Canonical scripts only:** agents CALL the scripts in `~/media-pipeline/scripts/` and never re-implement cutting/rendering/publishing inline.
- **Brevity:** briefings ≤ ~100 words.
- **No more big video edits (locked 2026-08-02):** one clip, near-raw, no cutting/zooming/framing engine. If a future request drifts back toward multi-shot editing, that's a real format change — propose it, don't silently rebuild v3.
- **Copyright posture:** ≤25s on the single source clip (hard-capped in `cut_clip.py`), prefer real footage — archival/POV/documentary/gameplay/longplay — over commentary. The header card + hook + branding is the transformation layer that makes this a repost-with-value, not a reupload.
- **Grid visibility (locked 2026-08-02):** `publish_reel.py` sets `share_to_feed: "false"` — reels live in the Reels tab/Explore/audio pages, never the main profile grid. Do not flip this back.
- **Subject-lock rule (scout):** a candidate video must be SPECIFICALLY ABOUT the announced subject, not merely contain it — an ensemble/team trailer is disqualified as the source for a narrower story even if the subject cameos in it.
- **Clean-frame + content-relevance QC (producer):** sample frames at every ~3-4s boundary across the WHOLE clip (not just start/mid/end) — burned-in text/watermarks fail; a frame that doesn't visibly show the actual subject fails even if text-clean.
- **QC must leave evidence, not just a claim (locked 2026-08-02 after an incident — see Pitfalls):** the producer records every sampled frame's timestamp, a one-line description of what's actually visible, and a pass/fail verdict into `produced_<HHMM>.json`'s `qc_frames` array, then runs `scripts/qc_gate.py` on that file. The gate fails the run (no `consumed_by` stamp, no "produced" status) if `qc_frames` is missing, too sparse for the clip length, or contains any `fail` verdict. A `qc_retries` counter with no underlying frame evidence is not acceptable — it doesn't prove the check happened.

## Stage 5 (Analytics) — updated 2026-09-08

`fetch_insights.py` now derives **anti-signals** from the bottom quartile of scored reels (within the 14-day window), alongside the existing positive signals. Anti-signals detect patterns that correlate with LOW performance — e.g., `anti-archetype:franchise-return` (generic franchise returns flopped) or `anti-archetype:denied-then-triumphant` (overcame-rejection stories underperformed).

`performance_lessons.json` now contains both:
```json
{
  "signals": [...],           // positive: lean toward
  "anti_signals": [...],      // negative: lean away
  "top_subjects": [...]
}
```

Stage 1 (collector) reads both arrays and biases selection accordingly (+1 = lean toward, -1 = lean away). Stage 5 reports both WIN/LOSE patterns in its briefing.

| Job ID | Name | Schedule | Model | Toolsets |
|--------|------|----------|-------|----------|
| 69f07a2136f9 | reel-1-news-collector | 0 11 * * * | profile default (flash) | web, file, terminal |
|| 33a66b847da9 | reel-2-video-scout | 20 11 * * * | profile default (flash) | web, file, terminal |
|| 00812f0c6424 | reel-3-producer | 0 12 * * * | **deepseek/deepseek-v4-pro** | web, file, terminal |
|| 657d4c2fa444 | reel-4-auto-publish | 30 12,15,18,21 * * * | profile default | terminal, file |
|| de9d28cb7f43 | reel-4b-share-sampler | 0 14,17,20,23 * * * | profile default | terminal, file |
|| 5f6766cef0a7 | reel-5-analytics | 0 21 * * * | profile default | file, terminal |
| Feedback loop (added 2026-08-14; scoring overhauled 2026-08-18): Stage 5's `fetch_insights.py` scores each reel with a **weighted composite in priority order — 6·rewatch(views/reach) + 5·save(saved/reach) + 4·velocity(early_shares/reach) + 2·completion(avg_watch/clip_seconds) + 1·noise((likes+comments)/reach)**, renormalized over whatever metrics landed (follows-per-reach is unavailable — the Media Insights API does not expose `follows` for REELS media). Early share velocity comes from `reel-4b-share-sampler`, which samples `shares` ~60-90 min after each publish slot (`sample_shares.py`, idempotent) and stamps `early_shares` into `performance.json`. It writes `performance_lessons.json` — a `signals` array of `{tag, weight, note}` from the trailing 14-day window comparing CONTENT ATTRIBUTES: the producer's per-post `ingredients` (emotional_charge / causal_chain / personal_ritual) and `hook_structure_ok`, with a capitalized-multi-word heuristic as fallback when structured fields are absent. It also scores per-`archetype` average composite (n≥3, same 14-day window) and emits `archetype:<tag> +1/-1` signals — **archetype IS a live scoring dimension**, unlike category, which was a proven false predictor (retired 2026-08-18) and is recorded for reference only. Separately it computes `top_subjects` (top 3 by composite score, 30-day window) for the variant-seeking step (see Hook section). `reel-1-news-collector` and `wisdom-1-collector` both read this file (step 3) and bias selection toward `weight: +1` tags and away from `weight: -1` — advisory only, never a hard exclude (an honest zero beats padding). The 14-day window IS the decay. Purely rule-based (not ML) — appropriate given the small daily volume. |
|| 7a0cdf8232a2 | wisdom-1-collector | 30 9 * * 1,4 (Mon/Thu only) | profile default (flash) | web, file, terminal |

The producer still runs the stronger model — picking the single strongest
clip and writing a sharp curiosity hook is still judgment-heavy even
without the old editing complexity. Stages gate on their predecessor's run
file, same as before.

## Content categories (added 2026-08-04)

Two content pillars now feed the same `news.json` queue, both consumed by
the same Stages 2-5:
- **pop-culture nostalgia** (daily, `reel-1-news-collector`) — the
  original nostalgia-bridge content (games, Y2K tech, early-internet
  culture, etc.). `news.json` entries with no `category` field default to
  this.
- **wisdom** (Mon/Thu only, `wisdom-1-collector`) — archival speeches/
  interviews from successful people (CEOs/founders/athletes/investors/
  scientists), framed around struggle/failure/formative lessons rather
  than pop-culture nostalgia. Entries carry `"category": "wisdom"` and a
  `"person"` field. Deliberately lower-cadence so it supplements the
  daily pop-culture content rather than diluting the account's primary
  identity (mirrors the lesson from the aggressive-callout hook
  experiment, which was tried and reverted the same day for a similar
  tone-dilution risk).

Scout's PERSON-LOCK check and producer's `category` field on `reel.json`
(defaults `"pop_culture"` for legacy entries) exist specifically to
support this split — see the Pitfalls section if either misbehaves.

**Category is a routing/cadence label only (which collector, which
schedule) — it is NOT a performance-scoring dimension** (proven a false
predictor 2026-08-18). Selection and the feedback loop score by content
attribute (the three winning ingredients + hook structure — see the Hook
section), not by category. Category is still recorded on `reel.json` and
`performance.json` for reference, just never scored.

## Data flow (v4)

```
sources.json ──▶ collect_news.py ──▶ runs/<d>/raw_news_1100.json
                        │ (agent: nostalgia-relevance filter + content-attribute weighting; NOT category)
                        ▼
                   news.json  {topic, importance, audience, angle, status}
                        │ status: collected → scouted → produced
                        ▼
   yt_search.py (footage-type filter, subject-lock, thumbnail QC)
                        ▼
                 runs/<d>/moments_<HHMM>_1.json, _2.json, _3.json  (up to 3, one per candidate)
                        ▼
   For EACH unconsumed moments file (up to 3):
   cut_clip.py (≤25s hard cap, ONE clip)
   clean-frame + content-relevance QC across the whole clip
   (recorded as qc_frames in produced_<HHMM>.json, enforced by qc_gate.py)
   reel.json {hook, clip, category, cta, ingredients, hook_structure_ok} ──▶ make_reel.py ──▶ reel.mp4
                        ▼
   12:30 / 15:30 / 18:30 / 21:30 auto-publish ──▶ publish_reel.py --pick oldest
                        │  Auto-publishes via Meta Graph API (no manual approval).
                        │  Moves queue/<name> -> posted/<name>, records in
                        │  reel_posted.json (dedup built-in). share_to_feed=false.
                        ▼
   14:00 / 17:00 / 20:00 / 23:00 sample_shares.py ──▶ early_shares in performance.json
                        ▼
   fetch_insights.py ──▶ performance.json + performance_lessons.json
                        ──▶ feeds Stage 1 content-attribute weighting (loop)
```

## reel.json manifest format (v4)

```json
{
  "hook": "The Button That Started *This* Disaster Disappeared 😱 💡",
  "clip": "clip_01.mp4",
  "category": "pop_culture",
  "cta": "Share if old games beat anything releasing today",
  "ingredients": { "emotional_charge": true, "causal_chain": true, "personal_ritual": false },
  "hook_structure_ok": true,
  "archetype": "hidden-mystery-fact",
  "subject": "Chernobyl control room"
}
```
- `hook`: Title Case, `*word*` = gold emphasis, real emoji supported inline;
  must follow the winning hook structure (see Hook section).
- `clip`: the single source file, ≤25s.
- `category`: `"pop_culture"` (default) or `"wisdom"` — **reference only,
  never scored** (see Content categories).
- `cta`: short (<=10 words) topic-specific share-prompt, or `""`.
- `ingredients` / `hook_structure_ok`: the producer's honest per-post
  self-assessment of the hook — which of the three winning ingredients it
  carries and whether the payoff ends on a named/number/countable thing.
  `fetch_insights.py` reads these to build content-attribute signals; be
  honest, since marking all-true on a weak hook poisons the feedback loop.
- `archetype` / `subject`: copied through from the moments/news.json entry.
  `archetype` is a freeform kebab-case story-shape tag; `subject` is the
  specific named person or franchise/IP. Unlike `category`, `archetype` IS
  scored (see Feedback loop table) and `subject` drives variant-seeking —
  see the "Archetype + subject tracking" note in the Hook section above.

## Audio

Reels use the ORIGINAL audio of the source clip, baked in by `make_reel.py`.
There is no music library, no Instagram Audio API call, and no
`music_query` / `audio_configuration`. Do not add music to the pipeline.

## Key paths

- Base dir: `~/media-pipeline/`
- Avatar: `assets/avatar.png` (full-res) / `assets/avatar_256.png` (circular-cropped, alpha-masked — used by `make_reel.py`'s header card)
- Fonts: `fonts/Inter-Variable.ttf` (header + hook text, variable weight axis — see Pitfalls), `fonts/Anton-Regular.ttf` + `fonts/EBGaramond-Bold.ttf` (unused by v4, kept for history/reference)
- Sources config: `sources.json`
- News queue: `news.json` (status lifecycle: collected → scouted → produced)
- Daily audit: `runs/<YYYY-MM-DD>/` — `raw_news_1100.json`, `transcript_*.json`, run-scoped `moments_<HHMM>.json` / `produced_<HHMM>.json` (never fixed names, never overwritten). Producer stamps `"consumed_by"` into the moments file it used.
- Drafts: `queue/<YYYY-MM-DD>_<slug>/` (`clip_01.mp4`, `reel.json`, `reel.mp4` [original clip audio], `caption.txt`)
- Published archive: `posted/` + tracker `reel_posted.json` (never wipe)
- Scripts: `scripts/{collect_news,yt_search,fetch_transcript,cut_clip,qc_gate,make_reel,publish_reel,fetch_insights}.py`
- Dashboard: `scripts/dashboard.py` + `scripts/dashboard_static/` — local read+control operating center (added 2026-08-03), see "Dashboard" section below
- IG credentials: `~/media-pipeline/ig_config.json` (@nostalgic.drop token)

## Backups (added 2026-08-02)

`~/media-pipeline` is a git repo (baseline + ongoing commits after each
change) — `git log`, `git diff`, `git checkout <commit> -- <file>` to
review/revert. A scoped repo also exists at
`~/.hermes/profiles/media-pipeline` tracking ONLY this skill file and
`cron/jobs.json` (everything else there is platform state/secrets and is
gitignored). See `~/media-pipeline/.gitignore` and the profile's
`.gitignore` for exact scope — rendered media and per-run artifacts are
excluded (large, regenerable), credentials are excluded (never commit
`ig_config.json`).

## Dashboard (added 2026-08-03)

`scripts/dashboard.py` is a local, read+control operating center for this
pipeline. stdlib-only (`http.server`), binds `127.0.0.1` ONLY — never
expose beyond localhost without adding real auth first. Not started by
cron; Eddy launches it manually when he wants the control surface up:

```bash
cd ~/media-pipeline && python3 scripts/dashboard.py --port 8787
# open http://127.0.0.1:8787
```

Read views: funnel (collected/scouted/produced/published, trailing 7d,
honest-zero days flagged), cron job health (real gateway status + per-job
last run/pause/resume), **QC transparency** (renders each produced reel's
`qc_frames` audit trail as a pass/fail timeline — any produced record
missing `qc_frames` is flagged red, since that means the gate should have
blocked it), pending queue with inline video preview, recently published
+ performance, skipped/held items, source-channel reuse.

Control actions — every one shells out to the existing canonical
scripts/`hermes` CLI, never reimplemented inline, and every call is logged
to `dashboard_audit.jsonl` (gitignored, local only):
- Publish now (`publish_reel.py --pick`) — force-publishes a specific queued reel immediately, bypassing the 12:30/17:00/20:30 schedule. Requires typing "publish"
  to confirm, since it's externally visible / not locally reversible.
- Skip, edit hook + re-render, re-cut window + re-render.
- Pause/resume/run-now a cron stage (`hermes -p media-pipeline cron ...`).
- Restart/install the gateway service.
- **Not implemented on purpose:** a QC-gate override button. Overriding
  the gate from a UI with no vision re-check would reintroduce the exact
  failure mode it was built to close (see Pitfalls incident below). If an
  override path is ever wanted, it should re-run QC, not just flip a flag.

## Gateway (fixed 2026-08-03 — was not actually running)

`hermes -p media-pipeline gateway install --start-now --start-on-login`
installs the profile's gateway as a persistent launchd user service so the
cron schedule (11:00/11:20/12:00/17:10/21:00) actually fires on its own.
Before this fix the gateway had never been installed for this profile —
every run to date had been triggered manually (`hermes -p media-pipeline
cron run <id>` + `cron tick`) by a prior session, not by the schedule.
Check with `hermes -p media-pipeline cron status` (or the dashboard's
gateway pill). **Known issue, not yet fixed:** the gateway service is
currently crash-looping every ~15-20s fighting another profile's gateway
over a shared Telegram bot token (see
`~/.hermes/profiles/media-pipeline/logs/gateway.error.log` —
repeated `SIGTERM` / "explicit --replace handoff" cycles). The cron
ticker itself seems to survive this so far (heartbeat stays fresh), but
it's an open reliability risk worth investigating separately — not
something this pipeline's own scripts caused, and out of scope for a
media-pipeline-only fix (needs to be resolved at the Telegram
platform/token-sharing level across profiles).

## Manual operations

```bash
# Force-publish a specific queued reel NOW (bypasses the cron schedule)
cd ~/media-pipeline && python3 scripts/publish_reel.py \
  --config ~/media-pipeline/ig_config.json --pick <folder-name>

# Skip it
mv ~/media-pipeline/queue/<name> ~/media-pipeline/skipped/ && rm -f ~/media-pipeline/pending_reel.json

# Re-render after editing reel.json
python3 scripts/make_reel.py queue/<name>

# Dry-run publish (no network)
python3 scripts/publish_reel.py --config ~/media-pipeline/ig_config.json --pick <name> --dry-run
```

## Pitfalls

- **Incident (2026-09-05): low-reach noise topped the analytics ranking.**
  `performance_lessons.json`'s `top_subjects` showed a 9-reach Buffy post
  (score 0.713) ranked ABOVE a 2,011-reach Jim Carrey post (score 0.485)
  and a 1,959-reach 1990s-show post — because `composite_score()` is built
  entirely from RATIOS (views/reach, saved/reach, etc.) with no reach floor.
  At n=9, 17 "views" (rewatches) produces a 1.89 rewatch ratio weighted 6x
  — pure small-sample noise, not a real signal, but it swamped posts with
  real audience size and real engagement. Fixed by adding `MIN_REACH_FLOOR
  = 50` in `fetch_insights.py` — `composite_score()` now returns `None`
  (excluded from scoring/signals/top_subjects entirely) for any post below
  that reach. If `top_subjects` or a signal ever again surfaces a post you
  don't recognize as a real winner, check its raw `reach` in
  `performance.json` first — low n is the likely culprit.
- **Known open issue (found 2026-09-05):** 4 posted reels
  (`clueless-closet-scene`, `steve-jobs-stay-hungry`, `pokemon_home`,
  `viola-davis-hunger`) fail `fetch_insights.py` with a Graph API "Object
  does not exist / missing permissions" error — likely expired media IDs
  or a token scope gap. They're permanently invisible to analytics until
  this is root-caused; not related to the reach-floor fix above.
- **Incident (2026-08-02): wrong-scene reel shipped past QC.** A "Clueless
  closet computer" story ended up sourced from a clip titled "Clueless:
  Dress by Calvin Klein (HD CLIP)" — a different scene. Root cause: (1) the
  scout only vision-checked the video's static default thumbnail, never
  frames from the actual chosen `[start, end]` window, and wrote a `reason`
  that wasn't grounded in anything it looked at; (2) the producer job's
  `enabled_toolsets` was `["file", "terminal"]` — no `web` — so it could not
  perform the vision QC its own instructions required, yet it still
  reported `qc_retries: 0` and let the file through. Fixed by adding `web`
  to the producer's toolset and requiring a real `qc_frames` audit trail
  (see `qc_gate.py`) instead of a bare retry counter. `produced_<HHMM>.json`
  now carries:
  ```json
  "qc_frames": [
    {"t": 11.0, "description": "Cher at digital closet computer, outfit grid on screen", "verdict": "pass"},
    {"t": 15.0, "description": "same shot, no watermark/text", "verdict": "pass"}
  ]
  ```
  one entry at least every ~4s of clip duration, each with a real
  description of what's in frame — not a placeholder.
- **Apple Color Emoji only renders at specific bitmap strike sizes**
  (confirmed working: 20, 64, 160px — arbitrary sizes like 109 raise
  "invalid pixel size"). `make_reel.py` renders each emoji token to its own
  RGBA tile at the 160px strike, then scales that tile down to fit the
  surrounding text line — never ask `ImageFont.truetype` for an arbitrary
  emoji size directly.
- **Inter is a variable font**, not separate Regular/Bold files — load
  `Inter-Variable.ttf` once and call `font.set_variation_by_axes([weight,
  optical_size])` (e.g. `[700, 20]` for bold, `[400, 20]` for regular)
  rather than looking for nonexistent static weight files.
- **`ig_config.json` must never be committed to git** — it holds the live
  @nostalgic.drop access token, excluded via `.gitignore`.
- **make_reel.py mux logic (added 2026-08-02):** if the source clip has an
  audio stream, it's mapped straight through (`0:a`); if not, a silent
  `anullsrc` track is generated and mapped instead (`3:a`) so the output
  container always has an audio stream regardless of the source.
- **v1-v3 sub-shot/zoom/THEN-NOW engine is superseded, not deleted** — full
  history is in git (`~/media-pipeline` repo, commits before 2026-08-02).
  If a future need calls for multi-clip editing again, look there before
  rebuilding from scratch.
- **Wrong-franchise/cameo footage and per-sub-shot QC lessons from v1-v3
  still apply conceptually** even though there's only one clip now — a
  clip can still drift mid-window to something off-subject, so the
  per-~3-4s-boundary sampling habit carries forward.
- **Heredocs are unreliable** in the hermes terminal — use `python3 -c "..."`
  with semicolons for JSON edits.
- **Render timeout (Chrome headless)** — not applicable to v4 (no HTML/Chrome
  rendering step anymore; `make_reel.py` v4 is pure ffmpeg + PIL). Kept
  here as a note in case a future format reintroduces HTML rendering.
