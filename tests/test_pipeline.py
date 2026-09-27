"""Tests for the QC gate, the overlay (watermark) check, and the feedback-loop
signal math. Run from the repo root:  python3 -m unittest discover tests
Overlay tests need ffmpeg and tesseract and are skipped without them."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)

import fetch_insights  # noqa: E402
import overlay_check  # noqa: E402

HAVE_MEDIA_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("tesseract"))
FONT = os.path.join(REPO, "fonts", "Inter-Variable.ttf")


def make_clip(path, watermark=None, static=False):
    """A 6s synthetic clip: moving fractal zoom (or a still frame), with an
    optional fixed text overlay in the bottom-left corner. The overlay is
    drawn with PIL so this works on ffmpeg builds without drawtext."""
    source = "color=c=gray:size=1280x720:rate=30" if static else "mandelbrot=size=1280x720:rate=30"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source]
    if watermark:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(FONT, 44)
        font.set_variation_by_axes([700, 20])
        tag = Image.new("RGBA", (460, 70), (0, 0, 0, 160))
        ImageDraw.Draw(tag).text((14, 6), watermark, font=font, fill="white")
        png = path + ".tag.png"
        tag.save(png)
        cmd += ["-i", png, "-filter_complex", "[0][1]overlay=30:H-100"]
    cmd += ["-t", "6", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True)


@unittest.skipUnless(HAVE_MEDIA_TOOLS, "needs ffmpeg and tesseract")
class OverlayCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_clean_moving_clip_passes(self):
        clip = os.path.join(self.tmp, "clean.mp4")
        make_clip(clip)
        self.assertEqual(overlay_check.check(clip)["status"], "clean")

    def test_url_watermark_is_flagged(self):
        clip = os.path.join(self.tmp, "wm.mp4")
        make_clip(clip, watermark="RETROCLIPS.COM")
        result = overlay_check.check(clip)
        self.assertEqual(result["status"], "flagged")
        self.assertEqual(result["findings"][0]["corner"], "bottom-left")

    def test_static_shot_is_inconclusive(self):
        clip = os.path.join(self.tmp, "still.mp4")
        make_clip(clip, static=True)
        self.assertEqual(overlay_check.check(clip)["status"], "inconclusive")

    def test_hud_words_are_allowed(self):
        self.assertEqual(overlay_check._overlay_words([("SCORE", 95), ("LEVEL", 92)]), [])
        self.assertEqual(overlay_check._overlay_words([("Recorded", 91)]), ["Recorded"])
        self.assertEqual(overlay_check._overlay_words([("Recorded", 40)]), [])


class QcGateTest(unittest.TestCase):
    """Runs qc_gate.py as the producer would, in a throwaway repo layout."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        shutil.copytree(SCRIPTS, os.path.join(self.base, "scripts"))
        os.makedirs(os.path.join(self.base, "queue", "r1"))
        self.clip = os.path.join(self.base, "queue", "r1", "clip_01.mp4")

    def tearDown(self):
        shutil.rmtree(self.base)

    def gate(self, **overrides):
        manifest = {"folder": "r1", "source": {"start": 10.0, "end": 22.0},
                    "qc_frames": [{"t": 10.0 + 4 * i, "description": "clean frame",
                                   "verdict": "pass"} for i in range(3)]}
        manifest.update(overrides)
        path = os.path.join(self.base, "produced.json")
        with open(path, "w") as f:
            json.dump(manifest, f)
        return subprocess.run([sys.executable, os.path.join(self.base, "scripts", "qc_gate.py"), path],
                              capture_output=True, text=True)

    def test_missing_evidence_fails(self):
        self.assertEqual(self.gate(qc_frames=[]).returncode, 1)

    def test_sparse_evidence_fails(self):
        r = self.gate(qc_frames=[{"t": 10.0, "description": "x", "verdict": "pass"}])
        self.assertEqual(r.returncode, 1)

    def test_failed_frame_fails(self):
        frames = [{"t": 10.0 + 4 * i, "description": "logo in corner", "verdict": "fail"} for i in range(3)]
        self.assertEqual(self.gate(qc_frames=frames).returncode, 1)

    @unittest.skipUnless(HAVE_MEDIA_TOOLS, "needs ffmpeg and tesseract")
    def test_clean_clip_passes(self):
        make_clip(self.clip)
        r = self.gate()
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(HAVE_MEDIA_TOOLS, "needs ffmpeg and tesseract")
    def test_watermark_fails_despite_clean_report(self):
        make_clip(self.clip, watermark="RETROCLIPS.COM")
        r = self.gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("watermark", r.stderr)

    @unittest.skipUnless(HAVE_MEDIA_TOOLS, "needs ffmpeg and tesseract")
    def test_override_needs_a_real_reason(self):
        make_clip(self.clip, watermark="RETROCLIPS.COM")
        self.assertEqual(self.gate(overlay_override={"reason": "ok"}).returncode, 1)
        r = self.gate(overlay_override={"reason": "shop sign physically present in the scene"})
        self.assertEqual(r.returncode, 0, r.stderr)


class SignalTest(unittest.TestCase):
    def row(self, score, ritual=True, arch="a"):
        return {"score": score, "ingredients": {"emotional_charge": True, "causal_chain": True,
                                                "personal_ritual": ritual},
                "hook_structure_ok": True, "archetype": arch, "hook": "", "subject": ""}

    def test_small_but_consistent_gap_emits_signal(self):
        # every score is within 20% of every other, which the old ratio
        # threshold could never flag; the gap is still > 0.5 sd
        rows = [self.row(s, ritual=True) for s in (0.46, 0.47, 0.45, 0.46)] + \
               [self.row(s, ritual=False) for s in (0.40, 0.41, 0.39, 0.40)]
        sig = fetch_insights._signal(rows, lambda r: r["ingredients"]["personal_ritual"],
                                     "ingredient:personal-ritual", "personal_ritual")
        self.assertEqual(len(sig), 1)
        self.assertEqual(sig[0]["weight"], 1)

    def test_no_difference_emits_nothing(self):
        rows = [self.row(0.43, ritual=i % 2 == 0) for i in range(8)]
        sig = fetch_insights._signal(rows, lambda r: r["ingredients"]["personal_ritual"], "t", "t")
        self.assertEqual(sig, [])

    def test_diagnostics_flag_saturated_self_assessment(self):
        rows = [self.row(0.4 + i / 100, arch=f"arch-{i}") for i in range(6)]
        notes = " ".join(fetch_insights._diagnostics(rows))
        self.assertIn("emotional_charge", notes)
        self.assertIn("hook_structure_ok", notes)
        self.assertIn("fragmented", notes)
        self.assertIn("compressed", notes)


if __name__ == "__main__":
    unittest.main()
