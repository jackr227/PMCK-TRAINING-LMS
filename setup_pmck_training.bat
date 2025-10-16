@echo off
setlocal

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ and re-run this file.
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

set "PYTHON_BIN=.venv\Scripts\python.exe"
if not exist %PYTHON_BIN% (
    echo Could not find %PYTHON_BIN%. Ensure Python 3.10+ is installed.
    exit /b 1
)

echo Upgrading pip...
%PYTHON_BIN% -m pip install --upgrade pip

echo Installing PMCK Training dependencies...
%PYTHON_BIN% -m pip install -r requirements.txt

echo Setup complete. Run run_pmck_training.bat to start the server.
endlocal
