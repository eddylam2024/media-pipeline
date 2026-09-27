#!/usr/bin/env python3
"""
yt_search.py — keyless YouTube search + ranking for the media pipeline.

Uses yt-dlp (no API key). Flat-searches N results, fetches full metadata for
the top candidates, and ranks by the velocity signal views ÷ days_since_upload
— a 500k-view video from 3 days ago beats a 5M-view video from 3 years ago.

Usage:
  python3 yt_search.py "<query>" [-n 15] [--details 6] [--max-age-days 3650]

Output (stdout): JSON list sorted by velocity desc, each item:
  id, url, title, channel, duration_s, view_count, upload_date, days_old,
  velocity, has_subs (auto or manual captions available)
"""
import json, sys, math, argparse, datetime

from yt_dlp import YoutubeDL

FLAT_OPTS = {"quiet": True, "no_warnings": True, "extract_flat": True,
             "skip_download": True}
DETAIL_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True}


def flat_search(query, n):
    with YoutubeDL(FLAT_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [e for e in info.get("entries", []) if e and e.get("id")]


def detail(video_id):
    with YoutubeDL(DETAIL_OPTS) as ydl:
        return ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=15, help="flat search breadth")
    ap.add_argument("--details", type=int, default=6,
                    help="fetch full metadata for top K by view count")
    ap.add_argument("--max-age-days", type=int, default=3650)
    args = ap.parse_args()

    entries = flat_search(args.query, args.n)
    # pre-rank by view_count (flat results usually carry it) to pick detail set
    entries.sort(key=lambda e: e.get("view_count") or 0, reverse=True)

    results, today = [], datetime.date.today()
    for e in entries[:args.details]:
        try:
            d = detail(e["id"])
        except Exception as ex:
            sys.stderr.write(f"  ! detail {e['id']}: {ex}\n")
            continue
        up = d.get("upload_date")  # YYYYMMDD
        days_old = None
        if up:
            try:
                days_old = max((today - datetime.date(
                    int(up[:4]), int(up[4:6]), int(up[6:8]))).days, 1)
            except ValueError:
                pass
        if days_old and days_old > args.max_age_days:
            continue
        views = d.get("view_count") or 0
        has_subs = bool(d.get("subtitles")) or bool(d.get("automatic_captions"))
        results.append({
            "id": d["id"],
            "url": f"https://www.youtube.com/watch?v={d['id']}",
            "title": d.get("title", ""),
            "channel": d.get("channel") or d.get("uploader", ""),
            "duration_s": d.get("duration"),
            "view_count": views,
            "upload_date": up,
            "days_old": days_old,
            "velocity": round(views / days_old) if days_old else None,
            "has_subs": has_subs,
        })

    results.sort(key=lambda r: r["velocity"] or 0, reverse=True)
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
