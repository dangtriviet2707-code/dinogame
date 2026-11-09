import json
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
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
# Render đứng sau reverse proxy: lấy IP thật từ X-Forwarded-For để giới hạn đăng nhập sai
# theo từng người, không khoá chung cả server theo IP của proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
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
    "champion_helm": {"name":"Vương Miện Quán Quân", "slot":"helmet", "rarity":"exclusive", "img":"/assets/gear/champion_helm.png", "icon":"👑", "stats":{"cooldown":50,"armor":40,"hp":150}},
    "champion_armor": {"name":"Long Giáp Độc Tôn", "slot":"armor", "rarity":"exclusive", "img":"/assets/gear/champion_armor.png", "icon":"🐉", "stats":{"armor":90,"hp":400}},
    "champion_pants": {"name":"Chiến Khố Thiên Vương", "slot":"pants", "rarity":"exclusive", "img":"/assets/gear/champion_pants.png", "icon":"⚜️", "stats":{"hp":300,"armor":40}},
    "champion_boots": {"name":"Thần Hành Vô Ảnh", "slot":"boots", "rarity":"exclusive", "img":"/assets/gear/champion_boots.png", "icon":"💫", "stats":{"speed":60,"hp":120,"armor":20}},
    "long_king_helm": {"name":"Mũ Long Vương", "slot":"helmet", "rarity":"exclusive", "img":"/assets/ocean/long_king_helm.svg", "icon":"👑", "stats":{"cooldown":18,"armor":12,"hp":30}},
    "long_king_armor": {"name":"Áo Long Vương", "slot":"armor", "rarity":"exclusive", "img":"/assets/ocean/long_king_armor.svg", "icon":"🐉", "stats":{"armor":32,"hp":120}},
    "long_king_pants": {"name":"Quần Long Vương", "slot":"pants", "rarity":"exclusive", "img":"/assets/ocean/long_king_pants.svg", "icon":"⚜️", "stats":{"hp":85,"armor":14}},
    "long_king_boots": {"name":"Giày Long Vương", "slot":"boots", "rarity":"exclusive", "img":"/assets/ocean/long_king_boots.svg", "icon":"🌊", "stats":{"speed":18,"hp":35,"armor":8}},
}
GEAR_SLOTS = ("helmet", "armor", "pants", "boots")
RARITY_ORDER = {"common":0, "rare":1, "legendary":2, "exclusive":3}


def _defaults(rec):
    """Bổ sung trường mới mà không làm mất dữ liệu người chơi cũ."""
    rec.setdefault("level", 1); rec.setdefault("experience", 0)
    rec.setdefault("inventory", [])
    rec.setdefault("equipment", {slot: None for slot in GEAR_SLOTS})
    for slot in GEAR_SLOTS: rec["equipment"].setdefault(slot, None)
    rec.setdefault("skills", {"burrow": False, "transform": False, "oceanDragon": False, "oceanUltimate": False})
    rec["skills"].setdefault("oceanDragon", False); rec["skills"].setdefault("oceanUltimate", False)
    rec.setdefault("oceanEventStage", 0); rec.setdefault("oceanEventCompleted", False); rec.setdefault("oceanRewardClaimed", False)
    # Server-authoritative event session. Legacy accounts are migrated lazily and
    # retain all existing player data; no client-supplied stage is ever imported.
    rec.setdefault("oceanEventSession", None)
    rec.setdefault("oceanTitle", None)
    # Migrate legacy records only when the server-confirmed dialogue was completed.
    _legacy_ocean = rec.get("oceanEventSession")
    if rec.get("oceanEventCompleted") and isinstance(_legacy_ocean, dict) and _legacy_ocean.get("dialogueComplete"):
        rec["oceanTitle"] = "Long Vương"
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


def _public(rec, key=None):
    _defaults(rec)
    # Tên luôn lấy từ chính bản ghi của người chơi đang đăng nhập (không dùng tên Admin/mặc định).
    return {
        "id": key, "name": rec.get("name") or key or "Người chơi", "best": rec.get("best",0), "plays": rec.get("plays",0),
        "bestStage": rec.get("bestStage",0), "dodged": rec.get("dodged",0),
        "bestBoss": rec.get("bestBoss",0), "bossKills": rec.get("bossKills",0),
        "ach": rec.get("ach",[]), "rank": rank_info(rec.get("best",0)),
        "level": rec.get("level",1), "experience": rec.get("experience",0),
        "inventory": rec.get("inventory",[]), "equipment": rec.get("equipment",{}),
        "skills": rec.get("skills",{}), "exclusiveItems": rec.get("exclusiveItems",[]),
        "unlockedMaps": rec.get("unlockedMaps",[1]), "home": rec.get("home",{}),
        "stats": _gear_stats(rec), "oceanEventStage": rec.get("oceanEventStage",0),
        "oceanEventCompleted": rec.get("oceanEventCompleted",False), "oceanRewardClaimed": rec.get("oceanRewardClaimed",False),
        "title": rec.get("oceanTitle"),
        "oceanSession": _ocean_public_status(rec),
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


def _character_manifest():
    """Bộ sprite 9 nhân vật (người chơi + 8 boss): một nguồn dữ liệu để mọi client dùng cùng một hình ảnh."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "assets", "characters", "sprites.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


@app.get("/api/config")
def config():
    """Một nguồn dữ liệu chung để index.html dùng: hạng, boss, vật phẩm."""
    return jsonify(
        ranks=[{"id": i, "name": n, "min": at} for i, (n, at) in enumerate(RANKS)],
        bosses=BOSSES,
        items=ITEMS,
        stageAt=STAGE_AT,
        gear=GEAR_CATALOG,
        characters=_character_manifest(),
        oceanEvent={"name":"Sự kiện Đại Dương – Long Vương", "mode":"REALTIME_PLATFORMER", "map":"/assets/ocean/stage_1.webp", "bosses":[
            {"id":"hai_yeu_co_dai","name":"Hải Yêu Cổ Đại","hp":900,"damage":12,"defense":4,"speed":1.0,"cooldown":150},
            {"id":"thuy_hau_tu","name":"Thủy Hầu Tử","hp":1200,"damage":16,"defense":6,"speed":1.15,"cooldown":130},
            {"id":"cuu_dau_hai_xa","name":"Cửu Đầu Hải Xà","hp":1800,"damage":20,"defense":9,"speed":1.25,"cooldown":110},
            {"id":"hai_ma","name":"Hải Ma","hp":2300,"damage":24,"defense":12,"speed":1.1,"cooldown":95},
            {"id":"long_vuong","name":"Long Vương","hp":3200,"damage":30,"defense":16,"speed":1.35,"cooldown":80}],
            "assets":{"equipped":"/assets/ocean/long_vuong_equipped.png","dragon":"/assets/ocean/than_long_form.png"}},
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
        # Biệt danh đã tồn tại (kể cả bản ghi cũ không mật khẩu, trùng tên ở bất kỳ khóa nào)
        # thì không cho đăng ký lại: tránh tài khoản mới "thừa kế" điểm/level của người khác.
        if players.get(key) is not None or _resolve_player(players, name)[1] is not None:
            return jsonify(error="Biệt danh đã có người dùng."), 409
        # Tài khoản mới luôn bắt đầu từ con số 0: 0 điểm, level 1.
        # Điểm chơi khách (guestData) cố ý KHÔNG được chuyển sang tài khoản mới.
        rec = {"best": 0, "plays": 0, "bestBoss": 0, "bossKills": 0, "bestStage": 0,
               "dodged": 0, "ach": [], "firstSeen": now}
        _defaults(rec)
        rec.update(name=name, pw=generate_password_hash(pw), lastSeen=now)
        players[key] = rec
        write_players(players)
    session.permanent = True
    session["key"] = key
    return jsonify(ok=True, player=_public(rec, key), **_admin_state())


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
        rec.setdefault("name", storage_key)
        _defaults(rec)
        rec["lastSeen"] = datetime.now(timezone.utc).isoformat()
        players[storage_key] = rec
        write_players(players)
    _fails.pop(login_key, None)
    # Luôn thay thế phiên cũ bằng đúng tài khoản vừa xác thực. Quyền Admin là một
    # đặc quyền độc lập với danh tính người chơi nên được giữ nguyên khi đổi tài khoản
    # (chỉ nút Đăng xuất mới xoá toàn bộ phiên).
    was_admin, cheat = bool(session.get("admin")), session.get("cheat")
    session.clear()
    session.permanent = True
    session["key"] = storage_key
    if was_admin:
        session["admin"] = True
        session["cheat"] = cheat or dict(CHEAT_DEFAULT)
    return jsonify(ok=True, player=_public(rec, storage_key), **_admin_state())


@app.get("/api/me")
def me():
    key = session.get("key")
    rec = read_players().get(key) if key else None
    if isinstance(rec, dict):
        rec.setdefault("name", key)
    else:
        rec = None
    return jsonify(player=_public(rec, key) if rec else None, **_admin_state())


CHEAT_DEFAULT = {"speed": 0, "god": False, "jump": 1.0, "fire": False}


def _cheat_state():
    raw = session.get("cheat")
    state = dict(CHEAT_DEFAULT)
    if isinstance(raw, dict):
        for k in CHEAT_DEFAULT:
            if k in raw:
                state[k] = raw[k]
    return state


def _admin_state():
    """Trạng thái Admin gửi kèm mọi phản hồi xác thực để client luôn đồng bộ với server."""
    is_admin = bool(session.get("admin"))
    return {"admin": is_admin, "cheat": _cheat_state() if is_admin else dict(CHEAT_DEFAULT)}


def _admin_fail_key():
    return "admin:" + (request.remote_addr or "?")


@app.post("/api/admin")
def admin():
    admin_password = _get_admin_password()
    if not admin_password:
        return jsonify(error="Chưa cấu hình ADMIN_PASSWORD trên server. Hãy thêm biến ADMIN_PASSWORD trong Render Environment."), 503
    fkey = _admin_fail_key()
    count, until = _fails.get(fkey, (0, 0))
    if count >= 5 and time.time() < until:
        return jsonify(error="Sai quá nhiều lần, thử lại sau %d giây." % max(1, int(until - time.time()))), 429
    pw = (request.get_json(silent=True) or {}).get("password") or ""
    if not isinstance(pw, str) or not secrets.compare_digest(pw.encode(), admin_password.encode()):
        _fails[fkey] = (count + 1, time.time() + 300)
        return jsonify(error="Sai mật khẩu admin."), 401
    _fails.pop(fkey, None)
    # Chỉ đánh dấu quyền Admin; KHÔNG đụng tới session["key"] nên không đổi tài khoản người chơi.
    session["admin"] = True
    session["cheat"] = {**CHEAT_DEFAULT, "fire": True}
    session.permanent = True
    return jsonify(ok=True, message="Đã xác thực Admin. Gõ /help để xem lệnh.", **_admin_state())


def _parse_number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


ADMIN_HELP = (
    "/speed n|auto · /god on|off · /jump n · /fire on|off · /fly on|off · "
    "/grant <tên> <itemId...> · /whoami · /status · /off · /help"
)


@app.post("/api/admin/command")
def admin_command():
    """Mọi lệnh Admin đều chạy ở server: kiểm quyền, kiểm tham số, trả kết quả rõ ràng."""
    if not session.get("admin"):
        return jsonify(ok=False, needAuth=True, error="Chưa xác thực Admin. Hãy nhập mật khẩu Admin."), 403
    raw = (request.get_json(silent=True) or {}).get("command")
    if not isinstance(raw, str) or not raw.strip():
        return jsonify(ok=False, error="Lệnh trống. Gõ /help để xem danh sách lệnh."), 400
    raw = raw.strip()[:200]
    parts = raw.split()
    cmd, args = parts[0].lower(), parts[1:]
    arg = args[0].lower() if args else ""
    cheat = _cheat_state()
    effects = {}

    def done(message):
        session["cheat"] = cheat
        return jsonify(ok=True, command=cmd, message=message, cheat=cheat, effects=effects)

    def fail(message, status=400):
        return jsonify(ok=False, command=cmd, error=message, cheat=cheat), status

    if cmd == "/help":
        return done(ADMIN_HELP)
    if cmd == "/speed":
        if arg == "auto":
            cheat["speed"] = 0
            return done("Tốc độ: tự động.")
        n = _parse_number(arg)
        if n is None:
            return fail("Cú pháp: /speed <số 3-30> hoặc /speed auto")
        cheat["speed"] = min(30.0, max(3.0, n))
        return done("Tốc độ cố định: %g" % cheat["speed"])
    if cmd in ("/god", "/fire", "/fly"):
        if arg not in ("", "on", "off"):
            return fail("Cú pháp: %s on|off" % cmd)
        on = arg != "off"
        if cmd == "/fly":
            effects["fly"] = on
            return done("Biến hình khủng long bay: %s (áp dụng ngay khi đang trong ván)." % ("BẬT" if on else "TẮT"))
        cheat["god" if cmd == "/god" else "fire"] = on
        return done("%s: %s" % ("Bất tử" if cmd == "/god" else "Phun lửa", "bật" if on else "tắt"))
    if cmd == "/jump":
        n = _parse_number(arg)
        if n is None:
            return fail("Cú pháp: /jump <số 0.5-3>")
        cheat["jump"] = min(3.0, max(0.5, n))
        return done("Nhảy cao x%g" % cheat["jump"])
    if cmd == "/off":
        cheat = dict(CHEAT_DEFAULT)
        effects["fly"] = False
        return done("Đã tắt mọi lệnh Admin.")
    if cmd == "/whoami":
        key = session.get("key")
        rec = read_players().get(key) if key else None
        who = (rec.get("name") or key) if isinstance(rec, dict) else None
        return done("Phiên Admin đang hoạt động. Người chơi hiện tại: %s." % (who or "khách (chưa đăng nhập)"))
    if cmd == "/status":
        status = _storage_status()
        total = len(read_players())
        return done("Storage: %s%s · kết nối: %s · %d tài khoản." % (
            status["mode"], (" / " + status["table"]) if status.get("table") else "",
            "OK" if status["connected"] else "LỖI", total))
    if cmd == "/grant":
        items = []
        while args and args[-1] in GEAR_CATALOG:
            items.insert(0, args.pop())
        target_name = " ".join(args)
        if not target_name or not items:
            return fail("Cú pháp: /grant <tên người chơi> <itemId> [itemId...]")
        with _lock:
            players = read_players()
            storage_key, rec = _resolve_player(players, target_name)
            if not rec:
                return fail("Không tìm thấy người chơi '%s'." % target_name, 404)
            _defaults(rec)
            for item_id in items:
                rec["inventory"].append(_gear_instance(item_id))
            write_players(players)
        return done("Đã cấp %s cho %s." % (", ".join(items), rec.get("name") or storage_key))
    return fail("Lệnh '%s' không tồn tại. Gõ /help." % cmd)


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
    return jsonify(ok=True,player=_public(rec,key),drops=drops,new=[a for a in rec["ach"] if a not in old],rankUp=rank_info(rec["best"])["id"]>old_rank)


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
    return jsonify(ok=True,player=_public(rec,key))


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
    return jsonify(ok=True,player=_public(rec,key))


# Ocean event state machine. Transitions are deliberately private Python calls,
# not public HTTP endpoints. Giai đoạn 2 must call these only after its trusted
# server-side combat resolver confirms a boss defeat.
OCEAN_STAGES = (
    {"stage": 1, "bossId": "hai_yeu_co_dai", "bossName": "Hải Yêu Cổ Đại"},
    {"stage": 2, "bossId": "thuy_hau_tu", "bossName": "Thủy Hầu Tử"},
    {"stage": 3, "bossId": "cuu_dau_hai_xa", "bossName": "Cửu Đầu Hải Xà"},
    {"stage": 4, "bossId": "hai_ma", "bossName": "Hải Ma"},
    {"stage": 5, "bossId": "long_vuong", "bossName": "Long Vương"},
)
_OCEAN_SERVER_AUTHORITY = object()
_OCEAN_SESSION_TTL_SECONDS = 6 * 60 * 60


def _ocean_public_status(rec):
    """Return a safe read-only projection; never expose internal auth material."""
    event = rec.get("oceanEventSession") if isinstance(rec, dict) else None
    if not isinstance(event, dict):
        return {"active": False, "stage": 0, "status": "INACTIVE", "completedStages": []}
    battle = event.get("battle") if isinstance(event.get("battle"), dict) else {}
    return {
        "active": event.get("status") in ("ACTIVE", "BOSS_IN_PROGRESS", "STAGE_COMPLETED", "EVENT_COMPLETED"),
        "eventId": event.get("eventId"), "stage": int(event.get("stage", 0)),
        "status": event.get("status", "INACTIVE"), "bossId": event.get("bossId"),
        "completedStages": list(event.get("completedStages", [])),
        "startedAt": event.get("startedAt"), "updatedAt": event.get("updatedAt"),
        "dialogueComplete": bool(event.get("dialogueComplete", False)),
        "battle": ({"hp": int(battle.get("playerHp", 0)), "maxHp": int(battle.get("playerMaxHp", 0)),
                    "bossHp": int(battle.get("bossHp", 0)), "bossMaxHp": int(battle.get("bossMaxHp", 0)),
                    "potions": int(battle.get("potions", 0)), "turn": int(battle.get("turn", 0))}
                   if battle else None),
    }


def _ocean_start_session(rec, authority, now=None):
    """Start a session from a trusted server event trigger; caller holds _lock."""
    if authority is not _OCEAN_SERVER_AUTHORITY:
        raise PermissionError("Ocean session may only be started by trusted server logic")
    now = now or datetime.now(timezone.utc)
    if rec.get("oceanRewardClaimed"):
        raise ValueError("Tài khoản đã nhận phần thưởng sự kiện")
    _ocean_expire_if_needed(rec, now=now)
    current = rec.get("oceanEventSession")
    if isinstance(current, dict) and current.get("status") in ("ACTIVE", "BOSS_IN_PROGRESS", "STAGE_COMPLETED", "EVENT_COMPLETED"):
        return current
    event = {
        "eventId": secrets.token_urlsafe(24), "status": "BOSS_IN_PROGRESS",
        "stage": 1, "bossId": OCEAN_STAGES[0]["bossId"], "completedStages": [],
        "dialogueComplete": False, "rewardClaimed": False,
        "startedAt": now.isoformat(), "updatedAt": now.isoformat(),
        "expiresAt": (now.timestamp() + _OCEAN_SESSION_TTL_SECONDS),
        "dialogueStep": 0,
    }
    rec["oceanEventSession"] = event
    rec["oceanEventStage"] = 0
    rec["oceanEventCompleted"] = False
    return event


def _ocean_confirm_boss_defeat(rec, event_id, boss_id, authority, now=None):
    """Advance exactly one stage after trusted combat code confirms HP reached 0."""
    if authority is not _OCEAN_SERVER_AUTHORITY:
        raise PermissionError("Boss defeat must be confirmed by server combat logic")
    event = rec.get("oceanEventSession")
    now = now or datetime.now(timezone.utc)
    if not isinstance(event, dict) or event.get("eventId") != event_id:
        raise ValueError("Phiên sự kiện không hợp lệ")
    if event.get("status") not in ("BOSS_IN_PROGRESS", "ACTIVE"):
        raise ValueError("Phiên sự kiện không ở trạng thái chiến đấu")
    try:
        expires_at = float(event.get("expiresAt", 0))
    except (TypeError, ValueError):
        expires_at = 0
    if expires_at < now.timestamp():
        event["status"] = "EXPIRED"
        event["updatedAt"] = now.isoformat()
        raise ValueError("Phiên sự kiện đã hết hạn")
    stage = int(event.get("stage", 0))
    boss_stage = next((item["stage"] for item in OCEAN_STAGES if item["bossId"] == boss_id), None)
    completed = event.get("completedStages", [])
    if boss_stage is None:
        raise ValueError("Boss không thuộc sự kiện")
    if boss_stage in completed:
        raise ValueError("Boss đã được ghi nhận tiêu diệt")
    if not 1 <= stage <= len(OCEAN_STAGES) or boss_stage != stage:
        raise ValueError("Boss không khớp với ải hiện tại")
    event.setdefault("completedStages", []).append(stage)
    event["updatedAt"] = now.isoformat()
    rec["oceanEventStage"] = stage
    if stage == len(OCEAN_STAGES):
        event["status"] = "EVENT_COMPLETED"
        event["bossId"] = None
        rec["oceanEventCompleted"] = True
    else:
        event["stage"] = stage + 1
        event["bossId"] = OCEAN_STAGES[stage]["bossId"]
        event["status"] = "BOSS_IN_PROGRESS"
    return event


def _ocean_confirm_dialogue(rec, event_id, authority, now=None):
    """Called only by trusted server-side dialogue completion logic."""
    if authority is not _OCEAN_SERVER_AUTHORITY:
        raise PermissionError("Dialogue completion must be confirmed by server logic")
    event = rec.get("oceanEventSession")
    if not isinstance(event, dict) or event.get("eventId") != event_id or event.get("status") != "EVENT_COMPLETED":
        raise ValueError("Sự kiện chưa hoàn thành")
    event["dialogueComplete"] = True
    rec["oceanTitle"] = "Long Vương"
    event["updatedAt"] = (now or datetime.now(timezone.utc)).isoformat()
    return event


def _ocean_persist_transition(player_key, transition, *args, now=None):
    """Run a trusted event transition under the storage lock and persist it.

    The transition callable is never selected from request data. Supabase remains
    authoritative when configured; a failed write raises and is not reported as
    a successful state change.
    """
    if transition not in (_ocean_start_session, _ocean_confirm_boss_defeat, _ocean_confirm_dialogue):
        raise PermissionError("Ocean transition is not allow-listed")
    key = str(player_key or "").strip()
    if not key:
        raise ValueError("Thiếu tài khoản người chơi")
    with _lock:
        players = read_players()
        rec = players.get(key)
        if not isinstance(rec, dict):
            raise KeyError("Không tìm thấy tài khoản")
        _defaults(rec)
        if transition is _ocean_start_session:
            result = transition(rec, _OCEAN_SERVER_AUTHORITY, now=now)
        else:
            result = transition(rec, *args, _OCEAN_SERVER_AUTHORITY, now=now)
        # Do not return success until the durable store accepted the new snapshot.
        write_players(players)
        return result


def _ocean_start_for_player(player_key, now=None):
    return _ocean_persist_transition(player_key, _ocean_start_session, now=now)


def _ocean_confirm_boss_for_player(player_key, event_id, boss_id, now=None):
    return _ocean_persist_transition(player_key, _ocean_confirm_boss_defeat, event_id, boss_id, now=now)


def _ocean_confirm_dialogue_for_player(player_key, event_id, now=None):
    return _ocean_persist_transition(player_key, _ocean_confirm_dialogue, event_id, now=now)


def _ocean_expire_if_needed(rec, now=None):
    """Mark an expired in-progress event explicitly; caller persists if changed."""
    event = rec.get("oceanEventSession")
    if not isinstance(event, dict) or event.get("status") not in ("ACTIVE", "BOSS_IN_PROGRESS", "STAGE_COMPLETED"):
        return False
    now = now or datetime.now(timezone.utc)
    try:
        expires_at = float(event.get("expiresAt", 0))
    except (TypeError, ValueError):
        expires_at = 0
    if expires_at >= now.timestamp():
        return False
    event["status"] = "EXPIRED"
    event["updatedAt"] = now.isoformat()
    return True


@app.get("/api/ocean/progress")
def get_ocean_progress():
    """Read-only progress endpoint; the client cannot write authoritative state."""
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập để xem tiến trình"), 401
    with _lock:
        players = read_players()
        rec = players.get(key)
        if not isinstance(rec, dict):
            return jsonify(error="Không tìm thấy tài khoản"), 404
        _defaults(rec)
        if _ocean_expire_if_needed(rec):
            write_players(players)
        return jsonify(ok=True, progress=_ocean_public_status(rec))


OCEAN_BATTLE_BOSSES = (
    {"id":"hai_yeu_co_dai", "name":"Hải Yêu Cổ Đại", "hp":720, "attack":20, "defense":8, "cooldown":1, "skill":"Xúc Tu Càn Quét"},
    {"id":"thuy_hau_tu", "name":"Thủy Hầu Tử", "hp":920, "attack":24, "defense":12, "cooldown":1, "skill":"Thủy Ảnh Phân Thân"},
    {"id":"cuu_dau_hai_xa", "name":"Cửu Đầu Hải Xà", "hp":1220, "attack":29, "defense":16, "cooldown":2, "skill":"Cửu Đầu Phun Độc"},
    {"id":"hai_ma", "name":"Hải Ma", "hp":1580, "attack":35, "defense":20, "cooldown":2, "skill":"Hắc Triều Ma Vực"},
    {"id":"long_vuong", "name":"Long Vương", "hp":2100, "attack":42, "defense":25, "cooldown":2, "skill":"Long Vương Hải Khiếu"},
)
OCEAN_DIALOGUE = [
    {"speaker":"Long Vương", "text":"Kẻ phàm nhân đã vượt qua năm tầng sóng dữ. Biển sâu đã ghi nhận lòng can đảm của ngươi."},
    {"speaker":"Long Vương", "text":"Bộ giáp Long Vương này là lời thề bảo hộ đại dương. Hãy dùng sức mạnh ấy để giữ cân bằng các thế giới."},
    {"speaker":"Long Vương", "text":"Ta trao cho ngươi bốn bảo vật và bí thuật Thần Long. Từ hôm nay, ngươi là Long Vệ."},
]
OCEAN_REWARD_ITEMS = ("long_king_helm", "long_king_armor", "long_king_pants", "long_king_boots")


def _ocean_new_battle(rec, stage, turn=0):
    boss = OCEAN_BATTLE_BOSSES[stage - 1]
    stats = _gear_stats(rec)
    max_hp = max(300, 300 + int(stats.get("hp", 0)) + (int(rec.get("level", 1)) - 1) * 15)
    return {"playerHp": max_hp, "playerMaxHp": max_hp, "bossHp": boss["hp"], "bossMaxHp": boss["hp"],
            "potions": 3, "turn": int(turn), "guard": False, "lastActionAt": time.time(), "log": []}


def _ocean_battle_public(event):
    stage = max(1, min(5, int(event.get("stage", 1))))
    boss = OCEAN_BATTLE_BOSSES[stage - 1]
    b = event.get("battle") or {}
    return {"eventId": event.get("eventId"), "stage": stage, "status": event.get("status"),
            "boss": {"id": boss["id"], "name": boss["name"], "skill": boss["skill"], "defense": boss["defense"]},
            "hp": int(b.get("playerHp", 0)), "maxHp": int(b.get("playerMaxHp", 0)),
            "bossHp": int(b.get("bossHp", 0)), "bossMaxHp": int(b.get("bossMaxHp", 0)),
            "potions": int(b.get("potions", 0)), "turn": int(b.get("turn", 0)),
            "completedStages": list(event.get("completedStages", []))}


def _ocean_player_locked(key):
    players = read_players()
    rec = players.get(key)
    if not isinstance(rec, dict):
        return players, None
    _defaults(rec)
    return players, rec


@app.post("/api/ocean/encounter")
def ocean_encounter():
    """Roll event only after an eligible in-game boss defeat; never starts from the lobby."""
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập để tham gia sự kiện Đại Dương"), 401
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        if rec.get("oceanRewardClaimed"):
            return jsonify(error="Bạn đã nhận trọn bộ phần thưởng Long Vương"), 409
        current = rec.get("oceanEventSession")
        if isinstance(current, dict) and current.get("status") in ("BOSS_IN_PROGRESS", "ACTIVE"):
            return jsonify(ok=True, resumed=True, triggered=True, progress=_ocean_public_status(rec))
        now = time.time()
        last = float(rec.get("oceanEncounterLastAt", 0) or 0)
        wait = int(30 - (now - last))
        if wait > 0:
            return jsonify(ok=True, triggered=False, message="Sóng biển chưa kích hoạt lần này.", retryAfter=wait)
        rec["oceanEncounterLastAt"] = now
        if secrets.randbelow(100) >= 50:
            write_players(players)
            return jsonify(ok=True, triggered=False, message="Sóng biển đã lắng xuống. Bạn chưa gặp biến cố Đại Dương lần này.")
        event = _ocean_start_session(rec, _OCEAN_SERVER_AUTHORITY)
        event["mode"] = "REALTIME_PLATFORMER"
        event["battle"] = None
        event["status"] = "BOSS_IN_PROGRESS"
        write_players(players)
        return jsonify(ok=True, triggered=True, message="CƠN SÓNG LỚN ĐÃ ẬP TỚI!", progress=_ocean_public_status(rec))


@app.post("/api/ocean/realtime/defeat")
def ocean_realtime_defeat():
    """Record one sequential real-time boss defeat against the active server session."""
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập"), 401
    payload = request.get_json(silent=True) or {}
    event_id, stage, boss_id = payload.get("eventId"), payload.get("stage"), payload.get("bossId")
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("status") != "BOSS_IN_PROGRESS":
            return jsonify(error="Không có sự kiện đang diễn ra"), 409
        if not isinstance(event_id, str) or event_id != event.get("eventId"):
            return jsonify(error="Phiên sự kiện không hợp lệ"), 409
        if type(stage) is not int or stage != int(event.get("stage", 0)):
            return jsonify(error="Thứ tự Boss không hợp lệ"), 409
        expected = OCEAN_STAGES[stage-1]["bossId"] if 1 <= stage <= 5 else None
        if boss_id != expected:
            return jsonify(error="Boss không khớp với màn hiện tại"), 409
        _ocean_confirm_boss_defeat(rec, event_id, boss_id, _OCEAN_SERVER_AUTHORITY)
        event["mode"] = "REALTIME_PLATFORMER"
        event["battle"] = None
        write_players(players)
        return jsonify(ok=True, complete=event.get("status") == "EVENT_COMPLETED",
                       progress=_ocean_public_status(rec))


@app.post("/api/ocean/realtime/fail")
def ocean_realtime_fail():
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập"), 401
    payload = request.get_json(silent=True) or {}
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("eventId") != payload.get("eventId") or event.get("status") != "BOSS_IN_PROGRESS":
            return jsonify(error="Phiên sự kiện không hợp lệ"), 409
        event["status"] = "FAILED"
        event["battle"] = None
        event["updatedAt"] = datetime.now(timezone.utc).isoformat()
        write_players(players)
    return jsonify(ok=True, status="FAILED")


@app.post("/api/ocean/action")
def ocean_action():
    """Turn-based event combat: client submits intent only; server owns HP/damage/turns."""
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập"), 401
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").lower()
    expected_turn = payload.get("turn")
    expected_event_id = payload.get("eventId")
    if action not in ("attack", "guard", "heal"):
        return jsonify(error="Hành động không hợp lệ"), 400
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("status") != "BOSS_IN_PROGRESS":
            return jsonify(error="Không có trận Đại Dương đang diễn ra"), 409
        if not isinstance(expected_event_id, str) or expected_event_id != event.get("eventId"):
            return jsonify(error="Phiên chiến đấu không còn hợp lệ"), 409
        if _ocean_expire_if_needed(rec):
            write_players(players)
            return jsonify(error="Phiên sự kiện đã hết hạn"), 410
        battle = event.get("battle")
        if not isinstance(battle, dict):
            return jsonify(error="Dữ liệu trận đấu không hợp lệ"), 409
        turn = int(battle.get("turn", 0))
        if type(expected_turn) is not int or expected_turn != turn:
            return jsonify(error="Lượt đấu đã thay đổi; hãy đồng bộ lại trận đấu", battle=_ocean_battle_public(event)), 409
        stage = int(event.get("stage", 1)); boss = OCEAN_BATTLE_BOSSES[stage - 1]
        stats = _gear_stats(rec); level = int(rec.get("level", 1))
        log = []
        if action == "attack":
            raw = 230 + level * 8 + int(stats.get("speed", 0)) * 1.2
            damage = max(25, int(raw - boss["defense"] + secrets.randbelow(31) - 10))
            if secrets.randbelow(100) < 12:
                damage = int(damage * 1.7); log.append("Bạo kích!")
            battle["bossHp"] = max(0, int(battle["bossHp"]) - damage)
            log.append(f"Bạn gây {damage} sát thương.")
        elif action == "guard":
            battle["guard"] = True
            log.append("Bạn dựng thế thủ, giảm 65% sát thương đòn kế tiếp.")
        else:
            if int(battle.get("potions", 0)) <= 0:
                return jsonify(error="Bạn đã dùng hết bình hồi phục"), 409
            battle["potions"] -= 1
            heal = max(50, int(battle["playerMaxHp"] * .35))
            before = int(battle["playerHp"])
            battle["playerHp"] = min(int(battle["playerMaxHp"]), before + heal)
            log.append(f"Hồi phục {battle['playerHp'] - before} HP.")
        if int(battle["bossHp"]) <= 0:
            _ocean_confirm_boss_defeat(rec, event["eventId"], boss["id"], _OCEAN_SERVER_AUTHORITY)
            log.append(f"Đã đánh bại {boss['name']}!")
            if event["status"] == "BOSS_IN_PROGRESS":
                event["battle"] = _ocean_new_battle(rec, int(event["stage"]), turn=turn + 1)
                log.append(f"Ải tiếp theo: {OCEAN_BATTLE_BOSSES[int(event['stage']) - 1]['name']}.")
            else:
                event["battle"] = None
                log.append("Năm ải đã hoàn tất. Hãy gặp Long Vương để nghe lời chúc phúc.")
        else:
            # Server resolves boss turn; no client-provided HP, damage or hit result is trusted.
            turn_no = turn + 1
            multiplier = 1.0 + (0.12 if turn_no % max(1, boss["cooldown"]) == 0 else 0)
            incoming = int(boss["attack"] * multiplier + secrets.randbelow(13) - 6)
            if battle.get("guard"):
                incoming = int(incoming * .35); battle["guard"] = False
            incoming = max(4, incoming - int(stats.get("armor", 0)) // 3)
            battle["playerHp"] = max(0, int(battle["playerHp"]) - incoming)
            log.append(f"{boss['skill']}: bạn nhận {incoming} sát thương.")
            battle["turn"] = turn_no
            if battle["playerHp"] <= 0:
                event["status"] = "FAILED"
                event["battle"] = battle
                log.append("Bạn đã gục ngã. Hãy quay lại sau khi hồi phục.")
        battle["log"] = (battle.get("log", []) + log)[-8:]
        event["updatedAt"] = datetime.now(timezone.utc).isoformat()
        write_players(players)
        return jsonify(ok=True, battle=_ocean_battle_public(event), log=log,
                       progress=_ocean_public_status(rec), eventStatus=event.get("status"))


@app.get("/api/ocean/dialogue")
def ocean_dialogue():
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập"), 401
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("status") != "EVENT_COMPLETED":
            return jsonify(error="Bạn cần đánh bại đủ năm Boss trước"), 409
        step = int(event.get("dialogueStep", 0))
        return jsonify(ok=True, step=step, total=len(OCEAN_DIALOGUE), line=OCEAN_DIALOGUE[min(step, len(OCEAN_DIALOGUE)-1)] if step < len(OCEAN_DIALOGUE) else None)


@app.post("/api/ocean/dialogue/next")
def ocean_dialogue_next():
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập"), 401
    payload = request.get_json(silent=True) or {}
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("status") != "EVENT_COMPLETED":
            return jsonify(error="Sự kiện chưa hoàn thành"), 409
        step = int(event.get("dialogueStep", 0))
        if payload.get("step") != step:
            return jsonify(error="Hội thoại đã thay đổi; hãy tải lại"), 409
        if step < len(OCEAN_DIALOGUE):
            event["dialogueStep"] = step + 1
        if event["dialogueStep"] >= len(OCEAN_DIALOGUE):
            _ocean_confirm_dialogue(rec, event["eventId"], _OCEAN_SERVER_AUTHORITY)
        event["updatedAt"] = datetime.now(timezone.utc).isoformat()
        write_players(players)
        return jsonify(ok=True, step=int(event["dialogueStep"]), total=len(OCEAN_DIALOGUE),
                       complete=bool(event.get("dialogueComplete")),
                       line=OCEAN_DIALOGUE[event["dialogueStep"]] if event["dialogueStep"] < len(OCEAN_DIALOGUE) else None)


@app.post("/api/ocean/claim")
def claim_ocean_reward():
    key = session.get("key")
    if not key:
        return jsonify(error="Cần đăng nhập để nhận thưởng sự kiện"), 401
    with _lock:
        players, rec = _ocean_player_locked(key)
        if not rec:
            return jsonify(error="Không tìm thấy tài khoản"), 404
        if rec.get("oceanRewardClaimed"):
            return jsonify(ok=True, alreadyClaimed=True, player=_public(rec, key))
        event = rec.get("oceanEventSession")
        if not isinstance(event, dict) or event.get("status") != "EVENT_COMPLETED" or not event.get("dialogueComplete"):
            return jsonify(error="Hãy hoàn thành năm ải và hội thoại Long Vương trước"), 409
        inventory = rec.setdefault("inventory", [])
        owned = {item.get("itemId") for item in inventory if isinstance(item, dict)}
        for item_id in OCEAN_REWARD_ITEMS:
            if item_id not in owned:
                inventory.append(_gear_instance(item_id))
        rec.setdefault("skills", {})["oceanDragon"] = True
        rec["skills"]["oceanUltimate"] = True
        rec["oceanRewardClaimed"] = True
        event["rewardClaimed"] = True
        event["updatedAt"] = datetime.now(timezone.utc).isoformat()
        write_players(players)
        return jsonify(ok=True, alreadyClaimed=False, player=_public(rec, key),
                       rewards=[GEAR_CATALOG[x]["name"] for x in OCEAN_REWARD_ITEMS],
                       skills=["Thần Long", "Nộ Hải Thần Phong"])


@app.post("/api/ocean/progress")
def save_ocean_progress():
    """Reject client-authored progress mutations, including eventId/stage claims."""
    if not session.get("key"):
        return jsonify(error="Cần đăng nhập để lưu tiến trình"), 401
    return jsonify(error="Client không được phép thay đổi tiến trình sự kiện; máy chủ tự quản lý."), 409


VIP_CODES={"/AOVIP27":"champion_armor","/QUANVIP27":"champion_pants","/GIAYVIP27":"champion_boots","/MUVIP27":"champion_helm"}


@app.post("/api/redeem")
def redeem_code():
    key=session.get("key")
    if not key:return jsonify(error="Cần đăng nhập"),401
    code=((request.get_json(silent=True) or {}).get("code") or "").strip().upper().replace(" ","")
    if code and not code.startswith("/") and "/"+code in VIP_CODES:code="/"+code
    if code in VIP_CODES:
        with _lock:
            players=read_players();rec=players.get(key)
            if not rec:return jsonify(error="Không tìm thấy tài khoản"),404
            _defaults(rec);used=rec.setdefault("usedCodes",[])
            if code in used:return jsonify(error="Bạn đã nhận trang bị này rồi"),409
            used.append(code);rec["inventory"].append(_gear_instance(VIP_CODES[code]))
            write_players(players)
        return jsonify(ok=True,player=_public(rec,key),item=VIP_CODES[code])
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
    return jsonify(ok=True,player=_public(rec,key))


CHAT_FILE = os.path.join(DATA_DIR, "chat.json")
CHAT_TABLE = "dino_chat_messages"


def _chat_local_read():
    try:
        with open(CHAT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _chat_local_append(msg):
    with _lock:
        messages = _chat_local_read()
        messages.append(msg)
        messages = messages[-200:]
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CHAT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)
        os.replace(tmp, CHAT_FILE)


def _chat_clean(m):
    return {"name": str(m.get("name") or "Người chơi")[:40], "message": str(m.get("message") or "")[:240],
            "title": "Long Vương" if m.get("title") == "Long Vương" else None,
            "created_at": str(m.get("created_at") or "")}


@app.get("/api/chat")
def get_chat():
    """Đọc chat thế giới. Supabase là nguồn chính; nếu bảng chưa tạo/lỗi mạng thì tự dùng JSON local
    (không còn trả lỗi 503 làm khung chat trống)."""
    messages, storage, warn = [], "json", None
    if _supabase is not None:
        try:
            result = (_supabase.table(CHAT_TABLE).select("name,message,created_at")
                      .order("created_at", desc=True).limit(50).execute())
            messages, storage = list(reversed(result.data or [])), "supabase"
        except Exception as exc:
            warn = "Chat Supabase chưa sẵn sàng (hãy chạy supabase_schema.sql để tạo bảng %s): %s" % (CHAT_TABLE, str(exc)[:160])
            print("[chat] đọc Supabase lỗi:", exc)
    if storage != "supabase":
        messages = _chat_local_read()
    messages = [_chat_clean(m) for m in messages[-50:]]
    # Enrich public chat names from player records; no new Supabase column required.
    try:
        _chat_titles = {}
        for _player in read_players().values():
            if isinstance(_player, dict):
                _title = _player.get("oceanTitle")
                _session = _player.get("oceanEventSession")
                if _title == "Long Vương" or (isinstance(_session, dict) and _session.get("dialogueComplete")):
                    _chat_titles[str(_player.get("name") or "")] = "Long Vương"
        for _message in messages:
            _message["title"] = _chat_titles.get(_message.get("name") or "") or _message.get("title")
    except Exception:
        pass
    out = {"messages": messages, "storage": storage}
    if warn:
        out["warning"] = warn
    return jsonify(out)


@app.post("/api/chat")
def send_chat():
    key = session.get("key")
    if not key:
        return jsonify(error="Đăng nhập để gửi tin nhắn"), 401
    text = (request.get_json(silent=True) or {}).get("message", "")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 240:
        return jsonify(error="Tin nhắn phải từ 1-240 ký tự"), 400
    now_ts = time.time()
    if now_ts - _chat_last.get(key, 0) < 2:
        return jsonify(error="Bạn gửi quá nhanh. Hãy chờ 2 giây."), 429
    _chat_last[key] = now_ts
    rec = read_players().get(key)
    name = (rec.get("name") if isinstance(rec, dict) else None) or key or "Người chơi"
    msg = {"name": name, "message": text.strip(), "created_at": datetime.now(timezone.utc).isoformat()}
    if _supabase is not None:
        try:
            _supabase.table(CHAT_TABLE).insert(msg).execute()
            return jsonify(ok=True, message=msg, storage="supabase")
        except Exception as exc:
            print("[chat] ghi Supabase lỗi, chuyển sang JSON local:", exc)
    _chat_local_append(msg)
    return jsonify(ok=True, message=msg, storage="json")


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
    return jsonify(ok=True,player=_public(rec,target))


@app.get("/api/leaderboard")
def leaderboard():
    players = read_players()
    valid = [(k, r) for k, r in players.items() if isinstance(r, dict)]
    for k, r in valid:
        r.setdefault("name", k)
    top = sorted((r for _, r in valid), key=lambda r: r.get("best", 0), reverse=True)[:10]
    return jsonify(top=[{"name": r["name"], "title": (r.get("oceanTitle") or ("Long Vương" if r.get("oceanEventCompleted") and isinstance(r.get("oceanEventSession"), dict) and r["oceanEventSession"].get("dialogueComplete") else None)), "best": r.get("best", 0), "stage": r.get("bestStage", 0), "boss": r.get("bestBoss", 0), "level": r.get("level",1), "rank": rank_info(r.get("best", 0))["name"], "champion": i==0, "championSet": i==0} for i,r in enumerate(top)])


if __name__ == "__main__":
    print(f"Game khủng long (tác giả: Trí Việt) chạy tại {BASE_URL}")
    print("ADMIN_PASSWORD:", "ĐÃ CẤU HÌNH" if ADMIN_PASSWORD else "CHƯA CẤU HÌNH")
    print("STORAGE_MODE:", STORAGE_MODE, "SUPABASE_TABLE:", SUPABASE_TABLE or "CHƯA CẤU HÌNH", "SUPABASE:", "ĐÃ CẤU HÌNH" if _supabase is not None else "CHƯA CẤU HÌNH")
    app.run(host="0.0.0.0", port=PORT, debug=False)
