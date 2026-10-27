@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Primeira vez: criando ambiente...
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
echo.
echo Abra no PC:      http://localhost:5000
echo No celular use o IP deste PC na mesma Wi-Fi, ex.: http://192.168.0.10:5000
echo (descubra o IP com o comando: ipconfig)
echo.
start "" http://localhost:5000
.venv\Scripts\python app.py
