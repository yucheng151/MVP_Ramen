@echo off
setlocal
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git is not installed or is not in PATH.
    pause
    exit /b 1
)

for /f "delims=" %%R in ('git rev-parse --show-toplevel 2^>nul') do set "REPO_ROOT=%%R"
if not defined REPO_ROOT (
    echo [ERROR] This HMI folder was not installed with git clone.
    echo Clone the HMI 0.0.3 repository once, then run this file from that folder.
    pause
    exit /b 1
)

echo Updating MVP Ramen HMI from origin/main...
git -C "%REPO_ROOT%" pull --ff-only origin main
if errorlevel 1 (
    echo [FAIL] Git update failed. Local source files may have been changed.
    pause
    exit /b 1
)

echo [PASS] HMI source is up to date.
echo Start the FIELD HMI with start_hmi.cmd.
pause
