#!/usr/bin/env python3
"""
Dựng bộ tài nguyên nhân vật từ ảnh tham chiếu (assets_src/reference.jpg).

Với mỗi nhân vật trong 9 nhân vật:
  1. Cắt riêng chân dung lớn từ ảnh tổng hợp và tách nền đen -> PNG nền trong suốt.
  2. Chuẩn hóa về một khung 192x192 (neo chân ở giữa-đáy, cùng quy tắc tỉ lệ).
  3. Tạo 6 animation (idle, walk, attack, skill, hurt, die) x 6 frame, mỗi frame
     là một ảnh PNG riêng, rồi ghép thành sprite sheet 1152x1152 (hàng = animation).
  4. Ghi sprites.json (manifest) cho game.

Chạy:  python3 tools/build_sprites.py
Yêu cầu: numpy, opencv-python (cv2), scipy.
"""
import json, math, os
import numpy as np, cv2
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "assets_src", "reference.jpg")
OUT = os.path.join(ROOT, "public", "assets", "characters")
FRAMES = os.path.join(ROOT, "assets_src", "frames")

CELL = 192            # kích thước chuẩn của mọi frame
FIT_W, FIT_H = 146, 146  # vùng chứa nhân vật trong khung (chừa lề cho hiệu ứng lướt/hào quang)
FOOT_Y = 184          # hàng pixel của "chân" trong khung
N = 6                 # số frame mỗi animation
ANIMS = ["idle", "walk", "attack", "skill", "hurt", "die"]
FPS = {"idle": 6, "walk": 10, "attack": 14, "skill": 10, "hurt": 12, "die": 8}
LOOP = {"idle": True, "walk": True, "attack": False, "skill": False, "hurt": False, "die": False}

# id: (tên, vùng cắt x0,y0,x1,y1 trong ảnh gốc, lật ngang?, hướng nhìn sau chuẩn hóa (+1 phải/-1 trái), màu hào quang)
CHARS = {
    "player":      ("Người Chơi",  (8, 48, 218, 248),   False, +1, (255, 140, 40)),
    "boss_d":      ("Boss D",      (436, 48, 642, 242), True,  -1, (190, 90, 255)),
    "boss_c":      ("Boss C",      (872, 44, 1086, 246), False, -1, (80, 190, 255)),
    "boss_b":      ("Boss B",      (6, 326, 246, 516),  False, -1, (255, 90, 40)),
    "boss_a":      ("Boss A",      (434, 329, 694, 512), False, -1, (255, 200, 60)),
    "boss_s":      ("Boss S",      (858, 331, 1088, 506), False, -1, (170, 70, 255)),
    "linh_khuyen": ("Linh Khuyển", (8, 606, 232, 790),  True,  -1, (90, 220, 255)),
    "ma_nu":       ("Ma Nữ",       (432, 604, 664, 830), True,  -1, (200, 90, 255)),
    "ma_than":     ("Ma Thần",     (858, 604, 1086, 838), False, -1, (255, 190, 50)),
}


# --------------------------------------------------------------------------- tách nền
# vùng (x0,y0,x1,y1 trong ảnh gốc) cần xóa trước khi tách vì chứa sprite nhỏ/banner của ô bên cạnh
ERASE = {"ma_nu": [(572, 778, 664, 840)]}


def cutout(crop):
    """BGR (nền đen) -> BGRA nền trong suốt, chỉ giữ nhân vật chính (thành phần liên thông lớn nhất)."""
    mx = crop.max(2).astype(np.float32)
    core = (mx > 40).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    grow = cv2.dilate(core, np.ones((7, 7), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(grow)
    best = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    region = (lab == best)
    region = cv2.dilate(region.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    region &= cv2.dilate(grow, np.ones((5, 5), np.uint8)).astype(bool) | region

    soft = np.clip((mx - 14) / 46.0, 0, 1)           # alpha mềm theo độ sáng (viền phát sáng)
    solid = (mx > 30) & region
    solid = cv2.morphologyEx(solid.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
    # lấp các lỗ nhỏ (vùng tối nằm trong thân), KHÔNG lấp khoảng trống lớn giữa chân/đuôi
    holes = ndi.binary_fill_holes(solid) & ~solid
    lab_h, nh = ndi.label(holes)
    if nh:
        areas = ndi.sum(holes, lab_h, range(1, nh + 1))
        for i, a in enumerate(areas, 1):
            if a < 220:
                solid[lab_h == i] = True
    solid_core = cv2.erode(solid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32)
    alpha = np.maximum(solid_core, soft) * region
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0.6)
    alpha[~region] = 0
    # bỏ nhiễu nền JPEG
    alpha[alpha < 0.04] = 0

    a3 = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip(crop.astype(np.float32) / (255 * a3) * 1.0, 0, 1)
    # nơi alpha do độ sáng quyết định -> bỏ trộn đen (un-premultiply); nơi đặc -> giữ nguyên màu
    solid_mask = (solid_core > 0.5)[..., None]
    rgb = np.where(solid_mask, crop.astype(np.float32) / 255.0, np.clip(rgb, 0, 1))
    out = np.dstack([(rgb * 255).astype(np.uint8), (alpha * 255).astype(np.uint8)])
    # bỏ các mảnh rời nhỏ (viền banner, sprite nhỏ lân cận) - giữ mảnh lớn gần thân chính
    vis = cv2.dilate((out[..., 3] > 40).astype(np.uint8), np.ones((5, 5), np.uint8))
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(vis)
    big = st2[1:, cv2.CC_STAT_AREA].max()
    for i in range(1, n2):
        if st2[i, cv2.CC_STAT_AREA] < big * 0.06:
            out[lab2 == i] = 0
    ys, xs = np.where(out[..., 3] > 8)
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def to_cell(img):
    """Đặt ảnh vào khung CELLxCELL, cùng quy tắc tỉ lệ, neo chân giữa-đáy."""
    h, w = img.shape[:2]
    s = min(FIT_W / w, FIT_H / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    rs = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    cell = np.zeros((CELL, CELL, 4), np.uint8)
    x0 = (CELL - nw) // 2
    y0 = FOOT_Y - nh
    cell[y0:y0 + nh, x0:x0 + nw] = rs
    return cell


# --------------------------------------------------------------------------- biến đổi frame
def premult(img):
    f = img.astype(np.float32) / 255.0
    f[..., :3] *= f[..., 3:4]
    return f


def unpremult(f):
    a = np.clip(f[..., 3:4], 0, 1)
    rgb = np.where(a > 1e-3, f[..., :3] / np.maximum(a, 1e-3), 0)
    return (np.clip(np.dstack([rgb, a]), 0, 1) * 255 + 0.5).astype(np.uint8)


def xform(f, dx=0, dy=0, sx=1.0, sy=1.0, rot=0.0, skew=0.0):
    """Biến đổi quanh điểm chân (CELL/2, FOOT_Y). rot: độ, + = nghiêng theo chiều CW trên màn hình."""
    px, py = CELL / 2, FOOT_Y
    t = math.radians(rot)
    c, s = math.cos(t), math.sin(t)
    # ma trận: tịnh tiến về gốc -> scale -> skew -> xoay -> về lại + dịch
    A = np.array([[sx, skew * sy, 0], [0, sy, 0], [0, 0, 1]], np.float64)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)
    T1 = np.array([[1, 0, -px], [0, 1, -py], [0, 0, 1]], np.float64)
    T2 = np.array([[1, 0, px + dx], [0, 1, py + dy], [0, 0, 1]], np.float64)
    M = (T2 @ R @ A @ T1)[:2]
    return cv2.warpAffine(f, M, (CELL, CELL), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def tint(f, color, k):
    """Trộn màu (RGB 0-255) vào phần có alpha; k 0..1."""
    if k <= 0:
        return f
    col = np.array(color[::-1], np.float32) / 255.0  # sang BGR
    out = f.copy()
    a = out[..., 3:4]
    out[..., :3] = out[..., :3] * (1 - k) + col * a * k
    return out


def glow(f, color, k, radius=7):
    """Hào quang màu quanh nhân vật (cộng nền phía sau)."""
    if k <= 0:
        return f
    a = f[..., 3]
    g = cv2.GaussianBlur(a, (0, 0), radius) * k
    col = np.array(color[::-1], np.float32) / 255.0
    bg = np.dstack([col[0] * g, col[1] * g, col[2] * g, np.clip(g, 0, 1)])
    out = bg.copy()
    inv = 1 - f[..., 3:4]
    out = f + bg * inv
    out[..., 3] = np.clip(out[..., 3], 0, 1)
    return out


def over(dst, src, k=1.0):
    s = src * k
    return s + dst * (1 - s[..., 3:4])


def render(base_pm, kf, fwd, color):
    """kf: dict tham số của một frame. dx/rot lấy theo hướng nhìn `fwd` (+1 phải, -1 trái)."""
    dx = kf.get("dx", 0) * fwd
    rot = kf.get("rot", 0) * fwd
    skew = kf.get("skew", 0) * fwd
    img = xform(base_pm, dx, kf.get("dy", 0), kf.get("sx", 1), kf.get("sy", 1), rot, skew)
    canvas = np.zeros_like(img)
    # bóng mờ phía sau khi lướt/tấn công
    for i, (ox, k) in enumerate(kf.get("trail", [])):
        ghost = xform(base_pm, dx - ox * fwd, kf.get("dy", 0), kf.get("sx", 1), kf.get("sy", 1), rot * .5, skew)
        ghost = tint(ghost, color, .85)
        canvas = over(canvas, ghost, k)
    if kf.get("glow", 0) > 0:
        img = glow(img, color, kf["glow"], kf.get("glow_r", 7))
    if kf.get("flash", 0) > 0:
        img = tint(img, kf.get("flash_col", (255, 255, 255)), kf["flash"])
    canvas = over(canvas, img, 1.0)
    canvas[..., 3] *= kf.get("alpha", 1.0)
    canvas[..., :3] *= kf.get("alpha", 1.0)
    return canvas


# --------------------------------------------------------------------------- định nghĩa animation
def anim_keys(name, big):
    """Trả về N keyframe. `big`: boss lớn -> biên độ nhỏ hơn để không vượt khung."""
    k = .6 if big else .9
    out = []
    for i in range(N):
        p = i / N
        s = math.sin(2 * math.pi * p)
        if name == "idle":
            out.append(dict(dy=-2.5 * k * (s * .5 + .5), sy=1 + .02 * s, sx=1 - .008 * s, rot=.6 * s))
        elif name == "walk":
            step = abs(math.sin(math.pi * p * 2 * 1))  # 2 nhịp bước / chu kỳ
            out.append(dict(dy=-5 * k * abs(math.sin(2 * math.pi * p)), rot=2.2 * k * math.sin(2 * math.pi * p) + 1.5,
                            sy=1 - .03 * (1 - step), sx=1 + .02 * (1 - step), dx=1.5 * math.sin(2 * math.pi * p)))
        elif name == "attack":
            tbl = [dict(dx=-8, rot=-5, sx=.97, sy=1.03),
                   dict(dx=-12, rot=-8, sx=.95, sy=1.05, glow=.35),
                   dict(dx=22 * k, rot=9, sx=1.08, sy=.95, trail=[(14, .35), (28, .18)], flash=.25),
                   dict(dx=30 * k, rot=11, sx=1.1, sy=.94, trail=[(18, .3), (34, .14)], glow=.55, flash=.12),
                   dict(dx=14, rot=5, sx=1.03, sy=.99),
                   dict(dx=3, rot=1)]
            out.append(tbl[i])
        elif name == "skill":
            tbl = [dict(dy=0, sx=1.0, sy=1.0, glow=.25),
                   dict(dy=-5, sx=1.02, sy=.98, glow=.5, rot=-2),
                   dict(dy=-10 * k, sx=1.05, sy=.97, glow=.8, glow_r=10, rot=-3),
                   dict(dy=-14 * k, sx=1.08, sy=.95, glow=1.1, glow_r=12, flash=.2, rot=-3),
                   dict(dy=-6, dx=10, sx=1.1, sy=.92, glow=.9, glow_r=10, flash=.35, rot=4),
                   dict(dy=-1, glow=.35)]
            out.append(tbl[i])
        elif name == "hurt":
            tbl = [dict(dx=-4, rot=-4, sx=1.04, sy=.96, flash=.65),
                   dict(dx=-13 * k, rot=-9, sx=1.06, sy=.93, flash=.7, flash_col=(255, 70, 70)),
                   dict(dx=-16 * k, rot=-11, sx=1.05, sy=.94, flash=.45, flash_col=(255, 255, 255)),
                   dict(dx=-12, rot=-7, sx=1.03, sy=.97, flash=.3, flash_col=(255, 70, 70)),
                   dict(dx=-6, rot=-3, sx=1.01, sy=.99, flash=.12),
                   dict(dx=-1, rot=-1)]
            out.append(tbl[i])
        elif name == "die":
            tbl = [dict(dx=-4, rot=-5, flash=.7, sy=.98),
                   dict(dx=-8, rot=-10, flash=.45, flash_col=(255, 70, 70), sy=.9, sx=1.04),
                   dict(dx=-12 * k, dy=3, rot=-20, sy=.72, sx=1.1, alpha=.95),
                   dict(dx=-14 * k, dy=6, rot=-26, sy=.5, sx=1.16, alpha=.8),
                   dict(dx=-14 * k, dy=8, rot=-28, sy=.32, sx=1.2, alpha=.5),
                   dict(dx=-14 * k, dy=9, rot=-28, sy=.2, sx=1.22, alpha=.15)]
            out.append(tbl[i])
    return out


def main():
    ref = cv2.imread(REF)
    if ref is None:
        raise SystemExit("Không đọc được " + REF)
    os.makedirs(OUT, exist_ok=True)
    manifest = {"cell": CELL, "frames": N, "anims": {a: {"row": i, "frames": N, "fps": FPS[a], "loop": LOOP[a]}
                                                       for i, a in enumerate(ANIMS)}, "characters": {}}
    for cid, (name, (x0, y0, x1, y1), flip, fwd, color) in CHARS.items():
        crop = ref[y0:y1, x0:x1].copy()
        for (ex0, ey0, ex1, ey1) in ERASE.get(cid, []):
            crop[max(0, ey0 - y0):max(0, ey1 - y0), max(0, ex0 - x0):max(0, ex1 - x0)] = 0
        if flip:
            crop = crop[:, ::-1]
        rgba = cutout(crop)
        # PNG nền trong suốt của nhân vật (độ phân giải gốc, đã cắt sát)
        cv2.imwrite(os.path.join(OUT, f"{cid}.png"), rgba)
        base = to_cell(rgba)
        base_pm = premult(base)
        big = cid.startswith("boss") or cid == "linh_khuyen"
        sheet = np.zeros((CELL * len(ANIMS), CELL * N, 4), np.uint8)
        fdir = os.path.join(FRAMES, cid)
        os.makedirs(fdir, exist_ok=True)
        for r, an in enumerate(ANIMS):
            for i, kf in enumerate(anim_keys(an, big)):
                frame = unpremult(render(base_pm, kf, fwd, color))
                sheet[r * CELL:(r + 1) * CELL, i * CELL:(i + 1) * CELL] = frame
                cv2.imwrite(os.path.join(fdir, f"{an}_{i}.png"), frame)
        cv2.imwrite(os.path.join(OUT, f"{cid}_sheet.png"), sheet, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        ys, xs = np.where(base[..., 3] > 20)
        manifest["characters"][cid] = {
            "name": name, "sheet": f"/assets/characters/{cid}_sheet.png", "portrait": f"/assets/characters/{cid}.png",
            "fwd": fwd, "color": "#%02x%02x%02x" % color,
            # hộp bao của nhân vật trong khung (để căn kích thước khi vẽ)
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
            "foot": FOOT_Y,
        }
        print("ok", cid, rgba.shape)
    with open(os.path.join(OUT, "sprites.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
