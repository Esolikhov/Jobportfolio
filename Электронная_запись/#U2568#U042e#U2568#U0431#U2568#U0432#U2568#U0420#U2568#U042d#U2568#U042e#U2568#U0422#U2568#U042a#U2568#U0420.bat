@echo off
chcp 65001 >nul

echo ════════════════════════════════════════════════════════════
echo   ОСТАНОВКА СИСТЕМЫ
echo ════════════════════════════════════════════════════════════
echo.

taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM pythonw.exe /T 2>nul

echo ✓ Все процессы остановлены
echo.
timeout /t 2 /nobreak >nul
