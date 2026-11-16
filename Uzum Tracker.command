#!/bin/bash
# macOS: shu faylni ikki marta bosing.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python topilmadi. https://www.python.org/downloads/ dan o'rnating va qayta urinib ko'ring."
  open "https://www.python.org/downloads/"
  read -n 1 -s -r -p "Yopish uchun istalgan tugmani bosing"
  exit 1
fi
python3 run.py
