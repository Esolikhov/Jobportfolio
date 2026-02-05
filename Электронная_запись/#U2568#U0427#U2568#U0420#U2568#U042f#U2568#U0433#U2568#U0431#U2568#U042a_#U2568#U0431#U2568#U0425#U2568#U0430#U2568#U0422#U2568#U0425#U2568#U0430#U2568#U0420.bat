@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ════════════════════════════════════════════════════════════
echo   ЗАПУСК API СЕРВЕРА
echo ════════════════════════════════════════════════════════════
echo.

pip install -q fastapi uvicorn pydantic

echo.
echo Сервер запускается...
echo Сайт будет доступен по адресу: http://localhost:8000/website/index.html
echo.

python server.py

pause
