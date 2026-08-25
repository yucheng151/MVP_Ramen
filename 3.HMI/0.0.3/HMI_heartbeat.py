"""HMI 與 PLC 的雙向握手心跳模組。

本模組只負責 HMI <-> PLC 的心跳控制，使用由 main_hmi.py 建立並傳入的
共用 Modbus TCP client。它不會自行建立新的 ModbusTcpClient。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from HMI_plc_client import HMIPlcClient


# =====================================================
# PLC D 暫存器位址
# =====================================================

D_HMI_TO_PLC_HB_RETURN_INDEX = 1005   # D1005
D_PLC_TO_HMI_HB_INDEX = 1100          # D1100
D_HMI_COMM_STATUS = 1105              # D1105


@dataclass
class HMIHeartbeatResult:
    ok: bool
    plc_index: Optional[int]
    return_index: Optional[int]
    hmi_comm_status: Optional[int]
    message: str


class HMIHeartbeat:
    """HMI <-> PLC 雙向握手心跳控制器。"""

    def __init__(self, plc: HMIPlcClient):
        self.plc = plc
        self.last_error: Optional[str] = None
        self.last_plc_index: Optional[int] = None
        self.last_return_index: Optional[int] = None
        self.last_hmi_comm_status: Optional[int] = None

    @staticmethod
    def calc_return_index(plc_index: int) -> int:
        """計算 HMI 應回覆給 PLC 的下一個 16-bit Index。"""
        return (int(plc_index) + 1) & 0xFFFF

    def tick(self) -> HMIHeartbeatResult:
        """執行一次完整的 HMI 心跳讀寫。"""
        if not self.plc.connected:
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message="尚未連線 PLC",
            )

        data = self.plc.read_d(D_PLC_TO_HMI_HB_INDEX, 6)
        if data is None:
            self.last_error = self.plc.last_error
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message=self.last_error or "讀取 PLC 心跳失敗",
            )

        if len(data) < 6:
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message=f"PLC 回傳資料不足：預期 6 筆，收到 {len(data)} 筆",
            )

        plc_index = data[0]
        hmi_comm_status = data[5]
        return_index = self.calc_return_index(plc_index)

        write_ok = self.plc.write_d(D_HMI_TO_PLC_HB_RETURN_INDEX, return_index)
        if not write_ok:
            self.last_error = self.plc.last_error
            return HMIHeartbeatResult(
                ok=False,
                plc_index=plc_index,
                return_index=return_index,
                hmi_comm_status=hmi_comm_status,
                message="寫入 HMItoPLC_HB_ReturnIndex 失敗",
            )

        self.last_plc_index = plc_index
        self.last_return_index = return_index
        self.last_hmi_comm_status = hmi_comm_status

        ok = hmi_comm_status == 1
        return HMIHeartbeatResult(
            ok=ok,
            plc_index=plc_index,
            return_index=return_index,
            hmi_comm_status=hmi_comm_status,
            message="OK" if ok else "PLC 尚未判定 HMI 在線或已 Timeout",
        )
