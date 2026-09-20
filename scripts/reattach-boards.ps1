#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Reattach both bootlab-esp ESP32-S3 boards to WSL2 via usbipd-win.

.DESCRIPTION
    Finds both boards by VID:PID (303a:1001, the Espressif USB-Serial-JTAG
    debug-unit PID), binds them if needed (--force, since USBPcap is
    installed on this machine and is known-incompatible with plain bind),
    then attaches both to the WSL2 distro. Safe to re-run any time --
    every step checks current state first and skips what's already done.

    Must be run as Administrator (the #Requires line above enforces this --
    PowerShell will refuse to run the script otherwise).

.NOTES
    Project: bootlab-esp
    Boards (by MAC, confirmed via chip-id, see host/config/rig.yaml):
      lab-esp-zephyr: ac:a7:04:2c:3b:04
      lab-esp-idf:    e0:72:a1:aa:23:90
    Both share VID:PID 303a:1001 while in normal/bootloader USB-JTAG mode.
    A board showing 303a:4001 instead is stuck in ROM download mode and
    needs a manual BOOT-held reset before this script will find it under
    the expected PID -- see the WARN block this script prints if that
    happens.
#>

$ErrorActionPreference = 'Stop'
$TargetVidPid = '303a:1001'

Write-Host "=== bootlab-esp board reattach ===" -ForegroundColor Cyan
Write-Host "Looking for boards matching VID:PID $TargetVidPid ...`n"

# usbipd list has two sections (Connected / Persisted); we only want the
# Connected table. Parse it as fixed-width text since usbipd has no
# --json output as of this writing.
$listOutput = usbipd list 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "usbipd list failed (exit $LASTEXITCODE). Is usbipd-win installed? Output:`n$listOutput"
    exit 1
}

$lines = $listOutput -split "`r?`n"
$inConnected = $false
$boardBusIds = @()

foreach ($line in $lines) {
    if ($line -match '^Connected:') { $inConnected = $true; continue }
    if ($line -match '^Persisted:') { $inConnected = $false; continue }
    if (-not $inConnected) { continue }
    if ($line -match '^BUSID') { continue }  # header row
    if ($line.Trim() -eq '') { continue }

    # Columns are whitespace-separated, fixed-width-ish. BUSID is always
    # the first token; VID:PID is always the second.
    $tokens = $line -split '\s+', 3
    if ($tokens.Count -lt 2) { continue }
    $busid = $tokens[0]
    $vidpid = $tokens[1]

    if ($vidpid -eq $TargetVidPid) {
        $boardBusIds += $busid
    }
    elseif ($vidpid -eq '303a:4001') {
        Write-Host "WARN: found a board at busid $busid with PID 303a:4001 -- " -ForegroundColor Yellow -NoNewline
        Write-Host "this means it's stuck in ROM DOWNLOAD MODE, not normal run mode." -ForegroundColor Yellow
        Write-Host "       This script will NOT touch it. Manually reset it: hold BOOT, press" -ForegroundColor Yellow
        Write-Host "       and release RESET/EN, wait ~1-2s, release BOOT. Then re-run this script." -ForegroundColor Yellow
    }
}

if ($boardBusIds.Count -eq 0) {
    Write-Error "No boards found at $TargetVidPid. Are both boards physically plugged in? Run 'usbipd list' manually to check."
    exit 1
}

if ($boardBusIds.Count -eq 1) {
    Write-Host "Only found 1 board (expected 2) at $TargetVidPid -- continuing with what's here." -ForegroundColor Yellow
}

Write-Host "Found $($boardBusIds.Count) board(s) at busid(s): $($boardBusIds -join ', ')`n"

foreach ($busid in $boardBusIds) {
    Write-Host "--- busid $busid ---"

    # Check current state for this specific busid
    $stateLine = (usbipd list 2>&1) -split "`r?`n" | Where-Object { $_ -match "^$busid\s" }
    $currentState = if ($stateLine -match '(Attached|Shared( \(forced\))?|Not shared)\s*$') { $matches[1] } else { 'unknown' }
    Write-Host "  current state: $currentState"

    if ($currentState -eq 'Not shared') {
        Write-Host "  binding (forced, due to USBPcap incompatibility)..."
        usbipd bind --busid $busid --force
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  BIND FAILED for $busid -- skipping attach." -ForegroundColor Red
            continue
        }
    }

    Write-Host "  attaching to WSL..."
    usbipd attach --wsl --busid $busid
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ATTACH FAILED for $busid" -ForegroundColor Red
        continue
    }
    Write-Host "  OK" -ForegroundColor Green
}

Write-Host "`n=== Final state ===" -ForegroundColor Cyan
usbipd list

Write-Host "`nNow run check-boards.sh inside WSL2 to verify from the Linux side." -ForegroundColor Cyan
