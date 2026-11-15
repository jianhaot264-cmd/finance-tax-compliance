@echo off
setlocal enabledelayedexpansion
title Tax Compliance QA Server
cd /d "E:\workbuddy-data\finance-tax-compliance\app"
set "PY=C:\Users\aa152\AppData\Local\Programs\Python\Python312\python.exe"
set "PORT=8777"
set "HEALTH=import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8777/api/health',timeout=2).status==200 else 1)"

echo [..] Checking service health ...
"%PY%" -c "%HEALTH%" >nul 2>&1
if %errorlevel%==0 goto ready

REM TIME_WAIT sockets do not block bind; this is the reliable port check.
"%PY%" -c "import socket;s=socket.socket();s.bind(('127.0.0.1',8777));s.close()" >nul 2>&1
if errorlevel 1 goto portBusy

if not exist "%PY%" goto noPython
echo [..] Starting local service ...
start "TaxQA-Server" /min "%PY%" server.py %PORT%
set /a tries=0
:wait
"%PY%" -c "%HEALTH%" >nul 2>&1
if %errorlevel%==0 goto ready
set /a tries+=1
if !tries! GEQ 20 goto failed
ping -n 2 127.0.0.1 >nul
goto wait

:portBusy
echo [error] Port %PORT% is held by another process.
echo         Check with: netstat -ano ^| findstr ":%PORT%"
pause
goto :eof

:failed
echo [error] Service did not pass /api/health within 20 seconds.
echo         See app/logs/server.log
pause
goto :eof

:noPython
echo [error] Python not found: %PY%
pause
goto :eof

:ready
if not "%TAXQA_NO_BROWSER%"=="1" start "" http://127.0.0.1:%PORT%/
echo [ok] Service ready at http://127.0.0.1:%PORT%/
goto :eof
