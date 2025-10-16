@echo off
setlocal

if not exist .venv\Scripts\python.exe (
    echo Virtual environment missing. Please run setup_pmck_training.bat first.
    echo.
    pause
    exit /b 1
)

set "PYTHON_BIN=.venv\Scripts\python.exe"
echo Launching PMCK Training demo server...
%PYTHON_BIN% run_pmck_training.py

if %errorlevel% neq 0 (
    echo The server exited with an error. Review the output above for details.
) else (
    echo Server stopped. You may close this window or press any key to run it again.
)

echo.
pause
endlocal
