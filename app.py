import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

_HERE = os.path.dirname(os.path.abspath(__file__))
# Một số host không cho tạo file bắt đầu bằng dấu chấm nên chấp nhận thêm vài tên khác.
_loaded = []
for _n in (".env", "_env", "_evn", "env", "env.txt", ".env.txt"):
    _p = os.path.join(_HERE, _n)
    if os.path.isfile(_p):
        load_dotenv(_p, encoding="utf-8-sig")
        _loaded.append(_n)
print(f"Cấu hình: đã đọc {_loaded or 'KHÔNG file nào'} trong thư mục {_HERE}")
print("Các file trong thư mục:", sorted(os.listdir(_HERE)))

BASE_URL = os.getenv("BASE_URL", "http://localhost:4000").rstrip("/")
SECRET_KEY = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
PORT = int(os.getenv("PORT", "4000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # để trống = tắt hoàn toàn lệnh admin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "players.json")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_folder="public", static_url_path="")
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=BASE_URL.startswith("https"),
    PERMANENT_SESSION_LIFETIME=30 * 24 * 3600,
)

_lock = threading.Lock()
NAME_RE = re.compile(r"^[\w \-]{2,16}$", re.UNICODE)
STAGE_AT = [0, 500, 1500, 3000]  # điểm để lên từng dạng tiến hóa
BOSS_AT = [800, 1800, 3000, 4500, 6500, 8500, 12000, 20000]
# Boss 1-5: hạng D, C, B, A, S (như cũ). Boss mới (biết tấn công người chơi):
#   6 = Linh Khuyển (8500đ), 7 = Ma Nữ (12000đ), 8 = Ma Thần (20000đ)
BOSSES = [
    {"id": 1, "name": "Boss hạng D", "at": BOSS_AT[0], "attacks": False},
    {"id": 2, "name": "Boss hạng C", "at": BOSS_AT[1], "attacks": False},
    {"id": 3, "name": "Boss hạng B", "at": BOSS_AT[2], "attacks": False},
    {"id": 4, "name": "Boss hạng A", "at": BOSS_AT[3], "attacks": False},
    {"id": 5, "name": "Boss hạng S", "at": BOSS_AT[4], "attacks": False},
    {"id": 6, "name": "Linh Khuyển", "at": BOSS_AT[5], "attacks": True},
    {"id": 7, "name": "Ma Nữ", "at": BOSS_AT[6], "attacks": True},
    {"id": 8, "name": "Ma Thần", "at": BOSS_AT[7], "attacks": True},
]

# Bậc hạng: (tên, điểm tối thiểu). Bậc cuối không có giới hạn trên.
RANKS = [
    ("Đồng", 0),
    ("Bạc", 1000),
    ("Vàng", 3000),
    ("Bạch Kim", 5000),
    ("Kim Cương", 7000),
    ("Tinh Anh", 10000),
    ("Giao Long", 15000),
    ("Hóa Rồng", 20000),
    ("Thần Linh", 25000),
    ("Đại Kiếp", 35000),
    ("Phá Sát", 40000),
    ("Cửu Linh Vạn Thiên", 45000),
    ("Tuyệt Định Thiên Vương", 50000),
]

# Vật phẩm trên đường (thời gian hiệu lực tính bằng giây)
ITEMS = {
    "shield": {"name": "Khiên", "duration": 10},
    "fire": {"name": "Phun lửa", "duration": 15},
}


def rank_info(score):
    idx = max(i for i, (_, at) in enumerate(RANKS) if score >= at)
    nxt = RANKS[idx + 1][1] if idx + 1 < len(RANKS) else None
    return {"id": idx, "name": RANKS[idx][0], "min": RANKS[idx][1], "next": nxt}
_fails = {}  # key -> (số lần sai, thời điểm hết khóa)

# Điều kiện mở khóa thành tích (id phải khớp với bảng ACH trong public/index.html)
ACH_RULES = {
    "first": lambda r: r["plays"] >= 1,
    "s500": lambda r: r["best"] >= 500,
    "s1000": lambda r: r["best"] >= 1000,
    "s2500": lambda r: r["best"] >= 2500,
    "s5000": lambda r: r["best"] >= 5000,
    "evo1": lambda r: r["bestStage"] >= 1,
    "evo2": lambda r: r["bestStage"] >= 2,
    "evo3": lambda r: r["bestStage"] >= 3,
    "dodge30": lambda r: r["dodged"] >= 30,
    "plays20": lambda r: r["plays"] >= 20,
    "boss1": lambda r: r.get("bestBoss", 0) >= 1,
    "bossB": lambda r: r.get("bestBoss", 0) >= 3,
    "bossS": lambda r: r.get("bestBoss", 0) >= 5,
    "kills10": lambda r: r.get("bossKills", 0) >= 10,
    "boss6": lambda r: r.get("bestBoss", 0) >= 6,
    "boss7": lambda r: r.get("bestBoss", 0) >= 7,
    "boss8": lambda r: r.get("bestBoss", 0) >= 8,
}


# ---------- Lưu dữ liệu vào file ----------
def read_players():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_players(players):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def _key(name):
    return name.strip().lower()


def _public(rec):
    return {
        "name": rec["name"],
        "best": rec.get("best", 0),
        "plays": rec.get("plays", 0),
        "bestStage": rec.get("bestStage", 0),
        "dodged": rec.get("dodged", 0),
        "bestBoss": rec.get("bestBoss", 0),
        "bossKills": rec.get("bossKills", 0),
        "ach": rec.get("ach", []),
        "rank": rank_info(rec.get("best", 0)),
    }


def _credentials():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    pw = body.get("password") or ""
    if not NAME_RE.match(name):
        return None, None, "Biệt danh phải từ 2-16 ký tự chữ/số."
    if not isinstance(pw, str) or not 6 <= len(pw) <= 64:
        return None, None, "Mật khẩu phải từ 6-64 ký tự."
    return name, pw, None


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/config")
def config():
    """Một nguồn dữ liệu chung để index.html dùng: hạng, boss, vật phẩm."""
    return jsonify(
        ranks=[{"id": i, "name": n, "min": at} for i, (n, at) in enumerate(RANKS)],
        bosses=BOSSES,
        items=ITEMS,
        stageAt=STAGE_AT,
    )


@app.post("/api/register")
def register():
    name, pw, err = _credentials()
    if err:
        return jsonify(error=err), 400
    key = _key(name)
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        players = read_players()
        rec = players.get(key)
        # Bản ghi cũ (chưa có mật khẩu) được phép "nhận lại" để giữ điểm đã lưu.
        if rec and rec.get("pw"):
            return jsonify(error="Biệt danh đã có người dùng."), 409
        if not rec:
            rec = {"best": 0, "plays": 0, "bestStage": 0, "dodged": 0, "ach": [], "firstSeen": now}
        rec.update(name=name, pw=generate_password_hash(pw), lastSeen=now)
        players[key] = rec
        write_players(players)
    session.permanent = True
    session["key"] = key
    return jsonify(ok=True, player=_public(rec))


@app.post("/api/login")
def login():
    name, pw, err = _credentials()
    if err:
        return jsonify(error=err), 400
    key = _key(name)
    count, until = _fails.get(key, (0, 0))
    if count >= 5 and time.time() < until:
        return jsonify(error="Sai quá nhiều lần, thử lại sau vài phút."), 429
    with _lock:
        players = read_players()
        rec = players.get(key)
        if not rec or not rec.get("pw") or not check_password_hash(rec["pw"], pw):
            _fails[key] = (count + 1, time.time() + 300)
            return jsonify(error="Sai biệt danh hoặc mật khẩu."), 401
        rec["lastSeen"] = datetime.now(timezone.utc).isoformat()
        players[key] = rec
        write_players(players)
    _fails.pop(key, None)
    session.permanent = True
    session["key"] = key
    return jsonify(ok=True, player=_public(rec))


@app.get("/api/me")
def me():
    key = session.get("key")
    rec = read_players().get(key) if key else None
    return jsonify(player=_public(rec) if rec else None, admin=bool(session.get("admin")))


@app.post("/api/admin")
def admin():
    if not ADMIN_PASSWORD:
        return jsonify(error="Chưa cấu hình ADMIN_PASSWORD trên server."), 403
    fkey = "admin:" + (request.remote_addr or "?")
    count, until = _fails.get(fkey, (0, 0))
    if count >= 5 and time.time() < until:
        return jsonify(error="Sai quá nhiều lần, thử lại sau."), 429
    pw = (request.get_json(silent=True) or {}).get("password") or ""
    if not isinstance(pw, str) or not secrets.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
        _fails[fkey] = (count + 1, time.time() + 300)
        return jsonify(error="Sai mật khẩu admin."), 401
    _fails.pop(fkey, None)
    session["admin"] = True
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/score")
def submit_score():
    key = session.get("key")
    if not key:
        return jsonify(error="Chưa đăng nhập"), 401
    body = request.get_json(silent=True) or {}
    score, dodged = body.get("score"), body.get("dodged", 0)
    boss, kills = body.get("boss", 0), body.get("kills", 0)
    ok_int = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not all(ok_int(v) for v in (score, dodged, boss, kills)):
        return jsonify(error="Dữ liệu không hợp lệ"), 400
    score = max(0, min(score, 999999))
    dodged = max(0, min(dodged, 200))
    allowed = sum(1 for a in BOSS_AT if score >= a)  # chỉ công nhận boss đã tới mốc điểm
    boss = max(0, min(boss, allowed, len(BOSS_AT)))
    kills = max(0, min(kills, 10))
    stage = max(i for i, at in enumerate(STAGE_AT) if score >= at)  # server tự tính, không tin client

    with _lock:
        players = read_players()
        rec = players.get(key)
        if not rec:
            return jsonify(error="Chưa đăng nhập"), 401
        old_rank = rank_info(rec.get("best", 0))["id"]
        rec["best"] = max(rec.get("best", 0), score)
        rec["plays"] = rec.get("plays", 0) + 1
        rec["bestStage"] = max(rec.get("bestStage", 0), stage)
        rec["dodged"] = rec.get("dodged", 0) + dodged
        rec["bestBoss"] = max(rec.get("bestBoss", 0), boss)
        rec["bossKills"] = rec.get("bossKills", 0) + kills
        old = set(rec.get("ach", []))
        rec["ach"] = [a for a, rule in ACH_RULES.items() if a in old or rule(rec)]
        rec["lastSeen"] = datetime.now(timezone.utc).isoformat()
        write_players(players)

    rank_up = rank_info(rec["best"])["id"] > old_rank
    return jsonify(ok=True, player=_public(rec), new=[a for a in rec["ach"] if a not in old], rankUp=rank_up)


@app.get("/api/leaderboard")
def leaderboard():
    players = read_players()
    top = sorted(players.values(), key=lambda r: r.get("best", 0), reverse=True)[:10]
    return jsonify(top=[{"name": r["name"], "best": r.get("best", 0), "stage": r.get("bestStage", 0), "boss": r.get("bestBoss", 0), "rank": rank_info(r.get("best", 0))["name"]} for r in top])


if __name__ == "__main__":
    print(f"Game khủng long (tác giả: Trí Việt) chạy tại {BASE_URL}")
    print("Lệnh admin:", "ĐÃ BẬT" if ADMIN_PASSWORD else "TẮT (chưa đọc được ADMIN_PASSWORD)")
    app.run(host="0.0.0.0", port=PORT, debug=False)
