"""Cloud Run'da ishga tushirish: har uyg'onganda GitHub'dagi eng yangi kodni olib, uni ishga tushiradi.

Shu tufayli GitHub'ga yuborilgan har bir o'zgarish serverga ham o'zi yetib boradi —
qaytadan joylash (deploy) shart emas.
"""
import io
import os
import sys
import urllib.request
import zipfile

REPO = "cgenki1207/Aziz-uzum"
DEST = os.environ.get("UZUM_APP_DIR", "/tmp/app")


def main():
    url = f"https://codeload.github.com/{REPO}/zip/refs/heads/main"
    req = urllib.request.Request(url, headers={"User-Agent": "uzum-tracker-boot"})
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(req, timeout=30).read()
            break
        except Exception as e:
            print(f"Kodni yuklab bo'lmadi ({e}), qayta urinish…", flush=True)
    else:
        sys.exit("GitHub'dan kod olinmadi.")
    z = zipfile.ZipFile(io.BytesIO(data))
    z.extractall("/tmp")
    src = "/tmp/" + z.namelist()[0].split("/")[0]
    if os.path.exists(DEST):
        os.rename(DEST, DEST + ".old")
    os.rename(src, DEST)
    home = os.environ.setdefault("UZUM_TRACKER_HOME", "/tmp/uzum")
    os.makedirs(home, exist_ok=True)
    sha = z.comment.decode("ascii", "ignore").strip()      # GitHub arxiv izohida commit raqami bo'ladi
    if len(sha) == 40:
        with open(os.path.join(home, "installed_sha"), "w") as f:
            f.write(sha)
    os.environ.update(UZUM_SERVER="1", UZUM_NO_BROWSER="1")
    os.execv(sys.executable, [sys.executable, os.path.join(DEST, "run.py"), "--no-browser"])


if __name__ == "__main__":
    main()
