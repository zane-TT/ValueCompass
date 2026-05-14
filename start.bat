@echo off
setlocal

cd /d "%~dp0"

echo Building frontend static files...
cd frontend
call npm.cmd run build
if errorlevel 1 (
  echo Frontend build failed.
  exit /b 1
)

cd ..

if exist ".venv312\Scripts\python.exe" (
  set "PYTHON_EXE=.venv312\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
  set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo Starting backend and frontend at http://127.0.0.1:5001 ...
%PYTHON_EXE% backend\app.py
