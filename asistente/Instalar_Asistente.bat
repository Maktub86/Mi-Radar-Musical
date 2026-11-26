@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0Instalar_Asistente.ps1" (
  echo No encuentro Instalar_Asistente.ps1. Descomprime primero el ZIP completo y ejecuta este archivo desde esa carpeta.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Instalar_Asistente.ps1"
endlocal
