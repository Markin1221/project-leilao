@echo off
title Leilao AO VIVO - nao feche esta janela
cd /d "%~dp0"
call preparar.bat || (pause & exit /b 1)
.venv\Scripts\python copart.py ao-vivo
echo.
echo Terminou. O registro completo esta em robo.log
if "%1"=="" pause
