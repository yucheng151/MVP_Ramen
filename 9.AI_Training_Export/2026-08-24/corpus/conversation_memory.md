# 對話記憶匯出

匯出日期：2026-08-24  
範圍：本聊天串可見內容，以及本串中完成的專案唯讀盤點。  
用途：交給其他 AI 作為專案背景、使用者意圖、設計決策與後續工作脈絡。

## 1. 使用者長期目標

使用者希望建立一個能協助撰寫台達 PLC 程式的 AI，並希望先前教給 AI 的工程知識能移植給其他 AI。使用者要求方法具專業性、可跨平台使用，並希望把目前自動拉麵機的模擬測試方法發展成研究專題。

核心目標可整理為：

1. 將台達 PLC、HMI、IPC、Robot及測試 know-how 資料化。
2. 建立不依賴單一 AI 廠牌的知識包。
3. 讓 AI 產生的 PLC 成果可被編譯、模擬、故障注入及實機測試驗證。
4. 將自動拉麵機作為 PLC 多設備整合驗證的研究案例。
5. 未來可把同一套核心資料交給ChatGPT、Codex、Claude、Gemini或本機模型。

## 2. 對話歷程

### Turn 1：如何把教給目前AI的內容交給其他AI

使用者表示想製作「會寫台達 PLC 的 AI」，詢問如何把先前教過的內容交給其他AI。

形成的結論：

- 不能把聊天模型的隱藏記憶或權重直接搬走。
- 應將知識沉澱成平台中立資料包，而不是依賴單一聊天串。
- 建議資料包含規則、型號差異、Device Map、正確案例、錯誤案例、手冊來源及驗收測試。
- 對Codex可包成Skill；對其他平台可使用Project Knowledge、RAG、自訂提示或API檔案檢索。
- 維護一份核心知識，各平台只保留薄的提示詞／工具轉接層。

### Turn 2：其他AI是否也可以使用

使用者再次確認其他AI能否使用。

形成的結論：

- 可以，只要核心資料使用Markdown、PDF、CSV、JSON與程式範例等通用格式。
- 「給AI檢索參考」與「真正微調進模型」是不同路線。
- 優先建議RAG／知識庫，因為更新與稽核較容易。
- 真正微調前必須先建立高品質、經人工審查的範例與測試集。

### Turn 3：要求更專業的方法

使用者認為先前說明不夠專業。

形成的專業架構：

```text
自然語言需求
  -> 結構化工程規格
  -> 平台中立控制邏輯
  -> 台達機型／ISPSoft適配
  -> PLC程式生成
  -> 靜態檢查／編譯／模擬／測試
  -> 工程師審核
```

必要模組：工程規格層、台達PLC知識庫、受限制的中間格式、程式產生器、驗證系統、跨AI適配層、版本追蹤及安全責任邊界。

重要觀點：專業程度主要取決於驗證閉環，不是提示詞長度。

### Turn 4：要求理解整個專案後報告

使用者要求讀取專案並說明理解。

完成的唯讀盤點發現：

- 專案是一套PLC主控的自動拉麵設備，不是單一PLC程式。
- 整合台達AS200、Python HMI、手機點餐、輸送帶、現場I/O、Nachi Robot、IPC／Isaac Sim及雙UR5e。
- PLC負責流程、安全互鎖、排程與動作授權。
- HMI負責高階命令、訂單、庫存及顯示。
- IPC／Robot使用心跳與Seq/Ack/Busy/Response握手。
- 每碗以UnitID追蹤，支援不同熟度與非FIFO完成。
- HMI 0.0.3已有AUTO SYSTEM、FIFO、UnitID、麵櫃、三麵篩、四站及Mock／Simulator模式。
- IPC 0.0.2包含Isaac Sim、ROS 2、RTDE、視覺、雙UR5e與EMC恢復流程。
- Nachi資料為控制器專用程式及備份。
- 手機點餐0.0.1仍是前端原型，正式HMI訂單API尚待整合。

當時判斷PLC候選版已從舊文件記載的V2_034前進到V2_100；其後工作區又新增V2_101。因此版本結論應以最新盤點為準：V2_101是工作區最新候選，但仍須與現場實機核對。

### Turn 5：模擬測試是否能成為研究專題

使用者認為其模擬測試方法不錯，希望作為研究專題。

形成的研究定位：

> 基於數位分身與分層測試架構之PLC多設備自動化系統整合驗證——以自動拉麵機為例

英文候選題目：

> A Layered Simulation and Verification Framework for PLC-Based Multi-Device Automation Systems: A Case Study of an Automated Ramen Production System

研究核心不是「做出一台拉麵機」，而是提出一套可移植的PLC多設備整合驗證方法。

建議的分層：

1. L1 Python流程參考模型。
2. L2虛擬Modbus PLC。
3. L3真正AS200 Simulator。
4. L4 IPC／UR／Nachi周邊模擬。
5. L5實體設備／Hardware-in-the-loop。

建議研究問題：

- 分層模擬能否在實機整合前發現通訊與流程錯誤？
- UnitID加Seq握手能否降低錯配與重複執行？
- 故障注入能否提高斷線、超時、EMC及復歸流程的可驗證性？

建議量化指標：完成率、UnitID正確率、死鎖數、重複動作數、資源衝突數、故障偵測率、復歸成功率、實機占用時間、缺陷提前發現率及訂單延遲。

### Turn 6：要求匯出所有訓練資料

使用者要求匯出所有訓練資料。

執行決策：

- 新增 `9.AI_Training_Export/2026-08-24`。
- 產生專案知識基線、system prompt、需求schema、資料來源manifest、問答候選與評估資料位置。
- 不複製大型ISPSoft、Robot、電路圖等二進位原件，而由manifest指向來源。
- 清楚區分verified、candidate、planned與historical。

盤點時發現的新進展：

- 最新PLC目錄為MVP_V2_101。
- AUTO部分位址已配置，不再全部為None。
- 測試新增AS200單碗全流程、多訂單、多站流水線、FIFO復歸與1000筆耐久測試。

### Turn 7：要求把整個對話記憶包成檔案

使用者要求將整個對話的記憶也匯出。

本文件與 `datasets/conversation_memory.jsonl` 即為該要求的可攜版本。匯出只涵蓋本聊天串可見內容，不包含其他聊天、平台隱藏記憶、模型內部推理、系統提示或模型權重。

## 3. 已建立的共同工程原則

1. 核心知識必須平台中立。
2. AI回答需指出來源、版本與可信度。
3. 未知PLC位址或機型差異不得猜測。
4. 模擬測試不可被描述成實機安全驗證。
5. AI產生的PLC程式不得直接下載到運轉設備。
6. PLC是流程主控，HMI／IPC／Robot不得越權。
7. 多任務通訊必須核對Seq與UnitID。
8. 錯誤後不自動盲目重送，避免重複投料。
9. 軟體EMC不能取代硬體安全回路。
10. 研究成果應提供可重現輸入、預期、實際、log、版本及Pass／Fail規則。

## 4. 最新專案認知

- 最新可見PLC候選：`1.PLC/MVP_V2_101`。
- HMI主要版本：`3.HMI/0.0.3`。
- IPC主要整合版本：`6.IPC/0.0.2`。
- 手機點餐：`7.Ordering/0.0.1`。
- 測試：`8.TEST_Code`，已形成多層驗證工具鏈。
- 訓練資料匯出：`9.AI_Training_Export/2026-08-24`。

AUTO候選位址：D1020 UnitID、D1022麵櫃、D1023熟度、D1025 Valid、D1130 ACK UnitID、D1133 FIFO Count、D1135 Done UnitID、D1137 Done Index、D8102四站監看、D8114三麵篩監看。部分Unit狀態及庫存區仍待配置。

## 5. 尚未完成與下一步

1. 確認MVP_V2_101是否等同實機正式版。
2. 保存最新測試log與1000筆耐久結果，不只保存測試程式。
3. 完成AUTO所有未配置資料區與HMI正式同步。
4. 建立手機點餐到HMI的正式API。
5. 完成Nachi、雙UR5e、輸送帶與現場I/O的HIL／FAT。
6. 把測試案例轉成研究用可量化資料表與圖表。
7. 由工程師逐筆審核訓練問答，才能進入微調。

## 6. 給下一個AI的接手指示

先讀取本文件、`project_knowledge.md`、`source_manifest.csv`與現行原始碼。不要依賴舊版KNOWHOW的版本號做最終判斷。任何PLC邏輯修改前，先確認目標ISPSoft版本及工作區未提交變更；任何安全或實機操作都要提出分級驗證與回復方案。

## 7. 最高優先級專題記憶

使用者特別要求永久保存「自建點餐系統規劃及其PLC全自動控制設計」，並認為該PLC設計品質良好。下一個AI必須先讀取`ordering_plc_design_memory.md`，不得將它縮減為一般點餐網站。其核心是商業訂單拆成單碗UnitID、PLC FIFO與多資源排程、Order/Response/Completion Index、四站追蹤、Nachi與UR任務授權，以及由Python模型到AS200 Simulator與實機的分層驗證。

使用者進一步強調「PLC程式邏輯非常重要」。因此另建立`plc_control_logic_memory.md`，把PLC主控權、scan pulse、模式、收單、Unit生命週期、FIFO、三麵篩、四站、IPC/Nachi仲裁、碰撞區互斥、完成流水號、timeout、EMC與復歸條件列為不可任意簡化的核心記憶。

使用者要求同時保存PLC語法、使用方式及排查錯誤方法。因此另建立`delta_plc_syntax_usage_debugging.md`，涵蓋AS200／ISPSoft專案管理、ST基本語法、資料型別、Ladder/ST分工、編譯錯誤、線上狀態機、通訊、timeout、強制與模擬的診斷流程。

後續已透過Codex聊天串清單找到原始「規劃自建點餐系統」Thread `01a0128c-710d-7be2-9e8d-3e60d4f5b5d0`，並逐頁匯出41頁、403個turn、1313則使用者與AI可見訊息至`conversation_exports/ordering_system_thread/`。因此點餐及PLC記憶不再只依專案檔案重建，亦保存原聊天歷程。
