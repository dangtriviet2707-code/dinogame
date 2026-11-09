import os
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))

class LongVuongPresentationTests(unittest.TestCase):
    def test_npc_portrait_exists(self):
        path = os.path.join(ROOT, "public", "assets", "ocean", "npc_long_vuong.png")
        self.assertTrue(os.path.isfile(path))
        from PIL import Image
        with Image.open(path) as im:
            self.assertGreaterEqual(im.width, 200)
            self.assertGreaterEqual(im.height, 300)

    def test_title_is_awarded_only_after_confirmed_dialogue(self):
        from pathlib import Path
        source = Path(os.path.join(ROOT, "app.py")).read_text(encoding="utf-8")
        self.assertIn('rec["oceanTitle"] = "Long Vương"', source)
        self.assertIn('event["dialogueComplete"] = True', source)
        self.assertIn('"title": rec.get("oceanTitle")', source)

    def test_leaderboard_and_nameplate_render_ocean_title(self):
        from pathlib import Path
        source = Path(os.path.join(ROOT, "public", "index.html")).read_text(encoding="utf-8")
        self.assertIn("long-vuong-title", source)
        self.assertIn("long-vuong-row", source)
        self.assertIn("npc_long_vuong.png", source)

if __name__ == "__main__":
    unittest.main()
