"""Read-only monitor for the separate UR Robot IPC heartbeat."""

from __future__ import annotations

from dataclasses import dataclass

from HMI_plc_client import HMIPlcClient
from register_map import (
    PLC_IPC_COMM_NORMAL,
    PLC_IPC_HEARTBEAT_INDEX,
    UR_IPC_HEARTBEAT_RETURN,
)


@dataclass
class IPCHeartbeatResult:
    ok: bool
    plc_index: int | None
    return_index: int | None
    plc_comm_normal: bool
    message: str
    status_word: int | None = None
    execution_status: str = "Offline"
    last_result: str = "--"
    request_code: int | None = None
    request_seq: int | None = None
    request_valid: int | None = None
    emc_request: int | None = None
    ack_seq: int | None = None
    busy: int | None = None
    response_code: int | None = None
    response_seq: int | None = None
    error_code: int | None = None
    emc_done: int | None = None


class IPCHeartbeat:
    def __init__(self, plc: HMIPlcClient):
        self.plc = plc
        self.last_error = None

    def tick(self) -> IPCHeartbeatResult:
        if not self.plc.connected:
            return IPCHeartbeatResult(False, None, None, False, "PLC Offline")
        with self.plc.lock:
            plc_block = self.plc.read_d(PLC_IPC_HEARTBEAT_INDEX, 10)
            ipc_block = self.plc.read_d(UR_IPC_HEARTBEAT_RETURN, 9)
            if plc_block is None or ipc_block is None:
                self.last_error = self.plc.last_error
                return IPCHeartbeatResult(False, None, None, False,
                                          self.last_error or "Cannot read IPC heartbeat registers")
            plc_index = int(plc_block[0]) & 0xFFFF
            request_code = int(plc_block[1]) & 0xFFFF
            request_seq = int(plc_block[2]) & 0xFFFF
            request_valid = int(plc_block[3]) & 0xFFFF
            emc_request = int(plc_block[7]) & 0xFFFF
            status_word = int(plc_block[9]) & 0xFFFF
            return_index = int(ipc_block[0]) & 0xFFFF
            ack_seq = int(ipc_block[1]) & 0xFFFF
            busy = int(ipc_block[2]) & 0xFFFF
            response_code = int(ipc_block[3]) & 0xFFFF
            response_seq = int(ipc_block[4]) & 0xFFFF
            error_code = int(ipc_block[5]) & 0xFFFF
            emc_done = int(ipc_block[8]) & 0xFFFF
        expected = (plc_index + 1) & 0xFFFF
        # D1200 and D1300 belong to different PLC/UR-IPC scan moments, so a
        # single HMI poll can observe a transient index mismatch. D1209 is the
        # PLC's authoritative timeout/handshake result.
        normal = bool(status_word & 0x0001)
        detail = (
            "UR IPC heartbeat normal"
            if return_index == expected
            else f"UR IPC online; index updating (expected {expected})"
        )
        result_matches = response_seq == request_seq
        if response_code == 201 and result_matches:
            last_result = "前三料完成"
        elif response_code == 202 and result_matches:
            last_result = "後三料完成"
        elif response_code == 901 and result_matches:
            last_result = f"Error Code: {error_code}"
        else:
            last_result = "--"

        if not normal:
            execution_status = "Offline"
        elif emc_request == 1 and emc_done == 0:
            execution_status = "EMC Stopping"
        elif emc_request == 1 and emc_done == 1:
            execution_status = "EMC Stopped"
        elif response_code == 901 and result_matches:
            execution_status = "Error"
        elif request_valid == 1 and ack_seq != request_seq:
            execution_status = "Waiting IPC Ack"
        elif request_valid == 1 and ack_seq == request_seq and busy == 0:
            execution_status = "IPC Accepted / Preparing"
        elif request_valid == 1 and busy == 1 and request_code == 101:
            execution_status = "前三料執行中"
        elif request_valid == 1 and busy == 1 and request_code == 102:
            execution_status = "後三料執行中"
        elif request_valid == 0 and busy == 0:
            execution_status = "Ready"
        else:
            execution_status = "Error"

        return IPCHeartbeatResult(
            ok=normal, plc_index=plc_index, return_index=return_index,
            plc_comm_normal=normal,
            message=detail if normal else "PLC reports IPC communication timeout",
            status_word=status_word, execution_status=execution_status,
            last_result=last_result, request_code=request_code,
            request_seq=request_seq, request_valid=request_valid,
            emc_request=emc_request, ack_seq=ack_seq, busy=busy,
            response_code=response_code, response_seq=response_seq,
            error_code=error_code, emc_done=emc_done,
        )
