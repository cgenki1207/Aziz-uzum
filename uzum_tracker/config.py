"""Sozlamalar va ma'lumotlar foydalanuvchining uy papkasida saqlanadi (~/.uzum-tracker),
shuning uchun dastur yangilanganda yoki qayta o'rnatilganda ular yo'qolmaydi."""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("UZUM_TRACKER_HOME") or Path.home() / ".uzum-tracker")
FILE = DATA / "config.json"

DEFAULTS = {
    "token": "", "shop_id": None, "days": 0, "port": 4000, "sync_interval_min": 30,
    "transit_days": 7, "pickup_days": 10, "return_days": 14, "return_types": ["FBS"],
}
ENV = {  # eski .env fayli bilan moslik
    "UZUM_API_TOKEN": "token", "UZUM_SHOP_ID": "shop_id", "SYNC_DAYS": "days", "PORT": "port",
    "SYNC_INTERVAL_MIN": "sync_interval_min", "TRANSIT_DAYS": "transit_days",
    "PICKUP_DAYS": "pickup_days", "RETURN_DAYS": "return_days", "RETURN_TYPES": "return_types",
}


def _read_dotenv():
    out = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load():
    DATA.mkdir(parents=True, exist_ok=True)
    old_db = ROOT / "uzum.db"          # eski joydagi bazani ko'chirish
    if old_db.exists() and not (DATA / "uzum.db").exists():
        shutil.move(str(old_db), str(DATA / "uzum.db"))
    cfg = dict(DEFAULTS)
    env = {**_read_dotenv(), **{k: v for k, v in os.environ.items() if k in ENV}}
    saved = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
    for src in ({ENV[k]: v for k, v in env.items() if k in ENV and v != ""}, saved):
        for k, v in src.items():
            if k not in DEFAULTS or v in ("", None):
                continue
            d = DEFAULTS[k]
            try:
                if k == "return_types":
                    v = v if isinstance(v, list) else [t.strip() for t in str(v).split(",") if t.strip()]
                elif isinstance(d, (int, float)) and not isinstance(d, bool):
                    v = type(d)(float(v))
            except ValueError:
                continue
            cfg[k] = v
    if os.environ.get("PORT"):          # tashqaridan berilgan port ustun
        cfg["port"] = int(os.environ["PORT"])
    return cfg


def save(**updates):
    DATA.mkdir(parents=True, exist_ok=True)
    saved = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
    saved.update(updates)
    FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(FILE, 0o600)           # kalit faqat shu foydalanuvchiga ko'rinsin
    except OSError:
        pass
