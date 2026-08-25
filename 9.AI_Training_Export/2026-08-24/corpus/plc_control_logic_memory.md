# MVP Ramen PLC控制邏輯核心記憶

記憶優先級：最高／不可任意簡化  
主要候選版本：`1.PLC/MVP_V2_101`  
驗證來源：PLC專案、`FB_AutoIPCAction.st`、HMI契約、AS200整合及壓力測試。

> 本文件保存PLC邏輯的設計意圖、不變條件與狀態轉移。精確rung、FB介面、tag型別及掃描順序仍以同版本ISPSoft專案編譯結果為準。AI不得用本文件取代原始PLC專案。

## 1. PLC的最高控制權

PLC是整機製程主控。HMI、手機、IPC、Nachi及UR只能提出請求或回報狀態，不能自行推進製程。PLC必須在每個動作前確認：

- Machine Mode正確。
- EMC與Alarm未成立。
- HMI／IPC／Robot通訊符合該動作需求。
- 感測器與站位條件成立。
- 目標資源未被其他Unit占用。
- Robot碰撞區授權不衝突。
- 本次命令Seq／Index是新值。

任何條件消失時，PLC應停止推進、進入timeout／alarm或保持可診斷狀態，不可用下一步掩蓋錯誤。

## 2. 掃描週期原則

單次完成訊號、Trigger及Done Pulse在每個scan開始時先清除，只在確定的狀態轉移scan置位。持續狀態使用Step、Active、Busy或Latched Alarm保存。禁止將單scan pulse當成跨設備唯一真值；跨Modbus設備必須搭配Seq／Index或保持資料。

## 3. 模式邏輯

- Manual：允許受互鎖保護的單體手動操作，不執行AUTO排程。
- Semi-Auto：依測試mask或指定步驟執行，仍受相同安全與資源互鎖。
- Auto：接受單碗Unit、執行FIFO、多麵篩與多站流水線。

模式切換由HMI命令請求、PLC確認後回覆；HMI畫面應以PLC回報D1109為真值。模式變更不得讓既有輸出或Robot任務失去歸屬。

## 4. 訂單收單狀態機

輸入：UnitID、Cabinet、Firmness、Order Index、Valid。

不變條件：

1. 只有Valid成立且Index為新值才評估訂單。
2. UnitID必須合法且不得與有效Unit重複。
3. Cabinet必須在1~10，Firmness必須在核准範圍。
4. FIFO有空間才可接受。
5. PLC必須先把完整資料複製進內部FIFO，再回ACK。
6. ACK UnitID與ACK Index必須對應同一筆輸入。
7. Valid保持期間不得重複入列。
8. 拒絕時回明確Response，不得靜默吃單。

HMI清除Valid或送出新Index後，PLC才能接受下一筆。PLC/HMI重啟後的Index初始化必須避開殘留ACK，避免第一筆訂單被誤判舊資料。

## 5. Unit資料與生命週期

每個Unit至少保存：

- UnitID。
- Cabinet No。
- Firmness／煮麵時間設定。
- FIFO／排程狀態。
- Basket No。
- Current Station。
- Robot／IPC子任務狀態。
- Error／Cancel／Complete狀態。

UnitID不可在站與站之間靠位置推算或重新產生。任何搬移都應以「來源位置持有該UnitID、目標位置空閒、搬移完成確認」為原子狀態轉移。

## 6. FIFO與流水線

FIFO決定等待分配的基本順序，但整體完成可以非FIFO。PLC可在資源允許下讓不同Unit同時處於：

- FIFO等待。
- 落碗至放麵／UR1之間。
- 放麵／UR1至UR2之間。
- UR2至注湯之間。
- 三個麵篩中的任一個。

FIFO pop只能在下游資源確定接受該Unit時發生。不得先移除FIFO，再等待不確定資源，否則斷電或alarm可能遺失Unit。

## 7. 三麵篩排程

每個麵篩獨立保存Idle／Cooking／Ready及UnitID、Cabinet、Firmness與時間。排程需滿足：

- 只把Unit分配給Idle麵篩。
- 熟度轉換成經核准的煮麵時間。
- 計時完成只令該Unit Ready，不直接假定輸送站可接收。
- 取出完成後才釋放麵篩。
- 三個麵篩不得同時持有相同UnitID。
- 麵篩Ready順序可與FIFO輸入順序不同。

## 8. 四站轉移

四站為落碗、放麵&UR1、UR2、注湯&完成。每站至少保存Idle／Waiting／Working／Complete／Error及UnitID。

轉移不變條件：

1. 上游站持有UnitID。
2. 下游站為空或已明確Grant。
3. 輸送帶、感測器及相關Robot互鎖成立。
4. 動作完成後先把UnitID交給下游，再清除上游。
5. timeout時保留Unit位置與診斷資料，不可假裝轉移完成。

為避免同一實體碗被兩站同時認領，UnitID交接必須有固定掃描順序或中間Transfer狀態。

## 9. IPC／UR仲裁

AUTO IPC執行器在通道完全Idle時才挑選Grant。既有優先順序：

1. UR2 CMD102。
2. UR1 CMD101。
3. UR1 Vision CMD103。

送出條件包括RequestValid=0、IPCBusy=0且沒有既有FirstMaterialPending。Trigger只保持一個scan，實際Seq、Ack、timeout與Response由既有PLCtoIPC命令FB管理。

狀態概念：

```text
Idle(0)
  -> 選擇Grant與鎖定ActiveCommand/ActiveUnitID
  -> WaitChannel(10)
  -> Triggered(15)
  -> WaitingCompletion(20)
  -> Done Pulse + 對應UnitID -> Idle
  -> ErrorHold(90) -> 人工ErrorReset -> Idle
```

CMD103完成後不得自動接續CMD101；必須重新經PLC排程與Grant，避免資源條件已變化。錯誤狀態不自動重送。

## 10. Nachi Robot邏輯邊界

PLC讀取D12100~D12104狀態，寫D12150~D12156命令。命令應包含新Index、Action及必要參數；Robot Read Complete／Action Complete必須與Index或目前任務一致。HMI對整個D12100~D12156區唯讀。

PLC不能因Robot Busy解除就假定Action成功，應區分接收完成、動作完成、Error、Alarm、Home與E-stop狀態。

## 11. 碰撞區與資源互斥

Nachi、UR1、UR2及輸送帶可能共享物理區域。任何Robot Active訊號都應由PLC資源Grant派生。至少需要滿足：

- 同一碰撞區同時只有一個獲准動作者。
- Busy或完成回覆遺失時不把Grant轉給另一Robot。
- EMC／Alarm後清除執行許可，但保留目前Unit與恢復資訊。
- Robot回Home不應被誤當製程動作完成；製程完成條件需獨立定義。

## 12. 完成回報

整碗完成時PLC更新Completed UnitID及Completion Index。Completion Index必須對每次完成單調前進並跨HMI輪詢保持，避免短pulse遺失。

禁止：

- 只用Done Pulse、不保存UnitID。
- 只改UnitID、不更新Completion Index。
- 同一Completion Index代表兩碗。
- HMI重連後再次處理同一Completion Index。

## 13. Alarm、Timeout與復歸

每個外部動作需要獨立timeout與錯誤碼。發生異常時：

1. 停止發出新的Grant。
2. 將輸出帶到經風險評估的安全狀態。
3. 保留Active UnitID、Step、Command、Seq及錯誤碼。
4. 等待硬體安全狀態及人工復歸。
5. 復歸時判斷實體工件位置，不直接從下一步續跑。

Robot命令timeout尤其不能自動重送，因實體動作可能已完成但Response遺失。

## 14. EMC邏輯

軟體EMC要求需傳到IPC／Robot並等待確認，但硬體急停與危險能量切斷由獨立安全回路負責。只有控制器確認安全停止後才能建立軟體EMC Done。EMC解除後也不能自動恢復運動，需重新確認模式、位置、Unit歸屬、Robot Home／恢復路徑及人工允許。

## 15. Simulation Mode隔離

Simulation Mode只允許AS200 Simulator測試。模擬X、周邊完成及測試D區不得進入FIELD正式運轉路徑。HMI FIELD版需鎖定模擬控制。正式版變更必須驗證Simulation bit無法繞過硬體EMC及安全條件。

## 16. AI修改PLC時不可破壞的條件

1. PLC主控權。
2. UnitID端到端一致性。
3. 新Index／Seq去重。
4. ACK在資料複製完成後才回覆。
5. FIFO pop與下游接受的原子性。
6. 每個資源只持有一個Unit；每個Unit只在合法位置。
7. Robot碰撞區互斥。
8. timeout後不盲目重送。
9. 完成回報同時包含UnitID及新Completion Index。
10. EMC／Alarm後不自動恢復危險動作。

## 17. 必須保留的驗證

- 收單去重、非法參數、FIFO滿、Index循環及重啟殘留測試。
- 單碗完整流程。
- 三種熟度與三麵篩非FIFO完成。
- 多Unit同時位於不同站的流水線壓力。
- IPC 101／102／103的Seq、timeout、錯誤及殘留Response。
- Nachi接收、完成、Alarm、Home與E-stop。
- 感測器卡住、輸送帶timeout、HMI／IPC斷線。
- 任一Step發生EMC及斷電後的Unit/FIFO復歸。
- 1000筆耐久測試的遺失、重複、錯配、死鎖與延遲統計。

## 18. 保存層級

PLC邏輯以三層共同保存：

1. `project_snapshot/1.PLC/MVP_V2_101`：原始ISPSoft候選專案，保留精確實作。
2. 本文件：保存人類可讀的設計意圖與不變條件。
3. `datasets/evaluation_cases.jsonl`與`8.TEST_Code`：保存可執行的行為規格。

三者缺一不可。原始專案避免邏輯失真，設計記憶避免後人不理解原因，測試避免修改後悄悄破壞行為。
