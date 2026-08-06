@echo off
rem XMB Player -- console launcher. NOT the one to launch the app with.
rem
rem Runs the live source; there is no build step (CLAUDE.md, decisions log).
rem Keep this one for *debugging*: tracebacks and prints land in this window.
rem
rem To launch the app normally, double-click "XMB Player.lnk" -- in this folder
rem and on the Desktop, both pointing at pythonw.exe, so neither opens a console.
rem Generate them with:
rem     powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 -Here
rem
rem A .bat cannot be made console-free: cmd.exe is a console program, so Windows
rem creates the window before the first line of this file runs. That is why the
rem quiet launcher is a shortcut rather than a flag in here.

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
