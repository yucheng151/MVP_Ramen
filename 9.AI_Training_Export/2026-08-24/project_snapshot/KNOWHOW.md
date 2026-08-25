# MVP 拉麵機程式 Know-how（含 PLC）

> 盤點日期：2026-08-17  
> 文件定位：交接、維護、除錯與後續整合的入口文件。**只以目前程式實作為基準，不採用既有規劃表推定功能。**現場安全迴路、設備手冊及已下載至設備的正式版本仍具有最高優先權。

## 1. 一頁摘要

本系統採 **PLC 流程主控** 架構。HMI、IPC 與 Robot 都是受控端，不應自行跳越製程步驟。

```text
操作員
  │
  ▼
Python HMI ── Modbus TCP ──► PLC ── Modbus RTU/RS-485 ──► VECTOR-S100 輸送帶
  ▲                         │
  │                         ├── 實體 DI/DO ──► 落碗、感測器、閥、泵浦、安全訊號
  │                         │
  └──── 狀態/警報/握手 ─────┤
                            ├── Modbus TCP ──► Python IPC／小料手臂
                            └── 暫存器/網路 ─► Nachi Robot
```

核心原則：

1. PLC 決定模式、主流程、安全互鎖及動作允許。
2. HMI 只送高階命令並顯示 PLC 回報，不直接控制馬達或 Robot I/O。
3. IPC 收到 PLC 任務後依序回覆 Ack、Busy、Response；完成回覆必須帶相同 Seq。
4. Robot 狀態區 D12100~D12156 對 HMI 為唯讀，HMI 不得直接寫入。
5. 軟體急停/EMC 握手不能取代硬體安全迴路。

## 2. 專案目錄與正式版本判定

| 目錄 | 內容 | 目前應採用 | 備註 |
|---|---|---|---|
| `1.PLC/` | Delta ISPSoft PLC 專案 | `MVP_V2_034`（目前工作區最新候選版） | 尚未證明等同 PLC 內運轉版；須核對設備內版本、修改日期及 checksum |
| `2.電路圖/` | DWG、PDF、備份 | `煮麵機電路圖_V0.1` | PDF 僅 1 頁，完整性須由電控確認 |
| `3.HMI/0.0.2/` | Python/Tkinter HMI | `0.0.2` | 工作區有尚未提交的修改，不能只依 Git 判定正式版 |
| `4.IO/` | 舊通訊/I/O 規劃表 | 不作為程式依據 | 規劃內容有誤，本文件排除引用；僅保留作歷史追溯 |
| `5.Robot/` | Nachi Robot 備份與示範程式 | `3.OK _Demo` 或設備實際備份 | 必須由 Robot 控制器實機版本確認 |
| `6.IPC/0.0.1/` | 小料手臂 IPC Python | `0.0.1` | Robot SDK 尚未接妥的安全占位程式不可直接上線 |
| `0.Old/` | SS101A/B 舊版 PLC、HMI、I/O | 僅供追溯 | 不可覆蓋現行程式 |
| `tmp/` | PDF 梯形圖轉圖與分析中間檔 | 非正式成果 | 不可作為唯一備份 |

PLC 專案常見檔案：`.isp` 為專案入口，`.tag` 為標籤/符號資料，`.hwc` 為硬體設定，`.eiptag`/EDS 為 EtherNet/IP 描述，`.bak` 與 `.~bak` 是備份。交付 PLC 時應整個版本目錄封存，不要只複製 `.isp`。

## 3. 啟動與開發環境

### HMI

- Python 依賴：`pymodbus`、Tkinter（Windows Python 通常內建）。
- PLC 預設：`192.168.1.5:502`、Slave ID `1`、timeout `1.0 s`。
- 正式啟動：`3.HMI/0.0.2/start_hmi.cmd`。
- 模擬啟動：`3.HMI/0.0.2/start_hmi_mock.cmd`，不連實機 PLC。
- IPC 電腦初始化：`setup_ipc.cmd`；自動更新相關檔案需先在離線環境驗證來源與回復方式。
- Log：`3.HMI/0.0.2/logs/hmi.log`。

### IPC

- Python 依賴：`pymodbus`。
- `ipc_controller.py`：整合心跳、任務握手、EMC 與 Robot 任務執行。
- `ipc_heartbeat.py`：只做 D1200 → D1300 心跳回傳。
- `ipc_emc.py`：只做 D1207 → 安全停機 → D1308 確認。
- 三支程式不能在未設計連線仲裁時同時啟動，否則會建立多條 Modbus client 並競爭同一組暫存器；正式部署以整合版 `ipc_controller.py` 為主。

## 4. HMI 程式架構

| 模組 | 職責 |
|---|---|
| `HMI_ui.py` | 主應用、頁面切換、輪詢、模式握手、EMC、狀態 snapshot |
| `HMI_plc_client.py` | 全 HMI 共用的唯一 Modbus TCP client、鎖與讀寫封裝 |
| `HMI_heartbeat.py` | 讀 PLC 心跳 D1100，回寫 D1005，讀 D1105 通訊狀態 |
| `HMI_command.py` | D1000~D1002 命令握手、模式/輸送帶/Robot/半自動命令 |
| `HMI_status.py` | PLC、感測器、Robot、手動 Robot 狀態解析 |
| `register_map.py` | 目前 HMI 實作所依據的唯一暫存器常數表 |
| `mock_plc_client.py` | 離線 UI 與握手模擬；亦執行 Robot 唯讀區保護 |
| `process_models.py` | 自動/半自動流程資料模型、配方驗證與狀態角色 |
| `process_flow_widget.py`、`process_overview_panel.py` | 流程視覺化與操作面板 |
| `ui_*.py` | 主頁、輸送帶、Robot、IPC、通訊、警報、參數等頁面 |
| `main_hmi.py` | 命令列 demo/interactive 入口；正式 GUI 主要由 HMI UI 啟動 |

HMI 共用連線很重要：`HMIPlcClient` 只建立一次，再注入 heartbeat、command、status。新增功能不得另開一個無鎖 client，否則不同執行緒的 Modbus request 可能互相穿插。

## 5. 目前 HMI 實作暫存器（以現行 `register_map.py` 為準）

本節完全由 `3.HMI/0.0.2/register_map.py` 與其呼叫程式整理，未引用 `4.IO` 規劃表。位址是否已在 PLC V2_034 完成同名邏輯，仍須用 ISPSoft 匯出資料逐項核對。

### HMI ↔ PLC

| 位址 | 用途 |
|---|---|
| D1000 | HMI 命令碼 |
| D1001 | HMI 命令序號/Index |
| D1002 | 命令 Valid |
| D1003 | 輸送帶速度設定 |
| D1004.0 | HMI EMC 要求 |
| D1005 | HMI 心跳回傳 Index |
| D1010~D1013 | Robot 手動參數：Action、麵櫃、切數、出麵櫃 |
| D1014 | 半自動測試步驟 mask |
| D1100 | PLC 心跳 Index |
| D1102 | PLC 命令 Ack Index |
| D1103 | PLC 命令 Response Code |
| D1104 | 輸送帶狀態 |
| D1105 | PLC 判定 HMI 通訊狀態 |
| D1106 | PLC 狀態碼 |
| D1107 | 輸送帶 timeout bit word |
| D1108.0 | PLC EMC active |
| D1109 | Machine Mode：0 Manual、1 Semi-Auto、2 Auto |
| D1110 | 感測器 bit word；D1110.5 亦作半自動執行互鎖 |
| D1120~D1124 | Robot 手動執行狀態、Ack、結果、警報、Idle |
| D1400 | PLC 主流程 Step |

### PLC ↔ IPC

| 位址 | 用途 |
|---|---|
| D1200 | PLC 給 IPC 心跳 Index |
| D1201 | 任務碼：101 前三料、102 後三料 |
| D1202 | 任務 Seq |
| D1203 | 任務 Valid |
| D1207 | PLC EMC/Abort Request |
| D1209.0 | PLC 判定 IPC 通訊正常 |
| D1300 | IPC 心跳回傳 |
| D1301 | IPC Ack Seq |
| D1302 | IPC Busy |
| D1303 | Response：201 前三料完成、202 後三料完成、901 錯誤 |
| D1304 | Response Seq |
| D1305 | IPC Error Code |
| D1308 | IPC EMC 停止完成 |

### PLC ↔ Nachi Robot

| 位址 | 方向/用途 |
|---|---|
| D12100 | Robot status bits：Busy、通訊、Home、Error、Alarm、E-stop、Running 等 |
| D12101~D12104 | Read Complete、Error Code、Action Complete、Index |
| D12150 | PLC 給 Robot 的 command bits |
| D12151~D12156 | Index、Action、麵櫃、切數、出麵櫃、麵種 |

HMI 只能讀 D12100~D12156。`HMI_plc_client.py` 與 mock client 已有防寫保護；未來修改 client 時必須保留。

## 6. 命令碼與握手

目前 HMI 命令包含：1 初始化、6 警報復歸、10 輸送帶運轉、11 停止、12 設速度、20 落碗、30/31/32 模式切換、40 Robot 手動執行、50/51 小料前/後段、60 半自動單步。

標準命令流程：

1. 發起方先寫參數。
2. 將 Seq/Index 加 1（16-bit 循環）。
3. 寫 Request Code，再令 Valid=1。
4. 接收方僅在 Valid=1 且 Seq 是新值時接受，立即回 Ack Seq。
5. 執行中回 Busy/Accepted；完成或失敗時同時寫 Response Code 與相同 Response Seq。
6. 發起方只有在 Seq 相同時才採信結果，最後清 Valid/Code。

任何只看 Done bit、不核對 Seq 的作法，都可能把上一輪完成誤判成下一輪完成。

## 7. PLC Know-how

### 7.1 PLC 的責任

- 上電初始化、模式管理與狀態機。
- 急停、安全門、壓力/液位等硬體互鎖。
- 落碗、輸送帶定位、煮麵、放料、加湯及出餐流程。
- HMI/IPC 心跳監看、Ask/Ack/Response 握手與 timeout。
- Robot 命令和狀態轉接，不讓 HMI 直接越權控制。
- 所有輸出在 Alarm/EMC 時回到已風險評估的安全狀態。

### 7.2 主流程

現行 HMI 從 D1400 取得 PLC 主流程 Step，畫面模型目前顯示八個製程節點；但 PLC V2_034 的 `.isp/.tag` 是 ISPSoft 專用格式，僅靠一般文字工具無法可靠還原每一個 rung、Step 編號、轉移條件與 timeout。故本文件不引用舊規劃表補齊 PLC 流程。正式主流程必須以 ISPSoft 開啟 `MVP_V2_034.isp` 後匯出的最新程式 PDF、Device/Tag 與 Comment 為準。

### 7.3 輸送帶通訊

現行 HMI 程式可確認有輸送帶命令、速度設定、狀態、fault/readback 與 timeout 顯示：D1003、D1104、D1107，以及 `register_map.py` 中 100~112 的讀寫欄位。PLC V2_034 內部實際使用的 RTU 站號、baud rate、功能碼、設備位址與 `MODRWE` 參數尚未由可讀的現行 export 驗證，因此本版文件不沿用舊 Excel 或 V2_010/V2_012 PDF 的數值。這些值必須直接從 V2_034 ISPSoft 專案匯出後補入。

### 7.4 PLC 版本保存

每次上線前後各保存一份完整專案，命名至少包含版本、日期、設備，例如 `MVP_V2_035_2026-08-17_before`。同時留下：修改原因、影響 rung/FB、I/O/暫存器變更、下載人、PLC Run 結果、回復版本。`.~bak` 是工具自動備份，不可取代正式 release。

## 8. IPC Know-how 與未完成項

`ipc_controller.py` 已具備完整握手骨架：讀 D1200~D1207、心跳回寫、Ack、Busy、Response、錯誤碼及 EMC。`SmallMaterialRobot` 目前是介面/占位層，Robot SDK 尚未設定時會回錯誤，不應用模擬成功取代實機安全確認。

內建錯誤碼：1001 不支援命令、1002 Robot 未設定、1003 任務失敗、1004 EMC 中止。接入實機 SDK 時，至少實作 `execute(task_code, recipe_no)` 與 `stop_safely()`，並把「已送出停止命令」和「Robot 已確認停止」分開；只有後者才可令 D1308=1。

## 9. Robot Know-how

`5.Robot/` 是 Nachi MZ07LF 控制器備份。`PROGRAM/MZ07LF-01.001` 為 Main program；`.002`、`.003` 等為子程序/動作程序；`.998/.999`、`.1000+` 多為共用、通訊或測試程序；`USERTASK.001` 含 TCP socket 收送、狀態/I/O 編碼與外部命令解析。

Robot 檔案是控制器專用二進位/混合格式，直接用文字編輯器會出現亂碼。應使用 Nachi FD/CFD 控制器工具匯入、比對與修改。更換點位時要保存 Tool、Work、Robot、Signal、Program 與完整 controller backup，不能只備份單一 PROGRAM 資料夾。

## 10. I/O 與電路圖

`4.IO/MVP_Ramen_Comm_IO_Table_v3.xlsx` 屬有問題的舊規劃，**不得用於配線、PLC 位址、命令碼或驗收**。目前 I/O 真值來源只接受：PLC V2_034 的實際 Device/Tag/Comment、現場端子與線號，以及 `2.電路圖` 經電控確認的圖面。三者不一致時先停機查證，不能以舊 Excel 補值。

安全相關輸入不可只靠標準 PLC 軟體判斷。急停、安全門等應依風險評估使用安全繼電器/安全 PLC 和硬接線切斷危險能量；一般 PLC/HMI 僅讀取安全狀態作顯示與流程停止。

## 11. 舊規劃排除與現行程式注意事項

下表只用來說明為何舊規劃已被排除，不代表兩套資料都可使用。

| 項目 | 已排除的舊規劃 | 現行 HMI 程式 | 處置 |
|---|---|---|---|
| HMI 命令區 | D1001 Code、D1002 Seq、D1003 Valid | D1000 Code、D1001 Index、D1002 Valid | 以 PLC V2_034 實機確認後建立新正式表 |
| 心跳回傳 | D1000 | D1005 | 不可混用 |
| PLC 回 HMI | D1101~D1106 為 Step/Status/Error/Ack/Response | D1102 Ack、D1103 Response、D1104 Conveyor、D1105 Comm、D1106 Status | 逐欄 reconcile |
| 主流程 | D1101 | D1400 | 以目前 PLC tag/梯形圖確認 |
| HMI 命令碼 | 早期含 StartOrder/Pause/Resume/Stop | 現行加入模式 30~32、Robot 40、小料 50/51、半自動 60 | 建立單一正式 Code Table |
| Robot | 早期表未涵蓋完整 D12100 區 | 現行 HMI 已實作 D12100~D12156 | 補入新版 I/O 表 |

因此目前不再對舊 Excel 做 reconcile。正式 FAT 前應做「PLC V2_034 export → HMI `register_map.py` → IPC constants → Robot mapping → 現場配線」對表；確認後另建一份由現行程式反向產生的新 I/O/通訊表。

## 12. 測試與故障排查

建議順序：

1. 斷開動力或使用安全測試模式，先確認 PLC/HMI/IPC IP、port 502 與 Slave ID。
2. HMI mock 測 UI 與握手，不帶實機輸出。
3. 實機只測心跳：D1100↔D1005、D1200↔D1300。
4. 測命令 Ack/Response Seq，不先啟動機構。
5. 手動逐點確認 DI/DO 極性與標籤。
6. 單獨測輸送帶 RTU：模式、速度、方向、Run/Stop、timeout。
7. Robot 低速、單步、空載確認點位與外控握手。
8. 最後才跑完整流程與異常注入測試。

常見故障：

- HMI Offline：先看 D1100 是否變化、D1005 是否跟隨、D1105 PLC 判定，再查網路與多 client 競爭。
- IPC 不執行：查 D1203 Valid、D1202 是否新 Seq、D1301 Ack、D1302 Busy、D1305 Error。
- IPC 一直 Busy：Robot task 未回、例外未進 finally、EMC 未完成；不可直接強制清 PLC 流程。
- 輸送帶無反應：依 V2_034 線上監控查命令、D1104 狀態、D1107 timeout、實際通訊參數、配線與 PLC 通訊指令 Error；不得套用舊規劃參數。
- Robot 畫面顯示異常：查 D12100 status bits、D12102 error、D1124 Idle；不要由 HMI 寫 Robot 區修飾畫面。
- 模式旋鈕跳回：D1109 PLC Machine Mode 未跟隨命令結果，或 D1110.5 半自動互鎖仍 ON。

## 13. 變更與交接清單

- [ ] 確認 PLC 內正式版本是否為 MVP_V2_034。
- [ ] 從 ISPSoft 匯出最新版完整 PDF、Device/Tag、Comment 與硬體設定。
- [ ] 將 `register_map.py`、IPC constants、PLC tags、Robot mapping、現場配線五方對表；不要引用舊規劃 Excel。
- [ ] 標出所有安全 I/O 的硬體回路、常態極性與失效安全狀態。
- [ ] 接妥 IPC Robot SDK，移除 simulate/占位路徑的上線可能性。
- [ ] 建立 HMI、IPC 自動啟動、log rotation、備份與回復程序。
- [ ] 執行 FAT：正常循環、斷線、timeout、急停、安全門、缺料、Robot alarm、斷電復歸。
- [ ] 每次 release 保存 PLC/HMI/IPC/Robot/I/O/電路圖的同一組版本號。

## 14. 來源索引

- PLC：`1.PLC/MVP_V2_034/`。`MVP_V2_010`、`MVP_V2_012` PDF 是舊版，只供版本追溯，不作現行邏輯依據。
- HMI：`3.HMI/0.0.2/`，特別是 `register_map.py`、`HMI_plc_client.py`、`HMI_command.py`、`HMI_status.py`、`HMI_ui.py`。
- IPC：`6.IPC/0.0.1/ipc_controller.py`、`ipc_emc.py`、`ipc_heartbeat.py`。
- 舊規劃（排除引用）：`4.IO/MVP_Ramen_Comm_IO_Table_v3.xlsx`，僅作歷史追溯。
- Robot：`5.Robot/3.OK _Demo/PROGRAM/` 與 `5.Robot/1.bakeup/WORK/`。
- 電路：`2.電路圖/煮麵機電路圖_V0.1_P1.pdf`、`.dwg`。
