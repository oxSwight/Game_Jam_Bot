@echo off
REM Двойной клик по этому файлу перезапускает бота.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1"
