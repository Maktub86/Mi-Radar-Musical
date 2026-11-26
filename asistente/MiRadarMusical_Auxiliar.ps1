$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

if (-not ("RadarWindows" -as [type])) {
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class RadarWindows {
    [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GlobalAlloc(uint flags, UIntPtr bytes);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GlobalLock(IntPtr memory);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GlobalUnlock(IntPtr memory);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GlobalFree(IntPtr memory);
    [DllImport("user32.dll", SetLastError=true)] public static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError=true)] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hwnd);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, System.Text.StringBuilder text, int count);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, System.Text.StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", EntryPoint="SendMessageW")] public static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);
    public static string WindowText(IntPtr hwnd) { var b=new System.Text.StringBuilder(512); GetWindowText(hwnd,b,b.Capacity); return b.ToString(); }
    public static string WindowClass(IntPtr hwnd) { var b=new System.Text.StringBuilder(128); GetClassName(hwnd,b,b.Capacity); return b.ToString(); }
    public static IntPtr FindOtherWindowForProcess(uint pid, IntPtr mainWindow) {
        IntPtr found=IntPtr.Zero;
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if(h==mainWindow) return true;
            uint owner=0; GetWindowThreadProcessId(h,out owner);
            if(owner!=pid) return true;
            if(!IsWindow(h)) return true;
            // No elegir ventanas invisibles/minimizadas como aviso modal.
            if(!IsWindowVisible(h)) return true;
            found=h; return false;
        },IntPtr.Zero);
        return found;
    }
    public static string AllChildText(IntPtr parent) {
        var sb=new System.Text.StringBuilder();
        EnumChildWindows(parent,delegate(IntPtr child,IntPtr ignored) {
            string tx=WindowText(child);
            if(!string.IsNullOrWhiteSpace(tx)) { if(sb.Length>0) sb.Append(" | "); sb.Append(tx.Replace("\r"," ").Replace("\n"," ")); }
            return true;
        },IntPtr.Zero);
        return sb.ToString();
    }
    public static IntPtr FindId3CompletionDialog(uint pid) {
        // Buscar el aviso por su texto real en todas las ventanas, sin asumir
        // que Windows lo haya asociado al PID principal de ID3Remover.
        IntPtr found=IntPtr.Zero;
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            string title=WindowText(h);
            bool hasText=title.IndexOf("All ID3Tag Removed",StringComparison.OrdinalIgnoreCase)>=0
                      || title.IndexOf("All ID3Tag",StringComparison.OrdinalIgnoreCase)>=0;
            EnumChildWindows(h,delegate(IntPtr child,IntPtr ignored) {
                string t=WindowText(child);
                if(t.IndexOf("All ID3Tag Removed",StringComparison.OrdinalIgnoreCase)>=0
                   || t.IndexOf("All ID3Tag",StringComparison.OrdinalIgnoreCase)>=0) {
                    hasText=true;
                    return false;
                }
                return true;
            },IntPtr.Zero);
            if(hasText) { found=h; return false; }
            return true;
        },IntPtr.Zero);
        return found;
    }
    public static IntPtr FindChildButtonByText(IntPtr parent, string wantedText) {
        IntPtr found=IntPtr.Zero;
        EnumChildWindows(parent,delegate(IntPtr child,IntPtr ignored) {
            string text=WindowText(child);
            string cls=WindowClass(child);
            if(String.Equals(cls,"Button",StringComparison.OrdinalIgnoreCase)
               && String.Equals(text,wantedText,StringComparison.OrdinalIgnoreCase)) {
                found=child; return false;
            }
            return true;
        },IntPtr.Zero);
        return found;
    }
    public static bool ClickChildButtonByText(IntPtr parent, string wantedText) {
        if(parent==IntPtr.Zero || !IsWindow(parent)) return false;
        IntPtr button=FindChildButtonByText(parent,wantedText);
        if(button==IntPtr.Zero || !IsWindow(button)) return false;
        SendMessage(button,0x00F5,IntPtr.Zero,IntPtr.Zero); // BM_CLICK
        return true;
    }
    public static bool ClickId3Accept(IntPtr dialog) {
        if(dialog==IntPtr.Zero || !IsWindow(dialog)) return false;
        IntPtr button=IntPtr.Zero;
        EnumChildWindows(dialog,delegate(IntPtr child,IntPtr ignored) {
            string t=WindowText(child);
            if(String.Equals(t,"Aceptar",StringComparison.OrdinalIgnoreCase)
               || String.Equals(t,"OK",StringComparison.OrdinalIgnoreCase)) {
                button=child; return false;
            }
            return true;
        },IntPtr.Zero);
        if(button!=IntPtr.Zero) {
            // BM_CLICK sobre el control real del cuadro de mensaje.
            SendMessage(button,0x00F5,IntPtr.Zero,IntPtr.Zero);
        }
        if(IsWindow(dialog)) {
            // IDOK como alternativa para cuadros de diálogo Win32.
            SendMessage(dialog,0x0111,new IntPtr(1),IntPtr.Zero);
        }
        if(IsWindow(dialog)) {
            PostMessage(dialog,0x0010,IntPtr.Zero,IntPtr.Zero); // WM_CLOSE
        }
        return true;
    }
}
'@
}

if (-not ("RadarWindowsMp3tag" -as [type])) {
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class RadarWindowsMp3tag {
    private delegate bool EnumChildProc(IntPtr hwnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumChildProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll", EntryPoint="SendMessageW")] public static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
    public static IntPtr FindFileList(IntPtr parent) {
        IntPtr found=IntPtr.Zero;
        EnumChildWindows(parent, delegate(IntPtr h, IntPtr p) {
            StringBuilder b=new StringBuilder(128); GetClassName(h,b,b.Capacity);
            if(String.Equals(b.ToString(),"SysListView32",StringComparison.OrdinalIgnoreCase)) { found=h; return false; }
            return true;
        },IntPtr.Zero);
        return found;
    }
    public static IntPtr[] FindFileLists(IntPtr parent) {
        var lists=new System.Collections.Generic.List<IntPtr>();
        EnumChildWindows(parent, delegate(IntPtr h, IntPtr p) {
            StringBuilder b=new StringBuilder(128); GetClassName(h,b,b.Capacity);
            if(String.Equals(b.ToString(),"SysListView32",StringComparison.OrdinalIgnoreCase)) lists.Add(h);
            return true;
        },IntPtr.Zero);
        return lists.ToArray();
    }
}
'@
}


# La selección de archivos se realiza mediante el parámetro oficial /fn de Mp3tag.
# No se envían mensajes LVM con punteros de memoria entre procesos.

$configPath = Join-Path $PSScriptRoot "configuracion.json"
$logPath = Join-Path $PSScriptRoot "registro_auxiliar.txt"
$fallbackLogPath = Join-Path $env:TEMP "registro_auxiliar_radar.txt"

$script:logEnUso = $logPath
$script:avisoRegistro = $false
function Write-Log($message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), [string]$message
    try { Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8 -ErrorAction Stop; $script:logEnUso = $logPath }
    catch {
        $motivo = $_.Exception.Message
        try {
            if (-not $script:avisoRegistro) {
                $script:avisoRegistro = $true
                Add-Content -LiteralPath $fallbackLogPath -Value ("{0}  AVISO: no se pudo escribir en {1} ({2}). El registro sigue en este archivo." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $logPath, $motivo) -Encoding UTF8 -ErrorAction Stop
            }
            Add-Content -LiteralPath $fallbackLogPath -Value $line -Encoding UTF8 -ErrorAction Stop
            $script:logEnUso = $fallbackLogPath
        } catch { Write-Warning "No se pudo escribir el registro." }
    }
    Write-Host $line
}
function Show-Message($message) { [System.Windows.MessageBox]::Show($message, "Descargar Radar", "OK", "Information") | Out-Null }
function Ask-Message($message) { return [System.Windows.MessageBox]::Show($message, "Descargar Radar", "OKCancel", "Question") }

if (-not (Test-Path -LiteralPath $configPath)) { Show-Message "No encuentro configuracion.json:`n$configPath"; exit }
try { $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json }
catch { Show-Message "No se pudo leer configuracion.json:`n$($_.Exception.Message)"; exit }

$folder = $config.carpeta_descargas
$id3Remover = $config.id3_remover
$mp3gainCli = $config.mp3gain_cli
$mp3tag = $config.mp3tag
$objetivoDb = [double]$config.objetivo_db
# Archivos temporales que lee Mp3tag (se borran al terminar cada canción).
# Carpeta donde se dejan esos archivos: la misma que usan las 4 acciones de Mp3tag.
# Orden: 1) "carpeta_archivos_mp3tag" de configuracion.json (opcional), 2) Escritorio\Otros, 3) carpeta del script.
$radarFolder = $PSScriptRoot
$radarFolderConfig = ""
try { $radarFolderConfig = [string]$config.carpeta_archivos_mp3tag } catch {}
if ($radarFolderConfig -and (Test-Path -LiteralPath $radarFolderConfig)) { $radarFolder = $radarFolderConfig }
else {
    $radarDesktopOtros = Join-Path $env:USERPROFILE "Desktop\Otros"
    if (Test-Path -LiteralPath $radarDesktopOtros) { $radarFolder = $radarDesktopOtros }
}
$radarYearFile = Join-Path $radarFolder "radar_year.txt"
$radarGenreFile = Join-Path $radarFolder "radar_genre.txt"
$radarCoverFile = Join-Path $radarFolder "radar_portada.jpg"
foreach ($path in @($folder, $id3Remover, $mp3gainCli, $mp3tag)) {
    if ([string]::IsNullOrWhiteSpace([string]$path) -or -not (Test-Path -LiteralPath $path)) { Show-Message "No encuentro esta ruta configurada:`n$path"; exit }
}

function Get-ID3Window {
    $processes = @(Get-Process -Name "ID3Remover" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
    foreach ($process in $processes) {
        try { $handle = [IntPtr]$process.MainWindowHandle; $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle); if ($null -ne $root) { return @{ Process=$process; Handle=$handle; Root=$root } } } catch { Write-Log "ID3: no se pudo acceder a la ventana; se reintentará." }
    }
    return $null
}
function Send-FileDrop($hwnd, $song) {
    $pathBytes = [System.Text.Encoding]::Unicode.GetBytes($song + [char]0 + [char]0)
    $buffer = New-Object byte[] (20 + $pathBytes.Length)
    [BitConverter]::GetBytes([int]20).CopyTo($buffer,0); [BitConverter]::GetBytes([int]0).CopyTo($buffer,4); [BitConverter]::GetBytes([int]0).CopyTo($buffer,8); [BitConverter]::GetBytes([int]0).CopyTo($buffer,12); [BitConverter]::GetBytes([int]1).CopyTo($buffer,16)
    [Array]::Copy($pathBytes,0,$buffer,20,$pathBytes.Length)
    $memory = [RadarWindows]::GlobalAlloc(0x0042,[UIntPtr]([uint64]$buffer.Length))
    if ($memory -eq [IntPtr]::Zero) { throw "No se pudo reservar memoria para enviar la canción." }
    $locked = [RadarWindows]::GlobalLock($memory)
    if ($locked -eq [IntPtr]::Zero) { [RadarWindows]::GlobalFree($memory) | Out-Null; throw "No se pudo acceder a la memoria para enviar la canción." }
    try { [Runtime.InteropServices.Marshal]::Copy($buffer,0,$locked,$buffer.Length) } catch { [RadarWindows]::GlobalUnlock($memory) | Out-Null; [RadarWindows]::GlobalFree($memory) | Out-Null; throw }
    [RadarWindows]::GlobalUnlock($memory) | Out-Null
    if (-not [RadarWindows]::PostMessage($hwnd,0x0233,$memory,[IntPtr]::Zero)) { [RadarWindows]::GlobalFree($memory) | Out-Null; throw "Windows no pudo enviar la canción a ID3 Remover." }
}
function Invoke-ID3Auto($song) {
    Write-Log "ETAPA ID3: inicio para $song"

    # Cerrar cualquier instancia anterior para trabajar con una sola ventana.
    Get-Process -Name "ID3Remover" -ErrorAction SilentlyContinue | ForEach-Object { try { $_.CloseMainWindow() | Out-Null } catch {} }
    Start-Sleep -Seconds 2
    if (Get-Process -Name "ID3Remover" -ErrorAction SilentlyContinue) {
        throw "Cierra las ventanas anteriores de ID3 Remover y vuelve a intentarlo."
    }

    Start-Process -FilePath $id3Remover | Out-Null
    $window=$null
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        $window=Get-ID3Window
        if ($null -ne $window) { break }
    }
    if ($null -eq $window) { throw "No se encontró una ventana accesible de ID3 Remover." }

    $id3Pid=[uint32]$window.Process.Id
    $mainHandle=[IntPtr]$window.Handle
    Write-Log "ID3: ventana principal localizada en PID $id3Pid."
    Send-FileDrop $mainHandle $song
    Write-Log "ID3: archivo enviado a la aplicación."

    # Esperar al botón Remove y activarlo como en las versiones anteriores.
    $removeButton=$null; $lastError=""
    for ($i=0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $window=Get-ID3Window
            if ($null -eq $window) { continue }
            $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,"1003")
            $removeButton=$window.Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
            if ($null -ne $removeButton -and $removeButton.Current.IsEnabled) { break }
            $removeButton=$null
        } catch { $lastError=$_.Exception.Message; $removeButton=$null }
    }
    if ($null -eq $removeButton) {
        if ($lastError) { Write-Log "ID3 automatización: $lastError" }
        throw "No se encontró el botón Remove habilitado."
    }

    $removeClicked=$false
    try {
        $invoke=$null
        if ($removeButton.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$invoke)) {
            $invoke.Invoke(); $removeClicked=$true
        }
    } catch { Write-Log "ID3: no se pudo activar Remove por automatización; se intentará clic físico." }
    if (-not $removeClicked) {
        $rect=$removeButton.Current.BoundingRectangle
        if ($rect.Width -le 0 -or $rect.Height -le 0) { throw "La posición del botón Remove no es válida." }
        [RadarWindows]::SetCursorPos([int]($rect.Left+$rect.Width/2),[int]($rect.Top+$rect.Height/2)) | Out-Null
        Start-Sleep -Milliseconds 200
        [RadarWindows]::mouse_event(0x0002,0,0,0,[UIntPtr]::Zero)
        Start-Sleep -Milliseconds 100
        [RadarWindows]::mouse_event(0x0004,0,0,0,[UIntPtr]::Zero)
    }
    Write-Log "ID3: se pulsó Remove; esperando el aviso final."

    # El aviso se cierra con Intro, que es exactamente la acción manual indicada.
    # Se identifica una ventana emergente del MISMO proceso, sin depender de que
    # Windows exponga el texto del mensaje como un control accesible.
    $shell=New-Object -ComObject WScript.Shell
    $popupHandle=[IntPtr]::Zero
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        $candidate=[RadarWindows]::FindOtherWindowForProcess($id3Pid,$mainHandle)
        if ($candidate -ne [IntPtr]::Zero) { $popupHandle=$candidate; break }
        $mainStillRunning=Get-Process -Id $id3Pid -ErrorAction SilentlyContinue
        if ($null -eq $mainStillRunning) { break }
    }
    if ($popupHandle -eq [IntPtr]::Zero) {
        throw "ID3Remover no mostró una ventana emergente identificable. No se continuará con MP3Gain."
    }

    $popupTitle=[RadarWindows]::WindowText($popupHandle)
    Write-Log "ID3: ventana emergente localizada. Título='$popupTitle'; HWND=$popupHandle."
    [RadarWindows]::BringWindowToTop($popupHandle) | Out-Null
    [RadarWindows]::SetForegroundWindow($popupHandle) | Out-Null
    Start-Sleep -Milliseconds 300
    Start-Sleep -Milliseconds 200
    $shell.SendKeys('~')
    Write-Log "ID3: se envió Intro para aceptar el aviso final."

    # No avanzar hasta comprobar que el aviso desapareció.
    $popupClosed=$false
    for ($verify=0; $verify -lt 30; $verify++) {
        Start-Sleep -Milliseconds 200
        if (-not [RadarWindows]::IsWindow($popupHandle)) { $popupClosed=$true; break }
    }
    if (-not $popupClosed) {
        throw "Se envió Intro, pero el aviso de ID3Remover sigue abierto. No se continuará con MP3Gain."
    }
    Write-Log "ID3: aviso final cerrado tras Intro."

    # Tras aceptar el aviso, cerrar ID3Remover como hace el botón Cancelar.
    # El botón no está expuesto ni por UI Automation ni como control Win32
    # enumerado. Se envía primero IDCANCEL al formulario y, si sigue visible,
    # WM_CLOSE a la ventana principal. No se continúa mientras siga visible.
    Start-Sleep -Milliseconds 400
    $window=Get-ID3Window
    if ($null -eq $window) {
        Write-Log "ID3: la ventana principal ya no está disponible tras aceptar el aviso."
    } else {
        $mainHandle=[IntPtr]$window.Handle
        Write-Log "ID3: enviando comando estándar Cancelar (IDCANCEL) a HWND=$mainHandle."
        [RadarWindows]::SendMessage($mainHandle,0x0111,[IntPtr]2,[IntPtr]::Zero) | Out-Null
        $mainClosed=$false
        for ($verifyMain=0; $verifyMain -lt 15; $verifyMain++) {
            Start-Sleep -Milliseconds 200
            if (-not [RadarWindows]::IsWindowVisible($mainHandle)) { $mainClosed=$true; break }
        }
        if (-not $mainClosed) {
            Write-Log "ID3: IDCANCEL no cerró la ventana; enviando WM_CLOSE como cierre equivalente a Cancelar."
            [RadarWindows]::PostMessage($mainHandle,0x0010,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
            for ($verifyMain=0; $verifyMain -lt 25; $verifyMain++) {
                Start-Sleep -Milliseconds 200
                if (-not [RadarWindows]::IsWindowVisible($mainHandle)) { $mainClosed=$true; break }
            }
        }
        if (-not $mainClosed) {
            throw "Se aceptó el aviso, pero ID3Remover no se cerró con IDCANCEL ni WM_CLOSE. No se continuará con MP3Gain."
        }
        Write-Log "ID3: ventana principal cerrada tras IDCANCEL/WM_CLOSE."
    }
    Write-Log "ETAPA ID3: secuencia Intro + Cancelar completada para $song"
}

function Invoke-MP3GainCommand($arguments,$song,$stage) {
    $stdoutFile=Join-Path $env:TEMP ("Radar_"+[guid]::NewGuid().ToString()+".out"); $stderrFile=Join-Path $env:TEMP ("Radar_"+[guid]::NewGuid().ToString()+".err")
    try {
        $process=Start-Process -FilePath $mp3gainCli -ArgumentList $arguments -PassThru -Wait -NoNewWindow -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        if (Test-Path -LiteralPath $stdoutFile) { Get-Content -LiteralPath $stdoutFile | ForEach-Object { Write-Log "$stage SALIDA: $_" } }
        if (Test-Path -LiteralPath $stderrFile) { Get-Content -LiteralPath $stderrFile | ForEach-Object { Write-Log "$stage MENSAJE: $_" } }
        Write-Log "$stage código de salida: $($process.ExitCode)"
        if ($process.ExitCode -ne 0) { throw "$stage terminó con código $($process.ExitCode). Canción: $song" }
    } finally { Remove-Item -LiteralPath $stdoutFile,$stderrFile -Force -ErrorAction SilentlyContinue }
}
function Invoke-MP3Gain($song) {
    Write-Log "ETAPA MP3GAIN: inicio. Archivo: $song"
    Write-Log "Objetivo configurado: $objetivoDb dB"
    $quotedSong='"'+$song+'"'

    # ANÁLISIS PREVIO: no aplica ganancia ni modifica el audio.
    # /s s evita leer/escribir etiquetas ReplayGain; al no incluir /r, /a ni /g,
    # MP3Gain solo analiza y muestra la ganancia recomendada respecto a 89 dB.
    Write-Log "MP3GAIN: análisis ORIGINAL previo al ajuste (solo lectura; referencia ReplayGain 89 dB)."
    Invoke-MP3GainCommand "/s s /o $quotedSong" $song "MP3GAIN ANALISIS ORIGINAL"

    # Se conserva exactamente el ajuste que ya estaba funcionando.
    $offset=[int][Math]::Round($objetivoDb-89.0)
    Write-Log "Ajuste relativo calculado: $offset dB"
    Invoke-MP3GainCommand "/r /d $offset /k /p $quotedSong" $song "MP3GAIN AJUSTE"

    # Informe posterior, igual que en la versión anterior.
    Invoke-MP3GainCommand "/s s /o $quotedSong" $song "MP3GAIN INFORME FINAL"
    Write-Log "ETAPA MP3GAIN: fin correcto para $song"
}

function ConvertFrom-Synchsafe([byte[]]$b,[int]$offset) { return ([int]$b[$offset] -shl 21) -bor ([int]$b[$offset+1] -shl 14) -bor ([int]$b[$offset+2] -shl 7) -bor [int]$b[$offset+3] }
function Get-TextFrameValue([byte[]]$data) {
    if ($data.Length -lt 2) { return "" }
    switch ([int]$data[0]) {
        0 { return [Text.Encoding]::GetEncoding(28591).GetString($data,1,$data.Length-1).Trim([char]0) }
        1 { $s=[Text.Encoding]::Unicode.GetString($data,1,$data.Length-1); return $s.Trim([char]0,[char]0xFEFF) }
        2 { $s=[Text.Encoding]::BigEndianUnicode.GetString($data,1,$data.Length-1); return $s.Trim([char]0,[char]0xFEFF) }
        3 { return [Text.Encoding]::UTF8.GetString($data,1,$data.Length-1).Trim([char]0) }
        default { return "" }
    }
}
function Get-Id3Data($path) {
    $bytes=[IO.File]::ReadAllBytes($path); $frames=New-Object System.Collections.Generic.List[object]; $version=3; $tagEnd=0
    if ($bytes.Length -ge 10 -and [Text.Encoding]::ASCII.GetString($bytes,0,3) -eq "ID3") {
        $version=[int]$bytes[3]; if ($version -notin @(3,4)) { throw "La etiqueta ID3v2.$version no es compatible con la escritura automática; no se modificó." }
        if (($bytes[5] -band 0xC0) -ne 0) { throw "La etiqueta ID3 contiene opciones especiales; se evita modificarla para no dañar los metadatos." }
        $tagSize=ConvertFrom-Synchsafe $bytes 6; $tagEnd=[Math]::Min($bytes.Length,10+$tagSize); $pos=10
        while ($pos+10 -le $tagEnd) {
            $id=[Text.Encoding]::ASCII.GetString($bytes,$pos,4); if ($id -notmatch '^[A-Z0-9]{4}$') { break }
            if ($version -eq 4) { $size=ConvertFrom-Synchsafe $bytes ($pos+4) } else { $size=[BitConverter]::ToInt32([byte[]]@($bytes[$pos+7],$bytes[$pos+6],$bytes[$pos+5],$bytes[$pos+4]),0) }
            if ($size -lt 0 -or $pos+10+$size -gt $tagEnd) { throw "La etiqueta ID3 tiene una estructura inesperada; se evita modificarla." }
            $payload=New-Object byte[] $size; [Array]::Copy($bytes,$pos+10,$payload,0,$size)
            $frames.Add([pscustomobject]@{Id=$id;Flags=[byte[]]@($bytes[$pos+8],$bytes[$pos+9]);Payload=$payload})
            $pos+=10+$size
        }
    } else { $tagEnd=0 }
    $audio=New-Object byte[] ($bytes.Length-$tagEnd); if ($audio.Length -gt 0) { [Array]::Copy($bytes,$tagEnd,$audio,0,$audio.Length) }
    $title=""; $artist=""
    foreach ($fr in $frames) { if ($fr.Id -eq 'TIT2') { $title=Get-TextFrameValue $fr.Payload }; if ($fr.Id -eq 'TPE1') { $artist=Get-TextFrameValue $fr.Payload } }
    return @{Bytes=$bytes;Frames=$frames;Version=$version;TagEnd=$tagEnd;Audio=$audio;Title=$title;Artist=$artist}
}

# ======================================================================
# IMPORTANTE: PowerShell NO escribe etiquetas en el MP3. Solo lee el archivo
# para VERIFICAR lo que Mp3tag ha guardado. Los datos los escribe Mp3tag
# mediante el grupo de acciones "Radar datos" (ver instrucciones al arrancar).
# ======================================================================

$radarGroupName = 'Radar datos'

function Get-JsonFromUrl([string]$url,[hashtable]$headers,[int]$timeout) {
    $response = $null
    for ($try=1; $try -le 5; $try++) {
        try {
            # El User-Agent se pasa con -UserAgent: Windows PowerShell 5.1 puede rechazarlo dentro de -Headers.
            $otras = @{}; $agente = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MiRadarMusicalAuxiliar/1.1'
            if ($headers) { foreach ($k in $headers.Keys) { if ($k -ieq 'User-Agent') { $agente = [string]$headers[$k] } else { $otras[$k] = $headers[$k] } } }
            $response = Invoke-WebRequest -Uri $url -Headers $otras -UserAgent $agente -TimeoutSec $timeout -UseBasicParsing; break
        }
        catch {
            $msg = $_.Exception.Message
            if ($try -lt 5 -and $msg -match '503|429|502|504|tiempo|timed out|timeout') {
                Write-Log "Red: '$msg'. Reintento $try de 4 en $(3*$try) s."
                Start-Sleep -Seconds (3*$try)
            } else { throw }
        }
    }
    $stream = $response.RawContentStream
    $bytes = New-Object byte[] ([int]$stream.Length)
    $stream.Position = 0
    [void]$stream.Read($bytes,0,$bytes.Length)
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    return ($text | ConvertFrom-Json)
}

function ConvertTo-ComparableText([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return '' }
    # Símbolos usados como letras en nombres artísticos: Ke$ha, A$AP, P!nk, M@ndy...
    $text = $text -replace '\$','s' -replace '(?<=\p{L})!(?=\p{L})','i' -replace '(?<=\p{L})@(?=\p{L})','a'
    $decomposed = $text.Normalize([Text.NormalizationForm]::FormD)
    $sb = New-Object Text.StringBuilder
    foreach ($c in $decomposed.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($c) -ne [Globalization.UnicodeCategory]::NonSpacingMark) { [void]$sb.Append($c) }
    }
    $clean = $sb.ToString().ToLowerInvariant() -replace '[^\p{L}\p{N}]+',' '
    return $clean.Trim()
}
function Test-TextLooselyMatches([string]$a,[string]$b) {
    $x = ConvertTo-ComparableText $a; $y = ConvertTo-ComparableText $b
    if (-not $x -or -not $y) { return $false }
    if ($x -eq $y) { return $true }
    # Mismo texto sin espacios: "AC/DC" = "ACDC", "Ke ha" = "Keha".
    if (($x -replace ' ','') -eq ($y -replace ' ','')) { return $true }
    $shorter = [Math]::Min($x.Length,$y.Length)
    if ($shorter -lt 4) { return $false }
    return ($x.Contains($y) -or $y.Contains($x))
}
function Test-ArtistLooselyMatches([string]$wanted,[string]$found) {
    if (Test-TextLooselyMatches $wanted $found) { return $true }
    $foundClean = ConvertTo-ComparableText $found
    if (-not $foundClean) { return $false }
    $parts = @(([string]$wanted) -split '(?i),|;|&|/|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bcon\b|\by\b|\band\b' | ForEach-Object { ConvertTo-ComparableText $_ })
    foreach ($p in $parts) { if ($p.Length -ge 3 -and $foundClean.Contains($p)) { return $true } }
    return $false
}

function Get-LookupTitle([string]$title,[string]$artist) {
    # Uololo a veces deja el título como "Artista - Título". Para buscar se quita el prefijo del artista.
    $t=([string]$title).Trim()
    for ($i=0; $i -lt 3; $i++) {
        $idx=$t.IndexOf(' - ')
        if ($idx -lt 1) { break }
        $head=$t.Substring(0,$idx); $rest=$t.Substring($idx+3).Trim()
        if ($rest -and (Test-ArtistLooselyMatches $artist $head)) { $t=$rest } else { break }
    }
    return $t
}
function Get-CoreTitle([string]$title) {
    # Título sin colaboraciones ni etiquetas de versión, para comparar con los catálogos.
    $t = [string]$title
    $t = $t -replace '(?i)\s*[\(\[][^\)\]]*\b(feat|ft|featuring|with|con)\b[^\)\]]*[\)\]]',''
    $t = $t -replace '(?i)\s+(feat\.?|ft\.?|featuring)\s+.*$',''
    $t = $t -replace '(?i)\s*[\(\[][^\)\]]*\b(remaster(ed)?|version|versi.n|edit|mono|stereo|explicit|clean)\b[^\)\]]*[\)\]]',''
    $t = $t -replace '(?i)\s+-\s+.*\b(remaster(ed)?|version|versi.n|edit|mono|stereo)\b.*$',''
    return (ConvertTo-ComparableText $t)
}
function Test-TitleMatches([string]$wanted,[string]$found) {
    if (Test-TextLooselyMatches $wanted $found) { return $true }
    $a = Get-CoreTitle $wanted; $b = Get-CoreTitle $found
    if (-not $a -or -not $b) { return $false }
    if ($a -eq $b) { return $true }
    if ([Math]::Min($a.Length,$b.Length) -ge 4 -and ($a.Contains($b) -or $b.Contains($a))) { return $true }
    # Coincidencia por palabras: tolera "&"/"and"/"y", apóstrofos, artículos, etc.
    $ignorar = @('the','a','el','la','los','las','de','and','y','e')
    $wa = @($a -split ' ' | Where-Object { $_ -and ($ignorar -notcontains $_) })
    $wb = @($b -split ' ' | Where-Object { $_ -and ($ignorar -notcontains $_) })
    if ($wa.Count -eq 0 -or $wb.Count -eq 0) { return $false }
    $comunes = @($wa | Where-Object { $wb -contains $_ }).Count
    return (($comunes / [Math]::Max($wa.Count,$wb.Count)) -ge 0.8)
}
function Get-MainArtist([string]$artist) {
    $p = @(([string]$artist) -split '(?i)\s*,\s*|\s*;\s*|\s*&\s*|\s*/\s*|\s+feat\.?\s+|\s+ft\.?\s+|\s+featuring\s+|\s+x\s+|\s+y\s+|\s+con\s+')
    return ([string]$p[0]).Trim()
}
function Get-SearchTerms([string]$artist,[string]$title) {
    $core = (([string]$title) -replace '(?i)\s*[\(\[].*$','' -replace '(?i)\s+(feat\.?|ft\.?|featuring)\s+.*$','').Trim()
    $main = Get-MainArtist $artist
    return @{ Core=$core; Main=$main; Terms=@(@(
        (([string]$artist + ' ' + [string]$title).Trim()),
        (($main + ' ' + $core).Trim()),
        $core
    ) | Where-Object { $_ } | Select-Object -Unique) }
}
$script:cabecerasCatalogo = @{'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) MiRadarMusicalAuxiliar/1.1'}

function Find-iTunesTrack([string]$artist,[string]$title) {
    $b = Get-SearchTerms $artist $title
    foreach ($term in $b.Terms) {
        foreach ($country in @('es','us')) {
            $url = 'https://itunes.apple.com/search?term=' + [Uri]::EscapeDataString($term) + '&media=music&entity=song&explicit=Yes&limit=25&country=' + $country
            try { $result = Get-JsonFromUrl $url $script:cabecerasCatalogo 25 } catch { Write-Log "iTunes: consulta fallida ($term / $country): $($_.Exception.Message)"; continue }
            $lista = @($result.results | Where-Object { $_ })
            Write-Log "iTunes ($country) '$term': $($lista.Count) resultados."
            foreach ($r in $lista) {
                if (-not $r.artworkUrl100) { continue }
                if ((Test-ArtistLooselyMatches $artist ([string]$r.artistName)) -and (Test-TitleMatches $title ([string]$r.trackName))) { return $r }
            }
            if ($lista.Count -gt 0) { Write-Log ("iTunes: ninguno coincide. Primeros: " + ((@($lista | Select-Object -First 3) | ForEach-Object { "$($_.artistName) - $($_.trackName)" }) -join ' | ')) }
        }
    }
    return $null
}

function Find-DeezerTrack([string]$artist,[string]$title) {
    $b = Get-SearchTerms $artist $title
    $queries = @(@(('artist:"' + $b.Main.Replace('"','') + '" track:"' + $b.Core.Replace('"','') + '"')) + $b.Terms | Select-Object -Unique)
    foreach ($q in $queries) {
        $url = 'https://api.deezer.com/search?q=' + [Uri]::EscapeDataString($q) + '&limit=25'
        try { $result = Get-JsonFromUrl $url $script:cabecerasCatalogo 25 } catch { Write-Log "Deezer: consulta fallida ($q): $($_.Exception.Message)"; continue }
        if ($result.error) { Write-Log "Deezer: error en la consulta ($q): $($result.error.message)"; continue }
        $lista = @($result.data | Where-Object { $_ })
        Write-Log "Deezer '$q': $($lista.Count) resultados."
        foreach ($r in $lista) {
            $portada = [string]$r.album.cover_xl; if (-not $portada) { $portada = [string]$r.album.cover_big }
            if (-not $portada) { continue }
            if (-not ((Test-ArtistLooselyMatches $artist ([string]$r.artist.name)) -and (Test-TitleMatches $title ([string]$r.title)))) { continue }
            $year = ''; $genre = ''
            try {
                $album = Get-JsonFromUrl ('https://api.deezer.com/album/' + [string]$r.album.id) $script:cabecerasCatalogo 20
                if (([string]$album.release_date) -match '^\d{4}') { $year = $Matches[0] }
                $g = @($album.genres.data | Where-Object { $_ } | Select-Object -First 1)
                if ($g.Count -gt 0) { $genre = [string]$g[0].name }
            } catch { Write-Log "Deezer: no se pudo leer el álbum $($r.album.id): $($_.Exception.Message)" }
            return @{ ArtUrl=$portada; Artist=[string]$r.artist.name; Title=[string]$r.title; Genre=$genre; Year=$year }
        }
        if ($lista.Count -gt 0) { Write-Log ("Deezer: ninguno coincide. Primeros: " + ((@($lista | Select-Object -First 3) | ForEach-Object { "$($_.artist.name) - $($_.title)" }) -join ' | ')) }
    }
    return $null
}

function Save-CoverImage([string]$artUrl,[string]$destination) {
    if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Force }
    Invoke-WebRequest -Uri $artUrl -OutFile $destination -TimeoutSec 30 -UseBasicParsing -UserAgent ([string]$script:cabecerasCatalogo['User-Agent'])
    $bytes = [IO.File]::ReadAllBytes($destination)
    $isJpeg = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xD8 -and $bytes[2] -eq 0xFF)
    $isPng = ($bytes.Length -ge 8 -and $bytes[0] -eq 0x89 -and $bytes[1] -eq 0x50 -and $bytes[2] -eq 0x4E -and $bytes[3] -eq 0x47)
    if ($bytes.Length -lt 2048 -or (-not $isJpeg -and -not $isPng)) {
        Remove-Item -LiteralPath $destination -Force -ErrorAction SilentlyContinue
        throw 'La descarga no parece ser una imagen JPEG o PNG válida.'
    }
    if ($isPng) {
        # El archivo que lee Mp3tag se llama .jpg; si llega un PNG se convierte a JPEG real.
        Add-Type -AssemblyName System.Drawing
        $tmp = $destination + '.tmp'
        $img = [System.Drawing.Image]::FromFile($destination)
        try { $img.Save($tmp,[System.Drawing.Imaging.ImageFormat]::Jpeg) } finally { $img.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $destination -Force
    }
}

function Get-iTunesTrackInfo([string]$artist,[string]$title,[string]$destination) {
    # 1) iTunes. 2) Si iTunes no encuentra la canción (p. ej. porque ya no devuelve
    #    canciones marcadas como explícitas) o su imagen falla, Deezer.
    $chosen = Find-iTunesTrack $artist $title
    if ($chosen) {
        $artUrl = [string]$chosen.artworkUrl100 -replace '([0-9]+x[0-9]+)bb','600x600bb'
        try {
            Save-CoverImage $artUrl $destination
            Write-Log "iTunes: portada descargada. Artista='$($chosen.artistName)'; canción='$($chosen.trackName)'; género iTunes='$($chosen.primaryGenreName)'; URL='$artUrl'."
            $itunesYear=''
            if (([string]$chosen.releaseDate) -match '^\d{4}') { $itunesYear=$Matches[0] }
            return @{ Path=$destination; Genre=[string]$chosen.primaryGenreName; Year=$itunesYear }
        } catch { Write-Log "iTunes: la portada no se pudo descargar ($($_.Exception.Message)); se prueba con Deezer." }
    } else {
        Write-Log "iTunes no encontró una coincidencia fiable; se prueba con Deezer."
    }
    $dz = Find-DeezerTrack $artist $title
    if (-not $dz) { throw "Ni iTunes ni Deezer devolvieron una canción que coincida de forma fiable con artista='$artist' y título='$title'. No se usará ninguna portada." }
    Save-CoverImage $dz.ArtUrl $destination
    Write-Log "Deezer: portada descargada. Artista='$($dz.Artist)'; canción='$($dz.Title)'; género Deezer='$($dz.Genre)'; año='$($dz.Year)'; URL='$($dz.ArtUrl)'."
    return @{ Path=$destination; Genre=$dz.Genre; Year=$dz.Year }
}

$genreList=@('Pop','Rock','Pop Rock','R&B','Rumba / Flamenco','Fusión / Mestizaje','Urbana','Dance','Musical / BSO','Chill / Acústico','Autor / Raíz','Flamenco Pop','Latina','Disco','Flamenco de Autor','Dance Pop','Tropical')
function Get-GenreCategory([string]$tag,[switch]$Loose) {
    $t=$tag.ToLowerInvariant().Trim()
    if ($t -match 'salsa|bachata|merengue|cumbia|bolero') { return 'Latina' }
    if ($t -match 'flamenco' -and $t -match 'pop') { return 'Flamenco Pop' }
    if ($t -match 'flamenco' -and $t -match 'cantautor|singer.?songwriter|autor') { return 'Flamenco de Autor' }
    if ($t -match 'flamenco|rumba') { return 'Rumba / Flamenco' }
    if ($t -match 'dance.?pop|dance pop') { return 'Dance Pop' }
    if ($t -match 'disco') { return 'Disco' }
    if ($t -match 'r.?&.?b|rhythm and blues|neo.?soul') { return 'R&B' }
    if ($t -match 'reggaeton|reguet[oó]n|trap|urbano|hip.?hop|rap|drill') { return 'Urbana' }
    if ($t -match 'mestizaje|fusion|fusi[oó]n|world music') { return 'Fusión / Mestizaje' }
    if ($t -match 'soundtrack|film score|musical|bso|original score') { return 'Musical / BSO' }
    if ($t -match 'singer.?songwriter|cantautor|folk|roots|ra[ií]z') { return 'Autor / Raíz' }
    if ($t -match 'chill|acoustic|ac[uú]stico|ambient|downtempo') { return 'Chill / Acústico' }
    if ($t -match 'tropical|soca|calypso') { return 'Tropical' }
    if ($t -match 'dance|electronic|house|techno|trance|edm') { return 'Dance' }
    if ($t -match 'pop.?rock|pop rock') { return 'Pop Rock' }
    if ($t -match '^rock$|hard rock|alternative rock|indie rock|punk rock|classic rock') { return 'Rock' }
    if ($t -match '^pop$|synth.?pop|indie pop') { return 'Pop' }
    if ($Loose) {
        # Modo "el más parecido": se usa solo cuando ninguna etiqueta encaja con exactitud.
        if ($t -match 'latin|latino|latina') { return 'Latina' }
        if ($t -match 'flamenc|rumba') { return 'Rumba / Flamenco' }
        if ($t -match 'urban|reggaet|reguet|hip|rap|trap') { return 'Urbana' }
        if ($t -match 'soul|funk|r.?&.?b') { return 'R&B' }
        if ($t -match 'electr|dance|house|techno|baile') { return 'Dance' }
        if ($t -match 'banda sonora|soundtrack|score|bso') { return 'Musical / BSO' }
        if ($t -match 'folk|cantautor|songwriter|raiz|ra[ií]z|autor') { return 'Autor / Raíz' }
        if ($t -match 'chill|acoustic|ac[uú]stic|ambient') { return 'Chill / Acústico' }
        if ($t -match 'tropical') { return 'Tropical' }
        if ($t -match 'rock') { return 'Rock' }
        if ($t -match 'pop') { return 'Pop' }
    }
    return $null
}
function Select-GenreFromTags($tags,[switch]$Loose) {
    $counts=@{}
    foreach ($tag in $tags) { if ($Loose) { $cat=Get-GenreCategory ([string]$tag) -Loose } else { $cat=Get-GenreCategory ([string]$tag) }; if ($cat) { if (-not $counts.ContainsKey($cat)) { $counts[$cat]=0 }; $counts[$cat] += 1 } }
    if (-not $counts.Count) { return $null }
    $priority=@('Flamenco Pop','Flamenco de Autor','Dance Pop','Pop Rock','Latina','R&B','Rumba / Flamenco','Fusión / Mestizaje','Musical / BSO','Autor / Raíz','Chill / Acústico','Tropical','Disco','Urbana','Dance','Rock','Pop')
    $best = $counts.Keys | Sort-Object @{Expression={-$counts[$_]}}, @{Expression={[array]::IndexOf($priority,[string]$_)}} | Select-Object -First 1
    return [string]$best
}
function Get-MusicBrainzYear($rec) {
    $d=[string]$rec.'first-release-date'
    if ($d -match '^\d{4}') { return $Matches[0] }
    $dates=@()
    foreach ($r in @($rec.releases)) { if ($r -and ([string]$r.date) -match '^\d{4}') { $dates += ([string]$r.date).Substring(0,4) } }
    if ($dates.Count -gt 0) { return [string]($dates | Sort-Object | Select-Object -First 1) }
    return ''
}
function Get-MusicBrainzTagNames([string]$path,[string]$id,[hashtable]$headers) {
    Start-Sleep -Milliseconds 1100
    $names=@()
    try {
        $d=Get-JsonFromUrl ('https://musicbrainz.org/ws/2/'+$path+'/'+$id+'?inc=tags+genres&fmt=json') $headers 20
        if ($d.tags) { $names += @($d.tags | ForEach-Object { $_.name }) }
        if ($d.genres) { $names += @($d.genres | ForEach-Object { $_.name }) }
    } catch { Write-Log "MusicBrainz: consulta de etiquetas ($path) no disponible: $($_.Exception.Message)" }
    return $names
}
function Get-MusicBrainzMetadata([string]$title,[string]$artist,[string]$fallbackGenre) {
    if ([string]::IsNullOrWhiteSpace($title) -or [string]::IsNullOrWhiteSpace($artist)) { throw "Uololo no dejó título o artista legible en las etiquetas." }
    $headers=@{'User-Agent'='MiRadarMusicalAuxiliar/1.0 (personal music library)'}
    $recordings=@()
    $attempts=@(
        ('recording:"'+$title.Replace('\',' ').Replace('"','')+'" AND artist:"'+$artist.Replace('\',' ').Replace('"','')+'"'),
        ('recording:"'+$title.Replace('\',' ').Replace('"','')+'"'),
        ($artist.Replace('\',' ').Replace('"','')+' '+$title.Replace('\',' ').Replace('"',''))
    )
    foreach ($query in $attempts) {
        Start-Sleep -Milliseconds 1100
        $url='https://musicbrainz.org/ws/2/recording/?query='+[Uri]::EscapeDataString($query)+'&fmt=json&limit=15'
        try { $search=Get-JsonFromUrl $url $headers 25 } catch { Write-Log "MusicBrainz: consulta fallida: $($_.Exception.Message)"; continue }
        $found=@($search.recordings | Where-Object { $_ })
        $good=@()
        foreach ($r in $found) {
            $names=@(); try { foreach ($c in @($r.'artist-credit')) { $names += [string]$c.name; $names += [string]$c.artist.name } } catch {}
            $artistOk=$false
            foreach ($n in $names) { if ($n -and (Test-ArtistLooselyMatches $artist $n)) { $artistOk=$true; break } }
            if ($artistOk) { $good += $r }
        }
        if ($good.Count -gt 0) { $recordings=$good; break }
        Start-Sleep -Milliseconds 1100
    }
    if ($recordings.Count -eq 0) { throw "MusicBrainz no encontró una coincidencia del artista '$artist' para '$title'." }
    $ranked=@()
    foreach ($rec in $recordings) {
        if ([int]$rec.score -lt 85) { continue }
        if (-not (Test-TitleMatches $title ([string]$rec.title))) { continue }
        $y=Get-MusicBrainzYear $rec
        if (-not $y) { continue }
        $ranked += [pscustomobject]@{ Rec=$rec; Score=[int]$rec.score; Year=$y }
    }
    if ($ranked.Count -eq 0) { throw "MusicBrainz no devolvió una coincidencia suficientemente segura con fecha de publicación para '$artist - $title'. Mejor resultado: '$($recordings[0].title)' (puntuación $($recordings[0].score))." }
    $best = $ranked | Sort-Object @{Expression={$_.Score};Descending=$true}, @{Expression={$_.Year};Descending=$false} | Select-Object -First 1
    $rec=$best.Rec; $year=$best.Year

    $artistId=$null; $rgId=$null
    try { $artistId=[string]@($rec.'artist-credit')[0].artist.id } catch {}
    try { foreach ($r in @($rec.releases)) { if ($r.'release-group' -and $r.'release-group'.id) { $rgId=[string]$r.'release-group'.id; break } } } catch {}

    $genre=$null; $source=''; $allTags=@()
    $stages=@(
        @{Name='grabación';Path='recording';Id=[string]$rec.id},
        @{Name='álbum/sencillo';Path='release-group';Id=$rgId},
        @{Name='artista';Path='artist';Id=$artistId}
    )
    foreach ($stage in $stages) {
        if ([string]::IsNullOrWhiteSpace([string]$stage.Id)) { continue }
        $names=@(Get-MusicBrainzTagNames $stage.Path ([string]$stage.Id) $headers)
        if ($names.Count -gt 0) {
            $allTags += $names
            $g=Select-GenreFromTags $names
            if ($g) { $genre=$g; $source="MusicBrainz ($($stage.Name))"; break }
        }
    }
    if (-not $genre -and -not [string]::IsNullOrWhiteSpace($fallbackGenre)) {
        $g=Get-GenreCategory $fallbackGenre
        if ($g) { $genre=$g; $source="iTunes ('$fallbackGenre')" }
    }
    if (-not $genre -and $allTags.Count -gt 0) {
        $g=Select-GenreFromTags $allTags -Loose
        if ($g) { $genre=$g; $source='MusicBrainz (el más parecido de tu lista)' }
    }
    if (-not $genre -and -not [string]::IsNullOrWhiteSpace($fallbackGenre)) {
        $g=Get-GenreCategory $fallbackGenre -Loose
        if ($g) { $genre=$g; $source="iTunes ('$fallbackGenre', el más parecido de tu lista)" }
    }
    if (-not $genre) { throw "Se encontró el año $year, pero ni MusicBrainz ni iTunes aportan un género que encaje con tu lista de géneros (etiquetas vistas: $($allTags -join ', '); género iTunes: '$fallbackGenre'). No se inventará un género." }
    return @{Year=$year;Genre=$genre;GenreSource=$source;Tags=($allTags -join ', ');Score=$best.Score;RecordingId=[string]$rec.id}
}

# ---- Verificación de lo que Mp3tag ha guardado realmente en el archivo ----
function Get-Mp3tagSavedState([string]$song,[string]$year,[string]$genre) {
    try { $info=Get-Id3Data $song } catch { return @{Ok=$false;Problems=@("No se pudo leer el MP3: $($_.Exception.Message)");Summary=''} }
    $values=@{}
    foreach ($frame in $info.Frames) {
        if ($frame.Id -in @('TIT2','TPE1','TALB','TYER','TDRC','TCON')) { $values[$frame.Id]=Get-TextFrameValue $frame.Payload }
    }
    $album=([string]$values['TALB']).Trim()
    $savedYear=([string]$values['TYER']).Trim(); if (-not $savedYear) { $savedYear=([string]$values['TDRC']).Trim() }
    $savedGenre=(([string]$values['TCON']) -replace '^\(\d+\)','').Trim()
    $savedTitle=([string]$values['TIT2']).Trim(); $savedArtist=([string]$values['TPE1']).Trim()
    $coverFrames=@($info.Frames | Where-Object { $_.Id -eq 'APIC' -and $_.Payload.Length -gt 2048 })
    $hasCover=($coverFrames.Count -gt 0)
    $problems=@()
    if (-not $savedTitle) { $problems += 'Título vacío' }
    if (-not $savedArtist) { $problems += 'Intérprete vacío' }
    if ($album -ne $year) { $problems += "Álbum='$album' (debe ser '$year')" }
    if (-not ($savedYear.Length -ge 4 -and $savedYear.Substring(0,4) -eq $year)) { $problems += "Año='$savedYear' (debe ser '$year')" }
    if ($savedGenre -ne $genre) { $problems += "Género='$savedGenre' (debe ser '$genre')" }
    if (-not $hasCover) { $problems += 'Sin carátula incrustada' }
    return @{Ok=($problems.Count -eq 0);Problems=$problems;Title=$savedTitle;Artist=$savedArtist;Album=$album;Year=$savedYear;Genre=$savedGenre}
}

# ---- Comprobación de que el grupo de acciones existe en Mp3tag ----
function Get-RadarActionGroupStatus {
    $foundAny=$false
    $dirs=@((Join-Path $env:APPDATA 'Mp3tag\data\actions'),(Join-Path (Split-Path -Parent $mp3tag) 'data\actions'))
    foreach ($dir in $dirs) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        foreach ($file in @(Get-ChildItem -LiteralPath $dir -Filter '*.mta' -File -ErrorAction SilentlyContinue)) {
            try {
                if (Select-String -LiteralPath $file.FullName -SimpleMatch 'radar_year.txt' -Quiet) {
                    $foundAny=$true
                    # Comparación tolerante: ignora mayúsculas, barras / o \ y barras duplicadas.
                    $content = (Get-Content -LiteralPath $file.FullName -Raw) -replace '/','\' -replace '\\+','\'
                    $wantedPath = ($radarYearFile -replace '/','\' -replace '\\+','\')
                    if ($content.IndexOf($wantedPath,[StringComparison]::OrdinalIgnoreCase) -ge 0) { return 'ok' }
                    Write-Log "Grupo encontrado en '$($file.FullName)', pero no contiene la ruta exacta $radarYearFile"
                }
            } catch {}
        }
    }
    if ($foundAny) { return 'wrongpath' }
    return 'missing'
}
function Get-RadarSetupText {
@"
Falta crear UNA VEZ en Mp3tag el grupo de acciones "$radarGroupName". Es lo que permite que sea Mp3tag quien escriba Año, Álbum, Género y carátula.

1) En Mp3tag abre Acciones > Acciones (el mismo cuadro que usas con Alt+5).
2) Pulsa Nuevo y ponle de nombre:  $radarGroupName
3) Deja su casilla DESMARCADA (si se marca, se ejecutaría junto a Uololo).
4) Selecciónalo y pulsa Editar (F4). Añade estas 4 acciones con Nuevo:

 a) Tipo "Importar archivo de texto" (Import text file)
    Campo: YEAR
    Archivo: $radarYearFile
 b) Tipo "Importar archivo de texto"
    Campo: ALBUM
    Archivo: $radarYearFile
 c) Tipo "Importar archivo de texto"
    Campo: GENRE
    Archivo: $radarGenreFile
 d) Tipo "Importar carátula desde archivo" (Import cover from file)
    Archivo: $radarCoverFile
    Tipo de imagen: Front Cover (portada frontal)

5) Acepta todos los cuadros.

Pulsa OK para continuar igualmente (por si ya lo tienes creado con otro nombre) o Cancelar para salir.
"@
}

# ---- Ejecutar el grupo "Radar datos" desde el menú Acciones de Mp3tag ----
function Invoke-Mp3tagMenuAction($window,[string]$groupName) {
    $AE=[System.Windows.Automation.AutomationElement]
    $TS=[System.Windows.Automation.TreeScope]
    $CT=[System.Windows.Automation.ControlType]
    $itemCondition=New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty,$CT::MenuItem)
    $pidCondition=New-Object System.Windows.Automation.PropertyCondition($AE::ProcessIdProperty,[int]$window.Process.Id)
    $bothCondition=New-Object System.Windows.Automation.AndCondition($itemCondition,$pidCondition)
    $namePattern='(?i)^&?'+[regex]::Escape($groupName)+'$'

    # Busca el elemento de menú del grupo entre los menús abiertos de Mp3tag.
    $findTarget = {
        $found=$null
        try {
            foreach ($candidate in @($AE::RootElement.FindAll($TS::Descendants,$bothCondition))) {
                if (([string]$candidate.Current.Name) -match $namePattern) { $found=$candidate; break }
            }
        } catch {}
        return $found
    }
    $pressTarget = {
        param($target)
        $invoke=$null
        if ($target.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$invoke)) { $invoke.Invoke(); return $true }
        return $false
    }

    # Intento 1: barra de menús.
    $seenNames=@()
    $barCondition=New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty,$CT::MenuBar)
    $bar=$window.Root.FindFirst($TS::Descendants,$barCondition)
    if ($null -eq $bar) { Write-Log 'MP3TAG: la barra de menús no es accesible por UI Automation.' }
    else {
        foreach ($top in @($bar.FindAll($TS::Children,$itemCondition))) {
            $seenNames += [string]$top.Current.Name
            $expand=$null
            try {
                if ($top.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$expand)) { $expand.Expand() } else { continue }
            } catch { continue }
            Start-Sleep -Milliseconds 450
            $target = & $findTarget
            if ($null -ne $target -and (& $pressTarget $target)) { Write-Log "MP3TAG: grupo '$groupName' ejecutado desde el menú '$($top.Current.Name)'."; return $true }
            try { $expand.Collapse() } catch {}
        }
        Write-Log "MP3TAG: menús vistos: $($seenNames -join ' | ')"
    }

    # Intento 2 (experimental): desplegable de grupos de acción de la barra de herramientas.
    try {
        $btnCondition=New-Object System.Windows.Automation.OrCondition(
            (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty,$CT::Button)),
            (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty,$CT::SplitButton)),
            (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty,$CT::MenuItem)))
        $buttons=@($window.Root.FindAll($TS::Descendants,$btnCondition))
        $desc=@()
        foreach ($bt in $buttons) { if ($desc.Count -lt 40) { $desc += ('{0}:{1}' -f $bt.Current.ControlType.ProgrammaticName,$bt.Current.Name) } }
        Write-Log "MP3TAG: elementos de barra accesibles ($($buttons.Count)): $($desc -join ' | ')"
        foreach ($bt in $buttons) {
            $expand=$null
            if (-not $bt.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$expand)) { continue }
            try { $expand.Expand() } catch { continue }
            Start-Sleep -Milliseconds 450
            $target = & $findTarget
            if ($null -ne $target -and (& $pressTarget $target)) { Write-Log "MP3TAG: grupo '$groupName' ejecutado desde el desplegable de la barra de herramientas ('$($bt.Current.Name)')."; return $true }
            try { $expand.Collapse() } catch {}
        }
    } catch { Write-Log "MP3TAG: la prueba con la barra de herramientas falló: $($_.Exception.Message)" }

    Write-Log "MP3TAG: no se pudo ejecutar el grupo '$groupName' automáticamente."
    $shell=New-Object -ComObject WScript.Shell; $shell.SendKeys('{ESC}')
    return $false
}
function Get-DialogText([IntPtr]$handle) {
    $parts=New-Object System.Collections.Generic.List[string]
    $parts.Add([RadarWindows]::WindowText($handle))
    try { $kids=[RadarWindows]::AllChildText($handle); if ($kids) { $parts.Add($kids) } } catch {}
    try {
        $root=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Text)
        foreach ($e in @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond))) { $n=[string]$e.Current.Name; if ($n) { $parts.Add($n) } }
    } catch {}
    return ($parts -join ' | ')
}

function Get-ForegroundWindowInfo {
    $handle = [RadarWindowsMp3tag]::GetForegroundWindow()
    $builder = New-Object System.Text.StringBuilder 512
    if ($handle -ne [IntPtr]::Zero) { [RadarWindowsMp3tag]::GetWindowText($handle, $builder, $builder.Capacity) | Out-Null }
    return @{ Handle=$handle; Title=$builder.ToString() }
}
function Get-Mp3tagMainWindow {
    $processes = @(Get-Process -Name 'Mp3tag' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
    foreach ($process in $processes) {
        try {
            $handle = [IntPtr]$process.MainWindowHandle
            $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
            if ($null -ne $root) { return @{ Process=$process; Handle=$handle; Root=$root } }
        } catch { Write-Log "MP3TAG: no se pudo leer la ventana principal: $($_.Exception.Message)" }
    }
    return $null
}
function Wait-ForegroundWindowChange([IntPtr]$previousHandle, [IntPtr]$mainHandle, [int]$timeoutSeconds, [string]$stage) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    do {
        Start-Sleep -Milliseconds 200
        $current = Get-ForegroundWindowInfo
        if ($current.Handle -ne [IntPtr]::Zero -and $current.Handle -ne $previousHandle -and $current.Handle -ne $mainHandle) {
            Write-Log "${stage}: ventana activa detectada. Título='$($current.Title)' handle=$($current.Handle)"
            return $current
        }
    } while ((Get-Date) -lt $deadline)
    $current = Get-ForegroundWindowInfo
    throw "${stage}: no apareció la ventana esperada en $timeoutSeconds segundos. Ventana activa: '$($current.Title)'. No se enviaron confirmaciones a ciegas."
}
function Select-Mp3tagFileRow($window, [string]$song) {
    $fileName = [IO.Path]::GetFileName($song)
    # Mp3tag puede tardar en cargar la canción y su ventana tiene varias listas:
    # se revisan todas, durante hasta 15 s, hasta encontrar la visible con exactamente una fila.
    $list = [IntPtr]::Zero; $count = 0; $maxFilas = 0; $resumen = ''
    for ($intento=0; $intento -lt 30; $intento++) {
        $listas = @([RadarWindowsMp3tag]::FindFileLists([IntPtr]$window.Handle))
        $conteos = @()
        foreach ($l in $listas) {
            $visible = [RadarWindows]::IsWindowVisible($l)
            $c = [int][RadarWindowsMp3tag]::SendMessage($l,0x1004,[IntPtr]::Zero,[IntPtr]::Zero).ToInt64() # LVM_GETITEMCOUNT
            $conteos += ("{0}{1}" -f $c, $(if ($visible) { '' } else { ' (oculta)' }))
            if ($visible -and $c -eq 1 -and $list -eq [IntPtr]::Zero) { $list = $l; $count = 1 }
            if ($visible -and $c -gt $maxFilas) { $maxFilas = $c }
        }
        $resumen = "listas=$($listas.Count); filas=$($conteos -join ', ')"
        if ($list -ne [IntPtr]::Zero) { break }
        Start-Sleep -Milliseconds 500
    }
    Write-Log "MP3TAG: comprobación de la lista de archivos tras $([Math]::Round(($intento+1)*0.5,1)) s: $resumen"
    if ($list -eq [IntPtr]::Zero) {
        if ($maxFilas -gt 1) { throw "Mp3tag muestra $maxFilas filas después de abrir '$fileName'. Se esperaba exactamente una; no se ejecutará Uololo para evitar modificar otra canción." }
        throw "Mp3tag no mostró '$fileName' en su lista tras 15 segundos ($resumen). Comprueba que el cuadro de Filtro de la parte de abajo de Mp3tag está vacío (si tiene texto, oculta las canciones que no coinciden). No se ejecutará Uololo sin una selección verificada."
    }
    $rect = New-Object 'RadarWindowsMp3tag+RECT'
    if (-not [RadarWindowsMp3tag]::GetWindowRect($list,[ref]$rect)) { throw "No se pudo localizar visualmente la lista de Mp3tag para seleccionar '$fileName'." }
    $x = [int](($rect.Left + $rect.Right) / 2)
    $y = [int](($rect.Top + $rect.Bottom) / 2)
    if (-not [RadarWindowsMp3tag]::SetCursorPos($x,$y)) { throw "No se pudo situar el cursor en la lista de Mp3tag." }
    Start-Sleep -Milliseconds 100
    [RadarWindowsMp3tag]::mouse_event(0x0002,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [RadarWindowsMp3tag]::mouse_event(0x0004,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 150
    $ws = New-Object -ComObject WScript.Shell
    if (-not (Set-Mp3tagForeground $window $ws)) { throw "No se pudo activar Mp3tag para seleccionar '$fileName'." }
    $ws.SendKeys('^a')
    Start-Sleep -Milliseconds 200
    $state = [RadarWindowsMp3tag]::SendMessage($list,0x102C,[IntPtr]::Zero,[IntPtr]2).ToInt64() # LVM_GETITEMSTATE row 0, LVIS_SELECTED
    if (($state -band 0x0002) -eq 0) { throw "Mp3tag no confirmó la selección de la única fila correspondiente a '$fileName'. Uololo no se ejecutará." }
    Write-Log "MP3TAG: única fila seleccionada y comprobada mediante Ctrl+A. Archivo='$fileName'; filas=$count."
}

function Set-Mp3tagForeground($window,$ws) {
    # Intenta varias veces poner Mp3tag en primer plano (Windows a veces lo rechaza justo tras abrirlo).
    for ($i=0; $i -lt 20; $i++) {
        try {
            $h=[IntPtr]$window.Handle
            [RadarWindows]::BringWindowToTop($h) | Out-Null
            [RadarWindows]::SetForegroundWindow($h) | Out-Null
            if ([RadarWindowsMp3tag]::GetForegroundWindow() -eq $h) { return $true }
            if ($ws.AppActivate([int]$window.Process.Id)) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}
function Close-Mp3tagBeforeStart {
    $running=@(Get-Process -Name 'Mp3tag' -ErrorAction SilentlyContinue)
    if ($running.Count -eq 0) { return }
    Write-Log "MP3TAG: ya estaba abierto; se cierra para empezar con una única canción en la lista."
    foreach ($p in $running) { try { $p.CloseMainWindow() | Out-Null } catch {} }
    for ($i=0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Name 'Mp3tag' -ErrorAction SilentlyContinue)) { Write-Log "MP3TAG: instancia anterior cerrada."; return }
    }
    throw "Mp3tag ya estaba abierto y no se cerró (quizá pide guardar cambios). Ciérralo manualmente. El archivo de audio se conserva."
}
function Remove-RadarTempFiles {
    foreach ($f in @($radarYearFile,$radarGenreFile,$radarCoverFile,($radarCoverFile+'.tmp'))) { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue }
}

function Remove-NoiseBrackets([string]$text) {
    # Quita lo que va entre paréntesis o corchetes SOLO si es "ruido" de vídeo: (Videoclip oficial), [Official Video], (Lyric Video), (Audio)...
    # Lo demás, como (feat. X) o (Remix), se conserva.
    $clean = $text -replace '(?i)\s*[\(\[][^\)\]]*\b(video|vídeo|videoclip|clip|oficial|official|lyrics?|letras?|audio|visuali[sz]er|hd|4k|subtitulado)\b[^\)\]]*[\)\]]',''
    $clean = ($clean -replace '\s{2,}',' ').Trim()
    return $clean
}
function Rename-SongWithoutNoise([string]$song) {
    try {
        $dir  = [IO.Path]::GetDirectoryName($song)
        $base = [IO.Path]::GetFileNameWithoutExtension($song)
        $ext  = [IO.Path]::GetExtension($song)
        $newBase = Remove-NoiseBrackets $base
        if ([string]::IsNullOrWhiteSpace($newBase) -or $newBase -eq $base) { return $song }
        $newPath = Join-Path $dir ($newBase + $ext)
        if (Test-Path -LiteralPath $newPath) { Write-Log "NOMBRE: ya existe '$newPath'; se deja el nombre original."; return $song }
        Rename-Item -LiteralPath $song -NewName ($newBase + $ext) -ErrorAction Stop
        Write-Log "NOMBRE: '$base' -> '$newBase'"
        return $newPath
    } catch {
        Write-Log "NOMBRE: no se pudo limpiar el nombre ($($_.Exception.Message)); se sigue con el original."
        return $song
    }
}

function Get-RadarDataFiles([string]$song) {
    # Prepara año, género y portada ANTES de abrir Mp3tag, a partir del nombre del archivo "Artista - Título".
    $baseName=[IO.Path]::GetFileNameWithoutExtension($song)
    $idx=$baseName.IndexOf(' - ')
    if ($idx -lt 1) { throw "El nombre del archivo '$baseName' no tiene el formato 'Artista - Título'; no se puede buscar año, género ni portada." }
    $nameArtist=$baseName.Substring(0,$idx).Trim()
    $nameTitle=$baseName.Substring($idx+3).Trim()
    $nameTitle=Remove-NoiseBrackets $nameTitle
    $lookupTitle=Get-LookupTitle $nameTitle $nameArtist
    Write-Log "Datos para buscar: artista='$nameArtist'; título='$lookupTitle' (nombre del archivo: '$baseName')"

    Remove-RadarTempFiles
    $itunes = Get-iTunesTrackInfo $nameArtist $lookupTitle $radarCoverFile
    try { $meta = Get-MusicBrainzMetadata $lookupTitle $nameArtist $itunes.Genre }
    catch {
        $mbError = $_.Exception.Message
        Write-Log "MusicBrainz no pudo dar los datos: $mbError"
        # Plan B con datos reales: año de publicación y género que ofrece iTunes para esta misma canción.
        $fbGenre = Get-GenreCategory ([string]$itunes.Genre)
        if (-not $fbGenre) { $fbGenre = Get-GenreCategory ([string]$itunes.Genre) -Loose }
        if ($itunes.Year -and $fbGenre) {
            Write-Log "PLAN B: se usa el año y el género de iTunes (año=$($itunes.Year); género iTunes='$($itunes.Genre)' -> '$fbGenre')."
            $meta = @{Year=[string]$itunes.Year;Genre=$fbGenre;GenreSource='iTunes (plan B)';Tags='';Score='n/d';RecordingId='n/d'}
        } else { throw "$mbError Además, iTunes no aporta un año y un género utilizables (año='$($itunes.Year)'; género='$($itunes.Genre)')." }
    }
    Write-Log "Datos finales: puntuación=$($meta.Score); ID=$($meta.RecordingId); año=$($meta.Year); género='$($meta.Genre)' (fuente: $($meta.GenreSource)). Etiquetas: $($meta.Tags)"

    # Archivos que lee el grupo de acciones de Mp3tag (UTF-8 con BOM, sin salto de línea final).
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [IO.File]::WriteAllText($radarYearFile,[string]$meta.Year,$utf8Bom)
    [IO.File]::WriteAllText($radarGenreFile,[string]$meta.Genre,$utf8Bom)
    if (-not (Test-Path -LiteralPath $radarCoverFile)) { throw 'La portada temporal no existe; no se puede continuar.' }
    foreach ($tf in @($radarYearFile,$radarGenreFile,$radarCoverFile)) { Write-Log ("ARCHIVO PARA MP3TAG: {0} existe={1}" -f $tf,(Test-Path -LiteralPath $tf)) }
    return $meta
}

function Invoke-Mp3tagActionAndMetadata([string]$song) {
    try {
        # ---------- FASE A: datos externos, antes de abrir Mp3tag ----------
        $meta = Get-RadarDataFiles $song

        # ---------- FASE B: abrir Mp3tag ----------
        Write-Log "ETAPA MP3TAG: abriendo $song"
        Close-Mp3tagBeforeStart
        $mp3tagArgs = '/fn:"' + $song + '"'
        Write-Log "MP3TAG: ejecutando '$mp3tag' $mp3tagArgs"
        $launchProcess = Start-Process -FilePath $mp3tag -ArgumentList $mp3tagArgs -PassThru -ErrorAction Stop
        Write-Log "MP3TAG: solicitud de apertura enviada. PID devuelto=$($launchProcess.Id)."

        $window = $null
        for ($i=0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            $window = Get-Mp3tagMainWindow
            if ($null -ne $window) { break }
        }
        if ($null -eq $window) { throw "Se envió la orden de apertura de Mp3tag, pero no apareció una ventana principal accesible. El archivo de audio se conserva." }
        Start-Sleep -Milliseconds 2500   # dar tiempo a que Mp3tag termine de cargar
        $window = Get-Mp3tagMainWindow
        if ($null -eq $window) { throw "La ventana de Mp3tag desapareció mientras terminaba de abrirse." }
        $ws = New-Object -ComObject WScript.Shell
        if (-not (Set-Mp3tagForeground $window $ws)) { throw "No se pudo activar la ventana principal de Mp3tag. El archivo de audio se conserva." }
        Start-Sleep -Milliseconds 400
        $window = Get-Mp3tagMainWindow
        if ($null -eq $window) { throw "La ventana principal de Mp3tag dejó de estar disponible." }

        # ---------- FASE C: Alt+5 = ejecuta los grupos marcados (Uololo y, si está marcado, Radar datos) ----------
        Select-Mp3tagFileRow $window $song
        Start-Sleep -Milliseconds 300
        $before = Get-ForegroundWindowInfo
        $ws.SendKeys('%5')
        Write-Log "MP3TAG: enviado Alt+5; esperando el diálogo de grupos de acción."
        $actionDialog = Wait-ForegroundWindowChange $before.Handle $window.Handle 8 'MP3TAG primer diálogo de Uololo'
        $ws.SendKeys('{ENTER}')
        Write-Log "MP3TAG: aceptado el diálogo de grupos; esperando el aviso posterior."
        $resetDialog = Wait-ForegroundWindowChange $actionDialog.Handle $window.Handle 15 'MP3TAG aviso posterior a Uololo'
        Start-Sleep -Milliseconds 400
        $ws.SendKeys('{ENTER}')
        Write-Log "MP3TAG: aceptado el segundo aviso (reseteado)."
        Start-Sleep -Milliseconds 700
        if (-not (Set-Mp3tagForeground $window $ws)) { throw "Los grupos terminaron, pero no se pudo volver a activar Mp3tag. El archivo de audio se conserva." }
        Start-Sleep -Milliseconds 300
        $ws.SendKeys('^s')
        Write-Log "MP3TAG: enviado Ctrl+S tras los grupos de acción."

        # ---------- FASE D: verificación real (hasta 12 s) ----------
        $state=$null
        for ($t=0; $t -lt 16; $t++) {
            Start-Sleep -Milliseconds 750
            $state = Get-Mp3tagSavedState $song $meta.Year $meta.Genre
            if ($state.Ok) { break }
        }
        if (-not $state.Ok) {
            Write-Log "MP3TAG: tras los grupos faltan datos ($($state.Problems -join '; ')). Se pide ejecutar '$radarGroupName' a mano."
            Show-Message "Uololo ha terminado, pero faltan datos en el MP3 ($($state.Problems -join '; ')).`n`nPulsa OK y después, en Mp3tag (con la canción seleccionada), abre el desplegable de grupos de acción de la barra de herramientas y haz clic en '$radarGroupName'.`n`nNo hace falta volver aquí: esperaré hasta 3 minutos y comprobaré el archivo yo solo.`n`nPara que sea automático, deja MARCADO '$radarGroupName' en el cuadro Alt+5."
            $lastDialogText=''
            $deadline=(Get-Date).AddSeconds(180)
            while ($true) {
                Start-Sleep -Milliseconds 700
                $state = Get-Mp3tagSavedState $song $meta.Year $meta.Genre
                if ($state.Ok) { break }
                $dlg = [RadarWindows]::FindOtherWindowForProcess([uint32]$window.Process.Id,[IntPtr]$window.Handle)
                if ($dlg -ne [IntPtr]::Zero) {
                    $dlgText = Get-DialogText $dlg
                    if ($dlgText -ne $lastDialogText) { $lastDialogText = $dlgText; Write-Log "MP3TAG: ventana de aviso detectada (clase '$([RadarWindows]::WindowClass($dlg))'): $dlgText" }
                }
                if ((Get-Date) -gt $deadline) { throw "Verificación fallida: $($state.Problems -join '; '). Aviso de Mp3tag: '$lastDialogText'. No se marca como terminado." }
            }
        }
        Write-Log "PROCESO MP3TAG VERIFICADO: Artista=$($state.Artist); Título=$($state.Title); Álbum=$($state.Album); Año=$($state.Year); Género=$($state.Genre); carátula incrustada (APIC)."
        Show-Message "Mp3tag ha guardado y verificado los datos:`n`nArtista: $($state.Artist)`nTítulo: $($state.Title)`nÁlbum: $($state.Album)`nAño: $($state.Year)`nGénero: $($state.Genre)`nCarátula: incrustada."
    } finally { Remove-RadarTempFiles }
}

# Evita que dos copias del auxiliar vigilen la misma carpeta y dupliquen avisos/procesos.
$script:RadarMutex = New-Object System.Threading.Mutex($false, "Local\MiRadarMusical_DescargarRadar_Auxiliar")
if (-not $script:RadarMutex.WaitOne(0, $false)) {
    Show-Message "Descargar Radar ya está en ejecución. No se abrirá una segunda instancia para evitar procesar dos veces la misma canción."
    exit
}

Write-Log "=================================================="
Write-Log "Auxiliar iniciado. Instancia única confirmada."
Write-Log "Carpeta vigilada: $folder"; Write-Log "ID3 Remover: $id3Remover"; Write-Log "MP3Gain CLI: $mp3gainCli"; Write-Log "Mp3tag: $mp3tag"; Write-Log "Objetivo configurado: $objetivoDb dB"
Write-Log "Carpeta del script: $PSScriptRoot"; Write-Log "Registro en uso: $($script:logEnUso)"
Write-Log "Archivos temporales para Mp3tag: $radarYearFile | $radarGenreFile | $radarCoverFile"
$radarStatus = Get-RadarActionGroupStatus
if ($radarStatus -eq 'missing') {
    Write-Log "No se detecta el grupo de acciones '$radarGroupName' en Mp3tag."
    if ((Ask-Message (Get-RadarSetupText)) -ne 'OK') { Write-Log "Salida: falta el grupo de acciones."; exit }
} elseif ($radarStatus -eq 'wrongpath') {
    Write-Log "El grupo '$radarGroupName' existe, pero sus acciones apuntan a otra carpeta distinta de $radarFolder."
    $msg = "ATENCIÓN: el grupo '$radarGroupName' de Mp3tag apunta a otra carpeta distinta de la que usa el script.`n`nEl script escribirá los archivos temporales en:`n$radarFolder`n`nSi Mp3tag busca los archivos en otra carpeta no los encontrará y los datos no se guardarán.`n`nSolución: cambia las rutas de las 4 acciones de Mp3tag a:`n$radarYearFile`n$radarGenreFile`n$radarCoverFile`n`nPulsa Cancelar para salir y corregirlo, u OK para continuar igualmente."
    if ((Ask-Message $msg) -ne 'OK') { Write-Log "Salida: las rutas del grupo no coinciden."; exit }
}
$seen=@{}
Get-ChildItem -LiteralPath $folder -Filter "*.mp3" -File | ForEach-Object { $seen[$_.FullName.ToLowerInvariant()]=$true }
Show-Message "Descargar Radar está activo.`n`nCarpeta vigilada:`n$folder`n`nDescarga una canción nueva con MediaHuman."
Write-Log "Vigilando carpeta. Los MP3 existentes al iniciar se ignoran."
while ($true) {
    try {
        $files=Get-ChildItem -LiteralPath $folder -Filter "*.mp3" -File
        foreach ($file in $files) {
            $key=$file.FullName.ToLowerInvariant(); if ($seen.ContainsKey($key)) { continue }
            $previousSize=-1; $stableCount=0; $tries=0
            Write-Log "Nuevo archivo detectado: $($file.FullName). Esperando a que termine la descarga."
            while ($stableCount -lt 3 -and $tries -lt 180) {
                Start-Sleep -Seconds 2; $tries++; if (-not (Test-Path -LiteralPath $file.FullName)) { break }
                $current=Get-Item -LiteralPath $file.FullName
                if ($current.Length -gt 0 -and $current.Length -eq $previousSize) { $stableCount++ } else { $stableCount=0 }; $previousSize=$current.Length
            }
            if (-not (Test-Path -LiteralPath $file.FullName)) { continue }
            if ($stableCount -lt 3) { Write-Log "DESCARGA NO CONFIRMADA: $($file.Name)"; continue }
            $seen[$key]=$true; $song=$file.FullName; Write-Log "Descarga estable confirmada: $song"
            if ((Ask-Message "Nuevo MP3 detectado:`n`n$song`n`nPulsa OK para procesarlo o Cancelar para omitirlo.") -ne 'OK') { Write-Log "Usuario omitió el archivo: $song"; continue }
            $song = Rename-SongWithoutNoise $song
            $seen[$song.ToLowerInvariant()]=$true
            try { Invoke-ID3Auto $song }
            catch {
                Write-Log "ERROR ID3: $($_.Exception.Message)"; Show-Message "No se pudo completar ID3 Remover automáticamente:`n$($_.Exception.Message)`n`nCompleta este paso manualmente."
                # No abrir otra copia si la instancia que acaba de procesar la canción sigue viva.
                # Esto evita la segunda ventana que aparecía tras fallar la confirmación automática.
                $existingId3 = @(Get-Process -Name "ID3Remover" -ErrorAction SilentlyContinue)
                if ($existingId3.Count -eq 0) {
                    Write-Log "ID3: no queda ninguna instancia abierta; se inicia una única ventana para el paso manual."
                    Start-Process -FilePath $id3Remover | Out-Null
                    Start-Sleep -Milliseconds 800
                } else {
                    Write-Log "ID3: se reutiliza la ventana existente; no se abrirá una segunda instancia. PID(s)=$($existingId3.Id -join ',')"
                }
                if ((Ask-Message "Completa ID3 Remover en la ventana que ya está abierta: arrastra esta canción, pulsa Remove y acepta el aviso final. Después pulsa OK aquí:`n`n$song") -ne 'OK') { Write-Log "Usuario no confirmó el paso manual de ID3 para: $song"; continue }
                Write-Log "Usuario confirmó el paso manual de ID3 para: $song"
            }
            try { Invoke-MP3Gain $song }
            catch { $errorText=$_.Exception.Message; Write-Log "ERROR MP3GAIN: $errorText"; Show-Message "Error al procesar o comprobar MP3Gain:`n$errorText`n`nConsulta el registro:`n$($script:logEnUso)`n`nNo se abrirá Mp3tag automáticamente."; continue }
            try { Invoke-Mp3tagActionAndMetadata $song }
            catch { Write-Log "ERROR METADATOS/MP3TAG: $($_.Exception.Message)"; Show-Message "La canción se procesó con ID3 Remover y MP3Gain, pero no se pudieron completar automáticamente los metadatos:`n`n$($_.Exception.Message)`n`nEl archivo de audio no se ha eliminado. Consulta el registro:`n$($script:logEnUso)" }
        }
    } catch { Write-Log "ERROR GENERAL: $($_.Exception.Message)" }
    Start-Sleep -Seconds 2
}
