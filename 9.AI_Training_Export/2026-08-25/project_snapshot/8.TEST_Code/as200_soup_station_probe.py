"""Probe the existing bowl at X0.4 without changing PLC FB logic."""

from __future__ import annotations

import time

from pymodbus.client import ModbusTcpClient


HOST = "127.0.0.1"
PORT = 10002
DEVICE_ID = 1
D_SIMULATION = 8000
D_DEBUG_START = 8001
D_FIFO_COUNT = 1133
D_SOUP_DEBUG_WORD = 8011


def read_words(client: ModbusTcpClient, address: int, count: int = 1) -> list[int]:
    result = client.read_holding_registers(
        address=address, count=count, device_id=DEVICE_ID
    )
    if result.isError():
        raise RuntimeError(result)
    return [int(value) & 0xFFFF for value in result.registers]


def write_word(client: ModbusTcpClient, address: int, value: int) -> None:
    result = client.write_register(
        address=address, value=value & 0xFFFF, device_id=DEVICE_ID
    )
    if result.isError():
        raise RuntimeError(result)


def main() -> int:
    client = ModbusTcpClient(HOST, port=PORT, timeout=1.0)
    if not client.connect():
        print("[FAIL] Cannot connect AS200 Simulator")
        return 2

    original_simulation = 0
    try:
        original_simulation = read_words(client, D_SIMULATION)[0]
        previous: tuple[int, ...] | None = None

        # 保持模擬模式，先關閉X0.4並清除上一輪鎖存資料。
        write_word(client, D_SIMULATION, (original_simulation | 0x0001) & ~0x0010)
        time.sleep(0.20)
        debug_word = read_words(client, D_SOUP_DEBUG_WORD)[0]
        write_word(client, D_SOUP_DEBUG_WORD, debug_word | 0x8000)
        time.sleep(0.10)
        write_word(client, D_SOUP_DEBUG_WORD, debug_word & ~0x8000)
        time.sleep(0.20)

        # 模擬X0.4上升沿。
        write_word(client, D_SIMULATION, original_simulation | 0x0011)
        started = time.monotonic()
        while time.monotonic() - started < 8.0:
            flow = read_words(client, D_DEBUG_START, 24)
            fifo_count = read_words(client, D_FIFO_COUNT, 1)[0]
            snapshot = tuple(flow + [fifo_count])
            if snapshot != previous:
                elapsed = time.monotonic() - started
                live = snapshot[10]
                seen = snapshot[13]
                head_unit = snapshot[14] | (snapshot[15] << 16)
                request_unit = snapshot[16] | (snapshot[17] << 16)
                grant_unit = snapshot[18] | (snapshot[19] << 16)
                done_unit = snapshot[20] | (snapshot[21] << 16)
                print(
                    f"[{elapsed:5.2f}s] "
                    f"Rightmost={snapshot[5]}, "
                    f"Live(D8011)=0x{live:04X}, "
                    f"BowlState={snapshot[11]}, JobState={snapshot[12]}, "
                    f"Seen(D8014)=0x{seen:04X}, "
                    f"HeadUnitID={head_unit}, RequestUnitID={request_unit}, "
                    f"GrantUnitID={grant_unit}, DoneUnitID={done_unit}, "
                    f"Head={snapshot[22]}, DebugCount={snapshot[23]}, "
                    f"FIFO={snapshot[24]}"
                )
                previous = snapshot
            if snapshot[24] == 0:
                print("[PASS] Soup completion removed the order from FIFO")
                return 0
            time.sleep(0.05)

        print("[BLOCKED] X0.4 was ON but the order did not complete")
        return 1
    finally:
        # 保持模擬模式開啟，但關閉本次暫時送出的X0.4。
        write_word(client, D_SIMULATION, (original_simulation | 0x0001) & ~0x0010)
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
