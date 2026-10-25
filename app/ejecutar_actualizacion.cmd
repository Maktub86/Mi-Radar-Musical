@echo off
cd /d "C:\Users\34667\Desktop\Pagina radar musica\app"
echo.>>"C:\Users\34667\Desktop\Pagina radar musica\app\actualizacion_diaria.log"
echo ==== Inicio: %date% %time% ====>>"C:\Users\34667\Desktop\Pagina radar musica\app\actualizacion_diaria.log"
"C:\Users\34667\AppData\Local\Programs\Python\Python315\python.exe" "C:\Users\34667\Desktop\Pagina radar musica\app\actualizacion_diaria.py" >>"C:\Users\34667\Desktop\Pagina radar musica\app\actualizacion_diaria.log" 2>&1
echo ==== Fin: %date% %time% ====>>"C:\Users\34667\Desktop\Pagina radar musica\app\actualizacion_diaria.log"
