#!/usr/bin/env python3
"""
collect_news.py — deterministic news fetcher for the media pipeline.

Fetches Google News RSS queries, Reddit top/day posts, and plain RSS feeds
from ../sources.json, normalizes into one candidate list, dedups by title,
and writes runs/<today>/raw_news_1100.json.

This script does NO judgment — the collector agent reads the raw file and
decides which items have a genuine nostalgia bridge (topic/importance/
audience/angle), writing survivors to news.json. Strict separation keeps
the fetch reproducible and the judgment auditable.

Usage: python3 collect_news.py            (writes today's raw file, prints path + count)
       python3 collect_news.py --stdout   (prints JSON to stdout instead)
"""
import json, os, re, ssl, sys, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ~/media-pipeline
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) media-pipeline-collector/1.0"}
TIMEOUT = 20

# macOS system Python often lacks CA certs — use certifi like gen_image.py does
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX).read()


def parse_rss(xml_bytes, source_label, limit=15):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    # RSS 2.0 <item> or Atom <entry>
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry")
    for it in items[:limit]:
        def _t(tag, ns=""):
            el = it.find(ns + tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = _t("title") or _t("title", "{http://www.w3.org/2005/Atom}")
        link = _t("link") or (
            it.find("{http://www.w3.org/2005/Atom}link").get("href", "")
            if it.find("{http://www.w3.org/2005/Atom}link") is not None else "")
        pub = (_t("pubDate") or _t("published", "{http://www.w3.org/2005/Atom}")
               or _t("updated", "{http://www.w3.org/2005/Atom}"))
        desc = re.sub(r"<[^>]+>", " ", _t("description"))[:400].strip()
        if title:
            out.append({"source": source_label, "title": title, "url": link,
                        "published": pub, "summary": desc})
    return out


def fetch_google_news(query):
    url = ("https://news.google.com/rss/search?q=" +
           urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en")
    try:
        return parse_rss(fetch(url), "gnews:" + query, limit=8)
    except Exception as e:
        sys.stderr.write(f"  ! gnews '{query}': {e}\n")
        return []


def fetch_reddit(sub):
    url = f"https://www.reddit.com/r/{sub}/top/.json?t=day&limit=15"
    out = []
    try:
        data = json.loads(fetch(url))
        for ch in data.get("data", {}).get("children", []):
            d = ch.get("data", {})
            if d.get("stickied") or d.get("over_18"):
                continue
            out.append({
                "source": "reddit:r/" + sub,
                "title": d.get("title", ""),
                "url": "https://www.reddit.com" + d.get("permalink", ""),
                "published": datetime.datetime.utcfromtimestamp(
                    d.get("created_utc", 0)).isoformat() + "Z",
                "summary": (d.get("selftext") or "")[:400],
                "reddit_score": d.get("score", 0),
                "reddit_comments": d.get("num_comments", 0),
            })
    except Exception as e:
        sys.stderr.write(f"  ! reddit r/{sub}: {e}\n")
    return out


def _parse_pub_date(pub_str):
    """Best-effort parse of an RSS pubDate/Atom published string to a UTC datetime."""
    if not pub_str:
        return None
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00")).astimezone(
            datetime.timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _topic_words(title, stop=frozenset({
        "the", "a", "an", "and", "or", "of", "in", "on", "to", "is", "are",
        "was", "were", "for", "with", "at", "by", "from", "new", "gets",
        "announced", "revealed", "official", "officially", "just", "now",
        "how", "why", "what", "its", "your", "this", "that", "here",
        "reveals", "announces", "launch", "launches", "launched"})):
    """Significant lowercase word set for a title, for topic-overlap clustering."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) > 2 and w not in stop}


def add_topic_momentum(items, min_shared_words=2):
    """Non-Reddit velocity proxy: cross-source topic momentum.

    (added 2026-09-08 -- user wanted "velocity weighting" for viral signal,
    but Reddit's Responsible Builder Policy requires written approval for
    commercial use of Reddit API data, which this pipeline is, so we don't
    have a live Reddit engagement feed. Real velocity (rate of engagement
    growth) isn't available from Google News/RSS since they carry no
    score/vote data -- but we CAN measure how many independent sources are
    covering the same topic and how recently, which is a legitimate proxy
    for "this is heating up right now" using only data we already
    legitimately pull.

    Clustering: two items are the same topic if their significant-word sets
    share >= min_shared_words words (union-find over pairwise overlap --
    titles are phrased too differently for exact-match keys, e.g. "GTA 6
    Digital Launch..." vs "Is GTA 6 Too Realistic..." only share {"gta","6"}
    but that's enough to know it's the same story).

    `topic_mentions` = distinct sources (gnews query / rss feed / reddit
    sub) covering the same cluster. `topic_age_hours` = age of the freshest
    mention. `topic_momentum` = mentions / (age_hours + 1) -- more
    independent sources, more recently, ranks higher. A single evergreen
    post scores near zero; a topic hit by several sources in the last few
    hours scores high.
    """
    n = len(items)
    word_sets = [_topic_words(it["title"]) for it in items]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # bucket by word -> item indices, only compare within buckets (avoids
    # full O(n^2) title comparison while still catching shared-word pairs)
    word_to_items = {}
    for i, ws in enumerate(word_sets):
        for w in ws:
            word_to_items.setdefault(w, []).append(i)
    for w, idxs in word_to_items.items():
        if len(idxs) < 2 or len(idxs) > 40:  # skip near-universal words
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if len(word_sets[i] & word_sets[j]) >= min_shared_words:
                    union(i, j)

    now = datetime.datetime.utcnow()
    clusters = {}
    for i, it in enumerate(items):
        root = find(i)
        dt = _parse_pub_date(it.get("published"))
        c = clusters.setdefault(root, {"sources": set(), "newest": None})
        c["sources"].add(it["source"])
        if dt and (c["newest"] is None or dt > c["newest"]):
            c["newest"] = dt

    for i, it in enumerate(items):
        c = clusters[find(i)]
        mentions = len(c["sources"])
        age_hours = ((now - c["newest"]).total_seconds() / 3600.0
                     if c["newest"] else 48.0)
        age_hours = max(age_hours, 0.1)
        it["topic_mentions"] = mentions
        it["topic_age_hours"] = round(age_hours, 1)
        it["topic_momentum"] = round(mentions / (age_hours + 1), 3)
    return items


def main():
    cfg = json.load(open(os.path.join(BASE, "sources.json")))
    items = []
    for q in cfg.get("google_news_queries", []):
        items += fetch_google_news(q)
    for sub in cfg.get("reddit_subreddits", []):
        items += fetch_reddit(sub)
    for feed in cfg.get("rss_feeds", []):
        try:
            items += parse_rss(fetch(feed), "rss:" + feed.split("/")[2], limit=10)
        except Exception as e:
            sys.stderr.write(f"  ! rss {feed}: {e}\n")

    # dedup by normalized title
    seen, deduped = set(), []
    for it in items:
        key = re.sub(r"\W+", " ", it["title"].lower()).strip()[:80]
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)

    # Topic momentum: cluster items across ALL sources (gnews/rss/reddit) by
    # loose topic signature and rank by cross-source recency+coverage — see
    # add_topic_momentum() docstring for why this replaces true Reddit
    # engagement-velocity (Responsible Builder Policy blocks that path for
    # commercial use without written approval).
    deduped = add_topic_momentum(deduped)
    deduped.sort(key=lambda it: it.get("topic_momentum", 0.0), reverse=True)

    payload = {
        "fetched_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(deduped),
        "items": deduped,
    }
    if "--stdout" in sys.argv:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        return
    today = str(datetime.date.today())
    run_dir = os.path.join(BASE, "runs", today)
    os.makedirs(run_dir, exist_ok=True)
    out = os.path.join(run_dir, "raw_news_1100.json")
    json.dump(payload, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"{out}  ({len(deduped)} candidates from {len(items)} raw)")


if __name__ == "__main__":
    main()
