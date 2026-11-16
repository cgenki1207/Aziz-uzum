@echo off
rem Windows: shu faylni ikki marta bosing.
chcp 65001 >nul
cd /d "%~dp0"
title Uzum tovar kuzatuvi
where py >nul 2>nul && (py -3 run.py & goto end)
where python >nul 2>nul && (python run.py & goto end)
echo Python topilmadi. https://www.python.org/downloads/ dan o'rnatib, "Add Python to PATH" belgisini qo'ying.
start https://www.python.org/downloads/
:end
pause
