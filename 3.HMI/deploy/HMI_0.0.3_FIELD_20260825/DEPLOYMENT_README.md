# MVP Ramen HMI 0.0.3 FIELD 部署說明

## 版本

- HMI：0.0.3 FIELD
- 建置日期：2026-08-25
- PLC：192.168.1.5:502，Slave ID 1
- 軟硬度代碼：1=硬、2=正常、3=軟

## 新 IPC 第一次安裝

1. 將整個資料夾複製到 HMI IPC，例如 `C:\MVP_Ramen_HMI\0.0.3`。
2. 確認 IPC 已安裝 Python 3.10以上，安裝時需勾選「Add Python to PATH」。
3. 在 IPC 上執行 `setup_ipc.cmd`，建立該電腦專用的 `.venv` 並安裝 pymodbus、Pillow。
4. 先保持機台在安全狀態，再執行 `start_hmi.cmd`。
5. 確認標題顯示 `[FIELD]`，PLC 連線目標為 `192.168.1.5:502`。

## 更新既有 IPC

1. 關閉正在執行的 HMI。
2. 將原 HMI 資料夾改名備份，例如 `0.0.2_backup_20260825`。
3. 複製本部署包到新資料夾。
4. 不要從舊版複製 `.venv`；在新資料夾重新執行 `setup_ipc.cmd`。
5. 執行 `start_hmi.cmd`，確認啟動與 PLC 連線後再移除舊備份。

## PLC Debug LOG

- 持久化位置：`%LOCALAPPDATA%\MVP_Ramen_HMI\logs\plc_debug`。
- 每天產生JSONL與CSV，預設保留90天。
- AUTO SYSTEM的「PLC Debug LOG」分頁可看最近250筆並開啟資料夾、今日CSV或D位址表。
- LOG只保存PLC原始`D8000-D8031`與`D8100-D8134`，不混入HMI事件或Python程式狀態。
- 任一D值變更時保存完整快照，無變化時每60秒保存心跳快照；記錄器完全唯讀PLC。
- 更新HMI程式資料夾不會覆蓋此LOG目錄。
- IPC環境建立後，可執行 `test_plc_debug_log.cmd` 驗證PLC原始D值LOG寫入。
- 執行 `test_field_offline.cmd` 可確認FIELD模式在PLC離線時仍能建立並顯示介面。

## 安全與版本注意事項

- 正式 IPC 只能使用 `start_hmi.cmd` 或 `start_field_live_monitor.cmd`。
- FIELD 模式禁止 Mock、外部設備斷線 bypass，以及使用D8000資料做正式控制判斷。
- 診斷記錄器只會唯讀保存D8000與D8100區，不會回寫或影響PLC流程。
- 本部署包未安裝自動更新工作，因舊腳本仍指向 0.0.2 GitHub 倉庫。
- 正式訂單與麵櫃寫入仍須依 PLC 已完成的固定 D 位址通訊規格驗證。
- 實機啟動前須確認 PLC、輸送帶、UR1、UR2、Nachi 與 EMC 狀態。

## 已完成驗證

- 新增LOG以前的Python全模組編譯與載入已通過。
- 新增LOG以前的HMI 0.0.3七個主頁面、Mock命令與資料保存回歸已通過。
- 深色主題及灰色 ttk 邊框狀態驗證通過。
- 本建置新增的「PLC Debug LOG」分頁與原始D值寫入，需在IPC依序執行
  `test_plc_debug_log.cmd`、`test_field_offline.cmd`、`start_hmi.cmd`完成最後環境驗證。
