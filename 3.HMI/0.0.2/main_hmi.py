"""HMI 主程式入口。

本主程式建立唯一的 PLC Modbus TCP client，並把該實例傳給 heartbeat、
command 與 status 模組，確保所有功能共用一條連線。
"""

from __future__ import annotations

import argparse
import threading
from typing import Optional

from HMI_heartbeat import HMIHeartbeat
from HMI_command import HMICommand
from HMI_status import HMIStatus
from HMI_plc_client import HMIPlcClient
from HMI_ui import HMIUI
from config import HEARTBEAT_INTERVAL, PLC_IP


def build_services(ip: str) -> tuple[HMIPlcClient, HMIHeartbeat, HMICommand, HMIStatus]:
    """建立共用同一條 PLC 連線的 HMI 服務。"""
    plc = HMIPlcClient(ip=ip)
    return plc, HMIHeartbeat(plc), HMICommand(plc), HMIStatus(plc)


def run_demo(plc: HMIPlcClient, heartbeat: HMIHeartbeat, command: HMICommand, status: HMIStatus) -> int:
    """做一次簡單的非互動測試流程，適合直接在終端驗證。"""
    if not plc.connect():
        print(f"PLC 連線失敗：{plc.last_error}")
        return 1

    print("Demo 模式：執行一次心跳與命令流程")

    try:
        heartbeat_result = heartbeat.tick()
        print(
            f"HB | ok={heartbeat_result.ok} | PLC_Index={heartbeat_result.plc_index} | "
            f"ReturnIndex={heartbeat_result.return_index} | HMI_CommStatus={heartbeat_result.hmi_comm_status} | "
            f"{heartbeat_result.message}"
        )

        command_result = command.send_initialize()
        print(
            f"CMD | ok={command_result.ok} | code={command_result.command_code} | "
            f"index={command_result.command_index} | speed={command_result.conveyor_speed} | "
            f"{command_result.message}"
        )

        status_result = status.read_status()
        print(
            f"Status | ACK={status_result.ack_index} | ResponseCode={status_result.response_code} | "
            f"ConveyorStatus={status_result.conveyor_status} | HMI_CommStatus={status_result.hmi_comm_status} | "
            f"PLC_StatusCode={status_result.plc_status_code} | {status_result.message}"
        )
        return 0
    finally:
        command.clear_command()
        plc.close()


def run_interactive(plc: HMIPlcClient, heartbeat: HMIHeartbeat, command: HMICommand, status: HMIStatus) -> int:
    """保留互動式測試模式。"""
    if not plc.connect():
        print(f"PLC 連線失敗：{plc.last_error}")
        return 1

    stop_event = threading.Event()

    def heartbeat_loop() -> None:
        while not stop_event.is_set():
            if plc.connected:
                result = heartbeat.tick()
                if result.ok:
                    print(
                        f"HB OK | PLC_Index={result.plc_index} | "
                        f"ReturnIndex={result.return_index} | "
                        f"HMI_CommStatus={result.hmi_comm_status}",
                        flush=True,
                    )
                else:
                    print(f"HB NG | {result.message}", flush=True)
            else:
                print("HB 未連線", flush=True)
            stop_event.wait(HEARTBEAT_INTERVAL)

    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    print("HMI 主程式啟動")
    print("1 = 初始化")
    print("6 = 警報復歸")
    print("10 = 輸送帶正轉")
    print("11 = 輸送帶停止")
    print("0 = 清除命令")
    print("s = 讀 PLC 狀態")
    print("q = 離開")

    try:
        while True:
            user_input = input("> ").strip().lower()
            if user_input == "q":
                break

            if user_input == "1":
                result = command.send_initialize()
            elif user_input == "6":
                result = command.send_alarm_reset()
            elif user_input == "10":
                result = command.send_conveyor_run(speed=150)
            elif user_input == "11":
                result = command.send_conveyor_stop()
            elif user_input == "0":
                result = command.clear_command()
            elif user_input == "s":
                result = status.read_status()
                print(
                    f"Status | ACK={result.ack_index} | "
                    f"ResponseCode={result.response_code} | "
                    f"ConveyorStatus={result.conveyor_status} | "
                    f"HMI_CommStatus={result.hmi_comm_status} | "
                    f"PLC_StatusCode={result.plc_status_code} | "
                    f"{result.message}"
                )
                continue
            else:
                print("無效指令")
                continue

            print(
                f"CMD | ok={result.ok} | code={result.command_code} | "
                f"index={result.command_index} | speed={result.conveyor_speed} | "
                f"{result.message}"
            )
    except KeyboardInterrupt:
        print("\n使用者中止")
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1.0)
        plc.close()
        print("PLC 連線關閉")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="HMI 主程式")
    parser.add_argument("--demo", action="store_true", help="執行一次性測試流程")
    parser.add_argument("--cli", action="store_true", help="使用終端互動模式")
    parser.add_argument("--ip", default=PLC_IP, help="PLC IP 位址")
    parser.add_argument("--mock", action="store_true", help="不連 PLC，使用模擬資料啟動 UI")
    args = parser.parse_args(argv)

    if args.demo:
        plc, heartbeat, command, status = build_services(args.ip)
        return run_demo(plc, heartbeat, command, status)

    if args.cli:
        plc, heartbeat, command, status = build_services(args.ip)
        return run_interactive(plc, heartbeat, command, status)

    ui = HMIUI(ip=args.ip, mock=args.mock)
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
