@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run setup_ipc.cmd first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" test_plc_debug_log.py
if errorlevel 1 (
    echo [FAIL] PLC Debug log test failed.
    pause
    exit /b 1
)

echo [PASS] PLC Debug raw D-register log test passed.
pause
