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
BOSS_AT = [800, 1800, 3000, 4500, 6500]  # điểm xuất hiện boss hạng D, C, B, A, S
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
    boss = max(0, min(boss, allowed, 5))
    kills = max(0, min(kills, 10))
    stage = max(i for i, at in enumerate(STAGE_AT) if score >= at)  # server tự tính, không tin client

    with _lock:
        players = read_players()
        rec = players.get(key)
        if not rec:
            return jsonify(error="Chưa đăng nhập"), 401
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

    return jsonify(ok=True, player=_public(rec), new=[a for a in rec["ach"] if a not in old])


@app.get("/api/leaderboard")
def leaderboard():
    players = read_players()
    top = sorted(players.values(), key=lambda r: r.get("best", 0), reverse=True)[:10]
    return jsonify(top=[{"name": r["name"], "best": r.get("best", 0), "stage": r.get("bestStage", 0), "boss": r.get("bestBoss", 0)} for r in top])


if __name__ == "__main__":
    print(f"Game khủng long (tác giả: Trí Việt) chạy tại {BASE_URL}")
    print("Lệnh admin:", "ĐÃ BẬT" if ADMIN_PASSWORD else "TẮT (chưa đọc được ADMIN_PASSWORD)")
    app.run(host="0.0.0.0", port=PORT, debug=False)
