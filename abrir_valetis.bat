@echo off
cd /d "%~dp0"
echo =====================================
echo    Iniciando Valetis Control...
echo =====================================
call .venv\Scripts\activate
python web_server.py
pause
