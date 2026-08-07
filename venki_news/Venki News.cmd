@echo off
rem ---------------------------------------------------------------------------
rem  Venki News - desktop launcher
rem
rem  Double-clicked from the Desktop shortcut. Opens the browser once the desk
rem  answers, and holds the desk in this window. Close the window to stop it.
rem
rem  Three things this does that a bare `python -m venki_news` does not:
rem
rem    * cd /d to the repo, so the app is found no matter what "Start in" the
rem      shortcut inherited.
rem    * read the port from the app's own config, so this file cannot disagree
rem      with VENKI_PORT in .env.
rem    * wait for /healthz before opening the browser. The first wire tick polls
rem      nineteen feeds and takes a few seconds; opening the browser immediately
rem      shows a connection error and trains you to hit refresh.
rem
rem  The server runs in the FOREGROUND of this window on purpose. An earlier
rem  version backgrounded it and parked the window on a `timeout /t` loop --
rem  but `timeout` refuses to run when stdin is not a real console and returns
rem  instantly, which turned the wait into a busy loop pegging a CPU core.
rem  Holding the server in the foreground needs no sleep at all, and makes
rem  Ctrl+C and closing the window both do the obvious thing.
rem ---------------------------------------------------------------------------

setlocal
title Venki News - live world desk

rem Repo root is the parent of the folder holding this script.
cd /d "%~dp0.."

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo   Cannot find the virtualenv at:
  echo     %PY%
  echo.
  echo   Create it, then install the app:
  echo     uv venv
  echo     uv pip install -e ".[venki]"
  echo.
  pause
  exit /b 1
)

rem Port via a temp file, not `for /f ... in (`cmd`)`: that form re-parses the
rem command and mangles the nested quotes around both the interpreter path and
rem the -c argument. It failed silently and fell through to the default, so it
rem tested clean on a machine using the default port and would have opened the
rem browser at the wrong address for anyone who set VENKI_PORT.
set "PORTFILE=%TEMP%\venki-news-port.txt"
"%PY%" -c "from venki_news import config; print(config.load().port)" > "%PORTFILE%" 2>nul
if exist "%PORTFILE%" set /p PORT=<"%PORTFILE%"
del "%PORTFILE%" >nul 2>&1
rem An empty or non-numeric read leaves PORT unset and we fall back.
for /f "delims=0123456789" %%c in ("%PORT%") do set "PORT="
if not defined PORT set "PORT=8300"

echo.
echo   VENKI NEWS
echo   Live world desk on http://localhost:%PORT%
echo   Close this window to stop it.
echo.

rem Detached: polls /healthz, then opens the browser.
start "" /b "%PY%" "%~dp0_open_when_ready.py" %PORT%

rem Foreground. This is what keeps the window meaningful.
"%PY%" -m venki_news
set "RC=%ERRORLEVEL%"

rem A clean Ctrl+C exits non-zero too, so only hold the window open when the
rem desk fell over with something worth reading.
if not "%RC%"=="0" (
  echo.
  echo   The desk stopped ^(exit code %RC%^).
  echo   If that was not you closing it, the error is above.
  echo.
  pause
)
exit /b %RC%
