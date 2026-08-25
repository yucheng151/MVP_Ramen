# Claude 接手：HMI 0.0.3 部署到 IPC

## 本次工作範圍與權限邊界

- 本次只交由 Claude 處理 **IPC 端部署、啟動診斷與現場環境測試**。
- HMI 正式程式仍以開發電腦的 `3.HMI/0.0.3/` 為唯一來源。
- 不可直接在 IPC 上修改 Python 原始碼、PLC 程式或既有 FB。
- 若找到程式問題，只需提供 traceback、重現步驟、Python 版本與建議修正；實際原始碼修正回到開發電腦進行。
- IPC 端只允許覆蓋由開發電腦產生的部署檔、建立 `.venv`、安裝相依套件、執行測試與收集日誌。
- 測試成功後，IPC 保留部署成品；所有修正仍需同步回正式來源並重新打包，避免 IPC 與開發電腦版本分岔。

## 使用者目前看到的現象

- 最新 HMI 壓縮檔已透過 TeamViewer 傳到 HMI IPC。
- 使用者已完成解壓縮。
- 執行啟動檔後沒有跳出 HMI 視窗。
- 請從啟動環境診斷繼續，不要重做 PLC 邏輯，也不要修改既有 PLC FB。

## 正式來源與部署目標

- HMI 原始碼：`3.HMI/0.0.3/`
- 最新部署暫存資料夾：`3.HMI/deploy/HMI_0.0.3_FIELD_20260825/`
- 舊的完整 ZIP：`3.HMI/deploy/MVP_Ramen_HMI_0.0.3_FIELD_20260825.zip`
- 注意：完整 ZIP 建立時間早於下面的啟動修正，不能把該 ZIP 視為最新啟動版本。

## 已完成但尚未傳到 IPC 的啟動修正

部署暫存資料夾內已新增／更新：

- `hmi_launcher.pyw`
  - 捕捉啟動例外。
  - 寫入 `logs/hmi_startup_error.log`。
  - 嘗試顯示 Tk 錯誤對話框。
  - 檢查 Python 必須為 3.10 以上。
- `start_hmi.cmd`
  - 固定使用 `.venv/Scripts/pythonw.exe`。
  - 啟動 `hmi_launcher.pyw --profile field --ip 192.168.1.5 --port 502`。
- `start_field_live_monitor.cmd`
  - 同樣改用啟動包裝器。
- `setup_ipc.cmd`
  - 檢查 Python 3.10 以上。
  - 建立 `.venv` 並安裝 `requirements.txt`。
  - 驗證 `tkinter`、`PIL`、`pymodbus` 可匯入。

## 建議先做的遠端 IPC 診斷

1. 把上述四個新檔案複製到 IPC 已解壓的 HMI 根目錄並覆蓋舊檔。
2. 在 IPC 上執行 `setup_ipc.cmd`，保留命令視窗並確認最後是否顯示 `Runtime imports OK`。
3. 再執行 `start_hmi.cmd`。
4. 若仍無視窗，查看 `logs/hmi_startup_error.log`。
5. 若連錯誤日誌也沒有，從 IPC 的命令提示字元在 HMI 根目錄執行：

   ```cmd
   .venv\Scripts\python.exe main_hmi.py --profile field --ip 192.168.1.5 --port 502
   ```

   這會把原本被 `pythonw.exe` 隱藏的 traceback 留在畫面上。

## 判斷原則

- PLC `192.168.1.5:502` 暫時連不上，不應造成 Tk 主視窗完全無法建立；若一啟動就退出，優先查 Python、Tk、Pillow、pymodbus、工作目錄及 traceback。
- 不要把 FIELD 版本改成 `--mock` 來掩蓋問題；模擬版與現場版必須分開。
- 不要修改使用者已完成的 PLC FB。
- 正式修復後需重新建立完整部署 ZIP，並重新計算 SHA-256。

## 已知驗證狀態

- 啟動包裝器及新版批次檔已寫入本機原始碼與部署暫存資料夾。
- 這次工作環境找不到先前固定路徑的 `py.exe`，因此最新四個啟動檔尚未在本機完成重新編譯驗證；這是本機工具路徑問題，不等同於 IPC 程式失敗。
- 先前 HMI 介面回歸測試曾通過，但最新啟動包裝器仍需在 IPC 或可用 Python 3.10+ 的環境重新驗證。

## 完成條件

- IPC 雙擊 `start_hmi.cmd` 可顯示 `[FIELD]` HMI 視窗。
- HMI 即使 PLC 離線也能顯示介面並呈現離線狀態，而不是無聲退出。
- 成功後重新打包完整部署 ZIP、記錄 SHA-256，並回報實際 Python 版本與啟動測試結果。

## 2026-08-25 PLC Debug LOG測試包

- 測試包：`3.HMI/deploy/MVP_Ramen_HMI_0.0.3_FIELD_PLCDEBUG_20260825.zip`
- SHA-256：`85E8DE79DF40A2EA86AB8D8FDCCB63E5C48AE3CF12438C11F367EE6B8012483F`
- 正式原始碼仍是：`3.HMI/0.0.3/`
- IPC LOG位置：`%LOCALAPPDATA%\MVP_Ramen_HMI\logs\plc_debug`
- 每天產生 `plc_debug_YYYY-MM-DD.jsonl` 與 `plc_debug_YYYY-MM-DD.csv`，保留90天。
- `plc_debug_address_map.csv`保存D位址名稱對照。
- 只保存PLC原始`D8000-D8031`與`D8100-D8134`；不記錄HMI事件或Python程式狀態。
- 記錄器完全唯讀，不回寫PLC；FIELD正式流程畫面仍只採用D8100監看區。

IPC測試順序：

1. 將PLCDEBUG測試包解壓至新的資料夾，不要在IPC修改Python原始碼。
2. 執行 `setup_ipc.cmd`，記錄Python版本與安裝結果。
3. 執行 `test_plc_debug_log.cmd`；應顯示兩行PASS訊息。
4. 執行 `test_field_offline.cmd`；應顯示 `RESULT: PASS` 與 `FIELD offline startup test PASS`。
5. 執行 `start_hmi.cmd`，確認FIELD介面可開啟，AUTO SYSTEM有「PLC Debug LOG」分頁。
6. PLC可用時切入Auto並執行測試流程，確認今日CSV每個D位址各自一欄，且D值改變時增加快照。
7. 離開Auto後確認不再新增PLC Debug快照。
8. 回傳測試畫面、當日JSONL與CSV；若啟動失敗再一併回傳`hmi_startup_error.log`。

FIELD無視窗根因已在開發電腦修正：`ui_main_page.py`改用
`(snapshot.get("auto_live") or {}).get("available")`，避免啟動時
`auto_live=None`產生`AttributeError`。使用者已確認修正後IPC HMI可成功開啟。
