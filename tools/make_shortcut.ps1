<#
.SYNOPSIS
    Put an "XMB Player" shortcut on the Desktop.

.DESCRIPTION
    Points at venv\Scripts\pythonw.exe -- the windowed interpreter -- so
    double-clicking opens the player with no console behind it. It runs the live
    source, so edits show up on the next launch with no rebuild (CLAUDE.md,
    decisions log). Re-run this only if the repo moves.

    Use run.bat instead while debugging; pythonw.exe swallows stdout and any
    traceback with it.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
#>

[CmdletBinding()]
param(
    # Where to write the .lnk. Defaults to the Desktop.
    [string] $Destination = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'

$root    = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root 'venv\Scripts\pythonw.exe'
$python  = Join-Path $root 'venv\Scripts\python.exe'

if (-not (Test-Path $pythonw)) {
    Write-Error "No windowed interpreter at $pythonw -- create the venv first: python -m venv venv"
}

# The icon is drawn from theme.py by tools/make_icon.py, the same way the build
# draws the exe's. It goes to LOCALAPPDATA rather than into the repo because
# build_exe.py empties both build/ and dist/, and a shortcut pointing at a file
# that the next build deletes is worse than no icon at all.
#
# Best-effort on purpose: a missing or broken PySide6 should cost you the icon
# and not the shortcut, so this falls back to the interpreter's own.
$iconDir  = Join-Path $env:LOCALAPPDATA 'XMBPlayer'
$iconPath = Join-Path $iconDir 'XMB Player.ico'
$icon     = "$pythonw,0"

try {
    if (-not (Test-Path $iconDir)) {
        New-Item -ItemType Directory -Path $iconDir -Force | Out-Null
    }
    & $python (Join-Path $PSScriptRoot 'make_icon.py') $iconPath | Out-Null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $iconPath)) {
        $icon = "$iconPath,0"
    } else {
        Write-Warning "Could not draw the icon; using the interpreter's."
    }
} catch {
    Write-Warning "Could not draw the icon ($($_.Exception.Message)); using the interpreter's."
}

$linkPath = Join-Path $Destination 'XMB Player.lnk'

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut($linkPath)
$link.TargetPath       = $pythonw
$link.Arguments        = '-m mp3player.app'
$link.WorkingDirectory = $root
$link.Description      = 'XMB Player -- nightcore/daycore MP3 player'
$link.IconLocation     = $icon
$link.Save()

# Release the COM object rather than leaving it to the GC -- this script is
# often run from a shell that stays open.
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)

Write-Host "Created: $linkPath"
Write-Host "  -> $pythonw -m mp3player.app  (cwd $root)"
Write-Host "  icon: $icon"
