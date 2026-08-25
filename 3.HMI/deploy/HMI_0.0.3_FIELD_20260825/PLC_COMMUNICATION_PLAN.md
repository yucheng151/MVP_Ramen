# 全自動HMI／PLC通訊規劃

目前PLC尚未配置全自動訂單資料區，因此HMI不猜測D位址。正式位址統一在 `auto_plc_contract.py` 填入，`address=None` 代表禁止通訊。

## 建議交握

1. HMI從手機點餐後建立唯一UnitID。
2. HMI寫入UnitID、麵櫃編號、軟硬度與CommandIndex。
3. HMI最後打開OrderValid。
4. PLC將資料複製進內部FIFO後，回覆相同UnitID與ACK Index。
5. HMI收到正確ACK後才把訂單標成PLC Accepted。
6. PLC以UnitID回報每碗、麵篩與四站狀態。
7. PLC完成一碗時輸出一個Scan的DonePulse，並保持DoneUnitID直到下一碗完成。
8. HMI依DoneUnitID通知原下單者，不使用完成先後推算訂單。

## 必要資料區

- HMI → PLC：UnitID、麵櫃1~10、軟硬度1~3、CommandIndex、OrderValid。
- PLC → HMI：ACK UnitID、ACK Index、FIFO數量與接單結果。
- PLC → HMI：10筆Unit狀態監看、三筆DUT_NoodleBasket、四站狀態。
- HMI ↔ PLC：麵櫃10格與空盒櫃2格的數量同步。
- PLC → HMI：DonePulse與DoneUnitID。

## 原則

- 煮麵完成順序可以不同，但碗完成通知必須依UnitID。
- PLC內部排程、麵篩選擇與UR／Nachi安全互鎖由PLC決定。
- HMI只提交訂單與顯示狀態，不直接搶占機械手臂。
- PLC尚未完成的欄位在HMI上顯示Pending，不讀寫未知位址。
- 目前AS200 Simulator已能回ACK，但初始化回覆901；這是PLC流程待完成項目，不以HMI端硬改回覆碼。
- PLC位址確認後，先在AS200 Simulator完成單碗、三碗、非FIFO熟成及通訊中斷測試，再上機。
