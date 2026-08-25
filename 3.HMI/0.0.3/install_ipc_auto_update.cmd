@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Connecting this IPC to the MVP_Ramen Git repository...
call "%~dp0ipc_auto_update.cmd"
if errorlevel 1 (
    echo.
    echo ERROR: Initial GitHub update failed.
    echo Check the GitHub/network access, then run this file again.
    pause
    exit /b 1
)

echo [2/2] Creating the automatic update task...
schtasks /Create /TN "MVP Ramen HMI Auto Update" /TR "\"%SystemRoot%\System32\wscript.exe\" \"%~dp0ipc_auto_update_hidden.vbs\"" /SC MINUTE /MO 1 /F
if errorlevel 1 (
    echo.
    echo ERROR: Unable to create the automatic update task.
    pause
    exit /b 1
)

echo.
echo IPC automatic update is ready.
echo GitHub will be checked every minute while this Windows user is signed in.
echo Restart the HMI application to load downloaded program changes.
pause
