#!/usr/bin/env python3
"""
dashboard.py — local, read+control operating center for the media-pipeline
pipeline. stdlib only (http.server), binds 127.0.0.1 ONLY. Never expose this
beyond localhost without adding real auth first.

Every mutating action shells out to the pipeline's existing canonical
scripts / the `hermes` CLI — this file never reimplements cutting,
rendering, or publishing logic, per the skill's "canonical scripts only"
rule. Every action is appended to dashboard_audit.jsonl.

Usage:
  python3 dashboard.py [--port 8787]
  open http://127.0.0.1:8787
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_static")
AUDIT_LOG = os.path.join(BASE, "dashboard_audit.jsonl")
IG_CONFIG = os.environ.get("IG_CONFIG") or os.path.join(BASE, "ig_config.json")
PROFILE = os.environ.get("MEDIA_PIPELINE_PROFILE", "media-pipeline")


def audit(action, params, result):
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "params": params,
        "result": result,
    }
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def run_cmd(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "returncode": r.returncode,
                "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": f"timeout: {e}"}
    except FileNotFoundError as e:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(e)}


def hermes_cmd(*args, timeout=60):
    return run_cmd(["hermes", "-p", PROFILE] + list(args), timeout=timeout)


def safe_join(root, rel):
    root = os.path.abspath(root)
    p = os.path.abspath(os.path.join(root, rel))
    if not (p == root or p.startswith(root + os.sep)):
        return None
    return p


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------- read APIs

def api_funnel():
    news = load_json(os.path.join(BASE, "news.json"), [])
    counts = {"collected": 0, "scouted": 0, "produced": 0}
    for item in news:
        s = item.get("status")
        if s in counts:
            counts[s] += 1
    posted = load_json(os.path.join(BASE, "reel_posted.json"), {}).get("posted", [])

    days = sorted(glob.glob(os.path.join(BASE, "runs", "*")))[-7:]
    trailing = []
    for d in days:
        date = os.path.basename(d)
        raw = glob.glob(os.path.join(d, "raw_news_*.json"))
        moments = glob.glob(os.path.join(d, "moments_*.json"))
        produced = glob.glob(os.path.join(d, "produced_*.json"))
        trailing.append({
            "date": date,
            "collected": len(raw) > 0,
            "scouted": len(moments),
            "produced": len(produced),
            "honest_zero": len(raw) > 0 and len(moments) == 0,
        })
    return {"status_counts": counts, "published_total": len(posted), "trailing_7d": trailing}


def api_jobs():
    r = hermes_cmd("cron", "list", "--all")
    status = hermes_cmd("cron", "status")
    status_text = status["stdout"] if status["ok"] else status["stderr"]
    return {"cron_list_raw": r["stdout"] if r["ok"] else r["stderr"],
            "gateway_running": "Gateway is running" in status_text,
            "cron_status_raw": status_text}


def api_qc(date):
    if not date:
        dirs = sorted(glob.glob(os.path.join(BASE, "runs", "*")))
        date = os.path.basename(dirs[-1]) if dirs else None
    if not date:
        return {"date": None, "reels": []}
    out = []
    for path in sorted(glob.glob(os.path.join(BASE, "runs", date, "produced_*.json"))):
        rec = load_json(path, {})
        frames = rec.get("qc_frames")
        out.append({
            "file": os.path.basename(path),
            "folder": rec.get("folder"),
            "topic": rec.get("topic"),
            "hook": rec.get("hook"),
            "source": rec.get("source"),
            "qc_frames": frames or [],
            "qc_missing": not frames,
        })
    return {"date": date, "reels": out}


def _read_reel_folder(folder_path):
    name = os.path.basename(folder_path.rstrip("/"))
    reel = load_json(os.path.join(folder_path, "reel.json"), {})
    cap_path = os.path.join(folder_path, "caption.txt")
    caption = open(cap_path).read().strip() if os.path.exists(cap_path) else ""
    has_clip = os.path.exists(os.path.join(folder_path, "clip_01.mp4"))
    has_render = os.path.exists(os.path.join(folder_path, "reel.mp4"))
    return {"name": name, "hook": reel.get("hook"), "clip": reel.get("clip"),
            "caption": caption, "has_clip": has_clip, "has_render": has_render}


def api_queue():
    out = []
    for d in sorted(glob.glob(os.path.join(BASE, "queue", "*"))):
        name = os.path.basename(d.rstrip("/"))
        if not os.path.isdir(d) or name == "dont post":
            continue
        out.append(_read_reel_folder(d))
    return {"queue": out}


def api_posted():
    posted = load_json(os.path.join(BASE, "reel_posted.json"), {}).get("posted", [])
    perf = load_json(os.path.join(BASE, "performance.json"), {})
    out = []
    for p in reversed(posted[-25:]):
        name = p.get("id")
        folder = os.path.join(BASE, "posted", name)
        cap_path = os.path.join(folder, "caption.txt")
        caption = open(cap_path).read().strip() if os.path.exists(cap_path) else ""
        out.append({**p, "caption": caption, "performance": perf.get(name)})
    return {"posted": out}


def api_skipped():
    out = []
    for label, d in (("auto_skipped", "skipped"), ("manual_hold", "queue/dont post")):
        base = os.path.join(BASE, d)
        for item in sorted(glob.glob(os.path.join(base, "*"))):
            if os.path.isdir(item):
                out.append({"bucket": label, "name": os.path.basename(item)})
    return {"skipped": out}


def api_sources():
    channels = {}
    patterns = ("moments_*.json", "produced_*.json")
    for pattern in patterns:
        for path in glob.glob(os.path.join(BASE, "runs", "*", pattern)):
            rec = load_json(path, {})
            if not isinstance(rec, dict):
                continue
            src = rec.get("source") or {}
            ch = src.get("channel")
            if ch:
                channels[ch] = channels.get(ch, 0) + 1
    ranked = sorted(channels.items(), key=lambda kv: -kv[1])
    return {"channels": [{"channel": c, "count": n} for c, n in ranked]}


# -------------------------------------------------------------- action APIs

def find_source_for_folder(name):
    for path in glob.glob(os.path.join(BASE, "runs", "*", "produced_*.json")):
        rec = load_json(path, {})
        if rec.get("folder") == name:
            return rec.get("source")
    return None


def action_publish(params):
    name = params.get("name")
    confirm = params.get("confirm")
    if not name:
        return 400, {"error": "missing name"}
    if confirm != "publish":
        return 400, {"error": "type 'publish' to confirm — this posts to Instagram"}
    r = run_cmd([sys.executable, "scripts/publish_reel.py",
                 "--config", IG_CONFIG, "--pick", name], timeout=180)
    return (200 if r["ok"] else 500), r


def action_skip(params):
    name = params.get("name")
    if not name:
        return 400, {"error": "missing name"}
    src = safe_join(os.path.join(BASE, "queue"), name)
    dst = safe_join(os.path.join(BASE, "skipped"), name)
    if not src or not dst or not os.path.isdir(src):
        return 404, {"error": "queue folder not found"}
    os.makedirs(os.path.join(BASE, "skipped"), exist_ok=True)
    os.rename(src, dst)
    pending = os.path.join(BASE, "pending_reel.json")
    if os.path.exists(pending):
        p = load_json(pending, {})
        if p.get("name") == name:
            os.remove(pending)
    return 200, {"moved": name}


def action_edit(params):
    name = params.get("name")
    hook = params.get("hook")
    caption = params.get("caption")
    if not name:
        return 400, {"error": "missing name"}
    folder = safe_join(os.path.join(BASE, "queue"), name)
    if not folder or not os.path.isdir(folder):
        return 404, {"error": "queue folder not found"}
    reel_path = os.path.join(folder, "reel.json")
    reel = load_json(reel_path, {})
    if hook is not None:
        reel["hook"] = hook
    with open(reel_path, "w") as f:
        json.dump(reel, f, indent=2)
    if caption is not None:
        with open(os.path.join(folder, "caption.txt"), "w") as f:
            f.write(caption)
    r = run_cmd([sys.executable, "scripts/make_reel.py", os.path.join("queue", name)],
                timeout=180)
    return (200 if r["ok"] else 500), r


def action_recut(params):
    name = params.get("name")
    start = params.get("start")
    end = params.get("end")
    if not name or start is None or end is None:
        return 400, {"error": "missing name/start/end"}
    folder = safe_join(os.path.join(BASE, "queue"), name)
    if not folder or not os.path.isdir(folder):
        return 404, {"error": "queue folder not found"}
    source = find_source_for_folder(name)
    if not source or not source.get("video_id"):
        return 404, {"error": "could not find original source video_id for this folder"}
    clip_path = os.path.join(folder, "clip_01.mp4")
    r1 = run_cmd([sys.executable, "scripts/cut_clip.py", source["video_id"],
                  str(start), str(end), os.path.join("queue", name, "clip_01.mp4")],
                 timeout=180)
    if not r1["ok"]:
        return 500, r1
    r2 = run_cmd([sys.executable, "scripts/make_reel.py", os.path.join("queue", name)],
                 timeout=180)
    return (200 if r2["ok"] else 500), {"cut": r1, "render": r2}


def action_cron(sub, params):
    job_id = params.get("job_id")
    if not job_id:
        return 400, {"error": "missing job_id"}
    r = hermes_cmd("cron", sub, job_id)
    if sub == "run" and r["ok"]:
        hermes_cmd("cron", "tick")
    return (200 if r["ok"] else 500), r


def action_gateway(sub, params):
    r = hermes_cmd("gateway", sub)
    return (200 if r["ok"] else 500), r


ACTIONS = {
    "publish": action_publish,
    "skip": action_skip,
    "edit": action_edit,
    "recut": action_recut,
    "pause": lambda p: action_cron("pause", p),
    "resume": lambda p: action_cron("resume", p),
    "run_now": lambda p: action_cron("run", p),
    "gateway_restart": lambda p: action_gateway("restart", p),
    "gateway_install": lambda p: action_gateway("install", p),
}


# ---------------------------------------------------------------- HTTP glue

READ_ROUTES = {
    "/api/funnel": lambda q: api_funnel(),
    "/api/jobs": lambda q: api_jobs(),
    "/api/qc": lambda q: api_qc((q.get("date") or [None])[0]),
    "/api/queue": lambda q: api_queue(),
    "/api/posted": lambda q: api_posted(),
    "/api/skipped": lambda q: api_skipped(),
    "/api/sources": lambda q: api_sources(),
}

CONTENT_TYPES = {".html": "text/html", ".css": "text/css",
                  ".js": "application/javascript", ".json": "application/json",
                  ".mp4": "video/mp4", ".jpg": "image/jpeg", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[dashboard] " + (fmt % args) + "\n")

    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not os.path.isfile(path):
            self._send_json(404, {"error": "not found"})
            return
        ext = os.path.splitext(path)[1]
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        if path in READ_ROUTES:
            try:
                self._send_json(200, READ_ROUTES[path](q))
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        if path.startswith("/media/"):
            # rel is like "queue/<name>/clip_01.mp4" or "posted/<name>/caption.txt"
            rel = urllib.parse.unquote(path[len("/media/"):])
            top = rel.split("/", 1)
            resolved = None
            if len(top) == 2 and top[0] in ("queue", "posted"):
                resolved = safe_join(os.path.join(BASE, top[0]), top[1])
            if not resolved:
                self._send_json(400, {"error": "invalid media path"})
                return
            self._send_file(resolved)
            return

        # static file server
        if path == "/":
            path = "/index.html"
        static_path = safe_join(STATIC_DIR, path.lstrip("/"))
        if static_path and os.path.isfile(static_path):
            self._send_file(static_path)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/action/"):
            self._send_json(404, {"error": "not found"})
            return
        name = path[len("/api/action/"):]
        handler = ACTIONS.get(name)
        if not handler:
            self._send_json(404, {"error": f"unknown action {name}"})
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        try:
            code, result = handler(params)
        except Exception as e:
            code, result = 500, {"error": str(e)}
        audit(name, params, {"code": code, "result": result})
        self._send_json(code, result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"media-pipeline dashboard: http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
