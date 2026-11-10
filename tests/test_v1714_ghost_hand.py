"""Offline checks for the v1.7.14 redrawn ghost hand (visual only, no gameplay change)."""
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / 'public/index.html').read_text(encoding='utf-8')


class GhostHandTests(unittest.TestCase):
    def test_new_hand_helpers_exist(self):
        for name in ('function ghostLimbPath(', 'function ghostPalmPath(', 'function ghostClaw(', 'function drawGhostHand('):
            self.assertIn(name, HTML)

    def test_hand_receives_time_for_animation(self):
        self.assertIn('drawGhostHand(hx,cy,sc,curl,al,a)', HTML)

    def test_gameplay_numbers_unchanged(self):
        self.assertIn('handFx:86,crushAt:58', HTML)
        self.assertIn('650+(me.level||1)*28', HTML)


if __name__ == '__main__':
    unittest.main()
