@echo off
setlocal
cd /d "%~dp0"

set "GIT=C:\Program Files\Git\cmd\git.exe"
set "LOG=%~dp0logs\ipc_auto_update.log"
set "REMOTE=https://github.com/yucheng151/MVP_Ramen_HMI_0.0.3.git"

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo [%date% %time%] Checking GitHub for HMI updates...>>"%LOG%"

if exist "%~dp0ipc_auto_update_hidden.vbs" if not exist "%~dp0logs\.hidden_task_installed" (
    schtasks /Create /TN "MVP Ramen HMI Auto Update" /TR "\"%SystemRoot%\System32\wscript.exe\" \"%~dp0ipc_auto_update_hidden.vbs\"" /SC MINUTE /MO 1 /F >>"%LOG%" 2>&1
    if not errorlevel 1 (
        echo installed>"%~dp0logs\.hidden_task_installed"
        echo [%date% %time%] Automatic update task changed to hidden mode.>>"%LOG%"
    )
)

if not exist "%GIT%" (
    echo [%date% %time%] ERROR: Git is not installed.>>"%LOG%"
    exit /b 1
)

for /f "delims=" %%R in ('"%GIT%" rev-parse --show-toplevel 2^>nul') do set "REPO_ROOT=%%R"
if not defined REPO_ROOT (
    echo [%date% %time%] ERROR: This HMI was not installed with git clone.>>"%LOG%"
    exit /b 1
)

"%GIT%" config --global --add safe.directory "%REPO_ROOT%" >>"%LOG%" 2>&1
"%GIT%" -C "%REPO_ROOT%" remote set-url origin "%REMOTE%" >>"%LOG%" 2>&1
if errorlevel 1 (
    "%GIT%" -C "%REPO_ROOT%" remote add origin "%REMOTE%" >>"%LOG%" 2>&1
)

"%GIT%" -C "%REPO_ROOT%" fetch origin main >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Unable to fetch from GitHub.>>"%LOG%"
    exit /b 1
)

"%GIT%" -C "%REPO_ROOT%" merge --ff-only origin/main >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Update stopped because the IPC copy has local changes.>>"%LOG%"
    exit /b 1
)

echo [%date% %time%] HMI is up to date.>>"%LOG%"
exit /b 0
