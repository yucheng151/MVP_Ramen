@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "MVP Ramen HMI FIELD" ".venv\Scripts\pythonw.exe" main_hmi.py --profile field --ip 192.168.1.5 --port 502 --page AutoSystemPage
) else (
    start "MVP Ramen HMI FIELD" pyw main_hmi.py --profile field --ip 192.168.1.5 --port 502 --page AutoSystemPage
)
