@echo off
setlocal

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ and re-run this file.
    echo.
    pause
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

set "PYTHON_BIN=.venv\Scripts\python.exe"
if not exist %PYTHON_BIN% (
    echo Could not find %PYTHON_BIN%. Ensure Python 3.10+ is installed.
    echo.
    pause
    exit /b 1
)

echo Upgrading pip...
%PYTHON_BIN% -m pip install --upgrade pip

if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    echo.
    pause
    exit /b 1
)

echo Installing PMCK Training dependencies...
%PYTHON_BIN% -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Failed to install dependencies. Review the messages above for details.
    echo.
    pause
    exit /b 1
)

echo Setup complete. Run run_pmck_training.bat to start the server.
echo.
pause
endlocal
