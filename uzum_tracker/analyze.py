"""Tahlil: Uzumga topshirilgan har bir dona tovar qayerda ekanini hisoblaydi.

Asosiy g'oya (FBS):
  Uzum qabul qilgan dona = sotilgan + yo'lda + punktda kutyapti + sizga qaytishi kerak
  "Sizga qaytishi kerak" bo'lgan donalar qaytarish yuk xatlari bilan sana tartibida
  solishtiriladi. Yuk xati bilan yopilmagan dona = hisobsiz (yo'qolgan bo'lishi mumkin).
"""
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

TASHKENT = timezone(timedelta(hours=5))
DAY = 86400

IN_TRANSIT = {"ACCEPTED_AT_DP", "DELIVERING", "DELIVERED"}
AT_PICKUP = {"DELIVERED_TO_CUSTOMER_DELIVERY_POINT"}
SOLD = {"COMPLETED"}
BACK = {"CANCELED", "PENDING_CANCELLATION", "RETURNED"}

STATUS_UZ = {
    "CREATED": "Yangilar",
    "PACKING": "Yig'ishdagilar",
    "PENDING_DELIVERY": "Ta'minlashda",
    "ACCEPTED_AT_DP": "Uzum qabul qilgan",
    "DELIVERING": "Yo'lda (xaridor punktiga)",
    "DELIVERED": "Yetkazildi",
    "DELIVERED_TO_CUSTOMER_DELIVERY_POINT": "Topshirishni kutyapti",
    "COMPLETED": "Topshirilganlar",
    "CANCELED": "Bekor qilinganlar",
    "PENDING_CANCELLATION": "Bekor qilinmoqda",
    "RETURNED": "Qaytarishlar",
}
RETURN_UZ = {"COMPLETED": "Bajarildi", "ASSEMBLED": "Yig'ilgan (olib ketishga tayyor)",
             "IN_PROGRESS": "Yig'ilmoqda", "CREATED": "Yaratilgan"}


def ts(v):
    """Sana (epoch son, ISO matn yoki 31.12.2026) -> epoch soniya."""
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e11 else float(v)
    s = str(v).strip()
    if s.isdigit():
        return ts(int(s))
    for parse in (lambda: datetime.fromisoformat(s.replace("Z", "+00:00")),
                  lambda: datetime.strptime(s, "%d.%m.%Y")):
        try:
            d = parse()
            return (d if d.tzinfo else d.replace(tzinfo=TASHKENT)).timestamp()
        except ValueError:
            pass
    return None


def fmt(t):
    return datetime.fromtimestamp(t, TASHKENT).strftime("%d.%m.%Y %H:%M") if t else ""


def norm(s):
    return " ".join(str(s or "").lower().split())


def build_report(store, cfg, now=None):
    now = now or time.time()
    orders = store.orders()
    by_id = {o["id"]: o for o in orders}
    since_seen = store.status_since()
    returns = store.docs("return")
    fbs_invoices = store.docs("fbs_invoice")
    warnings = []

    # ---------- SKU katalogi: shtrix-kod / nom -> skuId ----------
    sku_info, by_barcode, by_title = {}, {}, {}

    def learn(sid, title=None, article=None, barcode=None, price=None, raw=None):
        if sid is None:
            return
        i = sku_info.setdefault(sid, {"title": "", "article": "", "price": 0, "raw": {}})
        i["title"] = i["title"] or title or ""
        i["article"] = i["article"] or article or ""
        i["price"] = i["price"] or price or 0
        if raw:
            i["raw"] = raw
        if barcode:
            by_barcode[str(barcode)] = sid
            i["barcode"] = str(barcode)
        if article:
            by_title[norm(article)] = sid

    for p in store.docs("product"):
        for s in p.get("skuList") or []:
            learn(s.get("skuId"), f"{s.get('productTitle') or p.get('title') or ''} ({s.get('characteristics') or s.get('skuTitle') or ''})",
                  s.get("skuFullTitle") or s.get("skuTitle"), s.get("barcode"), s.get("price"), s)
            by_title[norm(s.get("skuTitle"))] = s.get("skuId")
    for inv in fbs_invoices:
        for o in inv.get("_orders") or []:
            for it in o.get("items") or []:
                learn(it.get("skuId"), it.get("title"), it.get("skuTitle"), it.get("barcode"), it.get("price"))
    for r in returns:
        for it in r.get("returnItems") or []:
            learn(it.get("skuId"), it.get("productTitle"), it.get("skuTitle"))

    unresolved = 0

    def item_key(it):
        nonlocal unresolved
        k = it.get("skuId")
        if k is None:
            k = by_barcode.get(str(it.get("barcode")))
        if k is None:
            k = by_title.get(norm(it.get("skuTitle")))
        if k is None:
            unresolved += 1
            k = "t:" + norm(it.get("skuTitle") or it.get("title"))
        return k

    titles, articles = {}, {}

    def remember(k, it):
        titles.setdefault(k, it.get("title") or it.get("productTitle") or "")
        articles.setdefault(k, it.get("skuTitle") or "")

    def order_ref(o):
        return {"order_id": o["id"], "public_id": o.get("publicId") or ""}

    # ---------- FBS topshirish yuk xatlari ----------
    accepted_any = set()
    for inv in fbs_invoices:
        for o in inv.get("_orders") or []:
            for it in o.get("items") or []:
                if it.get("status") == "ACCEPTED":
                    accepted_any.add(it.get("orderId") or o.get("orderId"))

    def handed(o):
        """Tovar jismonan Uzumga o'tganmi?

        Diqqat: buyurtmadagi acceptedDate — yuk xati qabul qilingan sana, u Uzum SANAMAGAN
        buyurtmalarga ham qo'yiladi. Haqiqiy dalil — yuk xatidagi pozitsiya holati ACCEPTED.
        """
        st = o.get("status")
        if st in IN_TRANSIT | AT_PICKUP | SOLD or st == "RETURNED":
            return True
        if st in BACK:
            return bool(o["id"] in accepted_any or o.get("deliveringDate")
                        or o.get("deliveredToDeliveryPointDate"))
        return False

    invoice_rows, not_accepted, seen_na = [], [], set()
    for inv in sorted(fbs_invoices, key=lambda i: -(i.get("id") or 0)):
        cnt = defaultdict(int)
        inv_acc = ts(inv.get("acceptedDate"))
        for o in inv.get("_orders") or []:
            for it in o.get("items") or []:
                amt = it.get("amount") or 1
                cnt[it.get("status")] += amt
                oid = it.get("orderId") or o.get("orderId")
                if inv.get("_status") != "ACCEPTED" or it.get("status") != "NOT_ACCEPTED":
                    continue
                od = by_id.get(oid) or {}
                if oid in accepted_any or (oid, it.get("skuTitle")) in seen_na:
                    continue
                seen_na.add((oid, it.get("skuTitle")))
                canc = ts(od.get("dateCancelled"))
                if canc and inv_acc and canc <= inv_acc:
                    late, verdict = False, "Topshirishdan oldin bekor bo'lgan"
                elif canc:
                    late, verdict = True, "Uzum sanamagan, keyin bekor bo'lgan — topshirgan bo'lsangiz da'vo qiling"
                else:
                    late, verdict = True, "Uzum sanamagan — tovar qayerdaligini tekshiring"
                not_accepted.append({
                    "invoice": inv.get("number") or inv.get("id"), "order_id": oid,
                    "public_id": it.get("publicId") or od.get("publicId") or "",
                    "title": it.get("title") or "", "article": it.get("skuTitle") or "",
                    "units": amt, "value": (it.get("price") or 0) * amt,
                    "date": fmt(inv_acc), "status": STATUS_UZ.get(od.get("status"), od.get("status") or "?"),
                    "cancelled": fmt(canc), "reason": od.get("cancelReason") or "", "late": late, "verdict": verdict,
                })
        dp = inv.get("dropOffPoint") or {}
        invoice_rows.append({
            "number": inv.get("number") or inv.get("id"),
            "status": (inv.get("status") or {}).get("text") if isinstance(inv.get("status"), dict) else inv.get("_status"),
            "created": fmt(ts(inv.get("dateCreated"))), "accepted_date": fmt(inv_acc),
            "total": sum(cnt.values()), "accepted": cnt["ACCEPTED"], "not_accepted": cnt["NOT_ACCEPTED"],
            "cancelled": cnt["CANCELLED"], "in_progress": cnt["IN_PROGRESS"],
            "point": (dp.get("address") or "")[:70],
        })
    not_accepted.sort(key=lambda r: (-r["late"], -int(r["invoice"] or 0)))

    # ---------- Buyurtmalar ----------
    sku = defaultdict(lambda: defaultdict(float))
    status_counts = defaultdict(int)
    stuck_transit, stuck_pickup, owed = [], [], defaultdict(list)

    for o in orders:
        st = o.get("status")
        status_counts[st] += 1
        if not handed(o):
            continue
        items = o.get("orderItems") or [{"title": f"Buyurtma {o['id']}", "amount": 1, "price": o.get("price")}]
        o_units = o_value = 0
        names = []
        for it in items:
            k = item_key(it)
            remember(k, it)
            amt = it.get("amount") or 1
            price = it.get("price") or it.get("sellerPrice") or 0
            o_units += amt
            o_value += price * amt
            names.append(f"{it.get('skuTitle') or it.get('title')} ×{amt}")
            s = sku[k]
            s["price"] = price or s["price"]
            s["handed"] += amt
            if st in IN_TRANSIT:
                s["transit"] += amt
            elif st in AT_PICKUP:
                s["pickup"] += amt
            elif st in SOLD:
                s["sold"] += amt
            else:
                s["owed"] += amt
                when = ts(o.get("returnDate")) or ts(o.get("dateCancelled")) or since_seen.get(o["id"]) or now
                owed[k].append({**order_ref(o), "status": st, "when": when, "units": amt, "price": price,
                                "title": it.get("title") or "", "article": it.get("skuTitle") or "",
                                "reason": o.get("cancelReason") or ""})
        row = {**order_ref(o), "status": STATUS_UZ.get(st, st), "units": o_units,
               "value": o_value or o.get("price") or 0, "items": "; ".join(names),
               "invoice": o.get("invoiceNumber") or ""}
        if st in IN_TRANSIT:
            t0 = (ts(o.get("deliveringDate")) if st != "ACCEPTED_AT_DP" else None) \
                or ts(o.get("acceptedDate")) or since_seen.get(o["id"]) or now
            row.update(since=fmt(t0), days=round((now - t0) / DAY, 1))
            row["late"] = row["days"] > cfg["transit_days"]
            stuck_transit.append(row)
        elif st in AT_PICKUP:
            t0 = ts(o.get("deliveredToDeliveryPointDate")) or since_seen.get(o["id"]) or now
            row.update(since=fmt(t0), days=round((now - t0) / DAY, 1))
            row["late"] = row["days"] > cfg["pickup_days"]
            stuck_pickup.append(row)

    # ---------- Qaytarish yuk xatlari ----------
    ret_types = defaultdict(int)
    lots = defaultdict(list)       # sku -> [{when, units, done}]
    return_rows = []
    for r in returns:
        typ = r.get("type") or "?"
        ret_types[typ] += 1
        status = str(r.get("status") or "").upper()
        if status.startswith("CANCEL") or r.get("canceledDate"):
            state = "bekor"
        elif status in ("COMPLETED", "DONE") or r.get("completedDate"):
            state = "bajarildi"
        else:
            state = "jarayonda"
        created = ts(r.get("dateCreated")) or now
        units = 0
        for it in r.get("returnItems") or []:
            k = item_key(it)
            remember(k, {"title": it.get("productTitle"), "skuTitle": it.get("skuTitle")})
            amt = it.get("amount") or 0
            units += amt
            if typ in cfg["return_types"] and state != "bekor" and amt:
                lots[k].append({"when": created, "units": amt, "done": state == "bajarildi", "id": r.get("id")})
        return_rows.append({"id": r.get("id"), "type": typ, "state": state,
                            "status": RETURN_UZ.get(status, status),
                            "created": fmt(created), "completed": fmt(ts(r.get("completedDate"))),
                            "units": units})
    if returns and not any(t in cfg["return_types"] for t in ret_types):
        warnings.append(f"Qaytarish yuk xatlari orasida {cfg['return_types']} turi yo'q "
                        f"(bor turlar: {dict(ret_types)}). .env da RETURN_TYPES ni to'g'rilang.")

    # ---------- Solishtirish: yuk xati faqat o'zidan OLDIN qaytgan buyurtmani yopadi ----------
    unreturned, lags = [], []
    for k in set(owed) | set(lots):
        entries = sorted(owed.get(k, []), key=lambda e: e["when"])
        for e in entries:
            e["left"], e["pend"], e["ret_id"] = e["units"], 0, ""
        s = sku[k]
        for lot in sorted(lots.get(k, []), key=lambda l: l["when"]):
            u = lot["units"]
            for e in entries:
                if not u:
                    break
                if e["left"] and e["when"] <= lot["when"] + DAY:
                    take = min(u, e["left"])
                    u -= take
                    e["left"] -= take
                    e["ret_id"] = lot["id"]
                    if lot["done"]:
                        s["ret_done"] += take
                    else:
                        s["ret_pending"] += take
                        e["pend"] += take
                    lags.append((lot["when"] - e["when"]) / DAY)
            s["ret_extra"] += u
        for e in entries:
            if not (e["left"] or e["pend"]):
                continue
            days = round((now - e["when"]) / DAY, 1)
            lost = e["left"] > 0 and days > cfg["return_days"]
            s["missing"] += e["left"]
            s["lost"] += e["left"] if lost else 0
            unreturned.append({
                "order_id": e["order_id"], "public_id": e["public_id"],
                "status": STATUS_UZ.get(e["status"], e["status"]), "date": fmt(e["when"]), "days": days,
                "title": e["title"], "article": e["article"],
                "units_missing": e["left"], "units_pending": e["pend"],
                "value": e["price"] * e["left"], "reason": e["reason"], "late": lost,
                "ret_id": e["ret_id"] if e["pend"] else "",
                "verdict": ("YO'QOLGAN — da'vo qiling" if lost else
                            "Hali qaytmagan (muddat ichida)" if e["left"] else
                            "Qaytarish yuk xatida, jarayonda"),
            })
    lags.sort()

    # ---------- Tovarlar balansi ----------
    sku_rows = []
    for k, s in sku.items():
        info = sku_info.get(k, {})
        sku_rows.append({
            "sku": "" if str(k).startswith("t:") else str(k), "barcode": info.get("barcode", ""),
            "title": titles.get(k) or info.get("title") or str(k),
            "article": articles.get(k) or info.get("article", ""),
            "handed": s["handed"], "sold": s["sold"], "transit": s["transit"], "pickup": s["pickup"],
            "owed": s["owed"], "ret_done": s["ret_done"], "ret_pending": s["ret_pending"],
            "missing": s["missing"], "lost": s["lost"], "ret_extra": s["ret_extra"],
            "lost_value": s["lost"] * s["price"], "missing_value": s["missing"] * s["price"],
        })
    sku_rows.sort(key=lambda r: (-r["lost"], -r["missing"], -r["handed"]))

    # ---------- FBO (Uzum omboriga ta'minot) ----------
    fbo_inv, acc_by_sku = [], defaultdict(float)
    for inv in store.docs("supply_invoice"):
        sent, acc = inv.get("totalToStock") or 0, inv.get("totalAccepted") or 0
        st = inv.get("invoiceStatus") or {}
        is_acc = bool(inv.get("dateAccepted")) or acc > 0
        for p in inv.get("productForInvoiceDto") or []:
            for s in p.get("skuForInvoiceDtoList") or []:
                acc_by_sku[s.get("id")] += s.get("quantityAccepted") or 0
        fbo_inv.append({"id": inv.get("invoiceNumber") or inv.get("id"),
                        "date": fmt(ts(inv.get("dateCreated")))[:10],
                        "status": (st.get("text") or st.get("value")) if isinstance(st, dict) else inv.get("status"),
                        "sent": sent, "accepted": acc, "diff": (sent - acc) if is_acc else 0,
                        "accepted_date": fmt(ts(inv.get("dateAccepted")))})
    fbo_inv.sort(key=lambda r: -r["diff"])
    fbo_sku = []
    for sid, acc in acc_by_sku.items():
        raw = (sku_info.get(sid) or {}).get("raw") or {}
        if not raw or not acc:
            continue
        g = lambda f: raw.get(f) or 0
        fbo_sku.append({"title": sku_info[sid]["article"] or sku_info[sid]["title"], "accepted": acc,
                        "active": g("quantityActive"), "sold": g("quantitySold"),
                        "returned": g("quantityReturned"), "defected": g("quantityDefected"),
                        "missing": g("quantityMissing")})

    if unresolved:
        warnings.append(f"{unresolved} ta pozitsiya SKU katalogiga bog'lanmadi — nomi bo'yicha solishtirildi.")
    last = store.get_meta("last_sync") or {}
    for e in last.get("errors") or []:
        warnings.append("Sinxronlash xatosi — " + e)

    stuck_transit.sort(key=lambda r: -r["days"])
    stuck_pickup.sort(key=lambda r: -r["days"])
    unreturned.sort(key=lambda r: (-r["late"], -r["days"]))
    tot = lambda f: sum(r[f] for r in sku_rows)
    late_t = [r for r in stuck_transit if r["late"]]
    late_p = [r for r in stuck_pickup if r["late"]]
    late_na = [r for r in not_accepted if r["late"]]
    pct = lambda p: round(lags[min(int(len(lags) * p), len(lags) - 1)], 1) if lags else None
    return {
        "generated": fmt(now), "last_sync": fmt(last.get("at")), "shops": store.get_meta("shops") or [],
        "cfg": cfg, "warnings": warnings,
        "status_counts": [{"status": s, "name": STATUS_UZ.get(s, s), "n": status_counts.get(s, 0)}
                          for s in STATUS_UZ],
        "summary": {
            "handed": tot("handed"), "sold": tot("sold"), "transit": tot("transit"),
            "pickup": tot("pickup"), "owed": tot("owed"), "ret_done": tot("ret_done"),
            "ret_pending": tot("ret_pending"), "missing": tot("missing"), "ret_extra": tot("ret_extra"),
            "missing_value": tot("missing_value"), "lost": tot("lost"), "lost_value": tot("lost_value"),
            "late_transit": len(late_t), "late_transit_value": sum(r["value"] for r in late_t),
            "late_pickup": len(late_p), "late_pickup_value": sum(r["value"] for r in late_p),
            "not_accepted": sum(r["units"] for r in late_na),
            "not_accepted_value": sum(r["value"] for r in late_na),
            "return_lag_median": pct(0.5), "return_lag_p90": pct(0.9),
        },
        "stuck_transit": stuck_transit, "stuck_pickup": stuck_pickup,
        "unreturned": unreturned, "not_accepted": not_accepted,
        "sku": sku_rows, "returns": sorted(return_rows, key=lambda r: -(r["id"] or 0)),
        "fbs_invoices": invoice_rows, "fbo_invoices": fbo_inv, "fbo_sku": fbo_sku,
    }
