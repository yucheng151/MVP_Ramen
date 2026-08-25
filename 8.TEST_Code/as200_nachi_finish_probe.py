"""對卡住的AS200模擬流程逐段補送Nachi資料與動作完成訊號。"""

from __future__ import annotations

import time

from pymodbus.client import ModbusTcpClient


HOST = "127.0.0.1"
PORT = 10002
DEVICE_ID = 1


def read_words(client: ModbusTcpClient, address: int, count: int = 1) -> list[int]:
    result = client.read_holding_registers(
        address=address,
        count=count,
        device_id=DEVICE_ID,
    )
    if result.isError():
        raise RuntimeError(result)
    return [int(value) & 0xFFFF for value in result.registers]


def write_word(client: ModbusTcpClient, address: int, value: int) -> None:
    result = client.write_register(
        address=address,
        value=value & 0xFFFF,
        device_id=DEVICE_ID,
    )
    if result.isError():
        raise RuntimeError(result)


def print_state(client: ModbusTcpClient, label: str) -> None:
    mode = read_words(client, 1109)[0]
    nachi = read_words(client, 12100, 5)
    debug_bits = read_words(client, 8002)[0]
    states = read_words(client, 8003, 5)
    action_step = read_words(client, 8008)[0]
    action_debug = read_words(client, 8009)[0]
    print(
        f"[{label}] Mode={mode}, D12100=0x{nachi[0]:04X}, "
        f"D12101=0x{nachi[1]:04X}, D12103=0x{nachi[3]:04X}, "
        f"D8002=0x{debug_bits:04X}, ActionStep={action_step}, "
        f"ExchangeFinish={(action_debug >> 0) & 1}, "
        f"RobotActionFinish={(action_debug >> 1) & 1}, "
        f"Baskets={states[0:3]}, Rightmost={states[3]}, JobState={states[4]}"
    )


def hold_bit(client: ModbusTcpClient, address: int, seconds: float) -> None:
    current = read_words(client, address)[0]
    write_word(client, address, current | 0x0001)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        write_word(client, address, current | 0x0001)
        time.sleep(0.02)
    write_word(client, address, current & ~0x0001)


def main() -> int:
    client = ModbusTcpClient(HOST, port=PORT, timeout=1.0)
    if not client.connect():
        print("[FAIL] Cannot connect AS200 Simulator")
        return 2
    try:
        print_state(client, "BEFORE")
        hold_bit(client, 12101, 1.0)
        time.sleep(0.5)
        print_state(client, "AFTER D12101")
        hold_bit(client, 12103, 1.0)
        time.sleep(0.5)
        print_state(client, "AFTER D12103")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
