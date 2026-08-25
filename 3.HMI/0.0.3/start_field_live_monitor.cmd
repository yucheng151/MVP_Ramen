@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "MVP Ramen HMI FIELD" ".venv\Scripts\pythonw.exe" hmi_launcher.pyw --profile field --ip 192.168.1.5 --port 502 --page AutoSystemPage
) else (
    echo HMI environment is missing. Run setup_ipc.cmd first.
    pause
    exit /b 1
)
