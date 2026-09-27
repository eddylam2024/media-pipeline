#!/usr/bin/env python3
"""
qc_gate.py — hard gate on the producer's mandatory clean-frame + content-
relevance QC (added 2026-08-02 after a scout/producer QC bypass shipped a
reel sourced from the wrong scene — see media-pipeline SKILL.md "Clean-frame
+ content-relevance QC" rule).

The producer stage is REQUIRED to vision-check sampled frames of the actual
cut clip and record what it saw. This script refuses to let a candidate be
finalized (consumed_by stamped, news.json marked "produced") unless that
audit trail exists, covers the clip densely enough, and every frame passed.

It then runs an independent pixel-level check (overlay_check.py) on the cut
clip, so a burned-in watermark fails the gate even if the agent's report
called every frame clean. A flagged clip can only pass with an explicit
"overlay_override": {"reason": "..."} in the manifest (e.g. text that is
genuinely part of the scene), which is printed so a reviewer sees it.

Usage:
  python3 qc_gate.py runs/<date>/produced_<HHMM>.json
  (exit 0 = gate passed, proceed; exit 1 = gate failed, do NOT finalize —
   go back to the scout's next-best candidate or report an honest zero)

Required shape in the produced_<HHMM>.json manifest:
  "folder": "<queue folder name>"    (clip checked: queue/<folder>/clip_01.mp4)
  "source": {"start": <float>, "end": <float>, ...}
  "qc_frames": [
    {"t": <float, seconds into the source video>,
     "description": "<non-empty description of what's visibly in frame>",
     "verdict": "pass" | "fail"},
    ...
  ]

Coverage requirement mirrors the skill's "every ~3-4s boundary": at least
ceil(duration / 4) frames, duration = source.end - source.start.
"""
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fail(msg):
    sys.stderr.write(f"QC GATE FAILED: {msg}\n")
    sys.exit(1)


def check_overlay(data):
    """Independent watermark check on the actual clip. Fails the gate on
    overlay text unless the manifest carries an explicit override reason."""
    folder = data.get("folder")
    if not folder:
        fail("manifest missing 'folder' — cannot locate the clip for the overlay check")
    clip = os.path.join(BASE, "queue", folder, "clip_01.mp4")
    if not os.path.exists(clip):
        fail(f"clip not found for overlay check: {clip}")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from overlay_check import check
    result = check(clip)
    status = result["status"]
    if status == "flagged":
        found = "; ".join(f"{f['corner']}: {f['text']!r}" for f in result["findings"])
        reason = ((data.get("overlay_override") or {}).get("reason") or "").strip()
        if len(reason) < 20:
            fail(
                f"burned-in text/watermark detected in the clip ({found}). Re-cut "
                "a clean window or pick another source. If the text is genuinely "
                "part of the scene, add \"overlay_override\": {\"reason\": \"...\"} "
                "explaining why."
            )
        return f"FLAGGED ({found}) — overridden: {reason}"
    if status in ("inconclusive", "skipped"):
        sys.stderr.write(f"overlay check {status}: {result.get('reason')}\n")
    return status


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        sys.exit(2)

    path = sys.argv[1]
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read/parse {path}: {e}")

    source = data.get("source") or {}
    start, end = source.get("start"), source.get("end")
    if start is None or end is None:
        fail("manifest missing source.start/source.end — cannot check coverage")
    duration = end - start
    if duration <= 0:
        fail(f"non-positive clip duration ({duration}s)")

    frames = data.get("qc_frames")
    if not isinstance(frames, list) or not frames:
        fail(
            "no 'qc_frames' audit trail present — the mandatory clean-frame "
            "+ content-relevance vision QC was not recorded. A bare "
            "'qc_retries' counter is not evidence the check happened."
        )

    min_frames = max(1, math.ceil(duration / 4.0))
    if len(frames) < min_frames:
        fail(
            f"only {len(frames)} qc_frames recorded for a {duration:.1f}s "
            f"clip — need at least {min_frames} (~every 4s, per skill rule)"
        )

    bad = []
    for i, fr in enumerate(frames):
        t = fr.get("t")
        desc = (fr.get("description") or "").strip()
        verdict = fr.get("verdict")
        if t is None or not (start <= t <= end + 0.5):
            bad.append(f"frame {i}: t={t!r} out of clip range [{start},{end}]")
            continue
        if not desc:
            bad.append(f"frame {i} (t={t}): empty description")
            continue
        if verdict not in ("pass", "fail"):
            bad.append(f"frame {i} (t={t}): invalid verdict {verdict!r}")
            continue
        if verdict == "fail":
            bad.append(f"frame {i} (t={t}): FAILED — {desc}")

    if bad:
        fail("qc_frames did not clear the gate:\n  " + "\n  ".join(bad))

    overlay_note = check_overlay(data)

    print(f"QC GATE PASSED: {len(frames)} frames, all pass, duration {duration:.1f}s"
          f"; overlay check: {overlay_note}")
    sys.exit(0)


if __name__ == "__main__":
    main()
