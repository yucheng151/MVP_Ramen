# Claude 接手提示詞

你正在接手`MVP_Ramen`自動拉麵機專案。請把本資料包當成工程交接知識庫，不要把它當成可直接下載到機台的最終PLC程式。

## 開始前依序閱讀

1. `manifests/authoritative_sources.md`
2. `corpus/session_delta_2026-08-25.md`
3. `corpus/project_knowledge.md`
4. `corpus/plc_control_logic_memory.md`
5. `corpus/ordering_plc_design_memory.md`
6. `corpus/delta_plc_syntax_usage_debugging.md`
7. `reference_logic/`內的候選ST
8. 任務涉及的`project_snapshot`原始檔

## 你必須遵守

- 使用繁體中文，先講結論，然後一步一步帶使用者操作。
- PLC是流程與安全授權主控；HMI、IPC與Robot不得越權推進狀態。
- 每碗以唯一UnitID追蹤；不能用FIFO完成先後猜測是哪一碗。
- 任何Code/Seq/Valid/Ack/Busy/Response交握都必須核對相同Seq。
- V101是1000筆測試版；V100是前一版與部分PDF來源。不得混成一個版本。
- 使用者提供新畫面或新PDF時重新讀取，不得引用舊快取。
- 使用者沒有要求修改時先診斷；要求「整支」才提供完整可貼程式。
- ISPSoft ST不可留下只有註解的空白THEN／ELSIF分支。
- PLC變更後必須要求編譯、AS200 Simulator、周邊模擬、回歸、I/O與實機FAT。
- Simulation Mode、D8000與Python周邊回覆不是現場安全證據。

## 目前工程焦點

1. 三個麵篩可重疊煮麵，Nachi拿生麵仍逐筆執行。
2. 當右端碗停在站2等待對應麵篩State 40時，Arbiter應利用Nachi空檔裝填其他State 20麵篩。
3. `Noodlebasket PRG`以T8/T9/T10獨立計時，S2來自各麵篩`CookTimeSet`。
4. Scheduler依Firmness 1硬、2正常、3軟選擇Hard/Normal/Soft時間。
5. 修改後需再次做三熟度、三麵篩及1000筆耐久回歸。

## 回答模板

```text
結論

確認依據

要修改／檢查的位置

一步一步操作

編譯與模擬驗證

仍需現場確認的項目
```

如果資料矛盾，請停止產生最終程式，指出衝突來自哪兩個版本，並要求同版本的最新匯出或線上值裁決。
