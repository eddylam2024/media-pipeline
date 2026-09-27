#!/usr/bin/env python3
"""
make_reel.py — renders the "screenshotted post" reel format.

  - Header card: circular avatar + account name + verified badge + handle,
    all from brand.json, set in Inter.
  - Hook text below the header, styled as the post caption — white with
    *word* gold emphasis; real color emoji render inline.
  - ONE continuous clip below, full width, native aspect ratio preserved —
    no crop, zoom, or cuts. The clip plays close to as found.
  - Optional CTA line below the clip, only when the clip leaves room above
    Instagram's bottom safe zone.
  - The clip's original audio is baked in. If the clip has no audio stream,
    a silent track is muxed in so the container always has one.

reel.json:
{
  "hook": "The Button That Started *This* Disaster Disappeared 😱",
  "clip": "clip_01.mp4",
  "cta": "optional share prompt"
}
Usage: python3 make_reel.py <post_dir>
Output: <post_dir>/reel.mp4 (1080x1920)
"""
import json, os, re, sys, subprocess, tempfile, shutil

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_INTER = os.path.join(BASE, "fonts", "Inter-Variable.ttf")
BRAND_FILE = os.path.join(BASE, "brand.json")


def load_brand():
    """Account branding for the header card (brand.json at the repo root)."""
    brand = {"name": "Nostalgic Drop", "handle": "@nostalgic.drop",
             "avatar": "assets/avatar_256.png", "verified_badge": True}
    if os.path.exists(BRAND_FILE):
        with open(BRAND_FILE) as f:
            brand.update(json.load(f))
    return brand


BRAND = load_brand()
AVATAR = os.path.join(BASE, BRAND["avatar"])
APPLE_EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160  # one of the few valid Apple Color Emoji bitmap sizes

W, H = 1080, 1920
DARK = (13, 13, 15)
WHITE = (244, 241, 234)
GOLD = (232, 196, 107)
GRAY = (142, 146, 153)
VERIFIED_BLUE = (56, 151, 240)  # matches Instagram's real verified-badge blue
FPS = 30

# Instagram Reels safe zone (added 2026-08-02): the app overlays its own UI
# directly on the video -- username/back-bar at top, caption+audio+action
# buttons at bottom, a vertical like/comment/share/save icon rail on the
# right. Content outside this rectangle can be visually covered on a real
# device even though it looks fine in a raw frame extraction. Conservative
# synthesis of Meta's published guidance (varies slightly by source):
SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT = 250, 480, 60, 120

MARGIN_X = SAFE_LEFT
HEADER_TOP = SAFE_TOP
AVATAR_D = 84
HOOK_MAX_W = W - SAFE_LEFT - SAFE_RIGHT  # right edge stays clear of the icon rail
CLIP_BOTTOM_LIMIT = H - SAFE_BOTTOM

# CTA text (added 2026-08-11): an optional share-prompt line drawn in the
# gap between the clip's actual bottom edge and CLIP_BOTTOM_LIMIT. That gap
# only exists for landscape/square clips that don't fill their full
# available height -- tall portrait clips can leave zero room, in which
# case the CTA is dropped automatically (see build()). Never allowed to
# extend into Instagram's reserved bottom safe zone.
CTA_FONT_SIZE = 48
CTA_TOP_PAD = 18
CTA_LINE_H = CTA_FONT_SIZE + 14
CTA_MIN_AVAIL_H = CTA_LINE_H + 20  # one line + a little breathing room


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kw)
    if r.returncode != 0:
        raise RuntimeError("cmd failed: %s\n%s" % (" ".join(map(str, cmd)), r.stderr[-900:]))
    return r


def probe(path):
    r = run(["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path])
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in d["streams"])
    return float(d["format"]["duration"]), int(v["width"]), int(v["height"]), has_audio


_axis_order = None


def inter(size, weight=400):
    """Bug fixed 2026-08-02: PIL's set_variation_by_axes takes values
    POSITIONALLY matching the font's own declared axis order (from
    get_variation_axes()), NOT a fixed [weight, opsz] order. This font's
    real order is [Optical size, Weight] -- passing [weight, opsz] silently
    wrote 700 into the opsz slot (clamped to 32) and ~20 into the weight
    slot, rendering EXTRA LIGHT instead of bold. Axes are now matched by
    name so this can't silently invert again."""
    global _axis_order
    f = ImageFont.truetype(FONT_INTER, size)
    opsz = min(max(size * 0.14, 14), 32)
    try:
        if _axis_order is None:
            axes = f.get_variation_axes()
            _axis_order = [a["name"] for a in axes]
        values = []
        for name in _axis_order:
            if b"Weight" in name:
                values.append(weight)
            elif b"Optical" in name:
                values.append(opsz)
            else:
                values.append(None)  # filled from axis default below
        if any(v is None for v in values):
            axes = f.get_variation_axes()
            values = [v if v is not None else a["default"] for v, a in zip(values, axes)]
        f.set_variation_by_axes(values)
    except Exception as e:
        sys.stderr.write(f"  ! font weight variation failed: {e}\n")
    return f


EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0001F000-\U0001F0FF]+")


def is_emoji(tok):
    stripped = tok.replace("️", "").replace("‍", "")
    return bool(stripped) and bool(EMOJI_RE.fullmatch(stripped))


_emoji_cache = {}


def emoji_tile(ch, target_px):
    key = (ch, target_px)
    if key in _emoji_cache:
        return _emoji_cache[key]
    try:
        f = ImageFont.truetype(APPLE_EMOJI, EMOJI_STRIKE)
        tmp = Image.new("RGBA", (EMOJI_STRIKE * 2, EMOJI_STRIKE * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        d.text((EMOJI_STRIKE // 2, EMOJI_STRIKE // 2), ch, font=f, embedded_color=True)
        bbox = tmp.getbbox()
        tile = tmp.crop(bbox) if bbox else tmp
        scale = target_px / max(tile.size)
        tile = tile.resize((max(int(tile.width * scale), 1),
                            max(int(tile.height * scale), 1)), Image.LANCZOS)
    except Exception:
        tile = None
    _emoji_cache[key] = tile
    return tile


def tokenize(text):
    return [(t.replace("*", ""), "*" in t) for t in text.split()]


def measure(draw, tok, font, size):
    if is_emoji(tok):
        return size * 1.15
    return draw.textlength(tok + " ", font=font)


def wrap(draw, tokens, font, size, max_w):
    lines, cur, cur_w = [], [], 0.0
    for tok, emph in tokens:
        w = measure(draw, tok, font, size)
        if cur and cur_w + w > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur.append((tok, emph))
        cur_w += w
    if cur:
        lines.append(cur)
    return lines


def draw_line(img, draw, line, font, size, x, y, base_fill, emph_fill):
    cx = x
    for tok, emph in line:
        if is_emoji(tok):
            tile = emoji_tile(tok, int(size * 1.05))
            if tile:
                img.alpha_composite(tile, (int(cx), int(y - size * 0.08)))
                cx += size * 1.15
                continue
        draw.text((cx, y), tok, font=font, fill=emph_fill if emph else base_fill)
        cx += draw.textlength(tok + " ", font=font)


def draw_check_badge(draw, cx, cy, r):
    """The actual verified-badge shape (scalloped/sunburst seal, not a plain
    circle) -- a 12-point rounded rosette filled Instagram-verified-blue with
    a white checkmark, matching the real IG verified-badge silhouette."""
    import math
    n = 12
    pts = []
    for i in range(n * 2):
        ang = math.pi * i / n - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.82
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=VERIFIED_BLUE)
    lw = max(int(r * 0.22), 3)
    check = [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.32),
             (cx + r * 0.45, cy - r * 0.32)]
    draw.line(check, fill=WHITE, width=lw, joint="curve")
    for p in (check[0], check[-1]):
        draw.ellipse([p[0]-lw/2, p[1]-lw/2, p[0]+lw/2, p[1]+lw/2], fill=WHITE)


def render_header_hook(hook, out_png):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # avatar, with a white border ring around it (per Eddy's reference, 2026-08-02)
    ax, ay = MARGIN_X, HEADER_TOP
    BORDER_W = 4
    if os.path.exists(AVATAR):
        av = Image.open(AVATAR).convert("RGBA").resize((AVATAR_D, AVATAR_D), Image.LANCZOS)
        img.alpha_composite(av, (ax, ay))
    else:
        d.ellipse([ax, ay, ax + AVATAR_D, ay + AVATAR_D], fill=(60, 60, 65, 255))
    d.ellipse([ax - BORDER_W // 2, ay - BORDER_W // 2,
              ax + AVATAR_D + BORDER_W // 2, ay + AVATAR_D + BORDER_W // 2],
             outline=WHITE, width=BORDER_W)

    tx = ax + AVATAR_D + 20
    f_name = inter(38, 700)   # ONLY "Nostalgic Drop" is bold, everything else regular
    f_handle = inter(28, 400)
    name = BRAND["name"]
    handle = BRAND["handle"]

    # Center the name+handle block precisely on the avatar's height, using
    # REAL glyph ink metrics (textbbox), not assumed font-size offsets --
    # the same kind of eyeballed-offset bug that caused the earlier bold
    # weight regression. NAME_HANDLE_GAP tightened per Eddy's request
    # 2026-08-02 -- just enough clearance that descenders/ascenders don't touch.
    NAME_HANDLE_GAP = 6
    nb = d.textbbox((0, 0), name, font=f_name)
    hb = d.textbbox((0, 0), handle, font=f_handle)
    name_h, name_top_off = nb[3] - nb[1], nb[1]
    handle_h, handle_top_off = hb[3] - hb[1], hb[1]
    block_h = name_h + NAME_HANDLE_GAP + handle_h
    block_top = ay + (AVATAR_D - block_h) / 2

    name_y = block_top - name_top_off
    d.text((tx, name_y), name, font=f_name, fill=WHITE)
    nw = d.textbbox((tx, name_y), name, font=f_name)[2] - tx
    badge_cy = block_top + name_h / 2  # vertically centered on the name's real ink
    if BRAND["verified_badge"]:
        draw_check_badge(d, tx + nw + 20, badge_cy, 16)

    handle_y = block_top + name_h + NAME_HANDLE_GAP - handle_top_off
    d.text((tx, handle_y), handle, font=f_handle, fill=GRAY)

    # hook — regular weight; bold is reserved exclusively for "Nostalgic Drop"
    hook_y0 = ay + AVATAR_D + 36
    f_hook = inter(50, 400)
    lines = wrap(d, tokenize(hook), f_hook, 50, HOOK_MAX_W)
    line_h = 60
    y = hook_y0
    for ln in lines:
        draw_line(img, d, ln, f_hook, 50, MARGIN_X, y, WHITE, GOLD)
        y += line_h

    img.save(out_png)
    return int(y + 20)  # bottom of the text block, video starts here


def render_cta(cta, out_png, y_top):
    """Draws the optional share-prompt line into its own transparent overlay,
    composited last (on top of the video). Caller is responsible for only
    invoking this when there's actually room -- see build()."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = inter(CTA_FONT_SIZE, 600)
    lines = wrap(d, tokenize(cta), f, CTA_FONT_SIZE, HOOK_MAX_W)
    y = y_top
    for ln in lines:
        draw_line(img, d, ln, f, CTA_FONT_SIZE, MARGIN_X, y, WHITE, GOLD)
        y += CTA_LINE_H
    img.save(out_png)
    return int(y)  # bottom of the CTA text block


def build(post_dir, spec):
    clip_path = os.path.join(post_dir, spec["clip"])
    if not os.path.exists(clip_path):
        raise SystemExit(f"missing clip: {clip_path}")
    dur, cw, ch, has_audio = probe(clip_path)

    tmp = tempfile.mkdtemp(prefix="reel_")
    try:
        overlay_png = os.path.join(tmp, "overlay.png")
        video_y0 = render_header_hook(spec["hook"], overlay_png)
        if video_y0 < SAFE_TOP:
            sys.stderr.write(f"  ! header/hook block bottom ({video_y0}px) is above "
                             f"SAFE_TOP ({SAFE_TOP}px) -- should not happen, check layout\n")

        # fit-to-width, preserve native aspect, no crop/zoom -- but never let
        # the clip's bottom edge cross into the bottom safe-zone violation
        video_h = round(W * ch / cw)
        avail_h = min(H - video_y0 - 40, CLIP_BOTTOM_LIMIT - video_y0)
        if video_h > avail_h:
            video_h = avail_h
            video_w = round(video_h * cw / ch)
        else:
            video_w = W

        clip_bottom = video_y0 + video_h
        if clip_bottom > CLIP_BOTTOM_LIMIT:
            sys.stderr.write(f"  ! clip bottom ({clip_bottom}px) exceeds the safe-zone "
                             f"limit ({CLIP_BOTTOM_LIMIT}px) by {clip_bottom - CLIP_BOTTOM_LIMIT}px "
                             f"-- Instagram's caption/button UI may cover part of the clip\n")
        vx_check = (W - video_w) // 2
        if vx_check < 0 or vx_check + video_w > W:
            sys.stderr.write(f"  ! clip horizontal placement ({vx_check}..{vx_check+video_w}) "
                             f"exceeds canvas width {W}\n")

        bg_png = os.path.join(tmp, "bg.png")
        Image.new("RGB", (W, H), DARK).save(bg_png)

        # CTA (added 2026-08-11): only rendered if there's real room between
        # the clip's actual bottom edge and the safe-zone limit. Silently
        # skipped otherwise -- never allowed to encroach on Instagram's UI.
        cta_overlay_png = None
        cta = (spec.get("cta") or "").strip()
        if cta:
            cta_top = clip_bottom + CTA_TOP_PAD
            avail = CLIP_BOTTOM_LIMIT - cta_top
            if avail >= CTA_MIN_AVAIL_H:
                candidate_png = os.path.join(tmp, "cta.png")
                cta_bottom = render_cta(cta, candidate_png, cta_top)
                if cta_bottom <= CLIP_BOTTOM_LIMIT:
                    cta_overlay_png = candidate_png
                else:
                    sys.stderr.write(f"  ! CTA text wrapped past the safe-zone limit "
                                     f"({cta_bottom}px > {CLIP_BOTTOM_LIMIT}px) -- dropping CTA\n")
            else:
                sys.stderr.write(f"  ! insufficient space below clip for CTA "
                                 f"({avail}px available, need {CTA_MIN_AVAIL_H}px) -- skipping CTA\n")

        vx = (W - video_w) // 2
        inputs = ["-i", clip_path, "-loop", "1", "-i", bg_png, "-loop", "1", "-i", overlay_png]
        if cta_overlay_png:
            inputs += ["-loop", "1", "-i", cta_overlay_png]
            fc = (
                f"[0:v]scale={video_w}:{video_h}[clip];"
                f"[1:v][clip]overlay={vx}:{video_y0}[base1];"
                f"[base1][2:v]overlay=0:0[base2];"
                f"[base2][3:v]overlay=0:0,fps={FPS},format=yuv420p[v]"
            )
            audio_input_idx = "4:a"
        else:
            fc = (
                f"[0:v]scale={video_w}:{video_h}[clip];"
                f"[1:v][clip]overlay={vx}:{video_y0}[base];"
                f"[base][2:v]overlay=0:0,fps={FPS},format=yuv420p[v]"
            )
            audio_input_idx = "3:a"

        out = os.path.join(post_dir, "reel.mp4")
        cmd = ["ffmpeg", "-y"] + inputs
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd += ["-filter_complex", fc, "-map", "[v]",
                "-map", "0:a" if has_audio else audio_input_idx,
                "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-ar", "44100", "-shortest",
                "-movflags", "+faststart", out]
        run(cmd)
        return out, dur
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: make_reel.py <post_dir>\n")
        sys.exit(1)
    post_dir = os.path.abspath(sys.argv[1])
    spec = json.load(open(os.path.join(post_dir, "reel.json")))
    out, dur = build(post_dir, spec)
    print(f"{out}  ({dur:.1f}s, {os.path.getsize(out)//1024} KB) — original clip audio baked in")


if __name__ == "__main__":
    main()
