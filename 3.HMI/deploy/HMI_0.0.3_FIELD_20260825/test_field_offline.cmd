@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: HMI environment is missing. Run setup_ipc.cmd first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" test_hmi_field_offline.py
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
    echo FIELD offline startup test PASS.
) else (
    echo FIELD offline startup test FAIL. Error level: %RESULT%
)
pause
exit /b %RESULT%
