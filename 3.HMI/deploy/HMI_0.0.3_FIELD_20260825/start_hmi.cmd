@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo HMI environment is missing. Run setup_ipc.cmd first.
    pause
    exit /b 1
)
start "MVP Ramen HMI FIELD" ".venv\Scripts\pythonw.exe" hmi_launcher.pyw --profile field --ip 192.168.1.5 --port 502
