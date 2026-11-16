"""HTTPS ulanish sozlamasi.

python.org'dan o'rnatilgan Python'da ba'zan ishonchli sertifikatlar ro'yxati bo'sh bo'ladi
(macOS'da "Install Certificates" ishga tushirilmagan bo'lsa). Bunday holda tizimning o'z
ro'yxatidan foydalanamiz. Tekshiruv hech qachon o'chirilmaydi.
"""
import os
import ssl

_ctx = None


def context():
    global _ctx
    if _ctx is None:
        ctx = ssl.create_default_context()
        if not ctx.cert_store_stats().get("x509_ca"):
            for path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
                if os.path.exists(path):
                    ctx.load_verify_locations(path)
                    break
        _ctx = ctx
    return _ctx
