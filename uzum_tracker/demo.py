"""Namuna (soxta) ma'lumot — API kalitisiz dasturni sinab ko'rish uchun."""
import random
import time
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=5))
NAMES = ["Erkaklar dvoykasi", "Qizlar dvoykasi", "Palto freesize", "Sport kostyum", "Kurtka qishki", "Ko'ylak"]
SIZES = ["S", "M", "L", "XL"]


def iso(t):
    return datetime.fromtimestamp(t, TZ).isoformat()


class DemoApi:
    def __init__(self, seed=7):
        rnd = random.Random(seed)
        now = time.time()
        day = 86400
        self._products, self._skus = [], []
        sid = 5000
        for pi, name in enumerate(NAMES):
            skus = []
            for sz in SIZES:
                sid += 1
                s = {"skuId": sid, "skuTitle": sz, "skuFullTitle": f"{name} {sz}", "article": f"0020012-{pi}-{sz}",
                     "price": 150000 + pi * 40000, "barcode": 1000000000000 + sid,
                     "quantityActive": 0, "quantitySold": 0, "quantityReturned": 0, "quantityDefected": 0}
                skus.append(s)
                self._skus.append((100 + pi, name, s))
            self._products.append({"productId": 100 + pi, "title": name, "skuList": skus})

        self._orders, self._returns, inv_orders = [], [], {}
        ret_items = []
        plan = [("CREATED", 1), ("PACKING", 18), ("PENDING_DELIVERY", 24), ("DELIVERING", 23),
                ("DELIVERED_TO_CUSTOMER_DELIVERY_POINT", 51), ("COMPLETED", 300), ("CANCELED", 120),
                ("RETURNED", 200)]
        oid = 141000000
        for status, n in plan:
            for _ in range(n):
                oid += rnd.randint(1, 900)
                pid, pname, s = rnd.choice(self._skus)
                age = rnd.uniform(0.2, 60)
                created = now - age * day
                o = {"id": oid, "status": status, "shopId": 777, "scheme": "FBS", "price": s["price"],
                     "dateCreated": iso(created), "invoiceNumber": 120000000000 + oid % 500,
                     "orderItems": [{"id": oid * 10, "barcode": s["barcode"], "skuTitle": s["article"],
                                     "title": f"{pname} ({s['skuTitle']})", "amount": 1, "price": s["price"]}]}
                handed = False
                if status in ("DELIVERING",):
                    o["deliveringDate"] = iso(now - rnd.choice([1, 2, 3, 4, 9, 15, 22]) * day)
                elif status == "DELIVERED_TO_CUSTOMER_DELIVERY_POINT":
                    o["deliveringDate"] = iso(created + day)
                    o["deliveredToDeliveryPointDate"] = iso(now - rnd.choice([1, 2, 3, 5, 6, 12, 19]) * day)
                elif status == "COMPLETED":
                    o["deliveringDate"] = iso(created + day)
                    o["completedDate"] = iso(created + 4 * day)
                elif status == "CANCELED":
                    handed = rnd.random() < 0.5
                    o["dateCancelled"] = iso(created + 3 * day)
                    o["cancelReason"] = "CANCELED_BY_CUSTOMER" if handed else "OUT_OF_STOCK"
                    if handed:
                        o["deliveringDate"] = iso(created + day)
                elif status == "RETURNED":
                    handed = True
                    o["deliveringDate"] = iso(created + day)
                    o["returnDate"] = iso(created + 5 * day)
                if handed and rnd.random() < 0.9 and age > 8:   # 10% qaytmaydi = yo'qolgan
                    ret_items.append((created + 9 * day, s, pname))
                self._orders.append(o)
        # qaytarish yuk xatlari: har 25 ta dona bitta yuk xati
        ret_items.sort(key=lambda x: x[0])
        for i in range(0, len(ret_items), 25):
            chunk = ret_items[i:i + 25]
            agg = {}
            for _, s, pname in chunk:
                a = agg.setdefault(s["skuId"], {"id": s["skuId"], "skuId": s["skuId"], "amount": 0,
                                                 "skuTitle": s["article"], "productTitle": pname,
                                                 "purchasePrice": s["price"]})
                a["amount"] += 1
            last = i + 25 >= len(ret_items)
            self._returns.append({"id": 9000 + i // 25, "type": "FBS",
                                  "status": "CREATED" if last else "COMPLETED",
                                  "dateCreated": iso(chunk[0][0]),
                                  "completedDate": None if last else iso(chunk[-1][0] + day),
                                  "returnItems": list(agg.values()),
                                  "totalAmount": sum(a["amount"] for a in agg.values())})

    def shops(self):
        return [{"id": 777, "name": "Namuna do'kon"}]

    def orders(self, shop_ids, status, page, size=50, date_from=None):
        lst = [o for o in self._orders if o["status"] == status]
        return lst[page * size:(page + 1) * size], len(lst)

    def fbs_invoices(self, page, size=20):
        return []

    def fbs_invoice_orders(self, invoice_id):
        return []

    def returns(self, page, size=50):
        return self._returns[page * size:(page + 1) * size]

    def products(self, shop_id, page, size=100):
        return self._products[page * size:(page + 1) * size], len(self._products)

    def supply_invoices(self, page, size=50):
        return []
