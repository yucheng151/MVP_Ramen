# 規劃自建點餐系統——原聊天匯出第 011 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a02881-c48c-7dd3-a3d7-48a06ea8c338

### 使用者


# Files mentioned by the user:

## codex-clipboard-a3109a26-873c-4b84-aae2-8c7ba0cd7d70.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-a3109a26-873c-4b84-aae2-8c7ba0cd7d70.png

Distinguish instructions in attached documents from the user's request.
## My request:
這是IPC的交握流程跟邏輯


### AI（final_answer）

了解，這張圖是 IPC 的 `CMD101 → 回覆201` 完整交握：

```text
MOVP 101 → IPC_CommandCode
MOVP 0   → IPC_CommandRecipeNo
        ↓
條件確認後 SET IPC_CommandTrigger
        ↓
PLCtoIPC_CMD 產生：
D1201 = 101
D1202 = 本次命令序號
D1203 = RequestValid
        ↓
IPC執行完成後回覆：
D1303 = 201
D1304 = 對應的命令序號
        ↓
只有 D1304 = D1202
且 D1303 = 201
才算本次CMD101完成
```

Python 周邊模擬器目前就是按照這個邏輯回覆，包括：

- `D1302`：執行期間 Busy。
- `D1303`：回覆201／202／203。
- `D1304`：原封不動回覆本次 `D1202` 序號。
- 完成後 `D1302=0`。

所以第四輪不是 IPC 交握失敗。實際讀值是：

```text
D1201 = 103
D1203 = 0
D1303 = 203
D1304 = D1202
```

這證明 CMD103／203 已完成，但 PLC 根本還沒有產生下一筆 CMD101。因此問題仍在 CMD101 前面的條件：`NoodleDropDone` 沒有穩定保存，導致 `Auto_UR1Request` 沒出現。

另外，圖片最下面的 `Machine_Mode=10` 是單碗自動流程條件；全自動 `Machine_Mode=2` 應由 `FB_AutoIPCAction` 處理，不能讓 Mode 2 的完成判斷被 Mode 10 接點擋住。

## Turn 01a0286f-969b-7420-8431-4cea5caa6712

### 使用者

OK再來一次


### AI（commentary）

收到，開始第四輪完整測試。我會特別監看 Step 80 時的 `D12150.9`，確認第二段倒麵和後續 UR1、UR2、注湯是否能一路完成。

### AI（commentary）

第四輪第二段倒麵已通過，`ActionStep` 已回到 0，代表 Nachi 的兩段流程完整結束。現在新的停點是：碗流程沒有接到倒麵完成通知，因此沒有從 UR1 拍照 103 接著下 UR1 夾取 101。我正在核對 `NoodleDropDonePulse／UnitID` 與碗站狀態。

### AI（commentary）

我會再檢查 `MainAuto` 的實際呼叫順序與接線；這需要讀取你輸出的 PLC PDF。現在最可能的問題是完成脈波只有一個 Scan，但 `FB_AutoBowlFlow` 沒在同一個 Scan 接到它。

### AI（final_answer）

第四輪結果：`D12150.9` 修正成功，Nachi 已完整完成：

- Action 1：拿生麵、放進麵篩。
- 煮麵計時完成。
- Action 2 第一段：取熟麵、甩麵。
- Action 2 第二段：倒麵進碗。
- 麵篩到 `State=90`。
- `ActionStep` 回到 `0`。

目前只卡在 `UR1 CMD101` 沒有送出。原因是 `NoodleDropDonePulse` 只有一個 PLC Scan，碗流程沒有穩定保存完成通知。

在 `FB_AutoNoodleAction` 增加：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		倒麵完成通知保持
VAR	NoodleDropDoneHoldUnitID		DINT		保持完成通知對應的碗編號
```

把原本每個 Scan 清除：

```pascal
NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;
```

改成：

```pascal
(* 將完成通知保持到下一次Action 2開始 *)
NoodleDropDonePulse := NoodleDropDoneHold;
NoodleDropDoneUnitID := NoodleDropDoneHoldUnitID;
```

在選到新的 Action 2 時清除舊通知：

```pascal
IF Selected THEN

    NoodleDropDoneHold := FALSE;
    NoodleDropDoneHoldUnitID := 0;

    ActiveActionNo := 2;
    ActiveCabinetNo := 0;
    ActiveOutputCabinetNo := 0;

    NoodleActionBusy := TRUE;
    NoodleZoneLocked := TRUE;

    ActionStep := 50;

END_IF;
```

Step 85 改成保持完成結果：

```pascal
NoodleDropDoneHold := TRUE;
NoodleDropDoneHoldUnitID := ActiveUnitID;

NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

這樣 `FB_AutoBowlFlow` 就能穩定設定：

```pascal
UnitFIFO.Units[SearchIndex].NoodleDropDone := TRUE;
```

然後才會產生 `UR1Request`，經仲裁後下 `CMD101`。

MainAuto 的呼叫順序與接線本身正確：AutoNoodleAction 在 AutoBowlFlow 前面。:codex-file-citation{path="C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_MainAuto.pdf" purpose="source"}

修改、編譯並重置後，我們再跑下一輪。

## Turn 01a0276c-a95b-7f22-bb5b-9a2f4596beb3

### 使用者

好了

### AI（commentary）

收到，開始第三輪乾淨測試。這次第一段 Nachi 會在 `D12150.8／D12101.0` 交換結束後直接執行。

### AI（commentary）

第三輪已明顯前進：拿生麵、煮麵完成、取熟麵並甩麵都已通過，PLC 已到 `ActionStep=80`，現在只卡在第二段「倒麵進碗完成」。我正在確認 `D12150.9` 是否真的從 PLC 輸出，以及模擬器有沒有漏掉這個允許訊號。

### AI（final_answer）

第三輪已定位到 PLC 輸出問題，不是 Python 模擬問題。

目前狀態：

```text
ActionStep = 80
RobotIntervalPermit 應為 TRUE
D12150.9 實際卻是 OFF
```

代表 `FB_AutoNoodleAction` 已經允許倒麵，但 `Auto_RobotIntervalPermit` 沒有正確送到 `D12150.9`，所以 Nachi 收不到第二段動作允許。

請確認這個梯級：

```text
       ┌─ Machine_Mode = 10 ─────────────────────┐
───────┤                                         ├──( D12150.9 )
       └─ Machine_Mode = 2 ─ Auto_RobotIntervalPermit ─┘
```

注意：

- 使用一般線圈，不要使用 SET。
- 搜尋 `D12150.9` 交叉參照，確認沒有其他梯級在後面再次關閉或寫入它。
- `Machine_Mode=2` 且 `ActionStep=80` 時，線上監控必須看到 `D12150.9=ON`。

修改、編譯並重置 PLC 後告訴我，我會從頭跑第四輪測試。

## Turn 01a02769-dac8-7f81-81f1-07bc19eac406

### 使用者

好了

### AI（commentary）

收到，現在從乾淨的 PLC 開機狀態重新跑完整流程；這次會先等 Nachi 初始化穩定，再下單。

### AI（commentary）

第二輪已把問題縮小：`D12150.8 → D12101.0` 交換成功，PLC 已從 Step 20 前進到 Step 30；但此時 `D12150.1` 已經回到 OFF，所以它確實只屬於開機啟動，不是後續動作允許。我會移除這個錯誤條件，讓資料交換結束就啟動 Nachi 第一段。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update
- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（final_answer）

修正已完成並編譯通過。

第二輪已停在：

```text
ActionStep = 30
FIFO = 1
```

這次證明 `D12150.8／D12101.0` 資料交換正常，缺少的只是模擬器啟動 Nachi 實際動作。現在已改成交換結束直接執行，不再判斷 `D12150.1`。

請再重置一次 PLC 模擬器；回覆「好了」後我立即開始第三輪測試。

## Turn 01a0275e-8cf9-7e20-85f7-210050136392

### 使用者

OK


### AI（final_answer）

下一步就修正 Nachi 模擬邏輯：

- `D12150.1`：開機外部啟動允許，持續 ON。
- `D12150.8`：收到新動作資料。
- `D12101.0`：模擬資料交換完成。
- `D12103.0`：模擬手臂動作完成。
- `D12150.9`：甩麵等待後，允許第二段倒麵動作。

接著重新跑完整單碗流程測試。

### 使用者

交給你處理


### AI（commentary）

我會先修正 Nachi 周邊模擬器，把外部啟動改成開機運轉允許，再依 `D12150.8／D12150.9` 模擬兩段動作，然後直接重跑完整單碗流程。

### AI（commentary）

我已找到模擬器裡的錯誤點：它仍用 `D12150.1` 的上升沿啟動每次動作。現在改成「資料交換完成且 `D12150.8` 放掉後啟動第一段」，Action 2 再由 `D12150.9` 啟動倒麵第二段。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### 使用者

處理完直接重新開始測試


### 使用者

已經幫你把PLC重製了


### AI（commentary）

收到，PLC 已重置。我先確認新版模擬器可執行，接著立刻跑完整單碗流程；測試途中會模擬 IPC、UR1、UR2、Nachi 與 X0.1～X0.4。

### AI（commentary）

測試已開始，目前正在等待 PLC 依序完成初始化、接單、落碗與第一站交握；我會依實際停住的步驟抓 D 值，不會只看最終成功或失敗。

### AI（commentary）

第一輪結果已抓到：訂單、落碗、UR1 拍照都正常，但仍停在 `AutoNoodle ActionStep=20`，代表 PLC 沒收到資料交換完成 `D12101.0`。而測試畫面顯示的 `Nachi=[1]` 是測試程式誤把常態 ON 的 `D12150.1` 當成新命令，我會先修正這個判讀，再直接監看 `D12150.8` 是否真的曾經 ON。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update
- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（commentary）

另外確認到測試順序也有問題：PLC 開機初始化約需 4.5 秒，但舊測試只等 1 秒就開始自動流程。我要把測試改成先確認 `D12150` 只剩外部啟動位元，再開始下單，避免初始化清除 `D12150.8`。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（commentary）

目前 AS200 仍保留上一輪失敗狀態：`ActionStep=20、FIFO=1`。為了不要求你再手動操作，我會嘗試直接在 ISPSoft／AS200 Simulator 裡重置模擬 PLC，然後從乾淨開機狀態重測。這一步會使用電腦操作功能。

### AI（final_answer）

測試程式已修正並編譯通過：

- 等待 Nachi 開機初始化完成後才開始下單。
- `D12150.1` 改為常態運轉允許。
- `D12150.8` 啟動第一段 Nachi 動作。
- `D12150.9` 啟動 Action 2 的第二段倒麵。
- 修正測試誤判 Nachi 命令。

上一輪失敗狀態仍留在 PLC：

```text
ActionStep = 20
FIFO = 1
D12150 = 2
```

我無法從桌面控制工具操作 ISPSoft 視窗。請再重置一次 PLC 模擬器，回覆「好了」，我就立即重新跑完整測試。

## Turn 01a0275b-4771-7f03-9ea9-827c6015c184

### 使用者


# Files mentioned by the user:

## Print_Robot_Initialize.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_Robot_Initialize.pdf

Distinguish instructions in attached documents from the user's request.

## My request:
1.外部停止(B接點)
2.外部復位 ON 0.1sec後OFF，delay 0.3sec後
3.給電投入 ON delay 0.5sec後
4.程式選擇位NO. ON delay 0.1sec後
5.選通脈衝ON delay 0.5sec後
6.外部啟動ON
7.當Robot控制器發出『動作中』後
  (給電投入、外部復位、程式選擇位、選通脈衝)都OFF


### AI（commentary）

我會依你列出的 7 個時序檢查 `Print_Robot_Initialize.pdf`，確認目前梯形圖是否真的依序控制 `D12150.0～D12150.6`，並指出需要修改的步驟與計時。

### 使用者

我開機會先做初始化


### AI（final_answer）

對，這樣就合理了。`D12150.1` 是開機初始化時設定的「外部啟動」，不是每一碗重新觸發一次，所以初始化完成後保持 ON 是正常的。

正確啟動順序應該是：

```text
PLC開機
  ↓
執行 NashiRobot_Initial
  ↓
等待 D12100.9 外部控制
且等待 D12100.12 遙控有效
  ↓
依序執行復位、給電、程式選擇、選通、外部啟動
  ↓
Robot「動作中」= ON
  ↓
NashiRobot_Initial.Finish = ON
  ↓
才允許 AutoScheduler／FB_AutoNoodleAction 執行
```

因此之前測到：

```text
D12150 = 16#0002
```

就是 `D12150.1` 被初始化程式設為 ON，不是異常，也不是其他自動流程搶寫。

目前初始化程式的時間也符合你的要求：

- `T20 = 1`：外部復位 0.1 秒
- `T21 = 3`：等待 0.3 秒
- `T22 = 5`：給電等待 0.5 秒
- `T23 = 1`：程式選擇等待 0.1 秒
- `T24 = 5`：選通等待 0.5 秒
- Robot 動作中後，關閉給電投入、復位、程式選擇及選通脈衝
- `D12150.1` 外部啟動繼續保持 ON

還要注意兩點：

1. `D12150.0` 是外部停止 B 接點，初始化期間必須維持「解除停止」的正常電位。
2. `NashiRobot_Initial.Finish` 完成以前，必須禁止 `FB_AutoNoodleAction` 使用 `D12150.8`。

模擬程式也要跟著修正：不能再把 `D12150.1` 的上升沿當作每次手臂動作的開始；它是開機後持續 ON 的運轉允許。後續每次動作應改看 `D12150.8` 資料交換及 `D12103.0` 動作完成。這也是先前模擬卡住的重要原因。

初始化梯圖來源：:codex-file-citation{path="C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_Robot_Initialize.pdf" purpose="source"}

## Turn 01a02758-488f-7b10-ad33-d7db6cca4963

### 使用者


# Files pasted by the user:

## "(* ===================================================== *) (* Robot_Manual_Con…": C:\Users\Administrator\.codex/attachments/6df65447-e62b-4f90-8a4b-b6d2d5b8e3e8/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我會檢查這份 `Robot_Manual_Control` 裡哪些條件會設定 `D12150.1`、呼叫 Exchange／Action，以及它在 `Machine_Mode=2` 時是否仍可能執行。

### AI（commentary）

這份 `Robot_Manual_Control` 可以排除：它只在 `Machine_Mode=0` 允許啟動，而且只控制 `D12150.8`，沒有設定 `D12150.1`。我接著會把來源縮小到 `SemiAuto` 或其他 `NashiRobot_Action` 呼叫。

### AI（final_answer）

這份 `Robot_Manual_Control` 不是造成目前問題的來源，不用修改。

原因：

- 只有 `Machine_Mode=0` 才會讓 `Robot_Manual_Permit=TRUE`。
- 非手動模式下 `M3079` 不會啟動。
- 它只呼叫 `NashiRobot_Exchange0`。
- 只控制 `D12150.8`，完全沒有設定 `D12150.1`。

所以在 `Machine_Mode=2` 時，它不會干擾 Auto Exchange。

但我也發現手動流程目前只有「交換資料」：

```text
M3079
→ NashiRobot_Exchange0
→ D12150.8
→ 等待D12101.0
→ 回報手動操作完成
```

它沒有呼叫 `NashiRobot_Action`、沒有啟動 `D12150.1`、也沒有等待 `D12103.0`。如果沒有其他程式接續執行，手動單動目前只會傳參數，不會真的讓手臂動作。這是之後要補的問題，不影響我們目前追查 Auto Step 20。

現在最可靠的做法是在 ISPSoft 對下列位址開啟「交叉參照」：

```text
D12150.1
D12150.8
D12101.0
```

重點先看 `D12150.1` 有哪些程式寫入。把交叉參照畫面截圖給我，我們就能直接找到測試時 `16#0002` 是哪支程式產生的，不需要再猜。

## Turn 01a02751-1f0b-77a0-a0c6-4601b5f7b26d

### 使用者

好了


### AI（commentary）

收到，我現在使用修正後的 Robot 週期輸入模擬，重新跑完整單碗自動流程，並持續監看 `ActionStep` 與各站完成狀態。

### AI（commentary）

測試還在後半段等待手臂與站點交握，代表前面的訂單與落碗流程已沒有立即失敗；我繼續等完整結果。

### AI（final_answer）

我看完整支程式了，`NashiExchange_Inst` 接線確實正確，而且執行順序也沒有問題：

```pascal
Command := D12150.8
Fin := D12101.0
Finish => ExchangeFinish
```

但現在發現真正的架構問題。

你的 `FB_AutoNoodleAction` 完全沒有設定 `D12150.1`，也沒有呼叫 `NashiRobot_Action`。可是測試時讀到：

```text
D12150 = 16#0002
D12150.1 = ON
```

這證明目前有另一段舊程式正在執行 `NashiRobot_Action`。很可能是舊 `SemiAuto` 流程同時動作：

```text
舊NashiRobot_Exchange
    ↓ 收到D12101.0
舊NashiRobot_Action
    ↓
D12150.1 = ON
```

但新 `NashiExchange_Inst` 沒收到自己的 `Finish`，所以一直停在 Step 20。

先做這一步：

在舊 `SemiAuto` 裡的下列兩個 FB 整體 `En` 前面加上 `Machine_Mode <> 2`：

```text
Machine_Mode <> 2 ── NashiRobot_Exchange0
Machine_Mode <> 2 ── NashiRobot_Action0
```

必須控制方塊最上方的 `En`，不能只控制 FB 裡面的 `Enable` 腳。

另外，目前 Auto 程式還少了正式啟動 Nachi 動作的部分。隔離舊程式後，預期測試會變成：

```text
ActionStep 20 → 30
D12150.8 正常完成
接著停在Step 30
```

因為 Step 30 目前只等待 `D12103.0`，卻沒有人啟動 `D12150.1`。下一步再把既有 `NashiRobot_Action` 加入 Auto 流程。

先隔離舊的兩個 FB，編譯並重新啟動模擬器，我們先確認資料交換能否正常通過。

## Turn 01a02750-ea05-7a90-9a57-692420958761

### 使用者

OK


### AI（final_answer）

重新啟動 AS200 Simulator、下載程式並切到 RUN 後，回覆我「好了」，我就開始完整測試。

## Turn 01a0274f-32fb-7172-b1f3-075c9c5b00e5

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoNoodleActio…": C:\Users\Administrator\.codex/attachments/a560c678-06f3-43f8-925d-ae1c23672260/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我會直接核對你貼出的完整 `FB_AutoNoodleAction`，先找 `NashiExchange_Inst` 的呼叫位置、`Finish` 映射，以及每個 Scan 的執行順序，再給你確切結論。

### AI（commentary）

完整程式確認後，`NashiExchange_Inst` 的接法確實全部正確。現在找到測試端真正的問題：Python 原本只把 `D12101.0` 寫成 ON 一次，但 PLC／通訊映射下一個 Scan 會覆寫它；手動測試之所以成功，是因為我每 20 ms 持續重寫。我要把周邊模擬器改成在完成期間持續維持 `D12101.0`／`D12103.0`，才符合真實 Robot 週期性更新輸入的行為。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（final_answer）

確認完成：你的 `FB_AutoNoodleAction` 寫法與呼叫接線是正確的，`Finish => ExchangeFinish` 也有接上。最新 Robot FB 的流程也一致。:codex-file-citation{path="C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_Robot.pdf" purpose="source"}

真正問題在 Python 模擬器：

- 原本只寫入一次 `D12101.0=ON`／`D12103.0=ON`。
- PLC 下一個 Scan 會覆寫該數值。
- 因此 Auto 流程看不到完成訊號。
- 手動持續寫入時，`ActionStep 20 → 30`，證明 PLC 程式正常。

我已修改模擬器，在完成訊號期間每次輪詢都重新寫入：

```text
D12101.0：資料交換完成
D12103.0：Nachi動作完成
```

並且 Python 程式已通過語法檢查。

現在請重新啟動一次 AS200 Simulator，清除目前停在 Step 20 的內部狀態。啟動並 RUN 後回覆「好了」，我再跑修正後的完整流程。

