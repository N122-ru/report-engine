@echo off
chcp 65001 >nul
setlocal

set "ROOT_DIR=%~dp0"
if "%~1"=="--wait-for-browser" goto browser
set "PORT=8000"
set "OPEN_BROWSER=1"

:parse
if "%~1"=="" goto launch
if "%~1"=="--help" set "OPEN_BROWSER=0"
if "%~1"=="-h" set "OPEN_BROWSER=0"
if "%~1"=="--port" goto port_argument
set "ARG=%~1"
if "%ARG:~0,7%"=="--port=" set "PORT=%ARG:~7%"
shift
goto parse

:port_argument
set "PORT=%~2"
shift
shift
goto parse

:launch
echo Веб-интерфейс: http://127.0.0.1:%PORT%
echo Оставьте это окно открытым во время работы. Для остановки нажмите Ctrl+C.
set "REPORT_ENGINE_BROWSER_PORT=%PORT%"
rem An occupied port must not open an unrelated server in the browser.
if "%OPEN_BROWSER%"=="0" goto run
powershell -NoProfile -Command "$port=0; if(-not [int]::TryParse($env:REPORT_ENGINE_BROWSER_PORT,[ref]$port) -or $port -lt 1 -or $port -gt 65535){exit 1}; $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port); try{$listener.Start(); $listener.Stop(); exit 0}catch{exit 1}"
if not errorlevel 1 start "" /b "%ComSpec%" /d /c ""%~f0" --wait-for-browser "%PORT%""

:run
"%ROOT_DIR%report-engine-web.exe" %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo Не удалось запустить веб-интерфейс. Проверьте сообщения выше: порт может быть занят или пакет распакован не полностью. 1>&2
echo Попробуйте другой порт: start-web.bat --port 8001. Инструкция: "%ROOT_DIR%README.md". 1>&2
pause
exit /b %RESULT%

:browser
set "REPORT_ENGINE_BROWSER_PORT=%~2"
powershell -NoProfile -Command "$url='http://127.0.0.1:'+$env:REPORT_ENGINE_BROWSER_PORT; for($i=0;$i -lt 120;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -Uri ($url+'/api/health') -TimeoutSec 1; if($r.StatusCode -eq 200){exit 0}}catch{}; Start-Sleep -Milliseconds 250}; exit 1"
if errorlevel 1 exit /b 1
start "" "http://127.0.0.1:%REPORT_ENGINE_BROWSER_PORT%"
exit /b 0
