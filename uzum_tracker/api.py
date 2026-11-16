"""Uzum Seller OpenAPI mijozi (faqat o'qish — hech narsani o'zgartirmaydi)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .net import context

BASE = "https://api-seller.uzum.uz/api/seller-openapi"

ORDER_STATUSES = [
    "CREATED", "PACKING", "PENDING_DELIVERY", "DELIVERING", "DELIVERED",
    "ACCEPTED_AT_DP", "DELIVERED_TO_CUSTOMER_DELIVERY_POINT", "COMPLETED",
    "CANCELED", "PENDING_CANCELLATION", "RETURNED",
]
FBS_INVOICE_STATUSES = ["CREATED", "ACCEPTANCE_IN_PROGRESS", "CANCELLED", "ACCEPTED"]


class ApiError(Exception):
    def __init__(self, status, path, body):
        # Uzum oldidagi himoya tizimi (Cloudflare) bloklasa, JSON emas HTML sahifa qaytadi
        self.blocked = status in (403, 429) and "<html" in body[:2000].lower()
        super().__init__("Uzum serveri so'rovlarni vaqtincha blokladi. Birozdan keyin qayta urinib ko'ring."
                         if self.blocked else f"HTTP {status} {path}: {body[:300]}")
        self.status = status
        self.bad_key = status in (401, 403) and not self.blocked


def unwrap(data):
    """Ko'p javoblar {payload: ...} ichida keladi."""
    if isinstance(data, dict) and "payload" in data:
        return data["payload"]
    return data


def as_list(data, *keys):
    """Javobdan ro'yxatni topib oladi (ro'yxatning o'zi yoki nomli maydon ichida)."""
    data = unwrap(data)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys + ("content", "items", "data"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


class UzumApi:
    def __init__(self, token, pause=0.4, retries=4):
        self.token = "".join(token.split())
        self.pause = pause
        self.retries = retries

    def get(self, path, **params):
        q = {k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else v)
             for k, v in params.items() if v is not None}
        url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
        last = None
        for attempt in range(5):
            req = urllib.request.Request(url, headers={
                "Authorization": self.token,
                "Accept": "application/json",
                "Accept-Language": "uz",
                "User-Agent": "uzum-tracker/1.0 (seller openapi client)",
            })
            try:
                with urllib.request.urlopen(req, timeout=60, context=context()) as r:
                    body = r.read().decode("utf-8")
                time.sleep(self.pause)
                return json.loads(body) if body.strip() else None
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                last = ApiError(e.code, path, body)
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = ApiError(0, path, str(e))
                if attempt >= self.retries:
                    break
                time.sleep(2 * (attempt + 1))
            except (ValueError, UnicodeError) as e:   # kalit ichida bo'sh joy yoki noto'g'ri belgi
                raise ApiError(401, path, f"kalit formati noto'g'ri: {e}")
        raise last

    # --- usullar ---
    def shops(self):
        return as_list(self.get("/v1/shops"), "shops")

    def orders(self, shop_ids, status, page, size=50, date_from=None):
        p = unwrap(self.get("/v2/fbs/orders", shopIds=shop_ids, status=status,
                            page=page, size=size, dateFrom=date_from)) or {}
        return p.get("orders") or [], p.get("totalAmount")

    def fbs_invoices(self, page, size=20):
        return as_list(self.get("/v1/fbs/invoice", statuses=FBS_INVOICE_STATUSES,
                                page=page, size=size), "invoices")

    def fbs_invoice_orders(self, invoice_id):
        return as_list(self.get(f"/v1/fbs/invoice/{invoice_id}/orders"), "orders")

    def returns(self, page, size=50):
        return as_list(self.get("/v1/return", page=page, size=size), "returns")

    def products(self, shop_id, page, size=100):
        p = unwrap(self.get(f"/v1/product/shop/{shop_id}", page=page, size=size,
                            sortBy="ID", order="ASC", filter="ALL")) or {}
        return p.get("productList") or [], p.get("totalProductsAmount")

    def supply_invoices(self, page, size=50):
        return as_list(self.get("/v1/invoice", page=page, size=size), "invoices")
