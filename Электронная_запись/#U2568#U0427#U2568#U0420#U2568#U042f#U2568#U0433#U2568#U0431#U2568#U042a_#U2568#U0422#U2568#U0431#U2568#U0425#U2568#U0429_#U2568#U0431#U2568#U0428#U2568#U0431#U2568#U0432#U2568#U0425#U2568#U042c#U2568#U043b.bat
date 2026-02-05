@echo off
chcp 65001 >nul
title Запуск системы электронной очереди

cd /d "%~dp0"

color 0A
echo.
echo ════════════════════════════════════════════════════════════
echo     СИСТЕМА ЭЛЕКТРОННОЙ ОЧЕРЕДИ
echo     Стоматологическая клиника
echo ════════════════════════════════════════════════════════════
echo.

echo [1/4] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ❌ Python не найден!
    echo Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo ✓ Python установлен
echo.

echo [2/4] Установка зависимостей...
pip install -q fastapi uvicorn pydantic openpyxl pyttsx3
echo ✓ Зависимости установлены
echo.

echo [3/4] Запуск API сервера...
start "API Сервер" /min cmd /k "cd /d "%~dp0" && python server.py"
echo ✓ Сервер запущен
echo.

timeout /t 3 /nobreak >nul

echo [4/4] Запуск программы управления очередью...
echo.
echo ════════════════════════════════════════════════════════════
echo   СИСТЕМА ЗАПУЩЕНА!
echo ════════════════════════════════════════════════════════════
echo.
echo   Сервер: http://localhost:8000
echo   Сайт: http://localhost:8000/website/index.html
echo.
echo   Программа очереди запускается...
echo ════════════════════════════════════════════════════════════
echo.

python queue_program.py

echo.
echo Программа очереди закрыта.
pause
