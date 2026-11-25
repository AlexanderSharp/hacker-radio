<#
    HACKER RADIO - single-window launcher.

    Starts the console server, starts VLC fully headless (no VLC window), and
    opens/focuses the console as its own window. One window per run.
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Restart,
    [string]$Station = "defcon"
)

$ErrorActionPreference = "Stop"
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port   = 8799
$Chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$Edge   = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$PidFile = Join-Path $Root "vlc.pid"

$Vlc = $null
foreach ($c in @($env:HACKER_RADIO_VLC, $env:VLC_PATH,
                 "C:\Program Files\VideoLAN\VLC\vlc.exe",
                 "C:\Program Files (x86)\VideoLAN\VLC\vlc.exe")) {
    if ($c -and (Test-Path $c)) { $Vlc = $c; break }
}
if (-not $Vlc) {
    $cmd = Get-Command vlc -ErrorAction SilentlyContinue
    if ($cmd) { $Vlc = $cmd.Source }
}

if ($Restart) {
    & (Join-Path $Root "stop.ps1") | Out-Null
    Start-Sleep -Milliseconds 800
}

function Test-LocalPort([int]$Port) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if ($task.Wait(700)) { $client.Close(); return $true }
        $client.Close(); return $false
    } catch { return $false }
}

function Test-VlcApi {
    try {
        $b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(":hacker"))
        $r = Invoke-WebRequest "http://127.0.0.1:8099/requests/status.xml" `
            -Headers @{ Authorization = "Basic $b64" } -TimeoutSec 3 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Get-Python {
    foreach ($c in @("C:\Program Files\Python312\python.exe", "python")) {
        try {
            $p = if (Test-Path $c) { $c } else { (Get-Command $c -ErrorAction Stop).Source }
            if ($p) { return $p }
        } catch { }
    }
    throw "Python not found."
}

# ---------------------------------------------------------------- 1. server
Write-Host "[1/4] console server..." -ForegroundColor Cyan
if ($Restart -or -not (Test-LocalPort $Port)) {
    if ($Restart) {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 600
    }
    if (-not (Test-LocalPort $Port)) {
        $python = Get-Python
        Start-Process -FilePath $python `
            -ArgumentList @("`"$Root\server.py`"") `
            -WorkingDirectory $Root -WindowStyle Hidden `
            -RedirectStandardOutput "$Root\server.log" `
            -RedirectStandardError  "$Root\server.err.log" | Out-Null
        $ok = $false
        foreach ($i in 1..40) {
            Start-Sleep -Milliseconds 350
            if (Test-LocalPort $Port) { $ok = $true; break }
        }
        if (-not $ok) { throw "The console server did not start. See $Root\server.err.log" }
    }
    Write-Host "      listening on 127.0.0.1:$Port" -ForegroundColor Green
} else {
    Write-Host "      already running on 127.0.0.1:$Port" -ForegroundColor Green
}

# ---------------------------------------------------------------- 2. VLC
Write-Host "[2/4] audio engine (headless)..." -ForegroundColor Cyan
if (Test-VlcApi) {
    Write-Host "      VLC already running, no window" -ForegroundColor Green
} else {
    if (-not (Test-Path $Vlc)) { throw "VLC not found at $Vlc" }
    $proc = Start-Process -FilePath $Vlc -PassThru -ArgumentList @(
        "--intf", "dummy",
        "--extraintf=http", "--http-host=127.0.0.1", "--http-port=8099",
        "--http-password=hacker", "--no-video", "--no-osd",
        "--no-media-library", "--no-playlist-autostart", "--quiet"
    )
    $proc.Id | Set-Content -Path $PidFile -Encoding ASCII -ErrorAction SilentlyContinue
    $up = $false
    foreach ($i in 1..40) { Start-Sleep -Milliseconds 350; if (Test-VlcApi) { $up = $true; break } }
    if (-not $up) { throw "VLC control interface did not come up on 8099." }
    Write-Host "      VLC started with no window (pid $($proc.Id))" -ForegroundColor Green
}

# ---------------------------------------------------------------- 3. tune
Write-Host "[3/4] tuning..." -ForegroundColor Cyan
try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 8
    if ($status.state -ne "playing") {
        # VLC may be freshly started even though a station is remembered.
        $slug = if ($status.station.slug) { $status.station.slug } else { $Station }
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/play?slug=$slug" -TimeoutSec 30 | Out-Null
        $after = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 8
        if ($after.state -eq "playing") {
            Write-Host "      now playing: $($after.station.name)" -ForegroundColor Green
        } else {
            Write-Host "      warning: engine reports '$($after.state)'" -ForegroundColor Yellow
        }
    } else {
        Write-Host "      resuming: $($status.station.name)" -ForegroundColor Green
    }
} catch {
    Write-Host "      (could not tune automatically: $($_.Exception.Message))" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4. window
Write-Host "[4/4] console window..." -ForegroundColor Cyan
if ($NoBrowser) { return }

$existing = Get-Process chrome, msedge -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -like "HACKER RADIO*" } |
            Select-Object -First 1

if ($existing) {
    try {
        (New-Object -ComObject WScript.Shell).AppActivate("HACKER RADIO") | Out-Null
        Write-Host "      existing window focused (no duplicate)" -ForegroundColor Green
    } catch {
        Write-Host "      window already open" -ForegroundColor Green
    }
    return
}

$browser = $null
if (Test-Path $Chrome) { $browser = $Chrome }
elseif (Test-Path $Edge) { $browser = $Edge }

if ($browser) {
    Start-Process -FilePath $browser -ArgumentList @(
        "--app=http://127.0.0.1:$Port",
        "--window-size=1400,900",
        "--window-position=80,40"
    ) | Out-Null
    Write-Host "      opened" -ForegroundColor Green
} else {
    Start-Process "http://127.0.0.1:$Port" | Out-Null
    Write-Host "      opened in default browser" -ForegroundColor Green
}

Write-Host ""
Write-Host "  HACKER RADIO is live  ->  http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host ""
