"""SQLite ombori: xom javoblar + holat o'zgarishlari tarixi."""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, shop_id INTEGER, status TEXT, raw TEXT,
  first_seen REAL, last_seen REAL);
CREATE TABLE IF NOT EXISTS status_log(order_id INTEGER, status TEXT, seen_at REAL);
CREATE INDEX IF NOT EXISTS ix_log ON status_log(order_id);
CREATE TABLE IF NOT EXISTS docs(kind TEXT, id TEXT, raw TEXT, updated REAL, PRIMARY KEY(kind,id));
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)

    def upsert_order(self, o, now=None):
        now = now or time.time()
        o.pop("deliveryInfo", None)  # xaridorning shaxsiy ma'lumotlari saqlanmaydi
        with self.lock:
            row = self.db.execute("SELECT status FROM orders WHERE id=?", (o["id"],)).fetchone()
            raw = json.dumps(o, ensure_ascii=False)
            if row is None:
                self.db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?)",
                                (o["id"], o.get("shopId"), o.get("status"), raw, now, now))
            else:
                self.db.execute("UPDATE orders SET status=?, raw=?, last_seen=?, shop_id=? WHERE id=?",
                                (o.get("status"), raw, now, o.get("shopId"), o["id"]))
            if row is None or row[0] != o.get("status"):
                self.db.execute("INSERT INTO status_log VALUES(?,?,?)", (o["id"], o.get("status"), now))

    def put_doc(self, kind, id_, obj):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO docs VALUES(?,?,?,?)",
                            (kind, str(id_), json.dumps(obj, ensure_ascii=False), time.time()))

    def get_doc(self, kind, id_):
        with self.lock:
            r = self.db.execute("SELECT raw FROM docs WHERE kind=? AND id=?", (kind, str(id_))).fetchone()
        return json.loads(r[0]) if r else None

    def docs(self, kind):
        with self.lock:
            rows = self.db.execute("SELECT raw FROM docs WHERE kind=?", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def orders(self):
        with self.lock:
            rows = self.db.execute("SELECT raw, first_seen FROM orders").fetchall()
        out = []
        for raw, fs in rows:
            o = json.loads(raw)
            o["_first_seen"] = fs
            out.append(o)
        return out

    def status_since(self):
        """Har bir buyurtma hozirgi holatiga biz qachon birinchi ko'rganimiz."""
        with self.lock:
            rows = self.db.execute(
                "SELECT order_id, MAX(seen_at) FROM status_log GROUP BY order_id").fetchall()
        return dict(rows)

    def set_meta(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
            self.db.commit()

    def get_meta(self, k, default=None):
        with self.lock:
            r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default

    def commit(self):
        with self.lock:
            self.db.commit()
