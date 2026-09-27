# Changelog

How the pipeline evolved, and why. The operating rules themselves live in
[`hermes/skills/media-pipeline/SKILL.md`](hermes/skills/media-pipeline/SKILL.md).

## 5.0.0 — 2026-09-27

Renamed from `reel-nostalgia` to **Media Pipeline** and prepared for public release.

**Independent watermark check.** `qc_gate.py` used to verify only that the
producer *reported* a clean frame QC. Three published reels still carried
burned-in overlays (a `DEBUGMENU.COM` tag, a TV news lower-third, an
uploader's title card) because the agent described those frames as clean.
The new `overlay_check.py` finds text that stays still while the footage
moves, OCRs it, and fails the gate on words, URLs, or handles, allowing
native game HUDs through. Run against all 109 published clips, it caught
those 3 with one false positive (a game's weapon HUD, resolvable with an
explicit `overlay_override` reason).

**Feedback loop that can explain itself.** `performance_lessons.json` had
been empty for weeks. Two causes: the producer marked every hook as having
every ingredient, leaving nothing to compare; and once reach settled into a
narrow band, no score could clear the fixed ±20% threshold. Signals now use
an effect-size threshold (≥ 0.5 standard deviations), and a new
`diagnostics` list reports saturated self-assessments, fragmented
archetypes, and compressed scores.

**Scout saves as it goes.** From Sep 19–23 the scout hit its tool-call
budget every day before its final write step, discarding every vetted
candidate, so no reels were produced. It now writes each moments file as
soon as that candidate is vetted.

**Also:** `brand.json` for the header card (name, handle, avatar, badge);
`setup.sh` to create the Hermes profile, install the skill, and register
the jobs, with publishing paused; music library removed (the pipeline uses
each clip's original audio); unused Anton and EB Garamond fonts removed;
skill rewritten as rules only, with history moved here.

## 4.x — August–September 2026

- **2026-09-08** — Anti-signals from the bottom quartile of posts.
- **2026-09-05** — Publishing moved to 4× daily (12:30 / 15:30 / 18:30 /
  21:30). Added a 50-reach floor to scoring after a 9-reach post outranked a
  2,011-reach post on ratio noise.
- **2026-08-18** — Scoring overhauled into the weighted composite (rewatch,
  save, share velocity, completion, engagement). Category (`pop_culture` vs
  `wisdom`) proved a false predictor and was retired from scoring; the winning
  hook structure (named subject → setback → reversal → concrete payoff) and
  story archetypes became the tracked attributes, with variant-seeking on top
  subjects.
- **2026-08-14** — First feedback loop: Stage 5 writes
  `performance_lessons.json`, Stage 1 reads it.
- **2026-08-11** — Auto-publishing without manual approval; optional CTA line
  below the clip.
- **2026-08-04** — Second content pillar: `wisdom` (archival speeches and
  interviews), collected Mon/Thu.
- **2026-08-03** — Local operating dashboard. Discovered the profile gateway
  had never been installed, so the schedule wasn't firing on its own.

## 4.0.0 — 2026-08-02

Full rebuild into the current format: a screenshotted-post header card above
**one** continuous clip, near-raw — replacing the v1–v3 multi-shot engine
(sub-shot cuts, zooms, THEN/NOW pairing). The clip's original audio is baked
in instead of attaching Instagram audio at publish time.

Same day, a reel shipped with footage from the wrong scene: the scout had
checked only the video thumbnail, and the producer lacked the tools to do its
required frame QC but reported it as done. This led to the rule that QC must
leave per-frame evidence, enforced by `qc_gate.py`.

## 1.0 – 3.x — 2026-07-31 to 2026-08-01

Initial news → reel pipeline with a multi-clip editing engine (THEN/NOW
pairs, sub-shots, zooms, badges, CTA cards).
