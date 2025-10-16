@echo off
setlocal

if not exist .venv\Scripts\python.exe (
    echo Virtual environment missing. Please run setup_pmck_training.bat first.
    exit /b 1
)

echo Launching PMCK Training demo server...
set "PYTHON_BIN=.venv\Scripts\python.exe"
%PYTHON_BIN% run_pmck_training.py
endlocal
