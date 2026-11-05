@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Primeira vez: criando ambiente...
  python -m venv .venv || (echo Instale o Python 3.10+ em python.org & exit /b 1)
)
.venv\Scripts\pip install -q -r requirements.txt
if not exist .venv\playwright_ok (
  .venv\Scripts\python -m playwright install chromium && echo ok> .venv\playwright_ok
)
