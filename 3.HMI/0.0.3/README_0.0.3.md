# MVP Ramen HMI 0.0.3

## 啟動方式

- 正式PLC：雙擊 `start_hmi.cmd`，預設 `192.168.1.5:502`。
- AS200 Simulator：先啟動COMMGR與AS200 Simulator，再雙擊 `start_hmi_as200_sim.cmd`，使用 `127.0.0.1:10002`。
- AS200即時碗流程：雙擊 `start_auto_live_monitor.cmd`，直接開啟AUTO流程監看頁。
- 完全不連PLC：雙擊 `start_hmi_mock.cmd`。

也可以從命令列指定：

```powershell
py main_hmi.py --ip 127.0.0.1 --port 10002
```

## 0.0.3新增功能

- AUTO SYSTEM獨立頁面。
- 訂單FIFO，每碗自動建立唯一UnitID。
- 訂單指定麵櫃1~10與軟／正常／硬三種熟度。
- 麵櫃1~10目前數量、容量、訂單保留量與可用量。
- 左上兩個空盒櫃目前數量與容量上限。
- 使用實際麵櫃圖片作為底圖，直接點選12個格位設定BOX數量。
- 三個麵篩狀態。
- 四站流程：落碗 → 放麵&UR1 → UR2 → 注湯&完成。
- PLC唯讀即時監看：FIFO、完成UnitID、三個麵篩State、最右端碗、UR與注湯狀態。
- D8100精確監看區完成後，可同時顯示四個站與三個麵篩各自的UnitID。
- 本機流程模擬，不寫入PLC。
- PLC通訊契約頁，未配置位址不會被HMI讀寫。
- HMI IP與Port都能由啟動參數指定。

## 本機資料

PLC自動通訊完成前，AUTO SYSTEM的設定會保存在：

`data/auto_hmi_state.json`

手機訂單API與PLC自動資料區完成後，將資料來源替換成正式通訊即可；畫面不需要重做。

## PLC Debug LOG

HMI只在自動模式記錄PLC Debug區的原始D暫存器，不把HMI事件或Python程式狀態混進這份LOG。記錄範圍：

- `D8000-D8031`：PLC自動流程Debug區。
- `D8100-D8134`：PLC精確流程監看區。
- 任一D值變更時保存完整快照；若沒有變化，每60秒保存一次心跳快照。
- 僅唯讀PLC，不會由LOG功能回寫任何D位址。

Windows IPC的持久化位置：

`%LOCALAPPDATA%\MVP_Ramen_HMI\logs\plc_debug`

每天同時產生：

- `plc_debug_YYYY-MM-DD.jsonl`：包含原始D值與每筆變更明細，供後續程式與AI分析。
- `plc_debug_YYYY-MM-DD.csv`：每一個D位址各自一欄，可直接使用Excel開啟。
- `plc_debug_address_map.csv`：D位址與目前名稱對照表。

預設保留90天。AUTO SYSTEM的「PLC Debug LOG」分頁可查看最近250筆、開啟LOG資料夾、今日CSV或D位址表。

## 已確認

- Python編譯與全部模組載入通過。
- FIFO、UnitID、庫存保留、完成扣庫存、資料重開保存通過。
- AS200 Simulator `127.0.0.1:10002` 連線、命令寫入與ACK通過。
- 目前PLC模擬程式對初始化回覆`ResponseCode=901`；通訊本身正常，待PLC初始化流程完成後再改為成功碼。
- 1366×768視覺檢查通過。

完整測試結果請見 `VALIDATION_REPORT_2026-08-19.md`。

介面與Mock功能可重新執行：

```powershell
py ..\..\8.TEST_Code\hmi_003_interface_test.py
```
