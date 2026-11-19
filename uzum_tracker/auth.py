"""Server rejimi uchun parol bilan kirish.

Panel internetga chiqqanda hamma narsa (sotuv ma'lumotlari, API kaliti kiritish) faqat
parolni bilgan odamga ochiq bo'lishi kerak. Parol APP_PASSWORD muhit o'zgaruvchisidan olinadi.
"""
import hashlib
import hmac
import os
import secrets
import threading
import time

from .config import DATA

COOKIE = "uzt_session"
TTL = 30 * 86400                 # 30 kun eslab qoladi
WINDOW, PER_IP, GLOBAL = 900, 8, 40   # 15 daqiqada: bitta IP dan 8, jami 40 xato urinish


class Auth:
    def __init__(self, password):
        self.password = password.encode("utf-8")
        # Cloud Run'da disk har uyg'onganda tozalanadi, shuning uchun u yerda tuz SESSION_SECRET'dan olinadi —
        # aks holda server har uxlab turganda parolni qayta kiritishga to'g'ri kelardi.
        salt = os.environ.get("SESSION_SECRET", "")
        if not salt:
            salt_file = DATA / "session_salt"
            DATA.mkdir(parents=True, exist_ok=True)
            if not salt_file.exists():
                salt_file.write_text(secrets.token_hex(32))
            salt = salt_file.read_text()
        # Parol o'zgarsa eski sessiyalar o'z-o'zidan bekor bo'ladi
        self.key = hashlib.sha256(salt.encode() + b"|" + self.password).digest()
        self.fails = []          # (vaqt, ip)
        self.lock = threading.Lock()

    def _sign(self, exp):
        return hmac.new(self.key, str(exp).encode(), hashlib.sha256).hexdigest()

    def new_session(self):
        exp = int(time.time()) + TTL
        return f"{exp}.{self._sign(exp)}"

    def valid(self, cookie_header):
        for part in (cookie_header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                exp, _, sig = v.partition(".")
                if exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, self._sign(exp)):
                    return True
        return False

    def blocked(self, ip):
        now = time.time()
        with self.lock:
            self.fails = [f for f in self.fails if now - f[0] < WINDOW]
            return len(self.fails) >= GLOBAL or sum(1 for f in self.fails if f[1] == ip) >= PER_IP

    def check(self, ip, password):
        ok = hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).digest(),
                                 hashlib.sha256(self.password).digest())
        if not ok:
            with self.lock:
                self.fails.append((time.time(), ip))
            time.sleep(1)        # taxmin qilishni sekinlashtirish
        return ok


LOGIN_HTML = """<!doctype html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kirish — Uzum tovar kuzatuvi</title>
<style>
:root{--bg:#f3f3f7;--card:#fff;--ink:#17171c;--mute:#6b6b78;--line:#e4e4ec;--accent:#7000ff;--bad:#d92d20}
@media (prefers-color-scheme:dark){:root{--bg:#121216;--card:#1c1c23;--ink:#f0f0f5;--mute:#9a9aa8;--line:#2e2e39;--accent:#a871ff;--bad:#ff7066}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;
background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
form{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:28px;width:100%;max-width:380px}
h1{font-size:20px;margin:0 0 4px}p{color:var(--mute);margin:0 0 18px;font-size:14px}
input{width:100%;font:inherit;padding:12px 14px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);margin-bottom:12px}
button{width:100%;font:inherit;font-weight:600;border:0;border-radius:10px;padding:12px;background:var(--accent);color:#fff;cursor:pointer}
.err{color:var(--bad);font-size:14px;min-height:20px;margin-bottom:6px}
</style></head><body>
<form method="post" action="/login">
<h1>Uzum tovar kuzatuvi</h1><p>Davom etish uchun parolni kiriting.</p>
<input type="password" name="password" autocomplete="current-password" placeholder="Parol" autofocus required>
<div class="err">__ERR__</div><button>Kirish</button>
</form></body></html>"""
