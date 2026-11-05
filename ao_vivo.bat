@echo off
cd /d "%~dp0"
call preparar.bat || exit /b 1
.venv\Scripts\python copart.py ao-vivo >> robo.log 2>&1
