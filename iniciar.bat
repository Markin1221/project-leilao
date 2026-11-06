@echo off
title Arremate - site (deixe aberta)
cd /d "%~dp0"
call preparar.bat || (pause & exit /b 1)

rem fecha um site antigo que ainda esteja rodando na porta 5000, nao mexe no robo
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000 " ^| findstr LISTENING') do (
  echo Fechando site antigo, PID %%p
  taskkill /F /PID %%p >nul 2>&1
)
timeout /t 1 >nul

echo.
echo Abra no PC:      http://localhost:5000
echo No celular use o IP deste PC na mesma Wi-Fi, ex.: http://192.168.0.10:5000
echo Descubra o IP com o comando ipconfig
echo.
start "" http://localhost:5000
.venv\Scripts\python app.py
pause
