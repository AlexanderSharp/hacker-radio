<#
    HACKER RADIO - stop everything (console server + headless VLC).
#>
[CmdletBinding()]
param(
    [switch]$KeepVlc
)

$Root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port    = 8799
$PidFile = Join-Path $Root "vlc.pid"

# ---- console server -------------------------------------------------------
try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "stopping console server (pid $($proc.Id))..." -ForegroundColor Cyan
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    Write-Host "console server not running." -ForegroundColor DarkGray
}

# ---- VLC ------------------------------------------------------------------
if (-not $KeepVlc) {
    $killed = $false
    if (Test-Path $PidFile) {
        $vpid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($vpid -match '^\d+$') {
            $vp = Get-Process -Id ([int]$vpid) -ErrorAction SilentlyContinue
            if ($vp -and $vp.ProcessName -eq "vlc") {
                Write-Host "stopping VLC (pid $vpid)..." -ForegroundColor Cyan
                Stop-Process -Id $vp.Id -Force -ErrorAction SilentlyContinue
                $killed = $true
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    if (-not $killed) {
        # Only touch windowless VLC instances: never kill a player the user opened.
        $headless = Get-Process vlc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -eq 0 }
        if ($headless) {
            Write-Host "stopping windowless VLC ($($headless.Count))..." -ForegroundColor Cyan
            $headless | Stop-Process -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "HACKER RADIO stopped." -ForegroundColor Green
