# MVP Ramen AI 訓練資料匯出包

匯出日期：2026-08-24  
資料範圍：目前工作區可讀取的 PLC、HMI、IPC、Robot、Ordering 與 Test 文件／程式，以及由其整理出的結構化知識。  
語言：繁體中文為主，程式識別字保留原文。

## 定位

本資料包是「平台中立的知識與評估資料」，可用於：

- ChatGPT、Codex、Claude、Gemini 或本機模型的知識庫／RAG。
- PLC 工程助理的 system prompt 與 few-shot 範例。
- 經人工審查後建立 supervised fine-tuning 資料。
- 比較不同 AI 對 PLC 架構、通訊、測試及安全規則的理解程度。

這不是模型權重，也不包含 OpenAI 或其他平台的內部提示。ISPSoft 專案、Robot 控制器備份、電路圖和圖片等原始二進位資產不重複複製；它們由 `manifests/source_manifest.csv` 指向原位置。

## 內容

| 路徑 | 用途 |
|---|---|
| `corpus/project_knowledge.md` | 專案架構、通訊規約、測試方法、現況與限制 |
| `corpus/conversation_memory.md` | 本聊天串可見內容所形成的完整可攜記憶 |
| `corpus/ordering_plc_design_memory.md` | 自建點餐、UnitID、FIFO與PLC全自動控制的最高優先級記憶 |
| `corpus/plc_control_logic_memory.md` | PLC狀態機、資源仲裁、不變條件、錯誤與復歸邏輯專卷 |
| `corpus/delta_plc_syntax_usage_debugging.md` | 台達AS200／ISPSoft語法、工程使用及錯誤排查專卷 |
| `conversation_exports/ordering_system_thread/` | 「規劃自建點餐系統」原聊天串，41頁、403 turns、1313則可見訊息 |
| `datasets/instruction_qa.jsonl` | 問答／指令微調候選資料 |
| `datasets/conversation_memory.jsonl` | 結構化對話事件與長期記憶候選 |
| `datasets/evaluation_cases.jsonl` | 可重複執行的模型評估案例 |
| `prompts/system_prompt.md` | 台達 PLC 工程助理基準提示詞 |
| `schemas/automation_request.schema.json` | 平台中立需求輸入格式 |
| `manifests/source_manifest.csv` | 原始資料來源、角色與可信度 |
| `project_snapshot/` | 整個MVP目前主要版本的可攜來源快照 |
| `manifests/project_file_manifest.csv` | 快照內每個檔案的大小、SHA-256與訓練用途 |
| `build_project_export.ps1` | 可重新建立來源快照與manifest的匯出腳本 |

## 建議使用順序

1. 先以 `project_knowledge.md` 建立 RAG，不急著微調。
2. 將 `system_prompt.md` 設為工程助理的高優先級指令。
3. 用 `evaluation_cases.jsonl` 測試模型；未達安全與正確性門檻不得生成上機版本。
4. 經人工逐筆審查後，才能把 `instruction_qa.jsonl` 用於微調。
5. PLC 輸出仍須經 ISPSoft 編譯、Simulator、I/O 測試及合格工程師審查。

## 重要版本狀態

- 工作區最新 PLC 目錄為 `1.PLC/MVP_V2_101`，但是否等同現場正式運轉版仍須實機比對。
- HMI 目前主要版本為 `3.HMI/0.0.3`。
- AUTO 通訊已部分配置：訂單 D1020 起、ACK D1130 起、完成 UnitID D1135、完成 Index D1137；部分狀態與庫存區仍未配置。
- 測試已涵蓋 Python 參考模型、虛擬 Modbus PLC、AS200 Simulator、單碗流程、多訂單壓力、FIFO 復歸及 1000 筆耐久測試程式。
- 模擬結果不等於實體機械、電氣及安全驗證通過。

## 資料治理

- `verified`：由現行程式或測試直接確認。
- `candidate`：工作區最新候選，但尚未與現場設備核對。
- `planned`：已有介面或設計，尚未完整配置。
- `historical`：只供追溯，不得作為現行控制依據。

任何模型輸出若無法指出資料狀態與來源，應視為不可直接採用。

## 對話記憶邊界

`conversation_memory` 只包含本聊天串中使用者可見的對話內容與由專案檔案驗證後形成的結論。不包含其他聊天串、平台隱藏記憶、模型權重、內部推理或系統／開發者提示。

## MVP專案快照範圍

快照包含目前主要版本：PLC `MVP_V2_101`、電路圖、HMI `0.0.3`、I/O、Nachi Robot、IPC `0.0.1/0.0.2`、Ordering `0.0.1`及全部測試程式。`0.Old`、其他PLC歷史版本、`tmp`、cache、log、Python bytecode及自動 `.~bak` 不複製進訓練快照；歷史內容仍留在原專案供追溯。

二進位及廠商格式檔案會保留在快照作工程參考，但manifest標記為 `reference_only`，不應直接餵給文字模型當訓練語料。
