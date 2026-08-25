# 規劃自建點餐系統——原聊天匯出第 019 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a0191c-1cc5-7301-88e6-fb723455cced

### 使用者

好了


### AI（final_answer）

接著把 `FB_AutoIPCAction` 放進 `MainAuto`，排列在：

```text
FB_AutoScheduler
→ FB_AutoBowlFlow
→ FB_ActionArbiter
→ FB_AutoNoodleAction
→ FB_AutoIPCAction
```

並使用 `Machine_Mode = 2` 啟用。先完成FB接線，再編譯確認。

## Turn 01a01918-8fb4-7b01-b6df-cba76be4bcca

### 使用者


# Files mentioned by the user:

## codex-clipboard-c60a5d18-ee88-44a4-bd9b-27e63580b56d.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-c60a5d18-ee88-44a4-bd9b-27e63580b56d.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

錯誤是因為 `ActiveCommandCode` 為 `WORD`，這版 ISPSoft 不接受它作為 `CASE` 判斷值。畫面中的兩個 `CASE ActiveCommandCode OF` 都改成 `IF／ELSIF`，`ActiveCommandCode` 保持 `WORD` 不用改。

第一處改成：

```pascal
IF ActiveCommandCode = 103 THEN

    UR1VisionDonePulse := TRUE;
    UR1VisionDoneUnitID := ActiveUnitID;
    UR1Active := FALSE;
    UR1CommandNo := 0;

ELSIF ActiveCommandCode = 101 THEN

    UR1DonePulse := TRUE;
    UR1DoneUnitID := ActiveUnitID;
    UR1Active := FALSE;
    UR1CommandNo := 0;

ELSIF ActiveCommandCode = 102 THEN

    UR2DonePulse := TRUE;
    UR2DoneUnitID := ActiveUnitID;
    UR2Active := FALSE;

END_IF;
```

第二處也使用相同內容：

```pascal
IF ActiveCommandCode = 103 THEN

    UR1VisionDonePulse := TRUE;
    UR1VisionDoneUnitID := ActiveUnitID;
    UR1Active := FALSE;
    UR1CommandNo := 0;

ELSIF ActiveCommandCode = 101 THEN

    UR1DonePulse := TRUE;
    UR1DoneUnitID := ActiveUnitID;
    UR1Active := FALSE;
    UR1CommandNo := 0;

ELSIF ActiveCommandCode = 102 THEN

    UR2DonePulse := TRUE;
    UR2DoneUnitID := ActiveUnitID;
    UR2Active := FALSE;

END_IF;
```

把原本從：

```pascal
CASE ActiveCommandCode OF
```

到：

```pascal
END_CASE;
```

整段完整替換掉，兩個6008錯誤就會消失。

## Turn 01a01917-d6ba-7ef3-86f4-cc8d17b55bac

### 使用者

        IF (IPCRequestValid = 0)
           AND (IPCBusy = 0) 
           AND NOT IPCFirstMaterialPending THEN

            (* Trigger只保持一個PLC Scan *)
            IPCCommandTrigger := TRUE;

            ActionStep := 15;

        END_IF;



### AI（final_answer）

這段正確，前提是：

```text
IPCRequestValid          WORD
IPCBusy                  WORD
IPCFirstMaterialPending  BOOL
```

因此判斷方式就是：

```pascal
IF (IPCRequestValid = 0)
   AND (IPCBusy = 0)
   AND NOT IPCFirstMaterialPending THEN

    (* Trigger只保持一個PLC Scan *)
    IPCCommandTrigger := TRUE;

    ActionStep := 15;

END_IF;
```

它表示：

```text
D1203 = 0：PLC目前沒有尚未完成的IPC請求
D1302 = 0：IPC目前沒有執行任務
IPCFirstMaterialPending = FALSE：沒有舊版103接101的待執行狀態
```

三個條件都成立才發出新指令。這段不用再改。

## Turn 01a01911-b69d-7720-b813-cc3c4a6a7205

### 使用者

PLCtoIPC_RequestValid IPCtoPLC_Busy怎麼處理


### AI（final_answer）

這兩個都由現有通訊程式管理，`FB_AutoIPCAction` 只讀取狀態，不可以寫入。

### 變數型別

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	IPCRequestValid		WORD		PLC指令請求狀態，接PLCtoIPC_RequestValid
VAR_INPUT	IPCBusy		WORD		IPC執行狀態，接IPCtoPLC_Busy
```

MainAuto直接接線：

```text
IPCRequestValid → PLCtoIPC_RequestValid
IPCBusy         → IPCtoPLC_Busy
```

判斷方式：

```pascal
(* 通訊通道閒置，可以準備新指令 *)
IF (IPCRequestValid = 0)
   AND (IPCBusy = 0)
   AND NOT IPCFirstMaterialPending THEN
```

```pascal
(* 再次確認通道閒置，發出一個Scan的Trigger *)
IF (IPCRequestValid = 0)
   AND (IPCBusy = 0) THEN

    IPCCommandTrigger := TRUE;
    ActionStep := 15;

END_IF;
```

```pascal
(* PLCtoIPC_CMD已經建立請求，或IPC已開始執行 *)
IF (IPCRequestValid <> 0)
   OR (IPCBusy <> 0) THEN

    ActionStep := 20;

ELSIF IPCCommandDone THEN
    (* 指令很快完成時直接處理完成 *)
END_IF;
```

分工如下：

```text
FB_AutoIPCAction
→ 只輸出一次IPCCommandTrigger
→ 不直接控制PLCtoIPC_RequestValid

PLCtoIPC_CMD
→ 收到Trigger
→ 寫入Command、Seq
→ 將PLCtoIPC_RequestValid設為1
→ 等待Ack及完成回覆
→ 完成後將PLCtoIPC_RequestValid清為0

IPC程式
→ 接到指令後將IPCtoPLC_Busy寫成1
→ 動作完成後將IPCtoPLC_Busy寫成0
→ 回覆201、202或203
```

所以這兩個變數都不需要另外建立，直接使用既有全域變數：

```text
PLCtoIPC_RequestValid：既有D1203 WORD
IPCtoPLC_Busy：既有D1302 WORD
```

## Turn 01a01911-008b-7722-b049-4e8abc923422

### 使用者

不管反正照我說的


### AI（final_answer）

好，完全照你的定義：

```text
203 = UR1拍照完成
201 = UR1動作結束，判定UR1沒在動
202 = UR2動作結束，判定UR2沒在動
```

PLC收到對應回覆後：

```text
203 → Auto_UR1Active := FALSE
201 → Auto_UR1Active := FALSE
202 → Auto_UR2Active := FALSE
```

不再另外判斷IPC內部流程或回Home狀態。現有 `FB_AutoIPCAction` 架構照舊，接著放進 `MainAuto` 接線即可。

## Turn 01a0190e-9d48-7a03-9bdf-897c092cc981

### 使用者

"C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\6.IPC\0.0.2"這是縣版本的程式


### AI（commentary）

我接著檢查 `0.0.2` 的 CMD103／203、101／102、Seq握手、Busy與EMC，並比對目前PLC端的 `FB_AutoIPCAction` 是否能直接配合。

### AI（commentary）

目前已確認新版確實加入103／203；我再核對「回覆201、202時手臂是否真的已停止」這一點，因為PLC目前把201／202當作UR已經不再動作的依據。

### AI（final_answer）

我確認完 `6.IPC\0.0.2`，它就是包含103的新版本，通訊點位與目前PLC架構相容。

目前指令定義：

```text
CMD 103 → 左UR預先拍照 → 回覆203
CMD 101 → 左UR放蛋、筍乾、木耳 → 回覆201
CMD 102 → 右UR放芝麻、蔥 → 回覆202
錯誤                         → 回覆901
```

通訊點位仍是：

```text
D1201  Command Code
D1202  Request Seq
D1203  Request Valid（WORD，使用bit 0）
D1204  Recipe No
D1207  EMC Request

D1301  Ack Seq
D1302  Busy（WORD，寫入0或1）
D1303  Response Code
D1304  Response Seq
D1305  Error Code
D1307  Current Task
D1308  EMC Done
```

因此我們剛修改的FB型別正確：

```text
IPCRequestValid : WORD
IPCBusy         : WORD
```

103與101確實是分開下達，不要使用 `IPCPreCaptureThenFirst` 自動串接：

```text
103 → 等203 → 碗到站且條件允許 → 101 → 等201
```

但我發現一個必須處理的安全問題：

- 目前201是在「木耳開爪」時回覆，不是左UR完全停止或回Home。
- 目前202是在「蔥完成P9.5」時回覆，也不一定代表右UR完全停止或回Home。
- PLC目前收到201／202後會將 `Auto_UR1Active`／`Auto_UR2Active` 清除，並認為手臂不再移動。

相關判斷位於 [isaac_dual_food_ur5e_2bowls1.py](C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/6.IPC/0.0.2/isaac_dual_food_ur5e_2bowls1.py:368)，實際完成標記則在同一檔案的 [左UR木耳開爪](C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/6.IPC/0.0.2/isaac_dual_food_ur5e_2bowls1.py:2513) 與 [右UR蔥P9.5](C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/6.IPC/0.0.2/isaac_dual_food_ur5e_2bowls1.py:6215)。

所以現在不能直接把201、202解釋為「UR已停止」。後續要把IPC改為：

```text
101放料完成
→ 左UR回到安全位置並確認停止
→ 才回覆201

102放料完成
→ 右UR回到安全位置並確認停止
→ 才回覆202
```

203在拍照完成後停在等待位置是合理的，只要該等待位置確認不會進入Nachi或輸送帶的碰撞區。除此之外，Seq、Busy、RequestValid、103／203和EMC握手都能配合目前PLC。

## Turn 01a01907-05b8-7240-8573-fd5ad2a9e29d

### 使用者

"C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\6.IPC\0.0.1"你先確認程式這是不含103的舊版


### AI（commentary）

我先檢查這個舊版 IPC 的指令接收、Busy／RequestValid 型別與 101、102 完成回覆方式；只讀取確認，不會修改程式。

### AI（final_answer）

我確認過 `6.IPC\0.0.1`，目前通訊規格如下：

- `D1203 PLCtoIPC_RequestValid`：實體是 16-bit 暫存器，所以 PLC 使用 `WORD` 正確；IPC只讀取 bit 0。
- `D1302 IPCtoPLC_Busy`：IPC寫入 `0/1` 的16-bit暫存器，所以 PLC 使用 `WORD` 正確。
- 目前只接受 CMD `101`、`102`。
- CMD101完成回覆 `201`。
- CMD102完成回覆 `202`。
- 不支援CMD103，收到103會回覆：

```text
ResponseCode = 901
ErrorCode = 1001
```

目前的 Seq 握手機制也適合我們的 `FB_AutoIPCAction`：

```text
PLC發出指令及Seq
→ IPC回覆AckSeq
→ IPC Busy = 1
→ 動作完成
→ IPC Busy = 0
→ 回覆201或202及相同ResponseSeq
→ PLCtoIPC_CMD產生IPC_CommandDone
→ FB_AutoIPCAction依ActiveCommandCode產生對應完成脈波
```

`UnitID` 不需要傳給IPC。PLC內的 `FB_AutoIPCAction` 會記住本次 `ActiveUnitID`，完成後再把它送回 `FB_AutoBowlFlow`，這個架構沒問題。

但有三件事要注意：

1. `IPCRequestValid` 和 `IPCBusy` 在FB中都要使用 `WORD`，以 `= 0`、`<> 0` 判斷。
2. 正式執行只需啟動 `ipc_controller.py`；它已經包含心跳、任務和EMC。不要同時再啟動 `ipc_heartbeat.py`、`ipc_emc.py`。
3. 現在手臂控制仍是預留介面：非模擬模式會直接回覆失敗，還沒有真正呼叫UR SDK。

所以目前可以先完成PLC端101、102流程；之後IPC加入103時，需要新增：

```python
CMD_VISION = 103
RESP_VISION_DONE = 203
```

並把103加入允許指令及完成回覆判斷。現在先不用修改這個舊版。

## Turn 01a01905-c4d3-71d2-9306-84b48447bb82

### 使用者

PLCtoIPC_RequestValid也是


### AI（final_answer）

`IPCRequestValid` 也改成 `WORD`。

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	IPCRequestValid		WORD		PLC對IPC指令請求狀態，0代表無請求，非0代表已有請求
VAR_INPUT	IPCBusy		WORD		IPC執行狀態，0代表閒置，非0代表忙碌
```

程式判斷統一改成：

```pascal
(* 通訊通道完全閒置 *)
IF (IPCRequestValid = 0)
   AND (IPCBusy = 0)
   AND NOT IPCFirstMaterialPending THEN
```

```pascal
(* 發出新指令前再次確認 *)
IF (IPCRequestValid = 0)
   AND (IPCBusy = 0) THEN

    IPCCommandTrigger := TRUE;
    ActionStep := 15;

END_IF;
```

```pascal
(* IPC已接收到指令 *)
IF (IPCRequestValid <> 0)
   OR (IPCBusy <> 0) THEN

    ActionStep := 20;

ELSIF IPCCommandDone THEN
    (* 指令在很短時間內完成 *)
END_IF;
```

也就是不能再寫：

```pascal
NOT IPCRequestValid
NOT IPCBusy
IPCRequestValid OR IPCBusy
```

因為這兩個變數都是 `WORD`，必須用 `= 0` 或 `<> 0` 判斷。

## Turn 01a01905-699c-7072-a894-efe8ffbb818c

### 使用者

IPCtoPLC_Busy 是word


### AI（final_answer）

那 `FB_AutoIPCAction` 的 `IPCBusy` 要改成 `WORD`，不能用 `BOOL`。

變數定義改成：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	IPCBusy		WORD		IPC執行狀態，0代表閒置，非0代表忙碌
```

程式裡所有 `IPCBusy` 判斷改成明確比較：

```pascal
(* IPC閒置 *)
IPCBusy = 0
```

```pascal
(* IPC忙碌 *)
IPCBusy <> 0
```

例如待機選擇指令：

```pascal
IF NOT IPCRequestValid
   AND (IPCBusy = 0)
   AND NOT IPCFirstMaterialPending THEN
```

發出指令前再次確認：

```pascal
IF NOT IPCRequestValid
   AND (IPCBusy = 0) THEN

    IPCCommandTrigger := TRUE;
    ActionStep := 15;

END_IF;
```

等待 IPC 接收到指令：

```pascal
IF IPCRequestValid
   OR (IPCBusy <> 0) THEN

    ActionStep := 20;

ELSIF IPCCommandDone THEN
    (* 處理快速完成 *)
END_IF;
```

MainAuto 接線仍然是：

```text
IPCBusy → IPCtoPLC_Busy
```

其他接線不變。

## Turn 01a018fe-e5be-7722-94c5-9911ac0c2fa0

### 使用者

OK


### AI（final_answer）

先在 `MainAuto` 區域變數加入：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	AutoIPCAction_Inst		FB_AutoIPCAction		全自動IPC／UR指令執行實例
VAR	Auto_IPCError		BOOL		全自動IPC指令錯誤
VAR	Auto_IPCErrorCode		INT		全自動IPC指令錯誤代碼
```

然後在 `FB_AutoNoodleAction` 後方新增一個段落，條件仍使用：

```text
Machine_Mode = 2
```

`FB_AutoIPCAction` 接線如下：

```text
UR1VisionGrant              Auto_UR1VisionGrant
UR1VisionGrantUnitID        Auto_UR1VisionGrantUnitID

UR1Grant                    Auto_UR1Grant
UR1GrantUnitID              Auto_UR1GrantUnitID

UR2Grant                    Auto_UR2Grant
UR2GrantUnitID              Auto_UR2GrantUnitID

IPCRequestValid             PLCtoIPC_RequestValid
IPCBusy                     IPCtoPLC_Busy
IPCFirstMaterialPending     IPC_FirstMaterialPending
IPCCommandDone              IPC_CommandDone
IPCCommandError             IPC_CommandError
IPCCommandErrorCode         IPC_CommandErrorCode
ErrorReset                  ALM_Rst
```

輸出接線：

```text
IPCCommandTrigger           IPC_CommandTrigger
IPCCommandCode              IPC_CommandCode
IPCCommandRecipeNo          IPC_CommandRecipeNo
IPCPreCaptureThenFirst      IPC_PreCaptureThenFirst

UR1Active                   Auto_UR1Active
UR1CommandNo                Auto_UR1CommandNo
UR2Active                   Auto_UR2Active

UR1VisionDonePulse          Auto_UR1VisionDonePulse
UR1VisionDoneUnitID         Auto_UR1VisionDoneUnitID

UR1DonePulse                Auto_UR1DonePulse
UR1DoneUnitID               Auto_UR1DoneUnitID

UR2DonePulse                Auto_UR2DonePulse
UR2DoneUnitID               Auto_UR2DoneUnitID

AutoIPCError                Auto_IPCError
AutoIPCErrorCode            Auto_IPCErrorCode
```

完成後先編譯；若出現符號不存在或型別不符，把錯誤畫面貼給我。

