#!/usr/bin/env python3
"""Uzum tovar kuzatuvi.

  python3 run.py            — panelni ochadi (birinchi marta API kalitini so'raydi)
  python3 run.py sync       — faqat bir marta ma'lumot oladi
  python3 run.py report     — qisqa hisobotni terminalga chiqaradi
  python3 run.py demo       — API kalitisiz, namuna ma'lumot bilan panelni ochadi
"""
import os
import subprocess
import sys

if sys.version_info < (3, 8):
    sys.exit("Python 3.8 yoki undan yangi versiya kerak: https://www.python.org/downloads/")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    cmd = args[0] if args else "serve"

    # Avval yangilanish: kod o'zgargan bo'lsa, yangi kod bilan qaytadan ishga tushamiz.
    if cmd == "serve" and "--no-update" not in flags:
        from uzum_tracker import updater
        if updater.update_on_start():
            sys.exit(subprocess.call([sys.executable, os.path.abspath(__file__), "--no-update"]
                                     + sys.argv[1:]))

    from uzum_tracker import config
    from uzum_tracker.analyze import build_report
    from uzum_tracker.api import UzumApi
    from uzum_tracker.store import Store
    from uzum_tracker.sync import run_sync
    from uzum_tracker.web import serve

    cfg = config.load()

    if cmd == "demo":
        from uzum_tracker.demo import DemoApi
        store = Store(":memory:")
        run_sync(DemoApi(), store, log=lambda *a: None)
        return serve(store, cfg, demo=True, open_browser="--no-browser" not in flags)

    store = Store(config.DATA / "uzum.db")
    if cmd == "sync":
        if not cfg["token"]:
            sys.exit("API kaliti kiritilmagan. Avval `python3 run.py` ni ishga tushirib, kalitni kiriting.")
        sys.exit(1 if run_sync(UzumApi(cfg["token"]), store, cfg["shop_id"], cfg["days"]) else 0)
    elif cmd == "report":
        r = build_report(store, cfg)
        s = r["summary"]
        print(f"Oxirgi yangilanish: {r['last_sync'] or 'hali yoq'}")
        for c in r["status_counts"]:
            print(f"  {c['name']:<36} {c['n']}")
        print(f"\nUzum qabul qilgan: {s['handed']:.0f} dona = sotilgan {s['sold']:.0f} + yo'lda {s['transit']:.0f}"
              f" + punktda {s['pickup']:.0f} + qaytishi kerak {s['owed']:.0f}")
        print(f"Qaytishi kerak {s['owed']:.0f} dan: yuk xati bajarildi {s['ret_done']:.0f}, "
              f"jarayonda {s['ret_pending']:.0f}, HISOBSIZ {s['missing']:.0f} ({s['missing_value']:,.0f} so'm)")
        print(f"  shundan YO'QOLGAN ({cfg['return_days']:.0f} kundan oshgan): {s['lost']:.0f} dona, {s['lost_value']:,.0f} so'm")
        print(f"Buyurtmaga bog'lanmagan ortiqcha qaytgan: {s['ret_extra']:.0f} dona")
        print(f"Qaytish odatda: o'rtacha {s['return_lag_median']} kun, 90% hollarda {s['return_lag_p90']} kungacha")
        print(f"Uzumda yo'lda turib qolgan: {s['late_transit']} buyurtma; punktda turib qolgan: {s['late_pickup']}")
        print(f"Topshirilgan, lekin Uzum sanamagan (shubhali): {s['not_accepted']:.0f} dona, {s['not_accepted_value']:,.0f} so'm")
        for w in r["warnings"]:
            print("! " + w)
    else:
        serve(store, cfg, open_browser="--no-browser" not in flags)


if __name__ == "__main__":
    main()
