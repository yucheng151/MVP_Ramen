# MVP Ramen 專案知識基線

## 1. 系統目的

本專案是一套以台達 AS200 PLC 為製程主控的自動拉麵設備。整合 Python HMI、手機點餐、輸送帶與現場 I/O、Nachi MZ07LF Robot，以及 IPC／Isaac Sim／雙 UR5e 配料系統。

## 2. 控制權責

1. PLC 決定模式、流程步驟、排程、安全互鎖及動作授權。
2. HMI 送出高階命令、訂單與參數，顯示 PLC 回報；不得直接越權驅動 Robot 或危險輸出。
3. IPC 收到 PLC 任務後依 Seq 回覆 Ack、Busy 與 Response。
4. Nachi／UR 的動作完成只代表該子任務完成，不代表整碗已完成。
5. Modbus EMC 握手不能取代實體急停、安全繼電器或安全 PLC。

## 3. 主要資料流

```text
手機訂單
  -> HMI 拆成單碗 UnitID
  -> PLC 收單與 FIFO
  -> PLC 分配麵篩及四站流程
  -> PLC 授權 Nachi／UR1／UR2
  -> PLC 以 UnitID 與完成流水號回報
  -> HMI 扣庫存並通知顧客
```

每碗必須使用唯一 UnitID。煮麵熟成順序可能不是 FIFO，因此不能以完成先後推算訂單身分。

## 4. 一般 HMI／PLC 暫存器

| 位址 | 功能 |
|---|---|
| D1000 | HMI Command Code |
| D1001 | HMI Command Index |
| D1002 | HMI Command Valid |
| D1003 | 輸送帶速度設定 |
| D1004.0 | HMI EMC Request |
| D1005 | HMI 心跳回傳 |
| D1100 | PLC Heartbeat Index |
| D1102 | PLC Command Ack Index |
| D1103 | PLC Command Response Code |
| D1104 | 輸送帶狀態 |
| D1105 | PLC 判定 HMI 通訊狀態 |
| D1106 | PLC 狀態碼 |
| D1107 | 輸送帶 timeout word |
| D1108.0 | PLC EMC Active |
| D1109 | Machine Mode：0 Manual、1 Semi-Auto、2 Auto |
| D1110 | 感測器鏡像 bit word |
| D1120~D1124 | Robot 手動狀態、Ack、結果、警報、Idle |
| D1400 | PLC 主流程 Step |

命令包含初始化、警報復歸、輸送帶Run／Stop／速度、落碗、模式切換、Robot手動、小料前後段與半自動單步。確切命令碼以現行 `register_map.py` 與 PLC 程式共同核對。

## 5. PLC／IPC 通訊

| 位址 | 功能 |
|---|---|
| D1200 | PLC 心跳 Index |
| D1201 | Request Code：101／102／103 |
| D1202 | Request Seq |
| D1203 | Request Valid |
| D1207 | EMC／Abort Request |
| D1209.0 | PLC 判定 IPC 通訊正常 |
| D1300 | IPC 心跳回傳 |
| D1301 | Ack Seq |
| D1302 | Busy |
| D1303 | Response：201／202／203／901 |
| D1304 | Response Seq |
| D1305 | Error Code |
| D1308 | IPC 安全停止完成 |

任務語意：

- 103／203：UR1 預先拍照、辨識並凍結目標。
- 101／201：UR1 執行蛋、筍乾、木耳。
- 102／202：UR2 執行後段配料／湯勺流程。
- 901：任務失敗。

接收端只能接受 `Valid=1` 且 Seq 為新值的任務。完成結果必須攜帶相同 Response Seq。錯誤後不應自動重送，避免重複投料。

## 6. Nachi Robot 區

PLC 讀取 D12100~D12104 的 Robot 狀態，寫入 D12150~D12156 的命令與參數。HMI 對 D12100~D12156 僅能唯讀，不得為了修飾畫面直接寫入。

## 7. AUTO 訂單介面（2026-08-24狀態）

已配置候選位址：

- D1020：Order UnitID，DINT，占兩個 word。
- D1022：Cabinet No。
- D1023：Firmness。
- D1025：Order Valid／交握 word。
- D1130：ACK UnitID，DINT。
- D1133：FIFO Count。
- D1135：Done UnitID，DINT。
- D1137：Done Index，DWORD。
- D8102 起：四站精確監看區。
- D8114 起：三個麵篩精確監看區。

尚未完整配置：10筆 Unit Status、10格麵櫃庫存、2格空盒庫存，以及部分接單結果欄位。模型不得猜測未知位址。

## 8. HMI

HMI 0.0.3 是 Python／Tkinter 應用，支援正式 PLC、AS200 Simulator 及完全 Mock 三種模式。AUTO SYSTEM 已有 FIFO、UnitID、熟度、麵櫃庫存、三麵篩與四站顯示。本機流程可儲存 JSON；正式資料來源仍應以 PLC 回報為準。

HMI 應共用單一具鎖的 Modbus client。新增頁面或服務不得各自建立無仲裁連線，以免不同執行緒的 request 互相穿插。

## 9. IPC／雙 UR5e

新版 IPC 以 Isaac Sim、ROS 2、RTDE 和視覺資訊協調雙 UR5e：左臂處理蛋、筍乾、木耳；右臂處理芝麻、蔥和湯勺路徑。具目標穩定鎖定、A/S凍結與執行流程、真實 TCP 確認、EMC、watchdog及恢復checkpoint。

模擬開關不能被當作真實設備完成訊號。只有 Robot 控制器確認停止後才能回覆 EMC Done。

## 10. 分層測試方法

| 層級 | 驗證目標 | 限制 |
|---|---|---|
| L1 Python參考模型 | FIFO、UnitID、麵篩、熟度、資源衝突 | 不執行真實 PLC 程式 |
| L2 Virtual Modbus PLC | HMI／IPC介面、位址、故障注入 | 不代表 AS200 邏輯 |
| L3 AS200 Simulator | 真正 PLC 程式、心跳、模式、EMC、流程 | 不驗證實體電氣與機構 |
| L4 周邊模擬 | IPC／UR／Nachi Seq與Response | Robot 動作是模擬回覆 |
| L5 實機／HIL | I/O極性、時序、機構、碰撞區、安全 | 必須受控、低速、逐級執行 |

現有測試程式涵蓋單碗完整流程、多訂單流水、FIFO復歸、1000筆耐久、HMI介面、HMI live monitor、通訊與故障情境。測試程式存在不等於最近一次測試結果必然通過；結論必須連同log、PLC版本與時間保存。

## 11. 必要安全規則

1. AI輸出的 PLC 程式不得直接下載到運轉設備。
2. 先編譯，再做 Simulator、周邊模擬、斷動力 I/O、低速單步及完整 FAT。
3. 急停、安全門及危險能量切斷依風險評估採硬體安全回路。
4. 不得用測試專用 D15010、Simulation Mode 或強制 X 方法繞過正式上機安全條件。
5. 所有未知的 I/O、通訊位址、Robot SDK 狀態或現場版本都必須標為待確認，不得臆測。

## 12. 版本與可信度

- `MVP_V2_101`：工作區最新 PLC 候選版，尚需實機核對。
- `MVP_V2_100`：既有驗收曾使用的版本。
- `3.HMI/0.0.3`：目前主要 HMI 版本。
- `0.Old` 與舊 IO Excel：只供歷史追溯，不能作現行位址真值。
- 現行真值應由 PLC export、HMI register map、IPC constants、Robot mapping、現場端子及核准電路圖共同對表。
