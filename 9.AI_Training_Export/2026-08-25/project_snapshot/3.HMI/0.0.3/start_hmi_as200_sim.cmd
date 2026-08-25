@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo HMI environment is missing. Run setup_ipc.cmd first.
    pause
    exit /b 1
)
start "MVP Ramen HMI v0.0.3 SIMULATION" ".venv\Scripts\pythonw.exe" main_hmi.py --profile simulation --ip 127.0.0.1 --port 10002
