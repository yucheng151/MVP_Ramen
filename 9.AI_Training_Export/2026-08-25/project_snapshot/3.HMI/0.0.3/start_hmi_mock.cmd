@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo HMI environment is missing. Run setup_ipc.cmd first.
    pause
    exit /b 1
)
start "MVP Ramen HMI SIMULATION MOCK" ".venv\Scripts\pythonw.exe" main_hmi.py --profile simulation --mock
