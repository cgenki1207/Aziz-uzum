"""Mahalliy veb-panel (faqat shu kompyuterda ochiladi: 127.0.0.1)."""
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, updater
from .analyze import build_report
from .api import ApiError, UzumApi
from .sync import run_sync

HTML = Path(__file__).with_name("dashboard.html")


def serve(store, cfg, demo=False, open_browser=False):
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
                              if e.status in (401, 403) else str(e))
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["running"] = False

    def loop():
        last_check = 0
        while True:
            do_sync()
            if time.time() - last_check > 3 * 3600:      # yangi versiya chiqdimi?
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
            shops = api.shops()
        except ApiError as e:
            msg = ("Kalit noto'g'ri yoki bu kalitga do'kon ruxsati berilmagan." if e.status in (401, 403)
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

        def send(self, code, body, ctype="application/json"):
            if not isinstance(body, (bytes, str)):
                body = json.dumps(body, ensure_ascii=False)
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def local(self):
            """Boshqa saytlar bu serverga so'rov yubora olmasligi uchun."""
            host = (self.headers.get("Host") or "").split(":")[0]
            origin = self.headers.get("Origin")
            ok_origin = origin is None or origin.split("//")[-1].split(":")[0] in ("localhost", "127.0.0.1")
            return host in ("localhost", "127.0.0.1") and ok_origin

        def do_GET(self):
            if not self.local():
                return self.send(403, {"error": "ruxsat yo'q"})
            path = self.path.split("?")[0]
            if path == "/":
                self.send(200, HTML.read_bytes(), "text/html")
            elif path == "/api/report":
                if state["api"] is None and not demo:
                    return self.send(200, {"setup": True, "version": state["version"]})
                rep = build_report(store, cfg)
                rep["sync"] = {"running": state["running"], "error": state["error"],
                               "log": state["log"][-8:], "enabled": not demo}
                rep["version"], rep["update"] = state["version"], state["update"]
                self.send(200, rep)
            else:
                self.send(404, {"error": "topilmadi"})

        def do_POST(self):
            if not self.local() or "json" not in (self.headers.get("Content-Type") or ""):
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
                self.send(*setup(body.get("token")))
            else:
                self.send(404, {"error": "topilmadi"})

    srv = None
    for port in range(cfg["port"], cfg["port"] + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit("Bo'sh port topilmadi.")
    url = f"http://localhost:{srv.server_address[1]}"
    print(f"\nUzum tovar kuzatuvi ishlayapti:  {url}\n(Bu oynani yopmang. To'xtatish: Ctrl+C)\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTo'xtatildi.")
