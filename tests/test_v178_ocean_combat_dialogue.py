"""Dependency-free regression checks for Long Vuong combat FX and dialogue responsiveness."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OceanCombatDialogueV178Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        cls.sw = (ROOT / "public/sw.js").read_text(encoding="utf-8")

    def test_each_ocean_boss_stage_has_cast_effect_hook(self):
        self.assertIn("oceanStage:oceanCoreRun.stage", self.html)
        self.assertIn("k:'oceanCast',stage:oceanCoreRun.stage", self.html)
        self.assertIn("e.k==='oceanCast'", self.html)

    def test_boss_and_player_hits_have_dedicated_effects(self):
        self.assertIn("k:'oceanBossHit'", self.html)
        self.assertIn("k:'oceanPlayerHit'", self.html)
        self.assertIn("e.k==='oceanBossHit'||e.k==='oceanPlayerHit'", self.html)

    def test_dialogue_next_is_locked_and_uses_returned_next_line(self):
        self.assertIn("let oceanDialogueBusy=false,oceanDialogueRequest=0", self.html)
        self.assertIn("if(oceanDialogueBusy)return", self.html)
        self.assertIn("button.textContent='Đang tiếp tục…'", self.html)
        self.assertIn("else if(n.line)paintOceanDialogue(n.line,n.step,n.total)", self.html)

    def test_service_worker_cache_was_bumped(self):
        self.assertIn("dino-v17-ocean-boss-fx-dialogue-fast", self.sw)


if __name__ == "__main__":
    unittest.main()
