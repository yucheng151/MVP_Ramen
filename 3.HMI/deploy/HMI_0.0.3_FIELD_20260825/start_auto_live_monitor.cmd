@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "MVP Ramen SIMULATION Live Flow" ".venv\Scripts\pythonw.exe" main_hmi.py --profile simulation --ip 127.0.0.1 --port 10002 --page AutoSystemPage
) else (
    start "MVP Ramen SIMULATION Live Flow" pyw main_hmi.py --profile simulation --ip 127.0.0.1 --port 10002 --page AutoSystemPage
)
