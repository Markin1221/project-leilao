@echo off
title Leilao - atualizando lotes
cd /d "%~dp0"
call preparar.bat || (pause & exit /b 1)
.venv\Scripts\python copart.py atualizar
echo.
echo Terminou. O registro completo esta em robo.log
if "%1"=="" pause
