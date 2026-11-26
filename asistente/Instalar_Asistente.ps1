$ErrorActionPreference = "Stop"
# ======================================================================
#  Instalador del Asistente automático "Descargar Radar" (Mi Radar Musical)
#  - Copia el asistente a Escritorio\Otros\Descargar Radar
#  - Busca MP3Gain, ID3 Remover y Mp3tag y crea configuracion.json
#  - Instala en Mp3tag los grupos de acciones guardados (Uololo, Radar datos)
#  - Crea un acceso directo "Descargar Radar" en el Escritorio
#  No borra ni sobrescribe tu configuración si ya existe (salvo que lo confirmes).
# ======================================================================
Add-Type -AssemblyName PresentationFramework

function Paso($texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "   [OK] $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "   [!] $texto" -ForegroundColor Yellow }
function Pregunta($texto) { return [System.Windows.MessageBox]::Show($texto, "Instalar Descargar Radar", "YesNo", "Question") -eq "Yes" }

$origen      = $PSScriptRoot
$escritorio  = Join-Path $env:USERPROFILE "Desktop"
if (-not (Test-Path -LiteralPath $escritorio)) { $escritorio = [Environment]::GetFolderPath("Desktop") }
$otros       = Join-Path $escritorio "Otros"
$destino     = Join-Path $otros "Descargar Radar"
$descargas   = Join-Path $otros "Descarga música"

Write-Host "Instalador del Asistente automático de Mi Radar Musical" -ForegroundColor Magenta

# ---------- 1) Carpetas ----------
Paso "1. Carpetas"
foreach ($c in @($otros, $destino, $descargas)) {
    if (-not (Test-Path -LiteralPath $c)) { New-Item -ItemType Directory -Path $c | Out-Null; Ok "Creada: $c" } else { Ok "Ya existe: $c" }
}

# ---------- 2) Archivos del asistente ----------
Paso "2. Archivos del asistente"
foreach ($archivo in @("MiRadarMusical_Auxiliar.ps1", "Iniciar_MiRadarMusical.bat", "Diagnostico_Radar.ps1")) {
    $de = Join-Path $origen $archivo
    if (-not (Test-Path -LiteralPath $de)) { Aviso "No encuentro $archivo junto al instalador."; continue }
    Copy-Item -LiteralPath $de -Destination (Join-Path $destino $archivo) -Force
    Ok "Copiado $archivo"
}

# ---------- 3) Buscar programas ----------
Paso "3. Buscando los programas necesarios"
function Buscar-Exe([string]$nombre, [string[]]$rutasProbables, [string[]]$carpetasDondeBuscar) {
    foreach ($r in $rutasProbables) { if ($r -and (Test-Path -LiteralPath $r)) { return $r } }
    foreach ($carpeta in $carpetasDondeBuscar) {
        if (-not $carpeta -or -not (Test-Path -LiteralPath $carpeta)) { continue }
        $hallado = Get-ChildItem -LiteralPath $carpeta -Filter $nombre -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hallado) { return $hallado.FullName }
    }
    return ""
}
$pf86 = ${env:ProgramFiles(x86)}; $pf = $env:ProgramFiles
$mp3tag = Buscar-Exe "Mp3tag.exe" @((Join-Path $pf86 "Mp3tag\Mp3tag.exe"), (Join-Path $pf "Mp3tag\Mp3tag.exe")) @()
$id3    = Buscar-Exe "ID3Remover.exe" @((Join-Path $escritorio "ID3Remover.exe")) @($escritorio, $pf86, $pf, (Join-Path $env:USERPROFILE "Downloads"))
$gain   = Buscar-Exe "mp3gain.exe" @((Join-Path $descargas "95\mp3gain.exe")) @($otros, $pf86, $pf, (Join-Path $env:USERPROFILE "Downloads"))
$gainGui = ""
if ($gain) { $posible = Join-Path (Split-Path -Parent $gain) "MP3GainGUI.exe"; if (Test-Path -LiteralPath $posible) { $gainGui = $posible } }

$faltan = @()
foreach ($p in @(@("Mp3tag", $mp3tag), @("ID3 Remover", $id3), @("MP3Gain (mp3gain.exe)", $gain))) {
    if ($p[1]) { Ok "$($p[0]): $($p[1])" } else { Aviso "$($p[0]): NO ENCONTRADO"; $faltan += $p[0] }
}

# ---------- 4) configuracion.json ----------
Paso "4. configuracion.json"
$config = Join-Path $destino "configuracion.json"
$escribir = $true
if (Test-Path -LiteralPath $config) {
    $escribir = Pregunta "Ya existe configuracion.json en:`n$destino`n`n¿Quieres sustituirlo por uno nuevo con los programas encontrados ahora?`n(Pulsa No para conservar el tuyo.)"
}
if ($escribir) {
    $datos = [ordered]@{
        carpeta_descargas = $descargas
        id3_remover       = $id3
        mp3gain_gui       = $gainGui
        mp3gain_cli       = $gain
        mp3tag            = $mp3tag
        objetivo_db       = 95.0
    }
    $json = $datos | ConvertTo-Json
    [IO.File]::WriteAllText($config, $json, (New-Object System.Text.UTF8Encoding($false)))
    Ok "Creado $config"
} else { Ok "Se conserva tu configuracion.json" }

# ---------- 5) Grupos de acciones de Mp3tag ----------
Paso "5. Grupos de acciones de Mp3tag (Uololo y Radar datos)"
$accionesOrigen = Join-Path $origen "mp3tag"
$accionesDestino = Join-Path $env:APPDATA "Mp3tag\data\actions"
$mta = @()
if (Test-Path -LiteralPath $accionesOrigen) { $mta = @(Get-ChildItem -LiteralPath $accionesOrigen -Filter "*.mta" -File) }
if ($mta.Count -eq 0) {
    Aviso "El asistente no trae grupos de acciones guardados. Tendrás que crearlos a mano (mira el LEEME)."
} else {
    if (-not (Test-Path -LiteralPath $accionesDestino)) { New-Item -ItemType Directory -Path $accionesDestino -Force | Out-Null }
    foreach ($f in $mta) {
        $final = Join-Path $accionesDestino $f.Name
        if ((Test-Path -LiteralPath $final) -and -not (Pregunta "Mp3tag ya tiene el grupo de acciones '$($f.BaseName)'.`n`n¿Sustituirlo por el guardado en el asistente?")) { Ok "Se conserva tu '$($f.BaseName)'"; continue }
        # Las acciones guardan rutas completas; se adaptan a la carpeta de este usuario.
        $lector = New-Object System.IO.StreamReader($f.FullName, $true)
        try { $texto = $lector.ReadToEnd(); $codificacion = $lector.CurrentEncoding } finally { $lector.Close() }
        # Mp3tag guarda las rutas con barras dobles (C:\\Users\\...); se adaptan ambas formas.
        foreach ($par in @(@('C:\Users\34667\Desktop', $escritorio), @('C:\Users\34667', $env:USERPROFILE))) {
            $texto = $texto.Replace($par[0].Replace('\','\\'), $par[1].Replace('\','\\')).Replace($par[0], $par[1])
        }
        [IO.File]::WriteAllText($final, $texto, $codificacion)
        Ok "Instalado grupo de acciones '$($f.BaseName)'"
    }
}

# ---------- 6) Acceso directo ----------
Paso "6. Acceso directo en el Escritorio"
try {
    $shell = New-Object -ComObject WScript.Shell
    $acceso = $shell.CreateShortcut((Join-Path $escritorio "Descargar Radar.lnk"))
    $acceso.TargetPath = Join-Path $destino "Iniciar_MiRadarMusical.bat"
    $acceso.WorkingDirectory = $destino
    $acceso.Description = "Asistente automático de Mi Radar Musical"
    $acceso.Save()
    Ok "Creado 'Descargar Radar' en el Escritorio"
} catch { Aviso "No se pudo crear el acceso directo: $($_.Exception.Message)" }

# ---------- Resumen ----------
Paso "Resumen"
if ($faltan.Count -gt 0) {
    Aviso ("Faltan programas: " + ($faltan -join ", ") + ". Instálalos (página Programas de Mi Radar Musical) y vuelve a ejecutar este instalador, o escribe su ruta en configuracion.json.")
    Start-Process notepad.exe -ArgumentList ('"' + $config + '"')
} else {
    Ok "Todo listo."
}
Write-Host ""
Write-Host "Últimos pasos (solo una vez):" -ForegroundColor Magenta
Write-Host "  - MediaHuman: Preferencias > carpeta de salida = $descargas"
Write-Host "  - Mp3tag: Alt+5 y deja MARCADOS los grupos 'Uololo' y 'Radar datos'."
Write-Host "  - Mp3tag: el cuadro 'Filtro' de abajo debe estar VACÍO."
Write-Host "  - Para usarlo: doble clic en 'Descargar Radar' del Escritorio."
Write-Host ""
Read-Host "Pulsa INTRO para cerrar"
