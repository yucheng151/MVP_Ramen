# HMI四站UnitID精確監看

這個監看區只複製狀態，不會控制輸出，也不需要修改原本的FB。

1. 將 `HMI_AutoMonitor_GlobalVars.tsv` 的變數加入全域變數表。
2. 新增一支 `AutoHMIMonitor [PRG,ST]`。
3. 區域變數新增：`VAR  MonitorSearchIndex  N/A [Auto]  INT  N/A  FIFO掃描索引`。
4. 將 `PRG_AutoHMIMonitor.st` 貼入程式。
5. 在 `MainAuto` 最後呼叫 `AutoHMIMonitor`，每個PLC Scan執行一次。
6. 編譯並重新下載到PLC或Simulator。

HMI讀到 `D8100 = 16#A55A` 後會自動切換成精確模式，同時顯示四個站與三個麵篩各自的UnitID。若D8100尚未建立，HMI仍會使用既有D8000除錯區顯示最前端碗、FIFO、麵篩State、UR與注湯狀態。
