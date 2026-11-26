@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0MiRadarMusical_Auxiliar.ps1" (
  echo No encuentro MiRadarMusical_Auxiliar.ps1 en esta carpeta:
  echo %~dp0
  echo.
  echo Coloca este archivo .bat junto al script MiRadarMusical_Auxiliar.ps1 y configuracion.json.
  echo.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MiRadarMusical_Auxiliar.ps1"
if errorlevel 1 (
  echo.
  echo El auxiliar se ha cerrado con un error. Revisa el mensaje anterior.
  pause
)
endlocal
