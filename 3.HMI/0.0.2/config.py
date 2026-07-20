from __future__ import annotations

from pathlib import Path

PLC_IP = "192.168.1.5"
PLC_PORT = 502
PLC_SLAVE_ID = 1
PLC_TIMEOUT = 1.0

HEARTBEAT_INTERVAL = 0.5
RECONNECT_DELAY = 2.0
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "hmi.log"

# 若要新增命令或狀態讀取，可以在此定義常用的 PLC D 地址
PLC_HMI_TO_PLC_HB_RETURN_INDEX = 1005
PLC_PLC_TO_HMI_HB_INDEX = 1100
PLC_HMI_COMM_STATUS = 1105
