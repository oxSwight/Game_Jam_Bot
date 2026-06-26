@echo off
REM Двойной клик по этому файлу останавливает бота.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
