from __future__ import annotations

import os
from pathlib import Path

HMI_VERSION = "0.0.3"

PLC_IP = "192.168.1.5"
PLC_PORT = 502
PLC_SLAVE_ID = 1
PLC_TIMEOUT = 1.0

HEARTBEAT_INTERVAL = 0.5
RECONNECT_DELAY = 2.0
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "hmi.log"
_LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA")
PLC_DEBUG_LOG_DIR = (
    Path(_LOCAL_APP_DATA) / "MVP_Ramen_HMI" / "logs" / "plc_debug"
    if _LOCAL_APP_DATA
    else LOG_DIR / "plc_debug"
)
PLC_DEBUG_LOG_RETENTION_DAYS = 90
PLC_DEBUG_LOG_HEARTBEAT_SECONDS = 60.0

# 若要新增命令或狀態讀取，可以在此定義常用的 PLC D 地址
PLC_HMI_TO_PLC_HB_RETURN_INDEX = 1005
PLC_PLC_TO_HMI_HB_INDEX = 1100
PLC_HMI_COMM_STATUS = 1105
