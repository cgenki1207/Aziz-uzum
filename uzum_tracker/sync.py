"""Uzum API'dan hamma kerakli ma'lumotni olib, omborga yozadi."""
import time

from .api import ORDER_STATUSES


def _pages(fetch, size, max_pages=2000):
    """fetch(page) -> ro'yxat; bo'sh yoki to'liqmas sahifa kelguncha aylanadi."""
    for page in range(max_pages):
        items = fetch(page)
        if not items:
            return
        yield from items
        if len(items) < size:
            return


def run_sync(api, store, shop_id=None, days=0, log=print):
    started = time.time()
    errors = []

    def step(name, fn):
        try:
            n = fn()
            log(f"  ✓ {name}: {n}")
        except Exception as e:  # bitta bo'lim yiqilsa qolganlari davom etadi
            errors.append(f"{name}: {e}")
            log(f"  ✗ {name}: {e}")

    shops = api.shops()
    store.set_meta("shops", shops)
    shop_ids = [int(shop_id)] if shop_id else [s["id"] for s in shops]
    if not shop_ids:
        raise RuntimeError("Do'kon topilmadi — API kaliti to'g'riligini tekshiring.")
    log(f"Do'konlar: {shop_ids}")
    date_from = int(time.time() - days * 86400) if days else None

    def sync_orders():
        n = 0
        for st in ORDER_STATUSES:
            for o in _pages(lambda p: api.orders(shop_ids, st, p, 50, date_from)[0], 50):
                o.setdefault("status", st)
                store.upsert_order(o, started)
                n += 1
            store.commit()
        return n

    def sync_fbs_invoices():
        n = 0
        for inv in _pages(lambda p: api.fbs_invoices(p, 20), 20):
            st = (inv.get("status") or {})
            st = st.get("value") if isinstance(st, dict) else st
            old = store.get_doc("fbs_invoice", inv["id"])
            final = st in ("ACCEPTED", "CANCELLED")
            if not (old and old.get("_final") and old.get("_orders") is not None):
                inv["_orders"] = api.fbs_invoice_orders(inv["id"])
            else:
                inv["_orders"] = old["_orders"]
            inv["_final"] = final
            inv["_status"] = st
            store.put_doc("fbs_invoice", inv["id"], inv)
            n += 1
        store.commit()
        return n

    def sync_returns():
        n = 0
        for r in _pages(lambda p: api.returns(p, 50), 50):
            store.put_doc("return", r["id"], r)
            n += 1
        store.commit()
        return n

    def sync_products():
        n = 0
        for sid in shop_ids:
            page = got = 0
            while True:
                items, total = api.products(sid, page, 100)
                for p in items:
                    p["_shopId"] = sid
                    store.put_doc("product", p["productId"], p)
                got += len(items)
                page += 1
                if not items or len(items) < 100 or (total and got >= total):
                    break
            n += got
        store.commit()
        return n

    def sync_supply():
        n = 0
        for inv in _pages(lambda p: api.supply_invoices(p, 50), 50):
            store.put_doc("supply_invoice", inv["id"], inv)
            n += 1
        store.commit()
        return n

    step("Buyurtmalar", sync_orders)
    step("FBS yuk xatlari", sync_fbs_invoices)
    step("Qaytarish yuk xatlari", sync_returns)
    step("Mahsulotlar (SKU)", sync_products)
    step("Ta'minot yuk xatlari (FBO)", sync_supply)

    store.set_meta("last_sync", {"at": time.time(), "took": round(time.time() - started, 1),
                                 "errors": errors})
    return errors
