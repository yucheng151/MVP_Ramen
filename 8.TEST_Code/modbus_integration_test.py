#!/usr/bin/env python3
"""對 virtual_plc_modbus.py 執行可重複的 Modbus 整合測試。"""

from __future__ import annotations

import argparse
import time

from pymodbus.client import ModbusTcpClient


D_X0 = 15000
D_Y0 = 15001
D_SCENARIO = 15010


class TestFailure(RuntimeError):
    pass


def read_d(client: ModbusTcpClient, address: int, device_id: int) -> int:
    result = client.read_holding_registers(address=address, count=1, device_id=device_id)
    if result.isError():
        raise TestFailure(f"讀取 D{address} 失敗：{result}")
    return int(result.registers[0]) & 0xFFFF


def write_d(client: ModbusTcpClient, address: int, value: int, device_id: int) -> None:
    result = client.write_register(address=address, value=value & 0xFFFF, device_id=device_id)
    if result.isError():
        raise TestFailure(f"寫入 D{address} 失敗：{result}")


def wait_d(
    client: ModbusTcpClient,
    address: int,
    expected: int,
    device_id: int,
    timeout: float = 1.5,
) -> None:
    deadline = time.monotonic() + timeout
    actual = read_d(client, address, device_id)
    while actual != expected and time.monotonic() < deadline:
        time.sleep(0.03)
        actual = read_d(client, address, device_id)
    if actual != expected:
        raise TestFailure(f"D{address} 預期 {expected}，實際 {actual}")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise TestFailure(message)


def run(host: str, port: int, device_id: int) -> None:
    client = ModbusTcpClient(host=host, port=port, timeout=1.0)
    if not client.connect():
        raise TestFailure(f"無法連線 {host}:{port}")

    try:
        write_d(client, D_SCENARIO, 0, device_id)
        write_d(client, D_X0, 0, device_id)
        write_d(client, D_Y0, 0, device_id)
        time.sleep(0.08)

        hb1 = read_d(client, 1100, device_id)
        time.sleep(0.55)
        hb2 = read_d(client, 1100, device_id)
        check(hb2 != hb1, "D1100 PLC心跳沒有變化")
        print("[PASS] PLC心跳 D1100")

        write_d(client, 1002, 0, device_id)
        write_d(client, 1000, 1, device_id)
        write_d(client, 1001, 321, device_id)
        write_d(client, 1002, 1, device_id)
        wait_d(client, 1102, 321, device_id)
        wait_d(client, 1103, 200, device_id)
        print("[PASS] HMI命令握手 D1000~D1002 -> D1102/D1103")

        for bit in range(1, 5):
            write_d(client, D_X0, 1 << bit, device_id)
            time.sleep(0.05)
            sensor = read_d(client, 1110, device_id)
            check(bool(sensor & (1 << (bit - 1))), f"X0.{bit} 未映射到D1110")
        print("[PASS] X0.1~X0.4感測器映射")

        y_word = 0
        for bit in (0, 7, 8, 9):
            y_word |= 1 << bit
            write_d(client, D_Y0, y_word, device_id)
            time.sleep(0.04)
            check(bool(read_d(client, D_Y0, device_id) & (1 << bit)), f"Y0.{bit} 無法設定")
        write_d(client, D_Y0, 0, device_id)
        print("[PASS] Y0.0/Y0.7/Y0.8/Y0.9輸出控制")

        write_d(client, D_X0, 1 << 1, device_id)
        write_d(client, D_SCENARIO, 1, device_id)
        time.sleep(0.08)
        check(not (read_d(client, D_X0, device_id) & (1 << 1)), "落碗感測器卡住情境失效")
        print("[PASS] 落碗感測器卡住")

        write_d(client, D_X0, 1 << 2, device_id)
        write_d(client, D_SCENARIO, 2, device_id)
        time.sleep(0.08)
        check(not (read_d(client, D_X0, device_id) & (1 << 2)), "X0.2卡住情境失效")
        print("[PASS] X0.2站感測器卡住")

        write_d(client, D_SCENARIO, 3, device_id)
        wait_d(client, 1209, 0, device_id)
        print("[PASS] IPC通訊逾時")

        write_d(client, D_SCENARIO, 4, device_id)
        wait_d(client, 12102, 401, device_id)
        print("[PASS] Nachi手臂警報")

        write_d(client, D_SCENARIO, 5, device_id)
        wait_d(client, 1108, 1, device_id)
        wait_d(client, 1207, 1, device_id)
        print("[PASS] EMC停止")

        write_d(client, D_SCENARIO, 6, device_id)
        wait_d(client, D_SCENARIO, 6, device_id)
        print("[PASS] 慢速動作情境")

        print("RESULT: PASS - Modbus、HMI握手、I/O與故障注入全部通過。")
    finally:
        try:
            write_d(client, D_SCENARIO, 0, device_id)
            write_d(client, D_X0, 0, device_id)
            write_d(client, D_Y0, 0, device_id)
            write_d(client, 1002, 0, device_id)
        finally:
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="MVP Ramen虛擬PLC整合測試")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device-id", type=int, default=1)
    args = parser.parse_args()
    try:
        run(args.host, args.port, args.device_id)
    except TestFailure as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
