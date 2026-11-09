@echo off
setlocal
title Tax Compliance QA Server
cd /d E:\workbuddy-data\finance-tax-compliance\app

set PY=C:\Users\aa152\AppData\Local\Programs\Python\Python312\python.exe
set PORT=8777

netstat -ano | findstr /c:":%PORT%" | findstr /c:"LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo Server already running on port %PORT%.
  goto open
)

echo Starting server on port %PORT% ...
start "TaxQA-Server" /min "%PY%" server.py %PORT%
ping -n 4 127.0.0.1 >nul

:open
start "" http://localhost:%PORT%
echo Done. Close the minimized "TaxQA-Server" window to stop the server.
ping -n 4 127.0.0.1 >nul
