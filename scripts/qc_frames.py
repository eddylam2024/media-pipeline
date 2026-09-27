#!/usr/bin/env python3
"""Producer clean-frame + content-relevance QC driver.
For a cut clip, samples frames across the WHOLE clip (~every 4s), extracts
each, vision-checks it via local Ollama (gemma3:4b), and prints each frame's
raw vision output so the producer can read real evidence and set pass/fail.
't' = seconds into the SOURCE video (start <= t <= end).

Usage: python3 qc_frames.py <clip> <start> <end> <slug>
Emits a JSON array on stdout (and per-frame lines on stderr for live reading).
Frame JPEGs saved under runs/<date>/qc/<slug>/ as evidence.

This is the producer's mandated vision step. qc_gate.py only validates the
manifest this driver's output feeds; it never re-implements cut/render/publish.
"""
import os, sys, json, math, subprocess, datetime, time, base64
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA = "http://127.0.0.1:11434/api/generate"

VISION_PROMPT = (
    "QC gate for a nostalgia reel — one frame only. (1) TEXT: is there any "
    "burned-in text, subtitles, watermark, channel logo, or lower-third/overlay "
    "on this frame? Answer none or name it. (2) VISUAL: one sentence describing "
    "what is visibly happening (subject/setting/action/native HUD vs foreign "
    "overlay). (3) VERDICT: pass only if it shows real footage of the clip's "
    "subject with no burned-in text/watermark/logo, else fail. Reply on one line "
    "as: TEXT:<...> | VISUAL:<...> | VERDICT:<pass|fail>"
)

def ollama_vision(img_path, timeout=200):
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {"model": "gemma3:4b", "prompt": VISION_PROMPT,
               "images": [b64], "stream": False}
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode()).get("response", "").strip()
        except Exception as e:
            sys.stderr.write(f"    vision retry {attempt+1}/3: {e}\n"); time.sleep(3)
    return "VISION_ERROR"

def extract_frame(clip, offset, out):
    cmd = ["ffmpeg", "-y", "-ss", f"{offset:.3f}", "-i", clip,
           "-frames:v", "1", "-q:v", "2", out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000

def luminance(img):
    try:
        from PIL import Image, ImageStat
        st = ImageStat.Stat(Image.open(img).convert("L"))
        return st.mean[0], st.stddev[0]
    except Exception:
        return None, None

def main():
    if len(sys.argv) != 5:
        sys.stderr.write("usage: qc_frames.py <clip> <start> <end> <slug>\n")
        sys.exit(2)
    clip, start, end, slug = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    dur = end - start
    today = datetime.date.today().isoformat()
    qcdir = os.path.join(BASE, "runs", today, "qc", slug)
    os.makedirs(qcdir, exist_ok=True)
    n = max(1, math.ceil(dur / 4.0))
    offsets = [i * (dur / n) for i in range(n)]
    offsets[-1] = min(offsets[-1], dur - 0.1)
    results = []
    for i, off in enumerate(offsets):
        t = round(start + off, 2)
        jpg = os.path.join(qcdir, f"frame_{i:02d}_t{t}.jpg")
        line = ""
        if not extract_frame(clip, off, jpg):
            line = "FRAME t=%.1f TEXT:unknown | VISUAL:frame extraction failed | VERDICT:fail" % t
            results.append({"t": t, "description": "frame extraction failed",
                            "verdict": "fail", "frame": os.path.relpath(jpg, BASE)})
            sys.stderr.write(f"  t={t} EXTRACTION_FAILED\n"); print(line); continue
        mean, std = luminance(jpg)
        blank = mean is not None and std is not None and std < 3.0 and 10 < mean < 245
        if blank:
            line = "FRAME t=%.1f TEXT:none | VISUAL:solid/blank frame (mean=%.0f, std=%.1f) | VERDICT:fail" % (t, mean, std)
            results.append({"t": t, "description": "solid/blank frame (low luminance variance)",
                            "verdict": "fail", "frame": os.path.relpath(jpg, BASE)})
            sys.stderr.write(f"  t={t} BLANK\n"); print(line); continue
        out = ollama_vision(jpg)
        desc = out.replace("\n", " ").strip()[:260]
        sys.stderr.write(f"  t={t} vision_done\n")
        print(f"FRAME t={t} | {out}")
        results.append({"t": t, "description": desc, "frame": os.path.relpath(jpg, BASE)})
    print("===QC_JSON_BEGIN===")
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
