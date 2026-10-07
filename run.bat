@echo off
title Discord Music Bot
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe bot.py
) else (
    python bot.py
)
pause
