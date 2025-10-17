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

echo Upgrading pip, setuptools, and wheel...
%PYTHON_BIN% -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    echo.
    pause
    exit /b 1
)

echo Installing PMCK Training dependencies...
%PYTHON_BIN% -m pip install --upgrade --prefer-binary -r requirements.txt
if %errorlevel% neq 0 (
    echo Dependency installation failed. See the messages above for details.
    echo.
    pause
    exit /b 1
)

echo Seeding demo data...
%PYTHON_BIN% run_pmck_training.py --seed-only
if %errorlevel% neq 0 (
    echo Seeding failed. Resolve the issue and run this setup again.
    echo.
    pause
    exit /b 1
)

echo Verifying /health endpoint...
%PYTHON_BIN% run_pmck_training.py --health-check
if %errorlevel% neq 0 (
    echo Health check failed. Confirm dependencies are installed correctly.
    echo.
    pause
    exit /b 1
)

echo Setup complete. Double-click run_pmck_training.bat to launch the server.
echo.
pause
endlocal
