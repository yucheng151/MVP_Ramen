"""PLC -> HMI 的狀態讀取模組。

本模組只讀取 PLC 發送給 HMI 的狀態暫存器 D1102~D1106，使用由
main_hmi.py 建立並傳入的共用 Modbus TCP client。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from HMI_plc_client import HMIPlcClient
from register_map import PLC_TO_HMI_SENSOR_STATUS, SENSOR_BITS


# =====================================================
# PLC -> HMI 狀態 D 暫存器位址
# =====================================================
D_PLC_TO_HMI_CMD_ACK_INDEX = 1102   # D1102
D_PLC_TO_HMI_CMD_RESPONSE_CODE = 1103  # D1103
D_PLC_TO_HMI_CONVEYOR_STATUS = 1104    # D1104
D_HMI_COMM_STATUS = 1105               # D1105
D_PLC_TO_HMI_STATUS_CODE = 1106       # D1106


@dataclass
class HMISensorStatus:
    bowl_drop_confirm: bool = False
    pause_point_1: bool = False
    pause_point_2: bool = False
    right_stop_point: bool = False
    bowl_dispenser_busy: bool = False


@dataclass
class HMIStatusResult:
    ok: bool
    ack_index: Optional[int]
    response_code: Optional[int]
    conveyor_status: Optional[int]
    hmi_comm_status: Optional[int]
    plc_status_code: Optional[int]
    message: str
    sensors: HMISensorStatus = field(default_factory=HMISensorStatus)


class HMIStatus:
    """讀取 PLC -> HMI 狀態的控制器。"""

    def __init__(self, plc: HMIPlcClient):
        self.plc = plc
        self.last_error: Optional[str] = None

    def read_status(self) -> HMIStatusResult:
        """讀取 D1102~D1106，共 5 個 WORD。"""
        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message="尚未連線 PLC",
            )

        data = self.plc.read_d(D_PLC_TO_HMI_CMD_ACK_INDEX, 5)
        if data is None:
            self.last_error = self.plc.last_error
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message=self.last_error or "讀取 PLC 狀態失敗",
            )

        if len(data) < 5:
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message=f"PLC 回傳資料不足：預期 5 筆，收到 {len(data)} 筆",
            )

        sensor_data = self.plc.read_d(PLC_TO_HMI_SENSOR_STATUS, 1)
        if sensor_data is None:
            self.last_error = self.plc.last_error
            return HMIStatusResult(
                ok=False,
                ack_index=data[0],
                response_code=data[1],
                conveyor_status=data[2],
                hmi_comm_status=data[3],
                plc_status_code=data[4],
                message=self.last_error or "讀取 D1110 感測器狀態失敗",
            )

        sensor_word = sensor_data[0]
        sensors = HMISensorStatus(**{
            name: bool(sensor_word & (1 << bit))
            for name, bit in SENSOR_BITS.items()
        })

        return HMIStatusResult(
            ok=True,
            ack_index=data[0],
            response_code=data[1],
            conveyor_status=data[2],
            hmi_comm_status=data[3],
            plc_status_code=data[4],
            message="OK",
            sensors=sensors,
        )
