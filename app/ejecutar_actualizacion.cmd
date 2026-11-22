@echo off
rem Actualiza Mi Radar Musical. Funciona desde cualquier carpeta.
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
echo.>>"%~dp0actualizacion_diaria.log"
echo ==== Inicio: %date% %time% ====>>"%~dp0actualizacion_diaria.log"
%PY% "%~dp0actualizacion_diaria.py" >>"%~dp0actualizacion_diaria.log" 2>&1
echo ==== Fin: %date% %time% ====>>"%~dp0actualizacion_diaria.log"
