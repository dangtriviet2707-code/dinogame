"""Offline, dependency-free checks for the v1.7.11 Nộ Hải combo wiring."""
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / 'public/index.html').read_text(encoding='utf-8')


class NoHaiComboTests(unittest.TestCase):
    def test_three_stage_effects_exist(self):
        for kind in ("k:'nhTsunami'", "k:'nhStorm'", "k:'nhBolt'", "k:'nhHand'"):
            self.assertIn(kind, HTML)
        self.assertIn("e.k==='nhTsunami'", HTML)
        self.assertIn("e.k==='nhBolt'", HTML)
        self.assertIn("e.k==='nhHand'", HTML)
        self.assertIn('function drawGhostHand(', HTML)

    def test_seven_lightning_strikes(self):
        self.assertIn('boltCount:7', HTML)

    def test_total_damage_formula_unchanged(self):
        self.assertIn('650+(me.level||1)*28', HTML)
        self.assertIn('dCrush:damage-dWave-dBolt*NH.boltCount', HTML)

    def test_cooldown_unchanged(self):
        self.assertIn('oceanUltimateCd=600', HTML)

    def test_legacy_hooks_kept(self):
        self.assertIn('oceanStrike.delay<=0', HTML)
        self.assertIn("k:'lvSkill'", HTML)
        self.assertIn("k:'lvImpact'", HTML)


if __name__ == '__main__':
    unittest.main()
