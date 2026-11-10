@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Tax Compliance QA Server v2
cd /d E:\workbuddy-data\finance-tax-compliance\app

set "PY=C:\Users\aa152\AppData\Local\Programs\Python\Python312\python.exe"
set "PORT=8777"
set "LOG=E:\workbuddy-data\finance-tax-compliance\app\logs\server.log"

echo [..] 检查服务健康状态 ...
"%PY%" -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%PORT%/api/health',timeout=2).status==200 else 1)" >nul 2>&1
if %errorlevel%==0 goto ready

netstat -ano | findstr /c:":%PORT%" | findstr /c:"LISTENING" >nul 2>&1
if %errorlevel%==0 goto waitExisting

if not exist "%PY%" goto noPython
echo [..] 端口空闲，正在启动服务 ...
start "TaxQA-Server" /min "%PY%" server.py %PORT%
set /a tries=0
goto waitNew

:waitExisting
echo [warn] 端口 %PORT% 已被占用但健康检查未通过，等待 10 秒 ...
set /a tries=0
:waitExistingLoop
"%PY%" -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%PORT%/api/health',timeout=2).status==200 else 1)" >nul 2>&1
if %errorlevel%==0 goto ready
set /a tries+=1
if !tries! GEQ 10 goto portBusy
ping -n 2 127.0.0.1 >nul
goto waitExistingLoop

:waitNew
"%PY%" -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%PORT%/api/health',timeout=2).status==200 else 1)" >nul 2>&1
if %errorlevel%==0 goto ready
set /a tries+=1
if !tries! GEQ 20 goto failed
ping -n 2 127.0.0.1 >nul
goto waitNew

:portBusy
echo [error] 端口 %PORT% 被非本服务进程占用，健康检查 10 秒内始终未通过。
echo         查看占用进程： netstat -ano ^| findstr ":%PORT%"
echo         本次不启动、不打开浏览器。
pause
goto :eof

:failed
echo [error] 服务启动后 20 秒内未通过 /api/health，可能启动失败。
echo         日志路径： %LOG%
"%PY%" -c "import os;p=r'%LOG%';print(open(p,encoding='utf-8',errors='replace').read()[-1000:] if os.path.exists(p) else '(暂无日志)')"
pause
goto :eof

:noPython
echo [error] 找不到 Python 解释器：%PY%
pause
goto :eof

:ready
echo [ok] 服务健康检查通过（端口 %PORT%）。
if not "%TAXQA_NO_BROWSER%"=="1" start "" http://localhost:%PORT%
echo [ok] 已打开浏览器。服务日志：%LOG%
echo      关闭最小化的 "TaxQA-Server" 窗口即可停止服务。
ping -n 3 127.0.0.1 >nul
goto :eof
