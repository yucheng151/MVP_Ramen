"""Read-only snapshot of the AS200 automatic-flow debug registers."""

from pymodbus.client import ModbusTcpClient


def read_words(client: ModbusTcpClient, address: int, count: int = 1) -> list[int]:
    result = client.read_holding_registers(address=address, count=count, device_id=1)
    if result.isError():
        raise RuntimeError(result)
    return [int(value) & 0xFFFF for value in result.registers]


def main() -> int:
    client = ModbusTcpClient("127.0.0.1", port=10002, timeout=1.0)
    if not client.connect():
        print("[FAIL] Cannot connect AS200 Simulator")
        return 2
    try:
        print("D1024-D1031", read_words(client, 1024, 8))
        print("D1109", read_words(client, 1109)[0])
        print("D1130-D1138", read_words(client, 1130, 9))
        print("D1201-D1204", read_words(client, 1201, 4))
        print("D12100-D12103", [f"0x{x:04X}" for x in read_words(client, 12100, 4)])
        print("D12150-D12156", [f"0x{x:04X}" for x in read_words(client, 12150, 7)])
        print("D1302-D1305", read_words(client, 1302, 4))
        print("D8000-D8010", [f"0x{x:04X}" for x in read_words(client, 8000, 11)])
        soup_debug = read_words(client, 8011, 14)
        print("D8011-D8024", [f"0x{x:04X}" for x in soup_debug])
        print(
            "Soup debug",
            {
                "Live": f"0x{soup_debug[0]:04X}",
                "HeadBowlState": soup_debug[1],
                "HeadJobState": soup_debug[2],
                "Seen": f"0x{soup_debug[3]:04X}",
                "HeadUnitID": soup_debug[4] | (soup_debug[5] << 16),
                "RequestUnitID": soup_debug[6] | (soup_debug[7] << 16),
                "GrantUnitID": soup_debug[8] | (soup_debug[9] << 16),
                "DoneUnitID": soup_debug[10] | (soup_debug[11] << 16),
                "Head": soup_debug[12],
                "Count": soup_debug[13],
            },
        )
        ur_debug = read_words(client, 8025, 7)
        print("D8025-D8031", [f"0x{x:04X}" for x in ur_debug])
        print(
            "UR done debug",
            {
                "Flags": f"0x{ur_debug[0]:04X}",
                "UR1DoneUnitID": ur_debug[1] | (ur_debug[2] << 16),
                "UR2DoneUnitID": ur_debug[3] | (ur_debug[4] << 16),
                "StateAtUR1Done": ur_debug[5],
                "StateAtUR2Done": ur_debug[6],
            },
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
