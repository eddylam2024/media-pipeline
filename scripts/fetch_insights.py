#!/usr/bin/env python3
"""
fetch_insights.py — pull IG insights for published reels into performance.json.

Reads reel_posted.json (media ids from publish_reel.py), queries the Graph
API insights per reel, and merges into performance.json. Stage 1 reads the
derived performance_lessons.json to bias which CONTENT ATTRIBUTES (winning
hook ingredients / structure) actually perform — the feedback loop of the
pipeline. Category is NOT a scoring dimension (proven a false signal
2026-08-18) — it is recorded for reference only.

Scoring (weighted priority order, renormalized over whatever metrics landed;
follows-per-reach is intentionally absent — the Media Insights API does not
expose `follows` for REELS media):
    6 * rewatch    (views / reach)
    5 * save       (saved / reach)
    4 * velocity   (early_shares / reach)   [from sample_shares.py]
    2 * completion (avg_watch_seconds / clip_seconds)
    1 * noise      ((likes + comments) / reach)

Usage: python3 fetch_insights.py --config ~/media-pipeline/ig_config.json
Exit 2 if nothing has been posted yet (normal in the first days).
"""
import argparse, json, os, re, sys, subprocess, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v21.0")
GRAPH_URL = "https://graph.facebook.com/%s" % GRAPH_VERSION
# Probe-verified available for REELS media product type (2026-08-18).
# NOT available per-media and deliberately omitted: plays, follows,
# profile_visits, clips_replays_count. `views` stands in for plays.
METRICS = ("reach,saved,likes,comments,shares,total_interactions,views,"
           "ig_reels_video_view_total_time,ig_reels_avg_watch_time")
LESSONS_TTL_DAYS = 14
TOP_SUBJECTS_TTL_DAYS = 30
TOP_SUBJECTS_N = 3
# Minimum reach floor (added 2026-09-05 after an incident — see skill
# Pitfalls): the composite score is built from RATIOS (views/reach,
# saved/reach, etc.), which blow up into noise at tiny reach. A post seen
# by 9 people that got 17 "views" (rewatches) scored HIGHER than a post
# that reached 2,011 people with real engagement (71 likes, 9 saves) —
# pure small-sample-size artifact, not a real signal. Posts below this
# floor are excluded from scoring/signals/top_subjects entirely.
MIN_REACH_FLOOR = 50
NAMED_ENTITY_RE = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")

# composite weights, priority order (renormalized over present terms)
W_REWATCH, W_SAVE, W_VELOCITY, W_COMPLETION, W_NOISE = 6, 5, 4, 2, 1
INGREDIENT_KEYS = ("emotional_charge", "causal_chain", "personal_ritual")


def clip_seconds(name):
    """Best-effort clip duration (seconds) via ffprobe, for completion rate."""
    for sub in ("posted", "queue", "skipped"):
        for fn in ("clip_01.mp4", "reel.mp4"):
            p = os.path.join(BASE, sub, name, fn)
            if os.path.exists(p):
                try:
                    out = subprocess.check_output(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "default=nw=1:nk=1", p],
                        text=True).strip()
                    return float(out)
                except Exception:
                    return None
    return None


def composite_score(rec):
    """Weighted composite in priority order, renormalized over present terms.

    Returns None if reach is missing (nothing comparable). Terms whose inputs
    are absent are simply dropped and the remaining weights renormalized so
    scores stay comparable across posts with different available metrics.
    """
    m = rec.get("metrics", {})
    reach = m.get("reach")
    if not reach or reach < MIN_REACH_FLOOR:
        return None
    terms = []  # (weight, value)

    views = m.get("views")
    if views is not None:
        terms.append((W_REWATCH, views / reach))

    saved = m.get("saved")
    if saved is not None:
        terms.append((W_SAVE, saved / reach))

    early = rec.get("early_shares")
    if early is not None:
        terms.append((W_VELOCITY, early / reach))

    avg_ms = m.get("ig_reels_avg_watch_time")
    dur = rec.get("clip_seconds")
    if avg_ms is not None and dur:
        terms.append((W_COMPLETION, min((avg_ms / 1000.0) / dur, 1.0)))

    likes = m.get("likes") or 0
    comments = m.get("comments") or 0
    terms.append((W_NOISE, (likes + comments) / reach))

    wsum = sum(w for w, _ in terms)
    if not wsum:
        return None
    return sum(w * v for w, v in terms) / wsum


def load_reel_meta(name):
    """Find a posted reel's authoring metadata by folder name."""
    for sub in ("posted", "queue", "skipped"):
        p = os.path.join(BASE, sub, name, "reel.json")
        if os.path.exists(p):
            try:
                d = json.load(open(p))
                return {
                    "hook": d.get("hook", ""),
                    "ingredients": d.get("ingredients") or {},
                    "hook_structure_ok": d.get("hook_structure_ok"),
                    "category": d.get("category", "pop_culture"),
                    "archetype": d.get("archetype") or "",
                    "subject": d.get("subject") or "",
                }
            except Exception:
                break
    return {"hook": "", "ingredients": {}, "hook_structure_ok": None,
            "category": "pop_culture", "archetype": "", "subject": ""}


def _signal(rows, present_pred, tag, note_label, min_each=3):
    """Emit a +1/-1 signal comparing avg score of rows matching present_pred
    against the rest. Returns a list of 0, 1, or 2 signal dicts."""
    have = [r["score"] for r in rows if present_pred(r)]
    miss = [r["score"] for r in rows if not present_pred(r)]
    if len(have) < min_each or len(miss) < min_each:
        return []
    a, b = sum(have) / len(have), sum(miss) / len(miss)
    if a > b * 1.2:
        return [{"tag": tag, "weight": 1, "n": len(have),
                 "note": "%s avg %.3f vs without %.3f" % (note_label, a, b)}]
    if b > a * 1.2:
        return [{"tag": tag, "weight": -1, "n": len(have),
                 "note": "%s avg %.3f vs without %.3f" % (note_label, a, b)}]
    return []


def _collect_rows(perf, ttl_days):
    """Shared helper: scored, meta-enriched rows posted within ttl_days."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=ttl_days)
    rows = []
    for mid, rec in perf.items():
        posted_at = rec.get("posted_at")
        if not posted_at:
            continue
        try:
            dt = datetime.datetime.fromisoformat(posted_at)
        except Exception:
            continue
        if dt < cutoff:
            continue
        score = composite_score(rec)
        if score is None:
            continue
        meta = load_reel_meta(rec.get("name", ""))
        rows.append({
            "name": rec.get("name", ""),
            "score": score,
            "posted_at": posted_at,
            "hook": meta["hook"],
            "ingredients": meta["ingredients"],
            "hook_structure_ok": meta["hook_structure_ok"],
            "archetype": meta["archetype"],
            "subject": meta["subject"],
        })
    return rows


def _archetype_signals(rows, min_each=3):
    """Avg composite score per archetype vs baseline — same mechanism the
    old category-level signal used, generalized to a freeform tag written
    by the collectors at sourcing time. Category itself is intentionally
    NOT a signal dimension (proven a false predictor, retired 2026-08-18)."""
    signals = []
    if not rows:
        return signals
    baseline = sum(r["score"] for r in rows) / len(rows)
    by_arch = {}
    for r in rows:
        if r["archetype"]:
            by_arch.setdefault(r["archetype"], []).append(r["score"])
    for arch, scores in by_arch.items():
        if len(scores) < min_each:
            continue
        avg = sum(scores) / len(scores)
        if avg > baseline * 1.2:
            signals.append({"tag": "archetype:%s" % arch, "weight": 1,
                            "n": len(scores),
                            "note": "%s avg %.3f vs baseline %.3f" % (arch, avg, baseline)})
        elif avg < baseline * 0.8:
            signals.append({"tag": "archetype:%s" % arch, "weight": -1,
                            "n": len(scores),
                            "note": "%s avg %.3f vs baseline %.3f" % (arch, avg, baseline)})
    return signals


def _anti_signals(rows, min_each=3):
    """Anti-patterns from bottom quartile vs top 75%.
    If a feature is >1.2x more prevalent in bottom quartile, emit weight=-1 signal."""
    if len(rows) < 8:
        return []
    rows_sorted = sorted(rows, key=lambda r: r["score"])
    q = max(len(rows_sorted) // 4, 2)
    bottom = rows_sorted[:q]
    top = rows_sorted[q:]
    signals = []
    if not bottom or not top:
        return signals
    # ingredient anti-signals
    for key in INGREDIENT_KEYS:
        bottom_pct = sum(1 for r in bottom if r["ingredients"].get(key)) / len(bottom)
        top_pct = sum(1 for r in top if r["ingredients"].get(key)) / len(top)
        if bottom_pct > top_pct * 1.2 and bottom_pct > 0.25:
            signals.append({"tag": "anti-ingredient:%s" % key.replace("_", "-"),
                            "weight": -1, "n": len(bottom),
                            "note": "%s in %.0f%% bottom vs %.0f%% top" % (key, bottom_pct*100, top_pct*100)})
    # hook structure anti-signal
    bottom_pct = sum(1 for r in bottom if r["hook_structure_ok"] is True) / len(bottom)
    top_pct = sum(1 for r in top if r["hook_structure_ok"] is True) / len(top)
    if bottom_pct > top_pct * 1.2 and bottom_pct > 0.25:
        signals.append({"tag": "anti-hook-structure:concrete-payoff", "weight": -1, "n": len(bottom),
                        "note": "concrete-payoff in %.0f%% bottom vs %.0f%% top" % (bottom_pct*100, top_pct*100)})
    # named-entity hook anti-signal
    bottom_pct = sum(1 for r in bottom if len(NAMED_ENTITY_RE.findall(r["hook"])) >= 2) / len(bottom)
    top_pct = sum(1 for r in top if len(NAMED_ENTITY_RE.findall(r["hook"])) >= 2) / len(top)
    if bottom_pct > top_pct * 1.2 and bottom_pct > 0.25:
        signals.append({"tag": "anti-specific-named-hook", "weight": -1, "n": len(bottom),
                        "note": "specific-hook in %.0f%% bottom vs %.0f%% top" % (bottom_pct*100, top_pct*100)})
    # archetype anti-signals
    by_arch_bottom = {}
    by_arch_top = {}
    for r in bottom:
        if r["archetype"]:
            by_arch_bottom.setdefault(r["archetype"], 0)
            by_arch_bottom[r["archetype"]] += 1
    for r in top:
        if r["archetype"]:
            by_arch_top.setdefault(r["archetype"], 0)
            by_arch_top[r["archetype"]] += 1
    for arch in set(list(by_arch_bottom.keys()) + list(by_arch_top.keys())):
        bp = by_arch_bottom.get(arch, 0) / len(bottom)
        tp = by_arch_top.get(arch, 0) / len(top)
        if bp > tp * 1.2 and bp > 0.25:
            signals.append({"tag": "anti-archetype:%s" % arch, "weight": -1, "n": len(bottom),
                            "note": "%s in %.0f%% bottom vs %.0f%% top" % (arch, bp*100, tp*100)})
    return signals


def _top_subjects(perf, ttl_days=TOP_SUBJECTS_TTL_DAYS, n=TOP_SUBJECTS_N):
    """Top-N distinct named subjects by composite score, wider window than
    the signal decay — feeds the collectors' variant-seeking step (find one
    NEW, different moment about a subject that already proved out)."""
    rows = _collect_rows(perf, ttl_days)
    best = {}
    for r in rows:
        subj = r["subject"]
        if not subj:
            continue
        if subj not in best or r["score"] > best[subj]["score"]:
            best[subj] = r
    ranked = sorted(best.values(), key=lambda r: r["score"], reverse=True)[:n]
    return [{"subject": r["subject"], "archetype": r["archetype"],
             "score": round(r["score"], 3), "posted_at": r["posted_at"],
             "reel": r["name"]} for r in ranked]


def build_lessons(perf):
    """Derive decaying, rule-based CONTENT-ATTRIBUTE signals from recent
    performance. Only entries posted within LESSONS_TTL_DAYS count — that IS
    the decay (old posts age out of the window). Category is intentionally
    NOT a signal dimension (false predictor, retired 2026-08-18)."""
    rows = _collect_rows(perf, LESSONS_TTL_DAYS)

    signals = []
    anti_signals = []
    if rows:
        # ingredient-presence signals (prefer the producer's structured
        # self-assessment; requires it to exist on enough posts)
        for key in INGREDIENT_KEYS:
            signals += _signal(
                rows, lambda r, k=key: bool(r["ingredients"].get(k)),
                "ingredient:%s" % key.replace("_", "-"), key)

        # winning hook structure (concrete named/countable payoff)
        signals += _signal(
            rows, lambda r: r["hook_structure_ok"] is True,
            "hook-structure:concrete-payoff", "concrete-payoff")

        # fallback heuristic when structured fields are absent: >=2 multi-word
        # capitalized (named-entity-like) sequences vs a generic/quote hook
        structured = sum(1 for r in rows if r["ingredients"]
                         or r["hook_structure_ok"] is not None)
        if structured < 3:
            signals += _signal(
                rows,
                lambda r: len(NAMED_ENTITY_RE.findall(r["hook"])) >= 2,
                "specific-named-hook", "specific-hook")

        # story-archetype signals — the "obsess over what worked" layer
        signals += _archetype_signals(rows)

        # Anti-pattern signals from bottom quartile
        anti_signals += _anti_signals(rows)

    return {
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        "window_days": LESSONS_TTL_DAYS,
        "sample_size": len(rows),
        "signals": signals,
        "anti_signals": anti_signals,
        "top_subjects": _top_subjects(perf),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = json.load(open(os.path.expanduser(args.config)))
    token = os.environ.get("IG_TOKEN") or cfg.get("access_token")
    if not token:
        sys.stderr.write("no access_token\n")
        sys.exit(3)

    posted_path = os.path.join(BASE, "reel_posted.json")
    if not os.path.exists(posted_path):
        print("Nothing posted yet — no insights to fetch.")
        sys.exit(2)
    posted = json.load(open(posted_path)).get("posted", [])
    if not posted:
        print("Nothing posted yet — no insights to fetch.")
        sys.exit(2)

    perf_path = os.path.join(BASE, "performance.json")
    perf = json.load(open(perf_path)) if os.path.exists(perf_path) else {}

    import requests
    updated = 0
    for rec in posted:
        mid = rec.get("ig_media_id")
        if not mid:
            continue
        try:
            r = requests.get(GRAPH_URL + "/%s/insights" % mid,
                             params={"metric": METRICS, "access_token": token},
                             timeout=60)
            data = r.json()
            if "error" in data:
                # some metrics unsupported on some media — retry with core set
                r = requests.get(GRAPH_URL + "/%s/insights" % mid,
                                 params={"metric": "reach,likes,comments",
                                         "access_token": token}, timeout=60)
                data = r.json()
            metrics = {m["name"]: (m.get("values") or [{}])[0].get("value")
                       for m in data.get("data", [])}
            if not metrics:
                sys.stderr.write("  ! %s: no metrics (%s)\n"
                                 % (rec["id"], str(data)[:150]))
                continue
            meta = load_reel_meta(rec["id"])
            entry = perf.get(mid, {})
            entry.update({
                "name": rec["id"], "metrics": metrics,
                "category": rec.get("category", meta["category"]),
                "clip_seconds": clip_seconds(rec["id"]),
                "ingredients": meta["ingredients"],
                "hook_structure_ok": meta["hook_structure_ok"],
                "archetype": meta["archetype"],
                "subject": meta["subject"],
                "posted_at": rec.get("posted_at"),
                "fetched_at": datetime.datetime.now().isoformat(
                    timespec="seconds")})
            perf[mid] = entry  # preserves early_shares if sampler already set it
            updated += 1
        except Exception as e:
            sys.stderr.write("  ! %s: %s\n" % (rec.get("id"), e))

    json.dump(perf, open(perf_path, "w"), indent=2)
    print("performance.json updated: %d/%d reels" % (updated, len(posted)))

    lessons_path = os.path.join(BASE, "performance_lessons.json")
    lessons = build_lessons(perf)
    json.dump(lessons, open(lessons_path, "w"), indent=2)
    print("performance_lessons.json updated: %d signal(s) from %d posts (last %dd)"
          % (len(lessons["signals"]), lessons["sample_size"], lessons["window_days"]))


if __name__ == "__main__":
    main()
