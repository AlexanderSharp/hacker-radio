<#
    HACKER RADIO - crea los accesos directos:
      - Escritorio  : HACKER RADIO
      - Inicio auto : HACKER RADIO (se lanza al iniciar sesion)
    Ambos apuntan a launch.vbs, que arranca todo sin ventana de consola.
#>
[CmdletBinding()]
param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vbs    = Join-Path $Root "launch.vbs"
$Icon   = Join-Path $Root "hackerradio.ico"
$Name   = "HACKER RADIO"

function Get-DesktopPath {
    $p = [Environment]::GetFolderPath("Desktop")
    if (-not $p -or -not (Test-Path $p)) { $p = Join-Path $env:USERPROFILE "Desktop" }
    return $p
}
function Get-StartupPath {
    $p = [Environment]::GetFolderPath("Startup")
    if (-not $p) { $p = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup" }
    return $p
}

# ------------------------------------------------------------------ icon
function New-Icon {
    param([string]$Path)
    Add-Type -AssemblyName System.Drawing
    $s = 256
    $bmp = New-Object System.Drawing.Bitmap $s, $s
    $g   = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode   = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::FromArgb(5, 7, 10))

    $neon  = [System.Drawing.Color]::FromArgb(0, 255, 156)
    $dim   = [System.Drawing.Color]::FromArgb(0, 90, 66)
    $pen   = New-Object System.Drawing.Pen $neon, 7
    $g.DrawRectangle($pen, 18, 18, $s - 36, $s - 36)
    $pen2  = New-Object System.Drawing.Pen $dim, 2
    $g.DrawRectangle($pen2, 32, 32, $s - 64, $s - 64)

    # signal bars
    $brush = New-Object System.Drawing.SolidBrush $neon
    $bars  = @(48, 72, 96, 60)
    for ($i = 0; $i -lt $bars.Count; $i++) {
        $h = $bars[$i]
        $g.FillRectangle($brush, 58 + ($i * 22), 190 - $h, 12, $h)
    }

    # letters
    $font  = New-Object System.Drawing.Font("Consolas", 74, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $fmt   = New-Object System.Drawing.StringFormat
    $fmt.Alignment     = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $rect  = New-Object System.Drawing.RectangleF 0, 0, $s, 150
    $g.DrawString("HR", $font, $brush, $rect, $fmt)

    $g.Dispose()
    $hIcon = $bmp.GetHicon()
    $icon  = [System.Drawing.Icon]::FromHandle($hIcon)
    $fs    = [System.IO.File]::Create($Path)
    $icon.Save($fs)
    $fs.Close()
    $icon.Dispose()
    $bmp.Dispose()
}

if (-not (Test-Path $Icon)) {
    try { New-Icon -Path $Icon; Write-Host "icon created: $Icon" -ForegroundColor Green }
    catch { Write-Host "icon skipped: $($_.Exception.Message)" -ForegroundColor Yellow }
}

# ------------------------------------------------------------------ shortcuts
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    @{ Dir = (Get-DesktopPath); Label = "Escritorio" },
    @{ Dir = (Get-StartupPath); Label = "Inicio de sesion" }
)

foreach ($t in $targets) {
    $lnkPath = Join-Path $t.Dir "$Name.lnk"
    if ($Remove) {
        if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force; Write-Host "removed: $lnkPath" -ForegroundColor Yellow }
        continue
    }
    $sc = $shell.CreateShortcut($lnkPath)
    $sc.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
    $sc.Arguments        = "`"$Vbs`""
    $sc.WorkingDirectory = $Root
    $sc.Description      = "HACKER RADIO - consola de radio"
    $sc.WindowStyle      = 1
    if (Test-Path $Icon) { $sc.IconLocation = "$Icon,0" }
    $sc.Save()
    Write-Host "[$($t.Label)] $lnkPath" -ForegroundColor Green
}

""
if (-not $Remove) {
    Write-Host "Listo. Doble clic en 'HACKER RADIO' del escritorio para arrancar." -ForegroundColor Green
    Write-Host "Se abrira solo al iniciar sesion. Para quitarlo: .\create-shortcuts.ps1 -Remove" -ForegroundColor DarkGray
}
