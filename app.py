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
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

def _get_admin_password():
    # Đọc lại mỗi request để Render Environment được phản ánh sau restart/reload.
    return os.getenv("ADMIN_PASSWORD", "").strip()
STORAGE_MODE = os.getenv("STORAGE_MODE", "auto").strip().lower()  # auto | supabase | json

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

@app.after_request
def _no_store_api(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

_lock = threading.Lock()
_fails = {}
_chat_last = {}
_supabase = None
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "").strip()
SUPABASE_ID_COLUMN = os.getenv("SUPABASE_ID_COLUMN", "id").strip()
SUPABASE_DATA_COLUMN = os.getenv("SUPABASE_DATA_COLUMN", "data").strip()

# Bản chạy local mặc định dùng JSON; Supabase chỉ bật khi đủ URL và service key.
_supabase_url = os.getenv("SUPABASE_URL", "").strip()
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
if STORAGE_MODE == "supabase" and not (_supabase_url and _supabase_key):
    raise RuntimeError("STORAGE_MODE=supabase nhưng thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY. Hãy cấu hình chúng trên Render Environment.")
if STORAGE_MODE == "supabase" and not SUPABASE_TABLE:
    raise RuntimeError("STORAGE_MODE=supabase nhưng thiếu SUPABASE_TABLE. Phải khai báo đúng tên bảng người chơi CŨ.")
if (_supabase_url and not _supabase_key) or (_supabase_key and not _supabase_url):
    raise RuntimeError("Chỉ được cấu hình đồng thời SUPABASE_URL và SUPABASE_SERVICE_ROLE_KEY; không được chạy fallback JSON âm thầm.")
if _supabase_url and _supabase_key:
    try:
        from supabase import create_client
        _supabase = create_client(_supabase_url, _supabase_key)
    except Exception as _supabase_error:
        # Nếu đã cấu hình Supabase mà client không khởi tạo được, dừng startup thay vì
        # âm thầm chạy bằng JSON rỗng và làm người chơi tưởng dữ liệu cũ đã mất.
        raise RuntimeError(f"Không khởi tạo được Supabase: {_supabase_error}") from _supabase_error
elif STORAGE_MODE not in ("auto", "json"):
    raise RuntimeError("STORAGE_MODE không hợp lệ. Dùng auto, supabase hoặc json.")


_supabase_ready = False
_supabase_guard = threading.Lock()


def _read_local_players():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_local_players(players):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)


def _ensure_supabase_ready():
    """Import bản JSON cũ theo kiểu insert-only; tuyệt đối không ghi đè bản ghi DB."""
    global _supabase_ready
    if _supabase is None or _supabase_ready:
        return
    with _supabase_guard:
        if _supabase_ready:
            return
        remote = {}
        offset = 0
        while True:
            response = (_supabase.table(SUPABASE_TABLE).select(f"{SUPABASE_ID_COLUMN},{SUPABASE_DATA_COLUMN}")
                        .range(offset, offset + 999).execute())
            batch = response.data or []
            for row in batch:
                storage_key = str(row[SUPABASE_ID_COLUMN])
                record = _normalize_player_record(row[SUPABASE_DATA_COLUMN])
                if record is not None:
                    remote[storage_key] = record
            if len(batch) < 1000:
                break
            offset += 1000
        local = _read_local_players()
        missing = [(key, value) for key, value in local.items() if key not in remote]
        # Chỉ thêm tài khoản chưa tồn tại; không cập nhật/ghi đè bất kỳ tài khoản DB nào.
        for key, value in missing:
            _supabase.table(SUPABASE_TABLE).upsert(
                {SUPABASE_ID_COLUMN: key, SUPABASE_DATA_COLUMN: value}, on_conflict=SUPABASE_ID_COLUMN
            ).execute()
            remote[key] = value
        _write_local_players(remote)
        _supabase_ready = True


def read_players():
    """DB là nguồn chính khi bật Supabase; JSON là nguồn chính khi chạy local."""
    if _supabase is None:
        return _read_local_players()
    _ensure_supabase_ready()
    players = {}
    offset = 0
    while True:
        response = (_supabase.table(SUPABASE_TABLE).select(f"{SUPABASE_ID_COLUMN},{SUPABASE_DATA_COLUMN}")
                    .range(offset, offset + 999).execute())
        batch = response.data or []
        for row in batch:
            storage_key = str(row[SUPABASE_ID_COLUMN])
            record = _normalize_player_record(row[SUPABASE_DATA_COLUMN])
            if record is not None:
                players[storage_key] = record
        if len(batch) < 1000:
            break
        offset += 1000
    _write_local_players(players)
    return players


def write_players(players):
    """Persist an entire in-memory snapshot without silently downgrading storage.

    Supabase is written first when configured. The local JSON is only a snapshot and
    is refreshed after a successful remote write, so a DB failure cannot masquerade
    as a successful save.
    """
    if _supabase is not None:
        _ensure_supabase_ready()
        for key, value in players.items():
            _supabase.table(SUPABASE_TABLE).upsert(
                {SUPABASE_ID_COLUMN: key, SUPABASE_DATA_COLUMN: value}, on_conflict=SUPABASE_ID_COLUMN
            ).execute()
    _write_local_players(players)


def _storage_status():
    if _supabase is None:
        return {"mode": "json", "table": None, "connected": True}
    try:
        _supabase.table(SUPABASE_TABLE).select(SUPABASE_ID_COLUMN).limit(1).execute()
        return {"mode": "supabase", "table": SUPABASE_TABLE, "connected": True}
    except Exception as exc:
        return {"mode": "supabase", "table": SUPABASE_TABLE, "connected": False, "error": str(exc)[:240]}


def _key(name):
    return str(name or "").strip().casefold()


def _normalize_player_record(value):
    """Normalize legacy Supabase JSON values without changing their contents."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except (TypeError, ValueError):
            return None
    return None


def _resolve_player(players, login_name):
    """Resolve by storage key first, then by the player name inside legacy records."""
    wanted = _key(login_name)
    rec = players.get(wanted)
    if isinstance(rec, dict):
        return wanted, rec
    matches = []
    for storage_key, candidate in players.items():
        if not isinstance(candidate, dict):
            continue
        if _key(candidate.get("name")) == wanted:
            matches.append((str(storage_key), candidate))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return None, None
    return None, None


def rank_info(score):
    score = max(0, int(score or 0))
    idx = 0
    for i, (_, threshold) in enumerate(RANKS):
        if score >= threshold:
            idx = i
        else:
            break
    name, minimum = RANKS[idx]
    next_rank = RANKS[idx + 1] if idx + 1 < len(RANKS) else None
    return {"id": idx, "name": name, "min": minimum,
            "next": next_rank[1] if next_rank else None,
            "progress": (score - minimum) / (next_rank[1] - minimum) if next_rank else 1.0}

ACH_RULES = {
    "first": lambda r: r.get("plays", 0) >= 1,
    "s500": lambda r: r.get("best", 0) >= 500,
    "s1000": lambda r: r.get("best", 0) >= 1000,
    "s2500": lambda r: r.get("best", 0) >= 2500,
    "s5000": lambda r: r.get("best", 0) >= 5000,
    "dodge30": lambda r: r.get("dodged", 0) >= 30,
    "plays20": lambda r: r.get("plays", 0) >= 20,
    "boss1": lambda r: r.get("bestBoss", 0) >= 1,
    "bossB": lambda r: r.get("bestBoss", 0) >= 3,
    "bossS": lambda r: r.get("bestBoss", 0) >= 5,
    "kills10": lambda r: r.get("bossKills", 0) >= 10,
    "boss6": lambda r: r.get("bestBoss", 0) >= 6,
    "boss7": lambda r: r.get("bestBoss", 0) >= 7,
    "boss8": lambda r: r.get("bestBoss", 0) >= 8,
}
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


# Danh mục trang bị do máy chủ quản lý. Client chỉ nhận ID và dữ liệu hiển thị.
GEAR_CATALOG = {
    "helm_common": {"name":"Mũ Thám Hiểm", "slot":"helmet", "rarity":"common", "icon":"🪖", "stats":{"cooldown":2}},
    "helm_rare": {"name":"Vương Miện Lam Ngọc", "slot":"helmet", "rarity":"rare", "icon":"💠", "stats":{"cooldown":6,"armor":2}},
    "helm_legend": {"name":"Long Vương Hắc Diệm", "slot":"helmet", "rarity":"legendary", "icon":"👑", "stats":{"cooldown":12,"armor":4}},
    "armor_common": {"name":"Áo Da Cổ Đại", "slot":"armor", "rarity":"common", "icon":"🥋", "stats":{"armor":3}},
    "armor_rare": {"name":"Giáp Thép Hóa Thạch", "slot":"armor", "rarity":"rare", "icon":"🛡️", "stats":{"armor":8,"hp":10}},
    "armor_legend": {"name":"Giáp Thiên Long", "slot":"armor", "rarity":"legendary", "icon":"🦾", "stats":{"armor":16,"hp":25}},
    "pants_common": {"name":"Quần Lữ Hành", "slot":"pants", "rarity":"common", "icon":"👖", "stats":{"hp":15}},
    "pants_rare": {"name":"Giáp Chân Cổ Ngữ", "slot":"pants", "rarity":"rare", "icon":"🩳", "stats":{"hp":35,"armor":2}},
    "pants_legend": {"name":"Quần Vũ Trụ", "slot":"pants", "rarity":"legendary", "icon":"🌌", "stats":{"hp":65,"armor":5}},
    "boots_common": {"name":"Giày Da", "slot":"boots", "rarity":"common", "icon":"🥾", "stats":{"speed":3}},
    "boots_rare": {"name":"Ủng Phong Vân", "slot":"boots", "rarity":"rare", "icon":"👟", "stats":{"speed":7,"hp":8}},
    "boots_legend": {"name":"Phi Vân Thần Hài", "slot":"boots", "rarity":"legendary", "icon":"✨", "stats":{"speed":14,"hp":15}},
    "champion_helm": {"name":"Vương Miện Quán Quân", "slot":"helmet", "rarity":"exclusive", "icon":"👑", "stats":{"cooldown":18,"armor":8}},
    "champion_armor": {"name":"Long Giáp Độc Tôn", "slot":"armor", "rarity":"exclusive", "icon":"🐉", "stats":{"armor":25,"hp":50}},
    "champion_pants": {"name":"Chiến Khố Thiên Vương", "slot":"pants", "rarity":"exclusive", "icon":"⚜️", "stats":{"hp":100,"armor":8}},
    "champion_boots": {"name":"Thần Hành Vô Ảnh", "slot":"boots", "rarity":"exclusive", "icon":"💫", "stats":{"speed":20,"hp":20}},
}
GEAR_SLOTS = ("helmet", "armor", "pants", "boots")
RARITY_ORDER = {"common":0, "rare":1, "legendary":2, "exclusive":3}


def _defaults(rec):
    """Bổ sung trường mới mà không làm mất dữ liệu người chơi cũ."""
    rec.setdefault("level", 1); rec.setdefault("experience", 0)
    rec.setdefault("inventory", [])
    rec.setdefault("equipment", {slot: None for slot in GEAR_SLOTS})
    for slot in GEAR_SLOTS: rec["equipment"].setdefault(slot, None)
    rec.setdefault("skills", {"burrow": False, "transform": False})
    rec.setdefault("exclusiveItems", [])
    rec.setdefault("unlockedMaps", [1])
    rec.setdefault("home", {"theme":"default", "decorations":[]})
    rec.setdefault("bossLootClaimed", 0)
    # Đồng bộ cấp độ với kỷ lục hiện có, kể cả tài khoản tạo từ phiên bản cũ.
    rec["level"] = max(1, 1 + int(max(0, rec.get("best", 0)) // 1500))
    rec["experience"] = max(0, int(rec.get("best", 0))) % 1500
    if rec.get("bestBoss", 0) >= 4: rec["skills"]["burrow"] = True
    if rec.get("bestBoss", 0) >= 6: rec["skills"]["transform"] = True
    return rec


def _gear_instance(item_id):
    item = GEAR_CATALOG[item_id]
    return {"uid": secrets.token_hex(8), "itemId": item_id, **item}


def _gear_stats(rec):
    total = {"hp":0,"armor":0,"speed":0,"cooldown":0}
    for item_id in (rec.get("equipment") or {}).values():
        if item_id in GEAR_CATALOG:
            for stat, value in GEAR_CATALOG[item_id]["stats"].items(): total[stat] += value
    return total


def _public(rec):
    _defaults(rec)
    return {
        "name": rec["name"], "best": rec.get("best",0), "plays": rec.get("plays",0),
        "bestStage": rec.get("bestStage",0), "dodged": rec.get("dodged",0),
        "bestBoss": rec.get("bestBoss",0), "bossKills": rec.get("bossKills",0),
        "ach": rec.get("ach",[]), "rank": rank_info(rec.get("best",0)),
        "level": rec.get("level",1), "experience": rec.get("experience",0),
        "inventory": rec.get("inventory",[]), "equipment": rec.get("equipment",{}),
        "skills": rec.get("skills",{}), "exclusiveItems": rec.get("exclusiveItems",[]),
        "unlockedMaps": rec.get("unlockedMaps",[1]), "home": rec.get("home",{}),
        "stats": _gear_stats(rec),
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


@app.get("/healthz")
def healthz():
    # Kiểm tra kết nối DB nếu đã bật Supabase, để Render không báo khỏe khi DB lỗi.
    if _supabase is not None:
        try:
            _supabase.table(SUPABASE_TABLE).select(SUPABASE_ID_COLUMN).limit(1).execute()
        except Exception:
            return jsonify(ok=False, storage="supabase", error="database_unavailable"), 503
    status=_storage_status()
    return jsonify(ok=True, storage=status["mode"], table=status.get("table"), connected=status["connected"])


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/admin")
def admin_page():
    return app.send_static_file("admin.html")


@app.get("/api/config")
def config():
    """Một nguồn dữ liệu chung để index.html dùng: hạng, boss, vật phẩm."""
    return jsonify(
        ranks=[{"id": i, "name": n, "min": at} for i, (n, at) in enumerate(RANKS)],
        bosses=BOSSES,
        items=ITEMS,
        stageAt=STAGE_AT,
        gear=GEAR_CATALOG,
        maps=[{"id":1,"name":"Thế giới khởi nguyên","theme":"origin","unlocked":True},{"id":2,"name":"Kỷ nguyên tiền sử","theme":"prehistoric","unlocked":True},{"id":3,"name":"Khu vườn trên mây","theme":"cloud","unlocked":True}],
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
            guest = (request.get_json(silent=True) or {}).get("guestData") or {}
            def safe_num(field, limit):
                try: return max(0, min(int(guest.get(field, 0) or 0), limit))
                except (TypeError, ValueError): return 0
            rec = {"best": safe_num("best",999999), "plays": safe_num("plays",100000),
                   "bestBoss": safe_num("bestBoss",8), "bossKills": safe_num("bossKills",100000),
                   "bestStage": safe_num("bestStage",3), "dodged": safe_num("dodged",100000),
                   "ach": [], "firstSeen": now}
        _defaults(rec)
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
    login_key = _key(name)
    count, until = _fails.get(login_key, (0, 0))
    if count >= 5 and time.time() < until:
        return jsonify(error="Sai quá nhiều lần, thử lại sau vài phút."), 429
    with _lock:
        players = read_players()
        storage_key, rec = _resolve_player(players, name)
        if not rec or not rec.get("pw") or not check_password_hash(str(rec["pw"]), pw):
            _fails[login_key] = (count + 1, time.time() + 300)
            return jsonify(error="Sai biệt danh hoặc mật khẩu."), 401
        _defaults(rec)
        rec["lastSeen"] = datetime.now(timezone.utc).isoformat()
        players[storage_key] = rec
        write_players(players)
    _fails.pop(login_key, None)
    # Luôn thay thế phiên cũ bằng đúng tài khoản vừa xác thực.
    session.clear()
    session.permanent = True
    session["key"] = storage_key
    return jsonify(ok=True, player=_public(rec))


@app.get("/api/me")
def me():
    key = session.get("key")
    rec = read_players().get(key) if key else None
    return jsonify(player=_public(rec) if rec else None, admin=bool(session.get("admin")))


@app.post("/api/admin")
def admin():
    admin_password = _get_admin_password()
    if not admin_password:
        return jsonify(error="Chưa cấu hình ADMIN_PASSWORD trên server. Hãy thêm biến ADMIN_PASSWORD trong Render Environment."), 503
    fkey = "admin:" + (request.remote_addr or "?")
    count, until = _fails.get(fkey, (0, 0))
    if count >= 5 and time.time() < until:
        return jsonify(error="Sai quá nhiều lần, thử lại sau."), 429
    pw = (request.get_json(silent=True) or {}).get("password") or ""
    if not isinstance(pw, str) or not secrets.compare_digest(pw.encode(), admin_password.encode()):
        _fails[fkey] = (count + 1, time.time() + 300)
        return jsonify(error="Sai mật khẩu admin."), 401
    _fails.pop(fkey, None)
    session["admin"] = True
    session.permanent = True
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/score")
def submit_score():
    key = session.get("key")
    if not key: return jsonify(error="Chưa đăng nhập tài khoản"), 401
    body = request.get_json(silent=True) or {}
    score, dodged = body.get("score"), body.get("dodged", 0)
    boss, kills = body.get("boss", 0), body.get("kills", 0)
    ok_int = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not all(ok_int(v) for v in (score, dodged, boss, kills)): return jsonify(error="Dữ liệu không hợp lệ"), 400
    score=max(0,min(score,999999)); dodged=max(0,min(dodged,200))
    allowed=sum(1 for a in BOSS_AT if score>=a)
    boss=max(0,min(boss,allowed,len(BOSS_AT))); kills=max(0,min(kills,10))
    stage=max(i for i,at in enumerate(STAGE_AT) if score>=at)
    drops=[]
    with _lock:
        players=read_players(); rec=players.get(key)
        if not rec: return jsonify(error="Chưa đăng nhập"),401
        _defaults(rec)
        old_rank=rank_info(rec.get("best",0))["id"]
        old_boss=int(rec.get("bestBoss",0)); rec["best"]=max(rec.get("best",0),score)
        rec["plays"]=rec.get("plays",0)+1; rec["bestStage"]=max(rec.get("bestStage",0),stage)
        rec["dodged"]=rec.get("dodged",0)+dodged
        rec["bestBoss"]=max(old_boss,boss); rec["bossKills"]=rec.get("bossKills",0)+kills
        # Mỗi boss có tỷ lệ và bảng phẩm chất riêng; chỉ xét các boss mới được ghi nhận.
        # Boss D-A luôn rơi một món Common/Rare để người chơi chắc chắn
        # nhìn thấy loot; từ S trở lên có tỷ lệ rơi thấp hơn nhưng có Legendary.
        loot_rules = {
            1: (100, 82, 0), 2: (100, 75, 0), 3: (100, 68, 0), 4: (100, 60, 0),
            5: (70, 0, 20), 6: (75, 0, 30), 7: (80, 0, 40), 8: (85, 0, 50),
        }
        for boss_level in range(old_boss+1, min(boss,8)+1):
            chance, common_pct, legendary_pct = loot_rules[boss_level]
            if secrets.randbelow(100) >= chance: continue
            roll=secrets.randbelow(100)
            if boss_level <= 4:
                rarity="common" if roll < common_pct else "rare"
            else:
                rarity="legendary" if roll < legendary_pct else "rare"
            suffix={"common":"common","rare":"rare","legendary":"legend"}[rarity]
            slot=secrets.choice(("helm","armor","pants","boots"))
            inst=_gear_instance(f"{slot}_{suffix}"); rec["inventory"].append(inst); drops.append(inst)
        if rec["bestBoss"]>=4: rec["skills"]["burrow"]=True
        if rec["bestBoss"]>=6: rec["skills"]["transform"]=True
        rec["level"]=max(1,1+int(rec["best"]//1500)); rec["experience"]=rec["best"]%1500
        old=set(rec.get("ach",[])); rec["ach"]=[a for a,rule in ACH_RULES.items() if a in old or rule(rec)]
        rec["lastSeen"]=datetime.now(timezone.utc).isoformat(); write_players(players)
    return jsonify(ok=True,player=_public(rec),drops=drops,new=[a for a in rec["ach"] if a not in old],rankUp=rank_info(rec["best"])["id"]>old_rank)


@app.post("/api/equip")
def equip_item():
    key=session.get("key")
    if not key:return jsonify(error="Cần đăng nhập để trang bị"),401
    uid=(request.get_json(silent=True) or {}).get("uid")
    with _lock:
        players=read_players();rec=players.get(key)
        if not rec:return jsonify(error="Không tìm thấy tài khoản"),404
        _defaults(rec); idx=next((i for i,x in enumerate(rec["inventory"]) if x.get("uid")==uid),None)
        if idx is None:return jsonify(error="Vật phẩm không tồn tại trong túi"),404
        item=rec["inventory"][idx]; slot=item.get("slot")
        if slot not in GEAR_SLOTS:return jsonify(error="Vị trí trang bị không hợp lệ"),400
        previous=rec["equipment"].get(slot); rec["equipment"][slot]=item["itemId"]
        rec["inventory"].pop(idx)
        if previous and previous in GEAR_CATALOG: rec["inventory"].append(_gear_instance(previous))
        write_players(players)
    return jsonify(ok=True,player=_public(rec))


@app.post("/api/unequip")
def unequip_item():
    key=session.get("key")
    if not key:return jsonify(error="Cần đăng nhập"),401
    slot=(request.get_json(silent=True) or {}).get("slot")
    if slot not in GEAR_SLOTS:return jsonify(error="Vị trí không hợp lệ"),400
    with _lock:
        players=read_players();rec=players.get(key)
        if not rec:return jsonify(error="Không tìm thấy tài khoản"),404
        _defaults(rec); item_id=rec["equipment"].get(slot)
        if item_id and item_id in GEAR_CATALOG:rec["inventory"].append(_gear_instance(item_id))
        rec["equipment"][slot]=None;write_players(players)
    return jsonify(ok=True,player=_public(rec))


@app.post("/api/redeem")
def redeem_code():
    key=session.get("key")
    if not key:return jsonify(error="Cần đăng nhập"),401
    code=((request.get_json(silent=True) or {}).get("code") or "").strip().upper()
    # Mã được cấu hình ở biến môi trường, không nhúng mã bí mật vào frontend.
    codes={x.strip().upper() for x in os.getenv("DINO_EXCLUSIVE_CODES","").split(",") if x.strip()}
    if not code or code not in codes:return jsonify(error="Mã không hợp lệ hoặc đã hết hạn"),400
    with _lock:
        players=read_players();rec=players.get(key)
        if not rec:return jsonify(error="Không tìm thấy tài khoản"),404
        _defaults(rec);used=rec.setdefault("usedCodes",[])
        if code in used:return jsonify(error="Mã này đã được sử dụng"),409
        used.append(code)
        for item_id in ("champion_helm","champion_armor","champion_pants","champion_boots"):
            rec["inventory"].append(_gear_instance(item_id))
        write_players(players)
    return jsonify(ok=True,player=_public(rec))


@app.get("/api/chat")
def get_chat():
    if _supabase is not None:
        try:
            result=_supabase.table("dino_chat_messages").select("name,message,created_at").order("created_at",desc=True).limit(50).execute()
            return jsonify(messages=list(reversed(result.data or [])), storage="supabase")
        except Exception as exc:
            return jsonify(error="Không thể đọc chat từ Supabase. Dữ liệu chưa được chuyển sang JSON local.", detail=str(exc)[:240]), 503
    path=os.path.join(DATA_DIR,"chat.json")
    try:
        with open(path,encoding="utf-8") as f: messages=json.load(f)
    except (OSError,ValueError): messages=[]
    return jsonify(messages=messages[-50:])


@app.post("/api/chat")
def send_chat():
    key=session.get("key")
    if not key:return jsonify(error="Đăng nhập để gửi tin nhắn"),401
    text=(request.get_json(silent=True) or {}).get("message","")
    if not isinstance(text,str) or not 1<=len(text.strip())<=240:return jsonify(error="Tin nhắn phải từ 1-240 ký tự"),400
    now_ts=time.time()
    if now_ts-_chat_last.get(key,0)<2:return jsonify(error="Bạn gửi quá nhanh. Hãy chờ 2 giây."),429
    _chat_last[key]=now_ts
    rec=read_players().get(key,{})
    msg={"name":rec.get("name","Người chơi"),"message":text.strip(),"created_at":datetime.now(timezone.utc).isoformat()}
    if _supabase is not None:
        try:
            _supabase.table("dino_chat_messages").insert(msg).execute()
            return jsonify(ok=True,message=msg,storage="supabase")
        except Exception as exc:
            return jsonify(error="Không thể lưu chat vào Supabase. Tin nhắn chưa được lưu.", detail=str(exc)[:240]), 503
    # Chỉ dùng JSON local khi ứng dụng thực sự chạy ở chế độ JSON.
    path=os.path.join(DATA_DIR,"chat.json")
    with _lock:
        try:
            with open(path,encoding="utf-8") as f: messages=json.load(f)
        except (OSError,ValueError): messages=[]
        messages.append(msg);messages=messages[-200:]
        tmp=path+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(messages,f,ensure_ascii=False)
        os.replace(tmp,path)
    return jsonify(ok=True,message=msg,storage="json")


@app.get("/api/server-config")
def server_config():
    """Public, non-secret configuration diagnostics for deployment troubleshooting."""
    supabase_vars = bool(_supabase_url and _supabase_key)
    return jsonify(
        ok=True,
        adminConfigured=bool(_get_admin_password()),
        storageMode=STORAGE_MODE,
        supabaseConfigured=supabase_vars,
        supabaseTable=SUPABASE_TABLE or None,
        supabaseClientReady=_supabase is not None,
    )


@app.get("/api/admin/status")
def admin_status():
    if not session.get("admin"):
        return jsonify(error="Cần quyền admin"), 403
    return jsonify(ok=True, storage=_storage_status(), table=SUPABASE_TABLE, adminConfigured=bool(_get_admin_password()))


@app.get("/api/admin/players")
def admin_players():
    if not session.get("admin"):
        return jsonify(error="Cần quyền admin"), 403
    query=(request.args.get("q") or "").strip().casefold()
    players=read_players()
    rows=[]
    for key, rec in players.items():
        _defaults(rec)
        if query and query not in key and query not in str(rec.get("name", "")).casefold():
            continue
        rows.append({"id":key,"name":rec.get("name",key),"level":rec.get("level",1),"best":rec.get("best",0),
                     "experience":rec.get("experience",0),"bestBoss":rec.get("bestBoss",0),"bossKills":rec.get("bossKills",0),
                     "inventoryCount":len(rec.get("inventory",[])),"equipment":rec.get("equipment",{}),
                     "stats":_gear_stats(rec),"lastSeen":rec.get("lastSeen")})
    rows.sort(key=lambda r:(-int(r["best"]), r["name"].casefold()))
    return jsonify(players=rows)


@app.get("/api/admin/player/<path:player_id>")
def admin_player(player_id):
    if not session.get("admin"):
        return jsonify(error="Cần quyền admin"), 403
    key=_key(player_id)
    rec=read_players().get(key)
    if not rec:
        return jsonify(error="Không tìm thấy người chơi"),404
    _defaults(rec)
    safe=dict(rec)
    safe.pop("pw",None)
    return jsonify(id=key, player=_public(rec), raw=safe)


@app.post("/api/admin/grant")
def admin_grant():
    if not session.get("admin"): return jsonify(error="Cần quyền admin"),403
    body=request.get_json(silent=True) or {}; target=_key(str(body.get("name") or "")); item_ids=body.get("items") or []
    if not target or not isinstance(item_ids,list) or not item_ids or any(x not in GEAR_CATALOG for x in item_ids): return jsonify(error="Tài khoản hoặc danh sách vật phẩm không hợp lệ"),400
    with _lock:
        players=read_players();rec=players.get(target)
        if not rec:return jsonify(error="Không tìm thấy người chơi"),404
        _defaults(rec)
        for item_id in item_ids: rec["inventory"].append(_gear_instance(item_id))
        write_players(players)
    return jsonify(ok=True,player=_public(rec))


@app.get("/api/leaderboard")
def leaderboard():
    players = read_players()
    top = sorted(players.values(), key=lambda r: r.get("best", 0), reverse=True)[:10]
    return jsonify(top=[{"name": r["name"], "best": r.get("best", 0), "stage": r.get("bestStage", 0), "boss": r.get("bestBoss", 0), "level": r.get("level",1), "rank": rank_info(r.get("best", 0))["name"], "champion": i==0, "championSet": i==0} for i,r in enumerate(top)])


if __name__ == "__main__":
    print(f"Game khủng long (tác giả: Trí Việt) chạy tại {BASE_URL}")
    print("ADMIN_PASSWORD:", "ĐÃ CẤU HÌNH" if ADMIN_PASSWORD else "CHƯA CẤU HÌNH")
    print("STORAGE_MODE:", STORAGE_MODE, "SUPABASE_TABLE:", SUPABASE_TABLE or "CHƯA CẤU HÌNH", "SUPABASE:", "ĐÃ CẤU HÌNH" if _supabase is not None else "CHƯA CẤU HÌNH")
    app.run(host="0.0.0.0", port=PORT, debug=False)
