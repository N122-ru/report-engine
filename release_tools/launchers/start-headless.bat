@echo off
chcp 65001 >nul
setlocal

set "ROOT_DIR=%~dp0"
echo Конструктор отчётов: MCP-сервер без браузерного интерфейса. 1>&2
echo Для работы нужен MCP-клиент, например ИИ-агент с поддержкой stdio. 1>&2
echo Ожидание клиента — нормальное поведение. Настройка описана в README.md рядом с этим файлом. 1>&2
if not defined REPORT_ENGINE_OUTPUT_DIR set "REPORT_ENGINE_OUTPUT_DIR=%ROOT_DIR%output"
if not exist "%REPORT_ENGINE_OUTPUT_DIR%" mkdir "%REPORT_ENGINE_OUTPUT_DIR%"
if not exist "%REPORT_ENGINE_OUTPUT_DIR%" goto output_error

"%ROOT_DIR%report-engine-headless.exe" --output-dir "%REPORT_ENGINE_OUTPUT_DIR%" %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo Не удалось запустить MCP-сервер или сохранить отчёт. Проверьте сообщения выше, целостность пакета и права на папку вывода. 1>&2
echo Инструкция и устранение неполадок: "%ROOT_DIR%README.md". 1>&2
pause
exit /b %RESULT%

:output_error
echo Не удалось создать папку вывода. Распакуйте пакет в папку с правом записи или задайте REPORT_ENGINE_OUTPUT_DIR. 1>&2
pause
exit /b 1
