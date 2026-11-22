# ==========================================================================
#  Mi Radar Musical - Generar el listado de tus canciones (lista_mp3.txt)
#
#  Recorre tu carpeta de musica y crea en el ESCRITORIO el archivo
#  lista_mp3.txt, con una linea por cancion:
#        1982 | Michael Jackson - Thriller.mp3
#
#  Despues solo tienes que subir lista_mp3.txt al repositorio de GitHub
#  (Add file > Upload files). GitHub actualiza "Mi musica" solo y Render
#  publica la web en unos minutos.
#
#  Ejecutalo con clic derecho > "Ejecutar con PowerShell".
# ==========================================================================

# >>> CAMBIA ESTA RUTA por la carpeta donde tienes tus MP3 <<<
$CarpetaMusica = "D:\Musica"

$Lista = Join-Path ([Environment]::GetFolderPath("Desktop")) "lista_mp3.txt"

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path -LiteralPath $CarpetaMusica)) {
    Write-Host "No encuentro la carpeta de musica: $CarpetaMusica" -ForegroundColor Red
    Write-Host "Abre este archivo con el Bloc de notas y cambia la linea `$CarpetaMusica."
    Read-Host "Pulsa Intro para salir"; exit 1
}

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
Write-Host ("`nListado creado con {0} canciones en tu escritorio: {1}" -f $ordenadas.Count, $Lista) -ForegroundColor Green

if ($sinAnio.Count) {
    Write-Host "`nSin ano (rellena la etiqueta Ano con Mp3tag y vuelve a ejecutar):" -ForegroundColor Yellow
    $sinAnio | ForEach-Object { Write-Host "  $_" }
}
if ($sinGuion.Count) {
    Write-Host "`nSin el formato 'Artista - Titulo.mp3' (renombralas):" -ForegroundColor Yellow
    $sinGuion | ForEach-Object { Write-Host "  $_" }
}

Write-Host "`nAhora sube lista_mp3.txt a GitHub:" -ForegroundColor Cyan
Write-Host "  https://github.com/Maktub86/Mi-Radar-Musical  >  Add file  >  Upload files"
Write-Host "  Arrastra lista_mp3.txt y pulsa 'Commit changes'. En unos minutos la web estara actualizada."
Read-Host "`nPulsa Intro para cerrar"
