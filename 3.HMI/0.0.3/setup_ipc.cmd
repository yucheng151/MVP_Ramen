@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Checking Python...
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python 3 is not installed or is not in PATH.
        echo Install Python 3, enable "Add python.exe to PATH", then run this file again.
        pause
        exit /b 1
    )
    set "PY=python"
)

echo [2/3] Creating virtual environment...
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 goto :failed
)

echo [3/3] Installing HMI dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -c "import tkinter, PIL, pymodbus; print('Runtime imports OK')"
if errorlevel 1 goto :failed

echo.
echo IPC HMI environment is ready.
echo Run start_hmi_mock.cmd first, then use start_hmi.cmd for the real PLC.
pause
exit /b 0

:failed
echo.
echo ERROR: IPC HMI setup failed. Review the message above.
pause
exit /b 1
