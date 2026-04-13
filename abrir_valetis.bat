@echo off
cd /d "%~dp0"
echo =====================================
echo    Iniciando Valetis Control...
echo =====================================
taskkill /F /IM python.exe >nul 2>&1
call .venv\Scripts\activate.bat
start "" "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" http://localhost:8080/
python web_server.py
pause
