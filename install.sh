#!/bin/bash
# Uzum tovar kuzatuvi — Mac uchun o'rnatish.
# Terminalda ishga tushiring:
#   curl -fsSL https://raw.githubusercontent.com/cgenki1207/Aziz-uzum/main/install.sh | bash
set -e

REPO="cgenki1207/Aziz-uzum"
DIR="$HOME/UzumTracker"
LAUNCHER="$HOME/Desktop/Uzum Tracker.command"

echo "Uzum tovar kuzatuvi o'rnatilmoqda…"

# macOS'da /usr/bin/python3 bor, lekin Apple vositalari o'rnatilmagan bo'lsa u ishlamaydi.
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
  echo
  echo "Python topilmadi. https://www.python.org/downloads/ dan o'rnating,"
  echo "keyin shu buyruqni qayta ishga tushiring."
  open "https://www.python.org/downloads/" 2>/dev/null || true
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL -o "$TMP/app.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
unzip -q "$TMP/app.zip" -d "$TMP"
SRC="$(find "$TMP" -maxdepth 1 -type d -name '*-main' | head -1)"
[ -f "$SRC/run.py" ] || { echo "Yuklab olishda xato: run.py topilmadi."; exit 1; }

mkdir -p "$DIR"
cp -R "$SRC/." "$DIR/"

mkdir -p "$HOME/Desktop"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
exec bash "$DIR/launch.sh"
EOF
chmod +x "$LAUNCHER"

echo
echo "Tayyor. Ish stolida «Uzum Tracker» paydo bo'ldi — keyingi safar shuni ikki marta bosing."
echo "Hozir dastur ochilmoqda…"
echo
exec "$LAUNCHER"
