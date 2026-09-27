#!/usr/bin/env python3
"""
cut_clip.py — download ONLY a scored moment from a YouTube video.

Copyright posture (locked by Eddy 2026-07-31, cap widened 2026-08-02 for the
v4 single-clip format): transform-heavy short clips. This script enforces a
HARD CAP of 25 seconds on the one clip a v4 reel uses — the reel's original
layer (header card, hook text, branding) is added later by make_reel.py.
Never download whole videos. (v4 dropped the old multi-clip THEN/NOW total
budget — there's only ever one clip per reel now.)

Usage:
  python3 cut_clip.py <url-or-id> <start_s> <end_s> <out.mp4>

Example:
  python3 cut_clip.py dQw4w9WgXcQ 192.0 210.0 clip_01.mp4
"""
import os, sys, subprocess

MAX_CLIP_S = 25.0
PAD_S = 0.25  # keyframe padding either side


def main():
    if len(sys.argv) != 5:
        sys.stderr.write(__doc__)
        sys.exit(1)
    vid, start, end, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    if not vid.startswith("http"):
        vid = f"https://www.youtube.com/watch?v={vid}"
    if end <= start:
        sys.stderr.write("end must be > start\n")
        sys.exit(1)
    if end - start > MAX_CLIP_S:
        sys.stderr.write(
            f"REFUSED: clip {end-start:.1f}s exceeds the {MAX_CLIP_S:.0f}s "
            "hard cap (transform-heavy posture). Pick a tighter moment or "
            "split into two moments.\n")
        sys.exit(2)
    section = f"*{max(start - PAD_S, 0):.2f}-{end + PAD_S:.2f}"
    cmd = [sys.executable, "-m", "yt_dlp",
           "--quiet", "--no-warnings",
           "--download-sections", section,
           "--force-keyframes-at-cuts",
           "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
           "--merge-output-format", "mp4",
           "-o", out,
           vid]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(out):
        sys.stderr.write(r.stderr[-800:] + "\nclip download failed\n")
        sys.exit(3)
    size = os.path.getsize(out)
    print(f"{out}  ({size//1024} KB, {end-start:.1f}s requested)")


if __name__ == "__main__":
    main()
