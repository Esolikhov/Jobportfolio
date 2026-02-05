@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ════════════════════════════════════════════════════════════
echo   ПРОГРАММА УПРАВЛЕНИЯ ОЧЕРЕДЬЮ
echo ════════════════════════════════════════════════════════════
echo.

pip install -q openpyxl pyttsx3

echo.
echo Программа запускается...
echo.

python queue_program.py

pause
