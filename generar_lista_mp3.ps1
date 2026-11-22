# ==========================================================================
#  Mi Radar Musical - Generar el listado de canciones y actualizar "Mi musica"
#
#  1. Recorre tu carpeta de musica y crea lista_mp3.txt con lineas asi:
#        1982 | Michael Jackson - Thriller.mp3
#  2. Ejecuta app\actualizar_mi_musica.py, que pasa ese listado a la web
#     (app\mi_musica.json, mi_radar_musical.csv y artistas_unicos.txt).
#  3. Si la carpeta del proyecto es un repositorio de Git, te ofrece subirlo.
#
#  Guarda este archivo en la carpeta del proyecto ("Pagina radar musica"),
#  al lado de la carpeta "app". Ejecutalo con clic derecho > "Ejecutar con PowerShell".
# ==========================================================================

# >>> CAMBIA ESTA RUTA por la carpeta donde tienes tus MP3 <<<
$CarpetaMusica = "D:\Musica"

# Carpeta del proyecto: la misma en la que esta guardado este archivo.
$Proyecto = $PSScriptRoot
$Lista    = Join-Path $Proyecto "lista_mp3.txt"

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path -LiteralPath $CarpetaMusica)) {
    Write-Host "No encuentro la carpeta de musica: $CarpetaMusica" -ForegroundColor Red
    Write-Host "Abre este archivo con el Bloc de notas y cambia la linea `$CarpetaMusica."
    Read-Host "Pulsa Intro para salir"; exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $Proyecto "app\actualizar_mi_musica.py"))) {
    Write-Host "Este archivo tiene que estar en la carpeta del proyecto (junto a la carpeta 'app')." -ForegroundColor Red
    Read-Host "Pulsa Intro para salir"; exit 1
}

# --- 1. Leer los MP3 y averiguar el ano de cada uno -----------------------
# El ano se toma de la carpeta si se llama como un ano (p. ej. ...\1982\cancion.mp3);
# si no, de la etiqueta "Ano" del MP3 (la que rellenas con Mp3tag).
$shell   = New-Object -ComObject Shell.Application
$colAnio = $null
$nombresColumna = @("Year", ("A" + [char]0x00F1 + "o"))   # "Year" / "Ano" con enye

function Get-AnioCancion($archivo) {
    if ($archivo.Directory.Name -match '^(19|20)\d{2}$') { return $archivo.Directory.Name }
    $carpeta = $shell.Namespace($archivo.DirectoryName)
    if ($null -eq $script:colAnio) {
        for ($i = 0; $i -lt 400; $i++) {
            if ($nombresColumna -contains $carpeta.GetDetailsOf($null, $i)) { $script:colAnio = $i; break }
        }
        if ($null -eq $script:colAnio) { $script:colAnio = -1 }
    }
    if ($script:colAnio -lt 0) { return $null }
    $valor = $carpeta.GetDetailsOf($carpeta.ParseName($archivo.Name), $script:colAnio)
    if ($valor -match '(19|20)\d{2}') { return $Matches[0] }
    return $null
}

Write-Host "Leyendo canciones de $CarpetaMusica ..." -ForegroundColor Cyan
$archivos = Get-ChildItem -LiteralPath $CarpetaMusica -Filter *.mp3 -File -Recurse
$lineas   = New-Object System.Collections.Generic.List[string]
$sinAnio  = New-Object System.Collections.Generic.List[string]
$sinGuion = New-Object System.Collections.Generic.List[string]

foreach ($a in $archivos) {
    if ($a.Name -notmatch ' - ') { $sinGuion.Add($a.FullName); continue }
    $anio = Get-AnioCancion $a
    if (-not $anio) { $sinAnio.Add($a.FullName); continue }
    $lineas.Add("$anio | $($a.Name)")
}

if ($lineas.Count -eq 0) {
    Write-Host "No he encontrado ningun MP3 con ano en $CarpetaMusica." -ForegroundColor Red
    Read-Host "Pulsa Intro para salir"; exit 1
}
$ordenadas = @($lineas | Sort-Object -Unique)
[System.IO.File]::WriteAllLines($Lista, [string[]]$ordenadas, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Listado creado: {0} canciones -> {1}" -f $ordenadas.Count, $Lista) -ForegroundColor Green

if ($sinAnio.Count) {
    Write-Host "`nSin ano (rellena la etiqueta Ano con Mp3tag y vuelve a ejecutar):" -ForegroundColor Yellow
    $sinAnio | ForEach-Object { Write-Host "  $_" }
}
if ($sinGuion.Count) {
    Write-Host "`nSin el formato 'Artista - Titulo.mp3' (renombralas):" -ForegroundColor Yellow
    $sinGuion | ForEach-Object { Write-Host "  $_" }
}

# --- 2. Pasar el listado a la web -----------------------------------------
$python = $null
foreach ($candidato in @("py", "python")) {
    if (Get-Command $candidato -ErrorAction SilentlyContinue) { $python = $candidato; break }
}
if (-not $python) {
    $python = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
              Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $python) {
    Write-Host "`nNo encuentro Python. Instalalo desde python.org y vuelve a ejecutar." -ForegroundColor Red
    Read-Host "Pulsa Intro para salir"; exit 1
}

Write-Host "`nActualizando 'Mi musica' ..." -ForegroundColor Cyan
& $python (Join-Path $Proyecto "app\actualizar_mi_musica.py") $Lista
if ($LASTEXITCODE -ne 0) { Read-Host "Algo ha fallado. Pulsa Intro para salir"; exit 1 }

# --- 3. Subir a GitHub (opcional) -----------------------------------------
if ((Test-Path -LiteralPath (Join-Path $Proyecto ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    $r = Read-Host "`nSubir los cambios a GitHub? (s/n)"
    if ($r -match '^[sS]') {
        Push-Location $Proyecto
        git pull --rebase --autostash
        git add -- lista_mp3.txt app/mi_musica.json mi_radar_musical.csv artistas_unicos.txt
        git commit -m "Actualizar Mi musica con el listado de canciones"
        git push
        Pop-Location
    }
}

Write-Host "`nListo. Recarga la pagina 'Mi musica' para ver los cambios." -ForegroundColor Green
Read-Host "Pulsa Intro para cerrar"
