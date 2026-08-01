@echo off
rem XMB Player -- console launcher.
rem
rem Runs the live source; there is no build step (CLAUDE.md, decisions log).
rem Keep this one for debugging: tracebacks and prints land in this window.
rem For the real-app feel use the desktop shortcut -- tools\make_shortcut.ps1.

setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Could not find venv\Scripts\python.exe
    echo Create it first:  python -m venv venv
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -m mp3player.app %*
set EXIT=%ERRORLEVEL%

rem Crashed? Hold the window open so the traceback above is readable.
if not "%EXIT%"=="0" pause
endlocal & exit /b %EXIT%
