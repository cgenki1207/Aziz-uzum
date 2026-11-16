#!/bin/bash
# Mac'da dasturni orqa fonda ishga tushiradi (ish stolidagi «Uzum Tracker» shu faylni chaqiradi).
cd "$(dirname "$0")" || exit 1
mkdir -p "$HOME/.uzum-tracker"
nohup python3 run.py >> "$HOME/.uzum-tracker/log.txt" 2>&1 &
disown 2>/dev/null || true
echo "Uzum Tracker ishga tushdi, brauzerda ochilmoqda."
echo "Bu oynani yopishingiz mumkin. To'xtatish: paneldagi «To'xtatish» tugmasi."
sleep 3
