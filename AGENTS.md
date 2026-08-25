# AGENTS.md

這份檔案是這個工作區的 AI 協作入口，目的是讓 GitHub Copilot / AI agent 在進入專案時，先知道專案結構、常用工作流程、驗證方法，以及哪些地方不該碰。

## 1. 專案概覽

這個工作區是 MVP Ramen 自動拉麵機專案，重點分成四層：

- PLC 程式：`1.PLC/`
- 電路圖：`2.電路圖/`
- HMI：`3.HMI/`
- 測試與模擬：`8.TEST_Code/`
- 異常/歷史備份：`0.Old/`, `ErrorReports/`, `tmp/`

最重要的現場程式與回歸驗證資訊，通常在以下位置：

- [8.TEST_Code/README.md](8.TEST_Code/README.md)
- [9.AI_Training_Export/CLAUDE_START_HERE.md](9.AI_Training_Export/CLAUDE_START_HERE.md)

## 2. 先看哪些文件

在改任何程式前，先讀這些文件：

1. [8.TEST_Code/README.md](8.TEST_Code/README.md) — 本機模擬、Modbus、AS200 測試入口
2. [9.AI_Training_Export/CLAUDE_START_HERE.md](9.AI_Training_Export/CLAUDE_START_HERE.md) — 知識包與交接說明
3. 目標資料夾內的 README（若存在）

不要直接從 `.bak`、`~bak`、`0.Old/`、`tmp/` 或 `ErrorReports/` 裡面的舊檔案推斷當前狀態，這些通常是歷史資料或測試產物。

## 3. 這個專案的實際工作邏輯

### PLC 相關

- 主要版本位於 `1.PLC/` 下，像 `MVP_V2_100/`、`MVP_V2_101/` 等資料夾。
- 若要修改 PLC，務必先確認目標版本是 `V100` 還是 `V101`。
- `V101` 是後續 1000 筆耐久測試版，不能和 `V100` 混用。
- PLC 變更後需重新進行 ISPSoft 編譯與回歸測試，不可只靠舊 PASS 或既有歷史檔案判斷。

### HMI / IPC / 通訊

- HMI 程式在 `3.HMI/`，通常是 Python 或 UI 相關專案。
- 通訊與模擬測試多集中在 `8.TEST_Code/`，例如：
  - `virtual_plc_modbus.py`
  - `plc_auto_logic_sim.py`
  - `modbus_integration_test.py`
  - `as200_plc_integration_test.py`

### 測試優先順序

這專案的驗證流程通常是：

1. Python 邏輯模擬 / Modbus 測試
2. AS200 Simulator / 周邊設備模擬
3. PLC 編譯與 ISPSoft 回歸
4. 實機驗證

## 4. 常用命令

以下為最常用的測試入口，請以這些作為基準：

### 啟動虛擬 PLC

```powershell
cd .\8.TEST_Code
py virtual_plc_modbus.py
```

### 執行全自動流程壓力測試

```powershell
cd .\8.TEST_Code
py plc_auto_logic_sim.py --random-tests 200
py plc_auto_logic_sim.py --trace --random-tests 20
```

### 直接測 AS200 Simulator

```powershell
cd .\8.TEST_Code
py as200_plc_integration_test.py --host 127.0.0.1 --port 10002
```

### Modbus 整合測試

```powershell
cd .\8.TEST_Code
py modbus_integration_test.py --host 127.0.0.1 --port 502
```

### 查看 I/O 狀態與手動寫入

```powershell
cd .\8.TEST_Code
py modbus_io_control.py status
py modbus_io_control.py set-x X0.1 on
py modbus_io_control.py set-y Y0.7 on
```

## 5. 變更時的行為規範

- 先找到「真正要改的版本」及其相關測試，避免在舊備份資料中修改。
- 若是 PLC 變更，先確認是否影響實際 I/O / 通訊位址；不要隨意增減 D 位址或 X/Y 定義。
- 若是測試腳本修改，保留原本的模擬與回歸腳本用途，不要把正式 PLC 規格混入測試專用 D 位址。
- 不要在 `0.Old/`、`tmp/`、`ErrorReports/`、`*.bak`、`~bak` 內做有意義的工程修改，這些被視為歷史或暫存資料。
- 修改後，至少要做最小範圍驗證；若涉及 PLC 邏輯，需補 ISPSoft 編譯與回歸。

## 6. AI agent 寫程式時的建議順序

1. 先讀目標模組和對應 README。
2. 確認這是 PLC、HMI、Python 測試，還是通訊層問題。
3. 先做最小修正，不擴大影響範圍。
4. 以最相近的模擬器或測試腳本驗證。
5. 若是 PLC，必須附上編譯與回歸證據。

## 7. 對 AI 助理的提醒

- 優先使用繁體中文進行回應與說明。
- 先確認目標 PLC 版本再分析變更，避免混用 `V100` / `V101`。
- 若資料缺失，先確認是否有最新知識包或測試說明，不要直接推測。
- 遇到「模擬器 / PLC / HMI 互動」問題時，先檢查 `8.TEST_Code/README.md`，再做改動。

## 8. 這份文件的目的

這份 AGENTS.md 的目標不是取代專案文件，而是讓 AI agent 能在最短時間內理解：

- 專案是什麼
- 哪些資料夾是正式的
- 哪些是歷史/備份
- 該怎麼測
- 什麼時候需要編譯與回歸

這樣後續由 AI 協作或接手專案時，能更快進入狀態。
