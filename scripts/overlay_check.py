#!/usr/bin/env python3
"""
overlay_check.py — independent, deterministic watermark / burned-in text
check for a cut clip. Called by qc_gate.py; also runnable on its own.

Why: the producer's frame QC is an agent's own report, and qc_gate.py used to
only check that the report existed. A clip with a burned-in source watermark
(a "DEBUGMENU.COM" corner tag) was published because the agent described the
frames as clean. This check looks at the pixels itself, so the gate no longer
depends solely on the agent's claim.

How: sample frames across the clip and find corner regions whose pixels stay
still while the footage around them moves and that contain sharp edges — the
signature of an overlay. OCR those regions (tesseract) and flag confidently read
words (4+ letters) or URL/handle patterns. Native game HUDs (icons, digits,
words like SCORE/LEVEL/TIME) pass; channel names, sites, and handles are
flagged.

Limits: a near-static shot can't separate overlay from scene, so low-motion
clips are reported as "inconclusive" (not a failure). Without tesseract
installed, the check is skipped with a warning.

Usage:
  python3 overlay_check.py <clip.mp4>
  exit 0 = clean or inconclusive, 1 = overlay text found, 2 = usage error
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

WIDTH = 640              # analysis width (px)
SAMPLES = 10             # frames sampled across the clip
STILL_STD = 6.0          # per-pixel temporal std below this = "not moving"
EDGE_MIN = 40.0          # mean gradient above this = "sharp edge"
MIN_MOTION = 5.0         # median temporal std below this = static shot
MIN_COVERAGE = 0.005     # corner fraction of still-edge pixels worth OCRing
CORNER_H, CORNER_W = 0.25, 0.35

MIN_WORD_CONF = 80       # tesseract per-word confidence; drops misreads
WORD_RE = re.compile(r"^[A-Za-z]{4,}$")
URL_RE = re.compile(r"(\.(com|net|org|tv|io|co)\b|www\.|@\w{3,})", re.I)
# Words that appear in native game HUDs, which the QC rules allow.
HUD_WORDS = {
    "score", "level", "life", "lives", "time", "rings", "coins", "stage",
    "world", "health", "ammo", "player", "round", "lap", "best", "mario",
    "luigi", "sonic", "pause", "start", "select", "items", "gold", "exp",
}


def _duration(clip):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", clip], text=True)
    return float(out.strip())


def _gray_frame(clip, t):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", clip,
         "-frames:v", "1", "-vf", f"scale={WIDTH}:-2,format=gray",
         "-f", "rawvideo", "-"], capture_output=True).stdout
    h = len(raw) // WIDTH
    return np.frombuffer(raw[:WIDTH * h], np.uint8).reshape(h, WIDTH).astype(np.float32)


def _ocr(region):
    with tempfile.TemporaryDirectory() as d:
        pgm, png = f"{d}/r.pgm", f"{d}/r.png"
        with open(pgm, "wb") as f:
            f.write(b"P5 %d %d 255\n" % (region.shape[1], region.shape[0]))
            f.write(region.astype(np.uint8).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pgm,
                        "-vf", "scale=iw*4:-1", png], check=True)
        tsv = subprocess.run(["tesseract", png, "-", "--psm", "6", "tsv"],
                             capture_output=True, text=True).stdout
    words = []
    for line in tsv.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) == 12 and cols[11].strip():
            try:
                words.append((cols[11].strip(), float(cols[10])))
            except ValueError:
                pass
    return words


def _overlay_words(words):
    """Confident words that look like overlay text rather than a game HUD."""
    hits = []
    for word, conf in words:
        if conf < MIN_WORD_CONF:
            continue
        if URL_RE.search(word):
            hits.append(word)
            continue
        core = word.strip(".,:;!?'\"()[]-")
        if WORD_RE.match(core) and core.lower() not in HUD_WORDS:
            hits.append(core)
    return hits


def check(clip):
    """Return {"status": "clean"|"flagged"|"inconclusive"|"skipped", ...}."""
    if not shutil.which("tesseract"):
        return {"status": "skipped", "reason": "tesseract not installed"}

    dur = _duration(clip)
    frames = [_gray_frame(clip, dur * (i + 0.5) / SAMPLES) for i in range(SAMPLES)]
    h = min(f.shape[0] for f in frames)
    stack = np.stack([f[:h] for f in frames])

    temporal_std = stack.std(0)
    motion = float(np.median(temporal_std))
    if motion < MIN_MOTION:
        return {"status": "inconclusive", "motion": round(motion, 1),
                "reason": "near-static shot; overlay and scene can't be separated"}

    grad = (np.abs(np.diff(stack, axis=2))[:, :-1, :]
            + np.abs(np.diff(stack, axis=1))[:, :, :-1]).mean(0)
    still_edges = (temporal_std[:-1, :-1] < STILL_STD) & (grad > EDGE_MIN)
    median = np.median(stack, 0)

    H, W = still_edges.shape
    bh, bw = int(H * CORNER_H), int(W * CORNER_W)
    corners = {
        "top-left": (0, bh, 0, bw), "top-right": (0, bh, W - bw, W),
        "bottom-left": (H - bh, H, 0, bw), "bottom-right": (H - bh, H, W - bw, W),
    }
    findings, examined = [], []
    for name, (y0, y1, x0, x1) in corners.items():
        zone = still_edges[y0:y1, x0:x1]
        if zone.mean() < MIN_COVERAGE:
            continue
        ys, xs = np.nonzero(zone)
        ry0, ry1 = max(0, y0 + ys.min() - 4), y0 + ys.max() + 5
        rx0, rx1 = max(0, x0 + xs.min() - 4), x0 + xs.max() + 5
        words = _ocr(median[ry0:ry1, rx0:rx1])
        examined.append({"corner": name, "coverage": round(float(zone.mean()), 4),
                         "ocr": [[w, round(c)] for w, c in words][:12]})
        hits = _overlay_words(words)
        if hits:
            findings.append({"corner": name, "text": " ".join(hits)[:80]})

    return {"status": "flagged" if findings else "clean",
            "motion": round(motion, 1), "findings": findings, "examined": examined}


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    result = check(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["status"] == "flagged" else 0)


if __name__ == "__main__":
    main()
