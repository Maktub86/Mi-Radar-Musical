@echo off
cd /d "%~dp0app"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% servidor.py
pause
