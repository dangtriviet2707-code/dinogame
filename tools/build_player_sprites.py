"""Dựng sprite người chơi (mặc định + bộ độc tôn) và rồng bay độc tôn từ ảnh trong assets_src/.
Chạy: python3 tools/build_player_sprites.py   (cần numpy, opencv-python, scipy)
Chỉ cập nhật mục `player`, `player_vip` trong sprites.json; các nhân vật khác giữ nguyên."""
import os, sys, json
import cv2, numpy as np
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(__file__))
import build_sprites as B

SRC = os.path.join(B.ROOT, "assets_src")
OUT = B.OUT


def grab(path, rect, fgpoly, scale=.5, open_it=5, clean=None):
    im = cv2.imread(path); h, w = im.shape[:2]
    s = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    m = np.full(s.shape[:2], cv2.GC_BGD, np.uint8)
    x0, y0, x1, y1 = [int(v * scale) for v in rect]; m[y0:y1, x0:x1] = cv2.GC_PR_BGD
    inner = np.zeros(s.shape[:2], np.uint8); cv2.fillPoly(inner, [(np.array(fgpoly) * scale).astype(np.int32)], 1)
    ring = cv2.dilate(inner, np.ones((int(60 * scale),) * 2, np.uint8))
    m[(ring == 1) & (inner == 0)] = cv2.GC_PR_FGD; m[inner == 1] = cv2.GC_FGD
    cv2.grabCut(s, m, None, np.zeros((1, 65)), np.zeros((1, 65)), 6, cv2.GC_INIT_WITH_MASK)
    fg = ((m == 1) | (m == 3)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((open_it,) * 2, np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg); fg = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    fg = ndi.binary_fill_holes(fg).astype(np.float32)
    fg = cv2.resize(fg, (w, h), interpolation=cv2.INTER_LINEAR)
    if clean is not None: fg = clean(im, fg)
    fg = cv2.GaussianBlur(fg, (0, 0), 2.2); fg = np.clip((fg - .35) / .3, 0, 1)
    rgba = np.dstack([im, (fg * 255).astype(np.uint8)])
    ys, xs = np.where(rgba[..., 3] > 10)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def clean_default(im, fg):  # bỏ mảng nền xanh xám còn sót giữa hai chân / bên hông
    b, g, r = [im[..., i].astype(int) for i in range(3)]
    bg = (b > r + 8) & (b > g) & (np.maximum(np.maximum(r, g), b) > 48)
    fg = fg * (~bg); fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats((fg > .5).astype(np.uint8))
    return (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.float32)


def clean_vip(im, fg):  # bỏ nền hồng cạnh đầu và phần phản chiếu dưới chân
    h, w = fg.shape; b, g, r = [im[..., i].astype(int) for i in range(3)]
    pale = (r > 190) & (g > 120) & (b > 110)
    reg = np.zeros_like(fg, bool); reg[:int(h * .4), int(w * .62):] = True
    fg = fg * ~(pale & reg); fg[int(h * .93):] = 0; fg[int(h * .835):, int(w * .425):int(w * .57)] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats((fg > .5).astype(np.uint8))
    return (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.float32)


def make_sheet(cid, name, rgba, fwd, color):
    cv2.imwrite(os.path.join(OUT, f"{cid}.png"), rgba)
    base = B.to_cell(rgba); pm = B.premult(base)
    sheet = np.zeros((B.CELL * len(B.ANIMS), B.CELL * B.N, 4), np.uint8)
    for r, an in enumerate(B.ANIMS):
        for i, kf in enumerate(B.anim_keys(an, False)):
            sheet[r * B.CELL:(r + 1) * B.CELL, i * B.CELL:(i + 1) * B.CELL] = B.unpremult(B.render(pm, kf, fwd, color))
    cv2.imwrite(os.path.join(OUT, f"{cid}_sheet.png"), sheet, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    ys, xs = np.where(base[..., 3] > 20)
    return {"name": name, "sheet": f"/assets/characters/{cid}_sheet.png", "portrait": f"/assets/characters/{cid}.png",
            "fwd": fwd, "color": "#%02x%02x%02x" % color,
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)], "foot": B.FOOT_Y}


def make_dragon():
    im = cv2.imread(os.path.join(SRC, "dragon_vip.png")); mx = im.max(2)
    bg = (mx < 24).astype(np.uint8); n, lab, _, _ = cv2.connectedComponentsWithStats(bg)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgm = np.isin(lab, list(border))
    a = np.clip((mx.astype(np.float32) - 12) / 40, 0, 1) * (~bgm) + (~bgm) * (mx >= 24)
    a = np.clip(a, 0, 1); a = cv2.GaussianBlur(a, (0, 0), 1.0)
    rgba = np.dstack([im, (a * 255).astype(np.uint8)])
    ys, xs = np.where(rgba[..., 3] > 10); rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = 512 / rgba.shape[1]; rgba = cv2.resize(rgba, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, "dragon_vip.png"), rgba); print("dragon", rgba.shape)


def main():
    pd = grab(os.path.join(SRC, "player_default.png"), (330, 60, 860, 1240),
              [(540, 200), (700, 200), (780, 520), (790, 640), (740, 900), (650, 1090), (600, 1100), (500, 1100), (470, 800), (440, 560), (520, 420)], clean=clean_default)
    pv = grab(os.path.join(SRC, "player_vip.png"), (20, 100, 1254, 1190),
              [(560, 170), (720, 170), (770, 420), (780, 640), (760, 900), (700, 1100), (450, 1100), (430, 800), (470, 520), (520, 330)], open_it=7, clean=clean_vip)
    mp = os.path.join(OUT, "sprites.json"); man = json.load(open(mp, encoding="utf-8"))
    man["characters"]["player"] = make_sheet("player", "Người Chơi", pd, +1, (255, 140, 40))
    man["characters"]["player_vip"] = make_sheet("player_vip", "Người Chơi Độc Tôn", pv, +1, (255, 200, 60))
    json.dump(man, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    make_dragon(); print("xong")

if __name__ == "__main__":
    main()
