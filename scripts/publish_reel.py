#!/usr/bin/env python3
"""
publish_reel.py — stage/publish one Nostalgic Drop reel via Meta Graph API.

Contract:
preview mode NEVER publishes; real publishing only happens on Eddy's explicit
approval from the 5pm gate. Uses the same @nostalgic.drop credentials file
(--config ~/media-pipeline/ig_config.json).

Flow (REELS):
  1. Pick next queued folder under queue/ (oldest first) not already posted.
  2. Host reel.mp4 on a public URL (uguu.se; or public_url_base from config).
     reel.mp4 carries the clip's ORIGINAL source audio, baked in by
     make_reel.py (locked 2026-08-02 change — no more silent render + live
     Instagram Audio API pick; Eddy wants the source clip's own sound).
  3. POST /{ig_user_id}/media  media_type=REELS, video_url, caption,
     share_to_feed=false (reels stay in the Reels tab/Explore/audio pages
     but never appear on the main profile grid) — poll status until
     FINISHED (reels transcode can take minutes; poll budget is generous).
  4. POST /{ig_user_id}/media_publish.
  5. Move queue/<name> -> posted/<name>, record in reel_posted.json.

Args:
  --config PATH      (required) ig_config.json with ig_user_id/access_token
  --preview          stage oldest pending reel to pending_reel.json, exit. NO network.
  --dry-run          print what would be posted, NO network.
  --pick NAME        specific queue folder (else oldest)
  --slot NAME        cosmetic log label
  --no-move          publish but don't move the folder
"""
import argparse, json, os, sys, time, datetime, shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v21.0")
GRAPH_URL = "https://graph.facebook.com/%s" % GRAPH_VERSION


def log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def load_config(path):
    cfg = {}
    if path and os.path.exists(path):
        cfg = json.load(open(path))
    cfg["ig_user_id"] = os.environ.get("IG_USER_ID") or cfg.get("ig_user_id")
    cfg["access_token"] = os.environ.get("IG_TOKEN") or cfg.get("access_token")
    return cfg


def load_posted(path):
    if not os.path.exists(path):
        return {}
    try:
        raw = json.load(open(path)).get("posted", [])
    except Exception:
        return {}
    return {r["id"]: r for r in raw if isinstance(r, dict) and r.get("id")}


def save_posted(path, posted, name, media_id, category=None):
    rec = dict(posted.get(name) or {"id": name})
    rec["ig_media_id"] = media_id
    rec["posted_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    if category:
        rec["category"] = category
    posted[name] = rec
    json.dump({"posted": list(posted.values())}, open(path, "w"), indent=2)


def pick_folder(queue_dir, posted, explicit=None):
    if explicit:
        p = os.path.join(queue_dir, explicit)
        return p if os.path.isdir(p) else None
    if not os.path.isdir(queue_dir):
        return None
    folders = sorted(f for f in os.listdir(queue_dir)
                     if os.path.isdir(os.path.join(queue_dir, f)) and f not in posted)
    return os.path.join(queue_dir, folders[0]) if folders else None


def host_on_uguu(filepath):
    import requests
    r = requests.post("https://uguu.se/upload.php",
                      files={"files[]": (os.path.basename(filepath),
                                         open(filepath, "rb"))}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError("uguu upload failed %s: %s" % (r.status_code, r.text[:300]))
    return r.json()["files"][0]["url"]


def public_url(filepath, cfg):
    if cfg.get("public_url_base"):
        return cfg["public_url_base"].rstrip("/") + "/" + os.path.basename(filepath)
    return host_on_uguu(filepath)


def _post(url, data):
    import requests
    r = requests.post(url, data=data, timeout=120)
    if r.status_code != 200:
        raise RuntimeError("POST %s -> %s: %s" % (url, r.status_code, r.text[:500]))
    return r.json()


def _poll(creation_id, token, tries=60, wait=5):
    import requests
    for _ in range(tries):  # reels transcode: budget ~5 min
        time.sleep(wait)
        s = requests.get(GRAPH_URL + "/%s" % creation_id,
                         params={"fields": "status_code", "access_token": token},
                         timeout=60).json()
        code = s.get("status_code")
        if code == "FINISHED":
            return True
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError("Container %s status %s: %s" % (creation_id, code, s))
    raise RuntimeError("Container %s not FINISHED after polling" % creation_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pick", default=None)
    ap.add_argument("--slot", default="auto")
    ap.add_argument("--no-move", action="store_true")
    args = ap.parse_args()

    queue_dir = os.path.join(BASE, "queue")
    posted_dir = os.path.join(BASE, "posted")
    posted_state = os.path.join(BASE, "reel_posted.json")

    posted = load_posted(posted_state)
    folder = pick_folder(queue_dir, posted, args.pick)
    if not folder:
        log("Queue exhausted — nothing pending.")
        sys.exit(2)
    name = os.path.basename(folder.rstrip("/"))
    video = os.path.join(folder, "reel.mp4")
    cap_path = os.path.join(folder, "caption.txt")
    caption = open(cap_path).read().strip() if os.path.exists(cap_path) else ""
    if not os.path.exists(video):
        log("ERROR: no reel.mp4 in %s — render first." % folder)
        sys.exit(5)
    log("Slot=%s | folder=%s | video=%dKB | caption_len=%d"
        % (args.slot, name, os.path.getsize(video) // 1024, len(caption)))

    reel_json = os.path.join(folder, "reel.json")
    category = None
    if os.path.exists(reel_json):
        try:
            category = json.load(open(reel_json)).get("category")
        except Exception:
            category = None

    cfg = load_config(args.config)

    if args.dry_run:
        log("DRY-RUN: would publish reel %s\nCaption:\n%s" % (name, caption))
        log("Audio: clip's own original source audio (baked in, no IG Audio API)")
        print("DRY_RUN_OK name=%s" % name)
        return

    if args.preview:
        pending = {"name": name, "video": os.path.abspath(video),
                   "caption": caption,
                   "audio": "original clip audio (baked in)",
                   "previewed_at": datetime.datetime.now().isoformat(timespec="seconds")}
        pp = os.path.join(BASE, "pending_reel.json")
        json.dump(pending, open(pp, "w"), indent=2)
        log("PREVIEW staged %s -> %s — NOT published. Audio: original clip audio (baked in)."
            % (name, pp))
        print("PREVIEW_OK name=%s" % name)
        return

    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        log("MISSING CREDS in %s (or env IG_USER_ID/IG_TOKEN)." % args.config)
        sys.exit(3)

    try:
        url = public_url(video, cfg)
        log("Hosted video: %s" % url)
        data = {"media_type": "REELS", "video_url": url, "caption": caption,
                "share_to_feed": "false", "access_token": cfg["access_token"]}
        j = _post(GRAPH_URL + "/%s/media" % cfg["ig_user_id"], data)
        cid = j.get("id")
        if not cid:
            raise RuntimeError("No creation_id: %s" % j)
        _poll(cid, cfg["access_token"])
        media_id = _post(GRAPH_URL + "/%s/media_publish" % cfg["ig_user_id"],
                         {"creation_id": cid,
                          "access_token": cfg["access_token"]}).get("id")
    except Exception as e:
        log("POST FAILED: %s" % e)
        sys.exit(4)

    save_posted(posted_state, posted, name, media_id, category=category)
    log("PUBLISHED ig_media_id=%s" % media_id)
    if not args.no_move:
        os.makedirs(posted_dir, exist_ok=True)
        dest = os.path.join(posted_dir, name)
        if os.path.exists(dest):
            dest += "_" + datetime.datetime.now().strftime("%H%M%S")
        shutil.move(folder, dest)
        log("Moved %s -> %s" % (folder, dest))
    pp = os.path.join(BASE, "pending_reel.json")
    if os.path.exists(pp):
        os.remove(pp)
    print("OK posted %s (ig_media_id=%s)" % (name, media_id))


if __name__ == "__main__":
    main()
