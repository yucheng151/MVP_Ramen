# 規劃自建點餐系統——原聊天匯出第 008 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a02a7e-d877-7112-b90b-d1d28067d275

### 使用者

好了你測試下


### AI（commentary）

好，我先確認重置後狀態，再完整測到 CMD101、CMD102、注湯和 FIFO 完成。這次重點驗證剛修正的八條完成訊號接線。

## Turn 01a02a7b-625d-72a0-bda5-6420e3e52f58

### 使用者


# Files mentioned by the user:

## codex-clipboard-acf055ec-284b-4694-9e28-b2373db64bd1.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-acf055ec-284b-4694-9e28-b2373db64bd1.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

找到問題了：`FB_AutoBowlFlow` 下半部接線整組錯位。

前面到 `Auto_NoodleDropDoneUnitID` 都正確；從 `Auto_UR1VisionDonePulse` 開始接錯：

| FB 輸入腳位 | 應接變數 |
|---|---|
| `UR1DonePulse` | `Auto_UR1DonePulse` |
| `UR1DoneUnitID` | `Auto_UR1DoneUnitID` |
| `UR2DonePulse` | `Auto_UR2DonePulse` |
| `UR2DoneUnitID` | `Auto_UR2DoneUnitID` |
| `SoupDonePulse` | `Auto_SoupDonePulse` |
| `SoupDoneUnitID` | `Auto_SoupDoneUnitID` |
| `UR1VisionDonePulse`（最下面） | `Auto_UR1VisionDonePulse` |
| `UR1VisionDoneUnitID`（最下面） | `Auto_UR1VisionDoneUnitID` |

目前錯誤效果是：

- CMD103完成被當成 `UR1Done`
- 倒麵完成後 BowlState 直接變成25
- 因此跳過 CMD101，正好符合測試結果

不需要修改任何 FB 程式，只要重新接這八條線。完成、編譯並重置後，我再測一次。

## Turn 01a02a79-a9f4-7b70-8da9-8bde1cd34055

### 使用者


# Files mentioned by the user:

## codex-clipboard-e729a5bc-d0da-4512-85a4-dcea0907ed8f.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-e729a5bc-d0da-4512-85a4-dcea0907ed8f.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這張 `FB_AutoIPCAction` 的輸出接線是正確的：

```text
UR1VisionDonePulse  → Auto_UR1VisionDonePulse
UR1VisionDoneUnitID → Auto_UR1VisionDoneUnitID
```

現在要確認另一端。請截圖 `AutoBowlFlow_Inst` 左側輸入，確認有接：

```text
UR1VisionDonePulse  ← Auto_UR1VisionDonePulse
UR1VisionDoneUnitID ← Auto_UR1VisionDoneUnitID
```

如果 BowlFlow 這兩條也接好了，問題就在 `FB_AutoIPCAction` 內部收到 203 後沒有產生／保持完成通知，屆時再檢查該 FB 的目前程式。

## Turn 01a02a73-2ce2-79f1-a61d-f8266c4cab71

### 使用者

好了


### AI（commentary）

好，這輪會正確接受提前完成的 CMD103，並繼續檢查 CMD101、CMD102、X0.3、X0.4、注湯與 FIFO 清除。先確認重置狀態。

### AI（commentary）

測試已通過初始化、下單與前段流程，現在仍在等待後段 CMD101／CMD102 或站點完成，我會繼續等到它明確通過或指出缺少訊號。

### AI（commentary）

本輪結果已經可信：

- CMD103／203：通過
- Nachi Action1、Action2與倒麵：完成
- 卡在 CMD101 未產生

此時不是缺 IPC 回覆，因為 PLC 根本沒有送出 101。我讀取當下 BowlFlow 與完成 Hold，確認是「UR1VisionDone 沒寫回 UnitFIFO」還是「NoodleDropDone 後 BowlState 沒保持在20」。

### AI（final_answer）

目前缺少的是「CMD103完成結果回寫給 BowlFlow」這組內部訊號，不是外部感測器。

測試證據：

- IPC 已收到 `103`：`D1201=103`
- IPC 已回覆 `203`：`D1303=203`
- 命令與回覆序號都是 `1`
- 但 BowlFlow 沒收到 `UR1VisionDone`
- 因此 `UnitFIFO.UR1VisionDone` 沒變成 TRUE，PLC 不會產生 CMD101

請檢查 MainAuto 這兩組接線：

```text
FB_AutoIPCAction輸出
UR1VisionDonePulse  → Auto_UR1VisionDonePulse
UR1VisionDoneUnitID → Auto_UR1VisionDoneUnitID
```

再接入：

```text
FB_AutoBowlFlow輸入
UR1VisionDonePulse  ← Auto_UR1VisionDonePulse
UR1VisionDoneUnitID ← Auto_UR1VisionDoneUnitID
```

區域變數應為：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	Auto_UR1VisionDonePulse		BOOL		CMD103完成通知
VAR	Auto_UR1VisionDoneUnitID		DINT		CMD103完成對應的碗編號
```

若線已經接好，則要檢查 `FB_AutoIPCAction` 是否真的在收到 203 後保持這兩個輸出；目前測試看到它們沒有送達 BowlFlow。修正後重置，我再測 CMD101。

## Turn 01a02a6e-4b28-7e51-9e19-78506ac1a203

### 使用者

好了


### AI（commentary）

好，這次會等 Nachi 初始化交握真正完成後才下單。先確認狀態歸零，再直接跑完整流程。

### AI（commentary）

初始化時序修正有效：Nachi Action1、Action2 都已正常執行。現在唯一卡點是 UR1 預拍 CMD103 沒有產生；我讀取 BowlState、Request/Grant 與 IPC Hold，確認缺的是 BowlFlow 的哪個條件。

### AI（commentary）

現在 D 值證明 CMD103 其實已完成：

- `D1201=103`
- `D1202=1`
- `D1203 RequestValid=0`（任務已結束）
- `D1303=203`
- `D1304=1`

所以你沒有少給 CMD103／203。測試程式開始等待時，103 已經提早完成，因為拍照本來就允許在落碗與 Nachi 動作期間先做；我之前要求「等待期間必須親眼看到 RequestValid ON」反而漏掉這個合法的提早完成。

我會改成用「本輪新序號＋103/203相同序號」判定，仍可排除上一輪殘留，又不會漏掉預拍。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（final_answer）

這輪確認：你沒有少給 CMD103／203。

實際上 CMD103 已提早完成：

- `D1201=103`
- `D1202=1`
- `D1303=203`
- `D1304=1`

這符合你的設計：CMD103 可以趁輸送帶、落碗或 Nachi 動作期間預先拍照。

問題是測試程式開始監看時，103 已經完成，造成假判定失敗。我已改成用「本輪新序號，而且命令與回覆序號相同」判定。

目前訂單已執行到麵篩 State 90，請再重置一次 PLC 模擬器。完成後告訴我「好了」，下一輪應能繼續檢查 CMD101、CMD102、注湯及訂單完成。

## Turn 01a02a6b-66aa-7de0-88af-56739f81ca20

### 使用者

好了


### AI（commentary）

好，我先確認 FIFO、麵篩、站點及交握都歸零，接著直接跑修正後的完整流程。這輪若停住，我只回報 PLC 當下真正等待的訊號。

### AI（commentary）

狀態完全乾淨，現在開始完整測試：初始化、下單、落碗、Nachi Action1、煮麵、Action2兩階段、UR1拍照／執行、UR2、注湯及 FIFO 完成。

### AI（commentary）

乾淨重測仍停在同一點：落碗完成後，CMD103 與 Nachi 都沒有被允許。這表示不是周邊回覆缺少，而是 PLC 在它們之前沒有產生 Request／Grant。我讀取當下排程與站別，確認到底缺哪個前置條件。

### AI（commentary）

目前 PLC 明確停在 `FB_AutoNoodleAction Step20`：

- `NoodleBasket_1.State=30`
- Action1參數已寫入 `D12152～D12156`
- 但 `D12150.8=OFF`
- 所以 Nachi 不應回 `D12101.0`

換句話說，缺的不是你要另外給我的感測器，而是 PLC 本身應送出的「資料已準備」命令。我會在模擬器暫時把 `D12150.8` 寫成 ON；若一個 Scan 內又變 OFF，就能確定它仍被另一段 PLC 程式清除。

### AI（commentary）

強制寫入後 `D12150` 仍保持 `0x0102`，所以沒有其他程式清除它。真正原因找到了：完整測試在 Nachi 初始化的 ZRST 流程尚未完成前就下單，`NashiRobot_Exchange` 已進到等待回覆，但初始化隨後把 `.8` 清掉，造成 FB 卡在 Step20。

因此你沒有少給訊號；是測試程式太早下單。我會改成必須看到 Nachi 真正完成一次「外部啟動 → 動作中 → 回到 Standby/Home」才允許下訂單。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update
- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（final_answer）

你目前沒有少給任何外部訊號。

真正問題是測試程式太早下單：

1. `NashiRobot_Exchange` 先把 `D12150.8` 設為 ON。
2. Nachi 初始化的 `ZRST D12150.1～D12150.8` 尚未結束。
3. 初始化把 `.8` 清掉。
4. Exchange FB 已經進入等待 `D12101.0`，不會再次 SET `.8`，因此卡在 Step20。

我已修正測試程式：必須確認 Nachi 完整經過「外部啟動 → 動作中 → 回到 Standby/Home」，才會下訂單。

剛才為驗證曾強制寫入 `D12150.8`，請再重置一次 PLC 模擬器。完成後告訴我「好了」，我直接重新跑完整流程。

## Turn 01a02a66-3089-7d23-9f8a-c1da17426676

### 使用者

你在測試一次你跟我說我少給你什麼訊號


### AI（commentary）

好，我會從目前 PLC 狀態直接重測，並把卡住時「缺少的確切訊號、位址、當時應該是 ON 還是 OFF」列給你，不先要求改任何既有 FB。

### AI（commentary）

現在已讀到關鍵變化：`D12150=0x0102`，所以 `D12150.8` 已經成功 ON；原本的命令位衝突已排除。這筆流程目前停在 Action2 資料交換，缺的是 Nachi 回覆。我會啟動周邊模擬器接續這筆訂單，逐站確認下一個真正缺少的輸入。

### AI（commentary）

目前已定位到第一個缺少訊號：

- `D8008=60`
- 代表 Nachi Action2「拿熟麵並甩麵」已進入等待完成階段
- 此時 PLC 正在等 `D12103.0 = ON`

我會補送這個完成訊號，再看下一站需要哪個感測器；這樣能把整條流程需要的訊號逐一列完整。

### AI（commentary）

第一個 `D12103.0` 補上後，流程已從 Step60 進到 Step80，表示「甩麵完成」與放麵授權都正常。現在缺少第二次 `D12103.0`，也就是「熟麵已倒進碗」完成訊號。我補送第二次，再檢查 UR1／輸送帶接續。

### AI（commentary）

第二次 `D12103.0` 後，Nachi 已完成，麵篩 State＝90；接著 BowlFlow 沒有進 UR1，因為目前所有模擬站點輸入都是 OFF。下一個需要驗證的是 `X0.2=ON`（碗抵達放麵／UR1站）。我現在只打開模擬模式與 X0.2，再啟動 IPC 模擬回覆。

### AI（commentary）

剛才為了逐段補訊號，這筆訂單已不是乾淨的完整測試；另外我發現周邊模擬器在「中途重新啟動」時，會把仍為 ON 的 `D12150.1` 誤認成再次開機。這是測試程式問題，不是 PLC。我要先改成只接受 `D12150.1` 的上升沿，並把剛才開的 D8000 模擬輸入還原；之後重置一次就能得到可信的完整缺訊號清單。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（final_answer）

目前確認：

- `D12150.8` 已正常 ON，PLC 沒少這個訊號。
- 測試途中缺少的 `D12103.0`，是我的周邊模擬器中途啟動時誤判 Nachi 再次初始化，不是你的 PLC 少寫。
- 我已將模擬器改成只接受 `D12150.1` 上升沿。
- 暫時開啟的 `D8000` 已還原為 0。

目前這筆訂單已被逐段補訊號，不適合繼續當完整測試。請重置一次 PLC 模擬器，然後告訴我「好了」。下一輪我會從零完整跑完，卡住時直接報告確切缺少的訊號。

## Turn 01a02a63-359d-71a1-b16a-342ba4246491

### 使用者

不要改我原本寫好的FB


### AI（final_answer）

好，`NashiRobot_Exchange` 原本的 FB 完全不改。

目前較可能的問題是兩個 FB 實例同時連到 `D12150.8`：

- `Robot_Manual_Control` 的 `NashiRobot_Exchange0`
- `FB_AutoNoodleAction` 的 `NashiExchange_Inst`

先只改外部呼叫。在 `Robot_Manual_Control` 最下面，把原本 FB 呼叫包起來：

```pascal
IF Machine_Mode = 0 THEN

    NashiRobot_Exchange0(
        Enable := M3079,
        StandBy := D12100.0,
        Command := D12150.8,
        Fin := D12101.0,
        Parameter1 := Robot_Manual_ActionNo,
        Parameter2 := Robot_Manual_NoodleCabinetNo,
        Parameter3 := Robot_Manual_CutNo,
        Parameter4 := Robot_Manual_OutputCabinetNo,
        Parameter5 := Robot_Manual_NoodleTypeNo,
        Finish => Robot_Exchange_Finish,
        AlarmCode => Robot_Exchange_AlarmCode
    );

END_IF;
```

這樣自動模式 `Machine_Mode=2` 時，只有 `FB_AutoNoodleAction` 能操作 `D12150.8`。修改、編譯並重置模擬 PLC 後，我再直接讀 D 值重測。

## Turn 01a02a5a-0d89-7562-a76d-56c4317337ca

### 使用者

好了


### AI（commentary）

好，我先確認 FIFO 與三個麵篩都已歸零；乾淨的話就直接跑完整流程，不再新增殘留訂單。

### AI（commentary）

狀態已完全清乾淨：FIFO、三個麵篩、IPC 與 Nachi 都是 0。現在開始正式完整測試。

### AI（commentary）

乾淨重測後結果很明確：落碗完成，但排程器同時沒有允許 CMD103，也沒有允許 Nachi Action 1。這已不是殘留資料。我現在讀取落碗後的站別、麵篩 State、FIFO 與 Grant，找出是哪個前置條件沒有成立。

### AI（commentary）

目前卡點已縮小到 `FB_AutoNoodleAction ActionStep=20`：PLC 已選好麵篩1、Action1與參數，但 `NashiRobot_Exchange` 沒有把 `D12150.8` 打開，所以交換永遠不完成。我會用 PDF 檢查技能讀現有 `Print_Robot.pdf` 裡這個 FB 的實際啟動條件，確認缺的是 Enable 邊緣、StandBy 還是內部步驟。

### AI（commentary）

PDF 已確認 `NashiRobot_Exchange` 在內部 Step 2 應該會 SET `D12150.8`，並一直保持到 `D12101.0` 回覆；現在參數已寫入但命令位是 OFF，表示它被另一段程式清掉，或 Exchange 內部 Step 已異常跳走。為避免猜測，我會用 Windows 畫面檢查技能查看目前 ISPSoft 線上監控狀態，不修改你的程式。

### AI（commentary）

ISPSoft 目前沒有可讀取的視窗，所以我改用更直接的模擬診斷：在這筆已卡住的 Action1 上補送一次 `D12101.0`，再補 `D12103.0`。如果 ActionStep 能從 20 往下走，就證明 Auto 流程本身正常，唯一問題就是 `D12150.8` 被其他程式清掉。這只改 PLC 模擬器，不會碰機台。

### 使用者

你是可以直接讀取這些全部D值的


### AI（final_answer）

可以，我目前就是直接讀全部關鍵 D 值。現在讀到：

- `D8003=30`，補送完成訊號後變成 `60`
- `D8006=20`
- `D8008` 從 `20 → 30 → 55`
- `D12152=2`、`D12154=1`，Action2 參數已寫入
- 但 `D12150.8` 始終是 OFF

因此 Auto 流程有繼續走，真正缺少的是 `NashiRobot_Exchange` 的內部 `Exchange_Step`。它是 FB 區域變數，尚未映射到 D，所以目前無法從 Modbus 直接讀。

請新增：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	Auto_NashiExchangeStep	D8011	INT		全自動Nachi資料交換FB內部步驟
```

在 `NashiRobot_Exchange` 新增輸出：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_OUTPUT	DebugStep		INT		Nachi資料交換內部步驟
```

FB 最後增加一段無條件 MOV：

```text
MOV
S：Exchange_Step
D：DebugStep
```

`FB_AutoNoodleAction` 呼叫時接出來：

```pascal
NashiExchange_Inst(
    Enable := ExchangeEnable,
    StandBy := D12100.0,
    Command := D12150.8,
    Fin := D12101.0,

    Parameter1 := ActiveActionNo,
    Parameter2 := ActiveCabinetNo,
    Parameter3 := ActiveBasketNo,
    Parameter4 := ActiveOutputCabinetNo,
    Parameter5 := 1,

    Finish => ExchangeFinish,
    AlarmCode => ExchangeAlarmCode,
    DebugStep => DebugExchangeStep
);
```

最後把 `DebugExchangeStep` 接到 `Auto_NashiExchangeStep（D8011）`。完成後我就能直接讀 D8011，判斷是卡在 Step 2、Step 3，還是 `D12150.8` 被其他程式清除。現有 Exchange 梯圖依據：:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Robot.pdf" purpose="source"}

## Turn 01a02a52-9092-7252-9546-b0b17baea2e9

### 使用者

好了


### AI（commentary）

我現在重新跑完整流程，這次會特別確認CMD103完成保持、CMD101、CMD102，以及最後注湯與FIFO清除。

### AI（commentary）

前段已跑過，現在正在等完成通知被碗流程接收並解除Grant；如果這段正常，就會接著看到CMD101。

### AI（commentary）

這次發現測試工具本身抓到「上一輪殘留的203」，所以畫面顯示CMD103 PASS，但 `IPC=[]` 證明本輪根本沒有真正送出103。我要先修正測試判定：必須先看見本輪RequestValid與對應命令，之後才接受201／202／203，避免假通過。PLC先不用改。

### AI（commentary）

好，我先把 IPC 測試的「殘留 203 也算成功」問題修掉，接著直接重新跑完整流程；這次必須看到本輪 103／101／102 請求及相同序號的回覆才會判定通過。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（commentary）

測試判定已修正；目前只是 Windows 阻擋本機 Python 執行權限，我會用已允許的方式啟動同一支完整流程測試。

### AI（commentary）

這次不是 PLC 流程失敗，而是測試程式的「初始化完成條件」太死。現在讀到 `D12100=0x1207`，代表原點、外部控制、遠端等狀態已成立；`D12150=0` 是初始化輸出已關閉後的正常狀態。我要把判定改成看機器人回傳狀態，不再要求 D12150 必須保留啟動位。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（commentary）

現在測試已經排除「假 203」，真正卡點確認為：碗到 X0.1 後，本輪沒有送出 CMD103，而且 Nachi 卻執行了 Action 2。這通常表示上次中斷留下的麵篩／流程狀態沒有清乾淨。我先讀取目前 FIFO、三個麵篩、最右站與各 Grant，確認是殘留狀態還是排程條件漏接。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_state_dump.py：add

### AI（final_answer）

本次測試確認：

- Nachi 初始化：通過
- HMI 通訊、EMC、Auto 模式：通過
- 訂單進 FIFO：通過
- 落碗及 X0.1：通過
- 卡在 CMD103 前

目前 PLC 留有中斷狀態：

- FIFO＝1
- 麵篩1 State＝90
- UnitID＝27418526
- 上輪 IPC 回覆＝203
- `RequestValid＝0`

請再重置一次 PLC 模擬器，確定 `D8003～D8005＝0`、FIFO＝0，然後告訴我「好了」，我會立即從乾淨狀態重新跑完整流程。

