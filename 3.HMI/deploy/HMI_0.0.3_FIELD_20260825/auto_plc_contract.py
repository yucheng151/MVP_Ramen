"""全自動PLC通訊契約草案；address=None代表PLC尚未配置。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PLCField:
    name: str
    direction: str
    data_type: str
    count: int = 1
    address: int | None = None
    comment: str = ""


AUTO_PLC_FIELDS = (
    PLCField("Order_Write_UnitID", "HMI->PLC", "DINT", address=1020, comment="每碗唯一編號"),
    PLCField("Order_Write_CabinetNo", "HMI->PLC", "INT", address=1022, comment="麵櫃1~10"),
    PLCField("Order_Write_Firmness", "HMI->PLC", "INT", address=1023, comment="1硬、2正常、3軟"),
    PLCField("Order_Write_Index", "HMI->PLC", "WORD", address=1024, comment="每筆新訂單遞增序號"),
    PLCField("Order_Write_Valid", "HMI->PLC", "WORD", address=1025, comment="新訂單有效與交握"),
    PLCField("Order_ACK_UnitID", "PLC->HMI", "DINT", address=1130, comment="PLC收單回覆"),
    PLCField("Order_ACK_Index", "PLC->HMI", "WORD", address=1132, comment="PLC已處理的訂單序號"),
    PLCField("Order_FIFO_Count", "PLC->HMI", "INT", address=1133, comment="PLC待處理碗數"),
    PLCField("Order_Response", "PLC->HMI", "INT", address=1134, comment="200成功；400以上拒絕或異常"),
    PLCField("Unit_Status_Block", "PLC->HMI", "STRUCT", count=10, comment="UnitID與每碗狀態"),
    PLCField("Basket_Status_Block", "PLC->HMI", "MONITOR", count=3, address=8114, comment="D8100精確監看區的三個麵篩"),
    PLCField("Station_Status_Block", "PLC->HMI", "MONITOR", count=4, address=8102, comment="D8100精確監看區的四個輸送站"),
    PLCField("Cabinet_Quantity_Block", "HMI<->PLC", "INT", count=10, comment="麵櫃剩餘盒數"),
    PLCField("Empty_Box_Block", "HMI<->PLC", "INT", count=2, comment="左上兩個空盒櫃"),
    PLCField("Unit_Done_Pulse", "PLC->HMI", "BOOL", comment="完成脈波"),
    PLCField("Unit_Done_UnitID", "PLC->HMI", "DINT", address=1135, comment="完成的碗編號"),
    PLCField("Unit_Done_Index", "PLC->HMI", "DWORD", address=1137, comment="完成流水號"),
)


def assigned_count() -> int:
    return sum(field.address is not None for field in AUTO_PLC_FIELDS)
