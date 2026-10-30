@echo off
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m doppleganger %*
if errorlevel 1 pause
