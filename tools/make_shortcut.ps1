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

if (-not (Test-Path $pythonw)) {
    Write-Error "No windowed interpreter at $pythonw -- create the venv first: python -m venv venv"
}

$linkPath = Join-Path $Destination 'XMB Player.lnk'

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut($linkPath)
$link.TargetPath       = $pythonw
$link.Arguments        = '-m mp3player.app'
$link.WorkingDirectory = $root
$link.Description      = 'XMB Player -- nightcore/daycore MP3 player'
# No icon of our own yet; the interpreter's is better than a blank page.
$link.IconLocation     = "$pythonw,0"
$link.Save()

# Release the COM object rather than leaving it to the GC -- this script is
# often run from a shell that stays open.
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)

Write-Host "Created: $linkPath"
Write-Host "  -> $pythonw -m mp3player.app  (cwd $root)"
