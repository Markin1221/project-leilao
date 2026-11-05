@echo off
cd /d "%~dp0"
call preparar.bat || exit /b 1
.venv\Scripts\python copart.py atualizar >> robo.log 2>&1
