"""GitHub'dan avtomatik yangilanish.

Dastur har ochilganda GitHub'dagi oxirgi versiyani tekshiradi va farq bo'lsa o'zini yangilaydi.
git o'rnatilgan bo'lishi shart emas: git bilan klon qilingan bo'lsa `git pull`, aks holda ZIP yuklanadi.
Foydalanuvchi ma'lumotlari (~/.uzum-tracker) ga tegilmaydi.
"""
import io
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from .config import DATA, ROOT

REPO = "cgenki1207/Aziz-uzum"        # masalan "foydalanuvchi/uzum-tracker" — GitHub'ga yuklangandan keyin to'ldiriladi
BRANCH = "main"
SHA_FILE = DATA / "installed_sha"


def _get(url, timeout, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "git/2.0 (uzum-tracker-updater)",
                                               **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def enabled():
    return bool(REPO) and not (ROOT / ".dev").exists()


def local_sha():
    if (ROOT / ".git").exists():
        try:
            return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return SHA_FILE.read_text().strip() if SHA_FILE.exists() else ""


def remote_sha(timeout=6):
    """Oxirgi commit — git protokoli orqali (keshlanmaydi, so'rov limiti yo'q)."""
    data = _get(f"https://github.com/{REPO}.git/info/refs?service=git-upload-pack", timeout).decode("utf-8", "replace")
    for line in data.splitlines():
        if line.rstrip().endswith(f" refs/heads/{BRANCH}"):
            return line.split(" ")[0][-40:]
    return ""


def check():
    """-> (yangilanish bormi, hozirgi versiya, yangi versiya). Internet bo'lmasa jim o'tadi."""
    cur = local_sha()
    if not enabled():
        return False, cur, cur
    try:
        new = remote_sha()
    except Exception:
        return False, cur, cur
    return (len(new) == 40 and new != cur), cur, new


def apply(new_sha):
    if (ROOT / ".git").exists():
        r = subprocess.run(["git", "-C", str(ROOT), "pull", "--ff-only", "origin", BRANCH],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:300])
        return
    data = _get(f"https://github.com/{REPO}/archive/{new_sha}.zip", 120)
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        src = next(p for p in __import__("pathlib").Path(tmp).iterdir() if p.is_dir())
        if not (src / "run.py").exists():
            raise RuntimeError("yuklangan arxivda run.py yo'q")
        shutil.copytree(src, ROOT, dirs_exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    SHA_FILE.write_text(new_sha)


def update_on_start(log=print):
    """True qaytarsa — kod yangilandi, dasturni qayta ishga tushirish kerak."""
    has, _cur, new = check()
    if not has:
        return False
    log("Yangi versiya topildi, yangilanmoqda…")
    try:
        apply(new)
        log("Yangilandi.")
        return True
    except Exception as e:
        log(f"Yangilab bo'lmadi ({e}). Eski versiya bilan davom etiladi.")
        return False
