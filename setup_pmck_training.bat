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

echo Detecting Python version...
for /f "usebackq tokens=1,2*" %%a in (`"%PYTHON_BIN%" -c "import sys; print(sys.version.split()[0])"`) do (
    set "PY_VERSION=%%a"
)
echo Using Python %PY_VERSION% located at %PYTHON_BIN%

echo Upgrading pip, setuptools, and wheel...
%PYTHON_BIN% -m pip install --upgrade pip setuptools wheel

if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    echo.
    pause
    exit /b 1
)

echo Installing PMCK Training dependencies (preferring prebuilt wheels)...
%PYTHON_BIN% -m pip install --upgrade --prefer-binary -r requirements.txt

if %errorlevel% neq 0 (
    echo Failed to install dependencies. Review the messages above for details.
    echo If you are running Python 3.13, ensure you are using the latest release so wheel packages are available.
    echo You can also install the Rust toolchain from https://rustup.rs/ if a package falls back to source builds.
    echo.
    pause
    exit /b 1
)

echo Setup complete. Run run_pmck_training.bat to start the server.
echo.
pause
endlocal
