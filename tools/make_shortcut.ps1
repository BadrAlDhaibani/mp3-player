<#
.SYNOPSIS
    Put an "XMB Player" shortcut on the Desktop, and optionally in the repo.

.DESCRIPTION
    Points at venv\Scripts\pythonw.exe -- the windowed interpreter -- so
    double-clicking opens the player with no console behind it. It runs the live
    source, so edits show up on the next launch with no rebuild (CLAUDE.md,
    decisions log). Re-run this only if the repo moves.

    -Here also drops a .lnk next to run.bat. That is the console-free way to
    launch from the repo folder: a .bat *always* gets a console window, because
    cmd.exe is a console program and Windows creates one before the first line
    runs -- so there is nothing run.bat could be changed to that would suppress
    it. A shortcut is the fix, not a flag.

    Use run.bat while debugging; pythonw.exe swallows stdout and any traceback
    with it. Since Batch 13 the app also writes
    %APPDATA%\XMBPlayer\xmbplayer.log, which is where a crash goes either way.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 -Here
#>

[CmdletBinding()]
param(
    # Where to write the .lnk. Defaults to the Desktop.
    [string] $Destination = [Environment]::GetFolderPath('Desktop'),

    # Also write one into the repo root, beside run.bat. Gitignored: it holds
    # absolute paths to this machine's venv.
    [switch] $Here
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

$targets = @($Destination)
if ($Here) { $targets += $root }

$shell = New-Object -ComObject WScript.Shell
foreach ($folder in $targets) {
    $linkPath = Join-Path $folder 'XMB Player.lnk'
    $link = $shell.CreateShortcut($linkPath)
    $link.TargetPath       = $pythonw
    $link.Arguments        = '-m mp3player.app'
    $link.WorkingDirectory = $root
    $link.Description      = 'XMB Player -- nightcore/daycore MP3 player'
    $link.IconLocation     = $icon
    $link.Save()
    Write-Host "Created: $linkPath"
}

# Release the COM object rather than leaving it to the GC -- this script is
# often run from a shell that stays open.
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)

Write-Host "  -> $pythonw -m mp3player.app  (cwd $root)"
Write-Host "  icon: $icon"
