#!/usr/bin/env python3
"""
fetch_transcript.py — pull a YouTube video's captions as timestamped segments.

Prefers manual English subtitles, falls back to auto-generated. No video is
downloaded. Output is what the scout agent feeds to the LLM for moment
extraction (timestamp / quote / reason).

Usage:
  python3 fetch_transcript.py <youtube-url-or-id> [-o out.json]

Output JSON: {"id", "title", "duration_s", "kind": "manual"|"auto",
              "segments": [{"start": s, "end": s, "text": "..."}]}
Exit 3 if the video has no English captions at all.
"""
import json, os, re, sys, argparse, tempfile, glob

from yt_dlp import YoutubeDL


def parse_json3(path):
    data = json.load(open(path, encoding="utf-8"))
    segs = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs", []) or [])
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000.0
        dur = ev.get("dDurationMs", 0) / 1000.0
        segs.append({"start": round(start, 2),
                     "end": round(start + dur, 2), "text": text})
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()
    vid = args.video
    if not vid.startswith("http"):
        vid = f"https://www.youtube.com/watch?v={vid}"

    with tempfile.TemporaryDirectory() as td:
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB", "en-orig"],
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(td, "%(id)s.%(ext)s"),
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(vid, download=True)  # downloads subs only
        files = glob.glob(os.path.join(td, "*.json3"))
        if not files:
            sys.stderr.write("no English captions available\n")
            sys.exit(3)
        # manual subs listed in info['subtitles'] vs auto in 'automatic_captions'
        kind = "manual" if info.get("subtitles") else "auto"
        segs = parse_json3(files[0])

    out = {"id": info["id"], "title": info.get("title", ""),
           "duration_s": info.get("duration"), "kind": kind, "segments": segs}
    if args.out:
        json.dump(out, open(args.out, "w"), indent=2, ensure_ascii=False)
        print(f"{args.out}  ({len(segs)} segments, {kind})")
    else:
        json.dump(out, sys.stdout, ensure_ascii=False)
        print()


if __name__ == "__main__":
    main()
