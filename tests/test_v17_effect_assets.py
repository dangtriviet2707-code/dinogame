"""Offline, dependency-free checks for v1.7 effect assets and wiring."""
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def png_size(path):
    with path.open('rb') as f:
        header = f.read(24)
    if header[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError(f'Not a PNG: {path}')
    return struct.unpack('>II', header[16:24])


class LongVuongV17AssetTests(unittest.TestCase):
    def test_atlas_matches_metadata(self):
        meta = json.loads((ROOT / 'public/assets/effects/long_vuong_atlas.json').read_text(encoding='utf-8'))
        width, height = png_size(ROOT / 'public/assets/effects/long_vuong_atlas.png')
        self.assertEqual(width, meta['cellWidth'] * meta['columns'])
        self.assertEqual(height, meta['cellHeight'] * meta['rows'])
        self.assertEqual(len(meta['effects']), 10)
        self.assertEqual(sorted(meta['effects'].values()), list(range(10)))

    def test_dragon_art_is_transparent_png(self):
        path = ROOT / 'public/assets/effects/long_vuong_dragon.png'
        self.assertGreater(png_size(path)[0], 500)
        with path.open('rb') as f:
            f.seek(25)
            color_type = f.read(1)[0]
        self.assertIn(color_type, (4, 6), 'Dragon art must retain an alpha channel')

    def test_gameplay_references_effect_assets_and_impact(self):
        html = (ROOT / 'public/index.html').read_text(encoding='utf-8')
        self.assertIn('/assets/effects/long_vuong_atlas.png', html)
        self.assertIn('/assets/effects/long_vuong_dragon.png', html)
        self.assertIn("k:'lvSkill'", html)
        self.assertIn("k:'lvImpact'", html)
        self.assertIn('oceanStrike.delay<=0', html)

    def test_service_worker_cache_bumped(self):
        sw = (ROOT / 'public/sw.js').read_text(encoding='utf-8')
        self.assertIn('dino-v17-ocean-boss-fx-dialogue-fast', sw)

    def test_five_ocean_stage_backgrounds_exist_and_are_distinct(self):
        from PIL import Image
        html = (ROOT / 'public/index.html').read_text(encoding='utf-8')
        self.assertIn("stage_${Math.max(1,Math.min(5,stage))}.webp", html)
        hashes = set()
        for i in range(1, 6):
            path = ROOT / f'public/assets/ocean/stage_{i}.webp'
            self.assertTrue(path.is_file(), f'Missing stage background: {path.name}')
            with Image.open(path) as im:
                self.assertEqual(im.format, 'WEBP')
                self.assertGreaterEqual(im.width, 800)
                self.assertGreaterEqual(im.height, 800)
                hashes.add(__import__('hashlib').sha256(path.read_bytes()).hexdigest())
        self.assertEqual(len(hashes), 5, 'Each event stage must use its own background')

    def test_four_long_king_gear_assets_are_individual_and_catalogued(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        html = (ROOT / 'public/index.html').read_text(encoding='utf-8')
        for item in ('helm', 'armor', 'pants', 'boots'):
            path = ROOT / f'public/assets/ocean/long_king_{item}.svg'
            self.assertTrue(path.is_file())
            svg = path.read_text(encoding='utf-8')
            self.assertIn('<svg', svg)
            self.assertIn(f'long_king_{item}', app)
            self.assertIn(f'/assets/ocean/long_king_{item}.svg', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
