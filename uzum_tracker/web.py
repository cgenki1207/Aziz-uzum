"""Veb-panel.

Oddiy rejim: faqat shu kompyuterda ochiladi (127.0.0.1), parol yo'q.
Server rejimi (UZUM_SERVER=1): internetga ochiq, APP_PASSWORD bilan kirish talab qilinadi.
"""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, updater
from .auth import COOKIE, LOGIN_HTML, TTL, Auth
from .analyze import build_report
from .api import ApiError, UzumApi
from .sync import run_sync

HTML = Path(__file__).with_name("dashboard.html")


def serve(store, cfg, demo=False, open_browser=False):
    server = bool(os.environ.get("UZUM_SERVER"))
    auth = None
    if server:
        pw = os.environ.get("APP_PASSWORD", "")
        if len(pw) < 8:
            raise SystemExit("Server rejimida APP_PASSWORD muhit o'zgaruvchisi kerak (kamida 8 belgi).")
        auth = Auth(pw)
    state = {"running": False, "log": [], "error": None, "update": False,
             "api": UzumApi(cfg["token"]) if cfg.get("token") and not demo else None,
             "version": updater.local_sha()[:7]}
    wake = threading.Event()

    def do_sync():
        api = state["api"]
        if state["running"] or api is None:
            return
        state.update(running=True, log=[], error=None)
        try:
            run_sync(api, store, cfg.get("shop_id"), cfg.get("days", 0), log=state["log"].append)
        except ApiError as e:
            state["error"] = ("API kaliti noto'g'ri yoki muddati o'tgan — «API kaliti» tugmasi orqali yangilang."
                              if e.bad_key else str(e))
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["running"] = False

    def loop():
        last_check = 0
        while True:
            do_sync()
            if not server and time.time() - last_check > 3 * 3600:      # yangi versiya chiqdimi?
                last_check = time.time()
                state["update"] = updater.check()[0]
            wake.wait(max(cfg.get("sync_interval_min", 30), 5) * 60)
            wake.clear()

    if not demo:
        threading.Thread(target=loop, daemon=True).start()

    def setup(token):
        token = (token or "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if len(token) < 10:
            return 400, {"error": "API kalitini to'liq kiriting."}
        api = UzumApi(token)
        try:
            shops = UzumApi(token, retries=1).shops()
        except ApiError as e:
            msg = ("Kalit noto'g'ri yoki bu kalitga do'kon ruxsati berilmagan." if e.bad_key
                   else str(e) if e.blocked
                   else "Uzum serveriga ulanib bo'lmadi. Internetni tekshirib, qayta urinib ko'ring.")
            return 400, {"error": msg}
        if not shops:
            return 400, {"error": "Bu kalitga bog'langan do'kon topilmadi."}
        config.save(token=token)
        cfg["token"] = token
        state["api"] = api
        wake.set()
        return 200, {"ok": True, "shops": [s.get("name") for s in shops]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json", headers=None, etag=None):
            if not isinstance(body, (bytes, str)):
                body = json.dumps(body, ensure_ascii=False)
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            if etag and self.headers.get("If-None-Match") == etag:
                code, data = 304, b""
            gz = len(data) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or "")
            if gz:
                data = gzip.compress(data, 6)
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache" if etag else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if gz:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            if etag:
                self.send_header("ETag", etag)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if code != 304:
                self.wfile.write(data)

        def host(self):
            return (self.headers.get("Host") or "").split(":")[0].lower()

        def same_origin(self):
            """Boshqa saytlar bu serverga brauzer orqali so'rov yubora olmasligi uchun."""
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            o = urllib.parse.urlsplit(origin).hostname or ""
            return o.lower() == self.host()

        def allowed(self):
            if server:
                return self.same_origin()
            return self.host() in ("localhost", "127.0.0.1") and self.same_origin() \
                and (urllib.parse.urlsplit(self.headers.get("Origin") or "http://localhost").hostname
                     in ("localhost", "127.0.0.1"))

        def ip(self):
            # Oxirgi qiymatni proksi (Google/Caddy) o'zi qo'shadi; birinchisini mijoz soxtalashtirishi mumkin
            fwd = self.headers.get("X-Forwarded-For")
            return fwd.split(",")[-1].strip() if fwd else self.client_address[0]

        def authed(self):
            return auth is None or auth.valid(self.headers.get("Cookie"))

        def https(self):
            return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

        def login_page(self, err="", code=200):
            self.send(code, LOGIN_HTML.replace("__ERR__", err), "text/html")

        def report_etag(self):
            last = (store.get_meta("last_sync") or {}).get("at")
            key = f"{last}|{state['running']}|{state['error']}|{state['update']}|{len(state['log'])}|{state['version']}"
            return '"' + hashlib.sha1(key.encode()).hexdigest()[:16] + '"'

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error": "ruxsat yo'q"})
            path = self.path.split("?")[0]
            if path == "/api/ping":
                return self.send(200, {"app": "uzum-tracker"})
            if not self.authed():
                if path.startswith("/api/"):
                    return self.send(401, {"error": "login"})
                return self.login_page()
            if path == "/":
                self.send(200, HTML.read_bytes(), "text/html")
            elif path == "/api/report":
                if state["api"] is None and not demo:
                    return self.send(200, {"setup": True, "version": state["version"]})
                etag = self.report_etag()
                if self.headers.get("If-None-Match") == etag:
                    return self.send(304, b"", etag=etag)
                rep = build_report(store, cfg)
                rep["sync"] = {"running": state["running"], "error": state["error"],
                               "log": state["log"][-8:], "enabled": not demo}
                rep["version"], rep["update"] = state["version"], state["update"]
                rep["server"] = server
                self.send(200, rep, etag=etag)
            elif path == "/api/wait":
                # Yangilanish tugaguncha (ko'pi bilan 25 s) javobni ushlab turadi. Cloud Run protsessorni faqat
                # so'rov ochiq paytda beradi — panel shu so'rovni takrorlab turgani uchun yangilanish to'xtab qolmaydi.
                end = time.time() + 25
                while state["running"] and time.time() < end:
                    time.sleep(0.5)
                self.send(200, {"running": state["running"]})
            elif path == "/logout":
                self.send(303, b"", "text/plain", headers={
                    "Location": "/", "Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
            else:
                self.send(404, {"error": "topilmadi"})

        def do_POST(self):
            if not self.allowed():
                return self.send(403, {"error": "ruxsat yo'q"})
            if self.path == "/login" and auth is not None:
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                ip = self.ip()
                if auth.blocked(ip):
                    return self.login_page("Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.", 429)
                if not auth.check(ip, (form.get("password") or [""])[0]):
                    return self.login_page("Parol noto'g'ri.", 401)
                secure = "; Secure" if self.https() else ""
                return self.send(303, b"", "text/plain", headers={
                    "Location": "/",
                    "Set-Cookie": f"{COOKIE}={auth.new_session()}; Max-Age={TTL}; Path=/; HttpOnly; SameSite=Strict{secure}"})
            if not self.authed():
                return self.send(401, {"error": "login"})
            if "json" not in (self.headers.get("Content-Type") or ""):
                return self.send(403, {"error": "ruxsat yo'q"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                body = {}
            if self.path == "/api/sync":
                wake.set() if not state["running"] else None
                self.send(200, {})
            elif self.path == "/api/setup" and not demo:
                try:
                    self.send(*setup(body.get("token")))
                except Exception as e:
                    self.send(500, {"error": f"Kutilmagan xato: {e}"})
            elif self.path in ("/api/quit", "/api/restart") and not server:
                self.send(200, {})
                threading.Thread(target=stop, args=(self.path == "/api/restart",), daemon=True).start()
            else:
                self.send(404, {"error": "topilmadi"})

    def stop(restart):
        time.sleep(0.3)
        state["restart"] = restart
        state["srv"].shutdown()      # serve_forever qaytadi, davomi pastda asosiy oqimda

    srv = None
    if server:       # serverda port aniq beriladi, barcha tarmoqlarda tinglaydi
        srv = ThreadingHTTPServer(("0.0.0.0", cfg["port"]), H)
    for port in ([] if server else range(cfg["port"], cfg["port"] + 20)):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit("Bo'sh port topilmadi.")
    state["srv"], state["port"] = srv, srv.server_address[1]
    url = f"http://localhost:{srv.server_address[1]}"
    if server:
        print(f"Uzum tovar kuzatuvi server rejimida ishlayapti, port {state['port']}", flush=True)
    else:
        print(f"\nUzum tovar kuzatuvi ishlayapti:  {url}\n(To'xtatish: paneldagi «To'xtatish» tugmasi yoki Ctrl+C)\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTo'xtatildi.")
    srv.server_close()
    if state.get("restart"):         # yangi jarayon ochilishda o'zini GitHub'dan yangilaydi
        subprocess.Popen([sys.executable, os.path.join(str(config.ROOT), "run.py"), "--no-browser"],
                         env={**os.environ, "PORT": str(state["port"])})
