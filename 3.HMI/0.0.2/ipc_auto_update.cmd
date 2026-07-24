@echo off
setlocal
cd /d "%~dp0"

set "GIT=C:\Program Files\Git\cmd\git.exe"
set "LOG=%~dp0logs\ipc_auto_update.log"
set "REMOTE=https://github.com/yucheng151/MVP_Ramen_HMI_0.0.2.git"

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo [%date% %time%] Checking GitHub for HMI updates...>>"%LOG%"

if not exist "%GIT%" (
    echo [%date% %time%] ERROR: Git is not installed.>>"%LOG%"
    exit /b 1
)

if not exist ".git" (
    echo [%date% %time%] ERROR: This folder is not a Git repository.>>"%LOG%"
    exit /b 1
)

"%GIT%" config --global --add safe.directory "%CD%" >>"%LOG%" 2>&1
"%GIT%" remote set-url origin "%REMOTE%" >>"%LOG%" 2>&1
if errorlevel 1 (
    "%GIT%" remote add origin "%REMOTE%" >>"%LOG%" 2>&1
)

"%GIT%" fetch origin main >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Unable to fetch from GitHub.>>"%LOG%"
    exit /b 1
)

"%GIT%" merge --ff-only origin/main >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Update stopped because the IPC copy has local changes.>>"%LOG%"
    exit /b 1
)

echo [%date% %time%] HMI is up to date.>>"%LOG%"
exit /b 0
