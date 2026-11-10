"""Tách nền đen + thu nhỏ ảnh Đại Dương mới (RGB nền đen -> RGBA trong suốt).

Chạy: python tools/process_ocean_art.py
Chỉ xử lý ảnh còn là RGB (chưa có alpha); chạy lại nhiều lần vẫn an toàn.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

OCEAN = Path(__file__).resolve().parents[1] / 'public/assets/ocean'
# tên file -> chiều cao tối đa (px) sau khi thu nhỏ
TARGETS = {'hai_yeu_co_dai': 520, 'thuy_hau_tu': 520, 'hai_ma': 520,
           'long_vuong': 520, 'long_vuong_equipped': 560}
DARK = 22          # kênh sáng nhất <= DARK coi là nền đen
MIN_BG = 600       # vùng đen liền nhau nhỏ hơn mức này (px) coi là chi tiết, giữ lại


def key_black(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    mx = a.max(axis=2)
    dark = mx <= DARK
    lab, n = ndi.label(dark)
    sizes = ndi.sum(dark, lab, index=np.arange(1, n + 1))
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    bg = np.zeros_like(dark)
    for i, s in enumerate(sizes, start=1):
        if i in border or s >= MIN_BG:
            bg |= lab == i
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # viền mềm: làm mờ nhẹ rồi co 1px để không còn quầng đen quanh nét vẽ
    al = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    out = im.convert('RGBA')
    out.putalpha(al)
    return out


def crop_resize(im: Image.Image, max_h: int) -> Image.Image:
    box = im.getchannel('A').point(lambda v: 255 if v > 12 else 0).getbbox()
    if box:
        im = im.crop(box)
    if im.height > max_h:
        im = im.resize((round(im.width * max_h / im.height), max_h), Image.LANCZOS)
    return im


def main():
    for name, max_h in TARGETS.items():
        p = OCEAN / f'{name}.png'
        im = Image.open(p)
        if im.mode == 'RGBA' and im.getchannel('A').getextrema()[0] < 255:
            print('bỏ qua (đã có nền trong suốt):', name)
            continue
        out = crop_resize(key_black(im), max_h)
        out.save(p, optimize=True)
        print(f'{name}: {im.size} -> {out.size}, {p.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
