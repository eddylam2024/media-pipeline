#!/usr/bin/env python3
"""
sample_shares.py — capture EARLY share velocity for freshly-published reels.

Priority-#3 of the scoring model (shares in the first ~60-90 min) can't come
from the once-nightly fetch_insights run, so this samples `shares` shortly
after each publish slot and stamps it into performance.json. Idempotent: a
reel already carrying `early_shares` is skipped, so running it at each of the
14:00/18:00/22:00 slots only ever records the first (earliest) sample.

Usage: python3 sample_shares.py --config ~/media-pipeline/ig_config.json
       [--max-age-min 150]   # only sample reels posted within this window
Exit 2 if nothing has been posted yet.
"""
import argparse, json, os, sys, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v21.0")
GRAPH_URL = "https://graph.facebook.com/%s" % GRAPH_VERSION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--max-age-min", type=int, default=150)
    args = ap.parse_args()
    cfg = json.load(open(os.path.expanduser(args.config)))
    token = os.environ.get("IG_TOKEN") or cfg.get("access_token")
    if not token:
        sys.stderr.write("no access_token\n")
        sys.exit(3)

    posted_path = os.path.join(BASE, "reel_posted.json")
    if not os.path.exists(posted_path):
        print("Nothing posted yet — no shares to sample.")
        sys.exit(2)
    posted = json.load(open(posted_path)).get("posted", [])
    if not posted:
        print("Nothing posted yet — no shares to sample.")
        sys.exit(2)

    perf_path = os.path.join(BASE, "performance.json")
    perf = json.load(open(perf_path)) if os.path.exists(perf_path) else {}

    import requests
    now = datetime.datetime.now()
    sampled = 0
    for rec in posted:
        mid = rec.get("ig_media_id")
        if not mid:
            continue
        # skip if we've already captured an early sample for this reel
        if perf.get(mid, {}).get("early_shares") is not None:
            continue
        posted_at = rec.get("posted_at")
        if not posted_at:
            continue
        try:
            dt = datetime.datetime.fromisoformat(posted_at)
        except Exception:
            continue
        age_min = (now - dt).total_seconds() / 60.0
        if age_min < 0 or age_min > args.max_age_min:
            continue
        try:
            r = requests.get(GRAPH_URL + "/%s/insights" % mid,
                             params={"metric": "shares", "access_token": token},
                             timeout=60)
            data = r.json()
            if "error" in data:
                sys.stderr.write("  ! %s: %s\n"
                                 % (rec["id"], data["error"].get("message", "")[:120]))
                continue
            vals = (data.get("data") or [{}])[0].get("values") or [{}]
            shares = vals[0].get("value")
            if shares is None:
                continue
            entry = perf.get(mid, {})
            entry.setdefault("name", rec["id"])
            entry.setdefault("category", rec.get("category", "pop_culture"))
            entry.setdefault("posted_at", posted_at)
            entry["early_shares"] = shares
            entry["early_sampled_at"] = now.isoformat(timespec="seconds")
            entry["minutes_since_post"] = round(age_min)
            perf[mid] = entry
            sampled += 1
        except Exception as e:
            sys.stderr.write("  ! %s: %s\n" % (rec.get("id"), e))

    json.dump(perf, open(perf_path, "w"), indent=2)
    print("early share velocity sampled for %d reel(s)" % sampled)


if __name__ == "__main__":
    main()
