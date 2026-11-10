"""Kiểm tra offline: ảnh Đại Dương mới có nền trong suốt + code vẽ giữ tỉ lệ."""
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'public/index.html').read_text(encoding='utf-8')
OCEAN = ROOT / 'public/assets/ocean'


class OceanArtTests(unittest.TestCase):
    def test_new_images_are_transparent_and_small(self):
        for n in ('hai_yeu_co_dai', 'thuy_hau_tu', 'hai_ma', 'long_vuong', 'long_vuong_equipped'):
            p = OCEAN / f'{n}.png'
            im = Image.open(p)
            self.assertEqual(im.mode, 'RGBA', n)
            self.assertEqual(im.getchannel('A').getpixel((0, 0)), 0, n)
            self.assertLessEqual(max(im.size), 800, n)
            self.assertLess(p.stat().st_size, 1_000_000, n)

    def test_boss_drawn_with_aspect_ratio_and_flip_table(self):
        self.assertNotIn('c.drawImage(oceanBossArt,-76,-68,152,136)', HTML)
        self.assertIn('const OCEAN_FLIP=', HTML)
        self.assertIn('if(OCEAN_FLIP[bid])c.scale(-1,1)', HTML)

    def test_long_king_equipped_keeps_aspect(self):
        self.assertIn('Math.min(150*s/LONG_ART.naturalWidth,96*s/LONG_ART.naturalHeight)', HTML)

    def test_service_worker_cache_bumped(self):
        self.assertIn('dino-v17-ocean-art', (ROOT / 'public/sw.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
