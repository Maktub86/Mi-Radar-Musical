
$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "=== DIAGNOSTICO MI RADAR MUSICAL ===" -ForegroundColor Cyan
Write-Host ""

$ruta = $PSScriptRoot
$config = Join-Path $ruta "configuracion.json"
$log = Join-Path $ruta "registro_auxiliar.txt"
$script = Join-Path $ruta "MiRadarMusical_Auxiliar.ps1"

foreach ($archivo in @($config, $log, $script)) {
    if (Test-Path -LiteralPath $archivo) {
        Write-Host "[OK] $archivo" -ForegroundColor Green
    } else {
        Write-Host "[NO ENCONTRADO] $archivo" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== CONFIGURACION ===" -ForegroundColor Cyan

if (Test-Path -LiteralPath $config) {
    try {
        Get-Content -LiteralPath $config -Raw |
            ConvertFrom-Json |
            Format-List
    } catch {
        Write-Host "Error leyendo configuracion: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== PROCESOS ID3 REMOVER Y MP3TAG ===" -ForegroundColor Cyan

Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "ID3Remover|Mp3tag" } |
    Select-Object ProcessName, Id, MainWindowTitle, MainWindowHandle |
    Format-Table -AutoSize

Write-Host ""
Write-Host "=== ULTIMAS LINEAS DEL REGISTRO ===" -ForegroundColor Cyan

$logTemp = Join-Path $env:TEMP "registro_auxiliar_radar.txt"
foreach ($l in @($log, $logTemp)) {
    if (Test-Path -LiteralPath $l) {
        Write-Host "--- $l (modificado: $((Get-Item -LiteralPath $l).LastWriteTime)) ---" -ForegroundColor Yellow
        Get-Content -LiteralPath $l -Tail 20
    }
}

Write-Host ""
Write-Host "=== FIN DEL DIAGNOSTICO ===" -ForegroundColor Cyan
Read-Host "Pulsa INTRO para cerrar"
