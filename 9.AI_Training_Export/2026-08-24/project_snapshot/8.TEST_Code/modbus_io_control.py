#!/usr/bin/env python3
"""控制 virtual_plc_modbus.py 的 X/Y/D 與故障情境。"""

from __future__ import annotations

import argparse
import sys

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 pymodbus，請先執行：py -m pip install pymodbus") from exc


D_TEST_X0_WORD = 15000
D_TEST_Y0_WORD = 15001
D_TEST_SCENARIO = 15010

SCENARIOS = {
    "normal": 0,
    "bowl_sensor_stuck": 1,
    "station20_stuck": 2,
    "ipc_timeout": 3,
    "robot_alarm": 4,
    "emc": 5,
    "slow": 6,
}


def parse_io_address(text: str, prefix: str) -> int:
    normalized = text.strip().upper()
    expected = f"{prefix}0."
    if not normalized.startswith(expected):
        raise ValueError(f"地址格式必須像 {prefix}0.1")
    bit = int(normalized[len(expected):])
    if not 0 <= bit <= 15:
        raise ValueError("位元必須介於0~15")
    return bit


def parse_state(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized in ("1", "on", "true"):
        return True
    if normalized in ("0", "off", "false"):
        return False
    raise ValueError("狀態必須為 on/off 或 1/0")


def read_register(client: ModbusTcpClient, address: int, device_id: int) -> int:
    result = client.read_holding_registers(address=address, count=1, device_id=device_id)
    if result.isError():
        raise RuntimeError(str(result))
    return int(result.registers[0]) & 0xFFFF


def write_register(client: ModbusTcpClient, address: int, value: int, device_id: int) -> None:
    result = client.write_register(address=address, value=int(value) & 0xFFFF, device_id=device_id)
    if result.isError():
        raise RuntimeError(str(result))


def print_status(client: ModbusTcpClient, device_id: int) -> None:
    addresses = [
        1000, 1001, 1002, 1100, 1102, 1103, 1104, 1105, 1108, 1109,
        1110, 1120, 1124, 1200, 1201, 1202, 1203, 1209, 1300, 1302,
        1303, 1304, 1305, 15000, 15001, 15010,
    ]
    values = {address: read_register(client, address, device_id) for address in addresses}
    print("Virtual PLC status")
    for address in addresses:
        print(f"  D{address:<5} = {values[address]}")
    x_word = values[D_TEST_X0_WORD]
    y_word = values[D_TEST_Y0_WORD]
    print("  X0 = " + " ".join(f"X0.{bit}={int(bool(x_word & (1 << bit)))}" for bit in range(1, 5)))
    print("  Y0 = " + " ".join(f"Y0.{bit}={int(bool(y_word & (1 << bit)))}" for bit in (0, 7, 8, 9)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="控制MVP Ramen本機虛擬PLC")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device-id", type=int, default=1)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    set_x = sub.add_parser("set-x", help="設定X輸入，例如 set-x X0.2 on")
    set_x.add_argument("address")
    set_x.add_argument("state")

    set_y = sub.add_parser("set-y", help="設定Y輸出，例如 set-y Y0.7 on")
    set_y.add_argument("address")
    set_y.add_argument("state")

    read_d = sub.add_parser("read-d")
    read_d.add_argument("address", type=int)

    write_d = sub.add_parser("write-d")
    write_d.add_argument("address", type=int)
    write_d.add_argument("value", type=int)

    scenario = sub.add_parser("scenario")
    scenario.add_argument("name", choices=sorted(SCENARIOS))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = ModbusTcpClient(host=args.host, port=args.port, timeout=1.0)
    if not client.connect():
        print(f"無法連線虛擬PLC {args.host}:{args.port}", file=sys.stderr)
        return 1
    try:
        if args.command == "status":
            print_status(client, args.device_id)
        elif args.command == "set-x":
            bit = parse_io_address(args.address, "X")
            word = read_register(client, D_TEST_X0_WORD, args.device_id)
            word = word | (1 << bit) if parse_state(args.state) else word & ~(1 << bit)
            write_register(client, D_TEST_X0_WORD, word, args.device_id)
            print(f"{args.address.upper()} = {int(parse_state(args.state))}")
        elif args.command == "set-y":
            bit = parse_io_address(args.address, "Y")
            word = read_register(client, D_TEST_Y0_WORD, args.device_id)
            word = word | (1 << bit) if parse_state(args.state) else word & ~(1 << bit)
            write_register(client, D_TEST_Y0_WORD, word, args.device_id)
            print(f"{args.address.upper()} = {int(parse_state(args.state))}")
        elif args.command == "read-d":
            print(f"D{args.address} = {read_register(client, args.address, args.device_id)}")
        elif args.command == "write-d":
            write_register(client, args.address, args.value, args.device_id)
            print(f"D{args.address} = {args.value & 0xFFFF}")
        elif args.command == "scenario":
            write_register(client, D_TEST_SCENARIO, SCENARIOS[args.name], args.device_id)
            print(f"scenario = {args.name}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
