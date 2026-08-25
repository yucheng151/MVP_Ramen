# 規劃自建點餐系統——原聊天匯出第 009 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a02a49-cb3f-7fc1-a8d2-ac6810551471

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoIPCAction 全…": C:\Users\Administrator\.codex/attachments/bca17d56-75e0-4a8e-a780-c2f9e2066081/pasted-text.txt

## My request:
給我整枝好了


### AI（commentary）

我會以你剛貼的最新版為底，整合三組完成通知保持、正確清除時機，以及先前修正的Step 15，直接給你可整支替換的版本。

### AI（final_answer）

先新增這6個FB區域變數：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	UR1VisionDoneHold		BOOL		保持CMD103拍照完成通知
VAR	UR1VisionDoneHoldUnitID		DINT		保持CMD103完成的碗編號
VAR	UR1DoneHold		BOOL		保持CMD101完成通知
VAR	UR1DoneHoldUnitID		DINT		保持CMD101完成的碗編號
VAR	UR2DoneHold		BOOL		保持CMD102完成通知
VAR	UR2DoneHoldUnitID		DINT		保持CMD102完成的碗編號
```

完整 `FB_AutoIPCAction`：

```pascal
(* =========================================================
   FB_AutoIPCAction
   全自動IPC指令執行器

   CMD103 → IPC回覆203 → UR1VisionDonePulse
   CMD101 → IPC回覆201 → UR1DonePulse
   CMD102 → IPC回覆202 → UR2DonePulse

   Seq、Ack、Timeout及ResponseCode
   由既有PRG_PLCtoIPC_CMD負責。

   完成通知採用保持方式：
   1. IPC任務完成時SET對應Hold
   2. AutoBowlFlow收到通知後會解除Grant
   3. 本FB確認Grant解除後才清除Hold
   4. 避免只維持一個PLC Scan而漏接
   ========================================================= *)


(* =========================================================
   1. 每個PLC Scan的共用處理
   ========================================================= *)

(* IPC命令Trigger只保持一個PLC Scan *)
IPCCommandTrigger := FALSE;


(* 將保持訊號輸出給AutoBowlFlow *)
UR1VisionDonePulse := UR1VisionDoneHold;
UR1VisionDoneUnitID := UR1VisionDoneHoldUnitID;

UR1DonePulse := UR1DoneHold;
UR1DoneUnitID := UR1DoneHoldUnitID;

UR2DonePulse := UR2DoneHold;
UR2DoneUnitID := UR2DoneHoldUnitID;


(* 全自動模式CMD103不直接接續CMD101。
   CMD101由AutoBowlFlow確認拍照完成及倒麵完成後要求。 *)
IPCPreCaptureThenFirst := FALSE;


(* 目前IPC配方固定使用0 *)
IPCCommandRecipeNo := 0;



(* =========================================================
   2. IPC全自動動作流程
   ========================================================= *)

CASE ActionStep OF


    0:
        (* -------------------------------------------------
           待機，等待ActionArbiter發出新的Grant
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        ActiveCommandCode := 0;
        ActiveUnitID := 0;

        AutoIPCError := FALSE;
        AutoIPCErrorCode := 0;


        (* 確認既有IPC通訊通道完全空閒 *)
        IF (IPCRequestValid = 0)
           AND (IPCBusy = 0)
           AND NOT IPCFirstMaterialPending THEN


            (* -----------------------------------------
               第一優先：UR2執行CMD102
               ----------------------------------------- *)

            IF UR2Grant
               AND (UR2GrantUnitID <> 0) THEN

                (* 清除上一筆CMD102完成通知 *)
                UR2DoneHold := FALSE;
                UR2DoneHoldUnitID := 0;

                UR2DonePulse := FALSE;
                UR2DoneUnitID := 0;


                ActiveCommandCode := 102;
                ActiveUnitID := UR2GrantUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;

                UR2Active := TRUE;

                ActionStep := 10;


            (* -----------------------------------------
               第二優先：UR1執行CMD101
               ----------------------------------------- *)

            ELSIF UR1Grant
                  AND (UR1GrantUnitID <> 0) THEN

                (* 清除上一筆CMD101完成通知 *)
                UR1DoneHold := FALSE;
                UR1DoneHoldUnitID := 0;

                UR1DonePulse := FALSE;
                UR1DoneUnitID := 0;


                ActiveCommandCode := 101;
                ActiveUnitID := UR1GrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 101;

                UR2Active := FALSE;

                ActionStep := 10;


            (* -----------------------------------------
               第三優先：UR1執行CMD103預先拍照
               ----------------------------------------- *)

            ELSIF UR1VisionGrant
                  AND (UR1VisionGrantUnitID <> 0) THEN

                (* 清除上一筆CMD103完成通知 *)
                UR1VisionDoneHold := FALSE;
                UR1VisionDoneHoldUnitID := 0;

                UR1VisionDonePulse := FALSE;
                UR1VisionDoneUnitID := 0;


                ActiveCommandCode := 103;
                ActiveUnitID := UR1VisionGrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 103;

                UR2Active := FALSE;

                ActionStep := 10;

            END_IF;

        END_IF;



    10:
        (* -------------------------------------------------
           再次確認IPC通訊通道空閒後送出Trigger
           ------------------------------------------------- *)

        IF (IPCRequestValid = 0)
           AND (IPCBusy = 0)
           AND NOT IPCFirstMaterialPending THEN

            (* Trigger只保持一個PLC Scan *)
            IPCCommandTrigger := TRUE;

            (* 等待PLCtoIPC_CMD接收本次任務 *)
            ActionStep := 15;

        END_IF;



    15:
        (* -------------------------------------------------
           等待PLCtoIPC_CMD正式接收本次任務

           這裡不能判斷IPCCommandDone，
           因為IPCCommandDone可能仍保持上一筆的TRUE。

           必須看到RequestValid或Busy啟動，
           才能確認本次任務已經開始。
           ------------------------------------------------- *)

        IF (IPCRequestValid <> 0)
           OR (IPCBusy <> 0) THEN

            ActionStep := 20;

        END_IF;



    20:
        (* -------------------------------------------------
           本次IPC任務已經開始
           等待PLCtoIPC_CMD回報完成或錯誤
           ------------------------------------------------- *)

        IF IPCCommandDone THEN


            (* -----------------------------------------
               CMD103預先拍照完成
               ----------------------------------------- *)

            IF ActiveCommandCode = 103 THEN

                (* 保存CMD103完成通知及對應UnitID *)
                UR1VisionDoneHold := TRUE;
                UR1VisionDoneHoldUnitID :=
                    ActiveUnitID;

                (* 同一個Scan立即輸出 *)
                UR1VisionDonePulse := TRUE;
                UR1VisionDoneUnitID :=
                    ActiveUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;


            (* -----------------------------------------
               CMD101前三料完成
               ----------------------------------------- *)

            ELSIF ActiveCommandCode = 101 THEN

                (* 保存CMD101完成通知及對應UnitID *)
                UR1DoneHold := TRUE;
                UR1DoneHoldUnitID :=
                    ActiveUnitID;

                (* 同一個Scan立即輸出 *)
                UR1DonePulse := TRUE;
                UR1DoneUnitID :=
                    ActiveUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;


            (* -----------------------------------------
               CMD102後三料完成
               ----------------------------------------- *)

            ELSIF ActiveCommandCode = 102 THEN

                (* 保存CMD102完成通知及對應UnitID *)
                UR2DoneHold := TRUE;
                UR2DoneHoldUnitID :=
                    ActiveUnitID;

                (* 同一個Scan立即輸出 *)
                UR2DonePulse := TRUE;
                UR2DoneUnitID :=
                    ActiveUnitID;

                UR2Active := FALSE;

            END_IF;


            (* IPC實際動作已完成 *)
            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;


            (* 不立即回到Step 0。
               先等待AutoBowlFlow解除對應Grant，
               避免同一筆Grant再次觸發相同IPC命令。 *)
            ActionStep := 30;


        ELSIF IPCCommandError THEN

            (* IPC任務執行失敗。
               停止自動重送，避免重複夾料或投料。 *)

            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            AutoIPCError := TRUE;
            AutoIPCErrorCode :=
                IPCCommandErrorCode;

            ActionStep := 90;

        END_IF;



    30:
        (* -------------------------------------------------
           完成通知保持階段

           等待AutoBowlFlow收到完成通知，
           並解除本次動作的Grant。

           Grant解除後才清除Hold並回到待機，
           避免重複送出同一個IPC命令。
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;


        (* CMD103完成通知已被接收 *)
        IF ActiveCommandCode = 103 THEN

            IF NOT UR1VisionGrant
               OR
               (UR1VisionGrantUnitID <>
                ActiveUnitID) THEN

                UR1VisionDoneHold := FALSE;
                UR1VisionDoneHoldUnitID := 0;

                UR1VisionDonePulse := FALSE;
                UR1VisionDoneUnitID := 0;

                ActiveCommandCode := 0;
                ActiveUnitID := 0;

                ActionStep := 0;

            END_IF;


        (* CMD101完成通知已被接收 *)
        ELSIF ActiveCommandCode = 101 THEN

            IF NOT UR1Grant
               OR
               (UR1GrantUnitID <>
                ActiveUnitID) THEN

                UR1DoneHold := FALSE;
                UR1DoneHoldUnitID := 0;

                UR1DonePulse := FALSE;
                UR1DoneUnitID := 0;

                ActiveCommandCode := 0;
                ActiveUnitID := 0;

                ActionStep := 0;

            END_IF;


        (* CMD102完成通知已被接收 *)
        ELSIF ActiveCommandCode = 102 THEN

            IF NOT UR2Grant
               OR
               (UR2GrantUnitID <>
                ActiveUnitID) THEN

                UR2DoneHold := FALSE;
                UR2DoneHoldUnitID := 0;

                UR2DonePulse := FALSE;
                UR2DoneUnitID := 0;

                ActiveCommandCode := 0;
                ActiveUnitID := 0;

                ActionStep := 0;

            END_IF;


        ELSE

            (* 不正確的命令狀態，安全回到待機 *)
            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;

        END_IF;



    90:
        (* -------------------------------------------------
           IPC錯誤保持

           必須收到ErrorReset才可以離開。
           不允許自動重送，避免重複執行動作。
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        AutoIPCError := TRUE;


        IF ErrorReset THEN

            AutoIPCError := FALSE;
            AutoIPCErrorCode := 0;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;


            (* 錯誤復歸時清除所有完成通知 *)
            UR1VisionDoneHold := FALSE;
            UR1VisionDoneHoldUnitID := 0;

            UR1DoneHold := FALSE;
            UR1DoneHoldUnitID := 0;

            UR2DoneHold := FALSE;
            UR2DoneHoldUnitID := 0;

            UR1VisionDonePulse := FALSE;
            UR1VisionDoneUnitID := 0;

            UR1DonePulse := FALSE;
            UR1DoneUnitID := 0;

            UR2DonePulse := FALSE;
            UR2DoneUnitID := 0;

            ActionStep := 0;

        END_IF;



ELSE

    (* -------------------------------------------------
       遇到未定義的ActionStep時安全回到待機
       ------------------------------------------------- *)

    IPCCommandTrigger := FALSE;

    UR1Active := FALSE;
    UR1CommandNo := 0;
    UR2Active := FALSE;

    ActiveCommandCode := 0;
    ActiveUnitID := 0;

    AutoIPCError := FALSE;
    AutoIPCErrorCode := 0;


    (* 清除所有完成通知 *)
    UR1VisionDoneHold := FALSE;
    UR1VisionDoneHoldUnitID := 0;

    UR1DoneHold := FALSE;
    UR1DoneHoldUnitID := 0;

    UR2DoneHold := FALSE;
    UR2DoneHoldUnitID := 0;

    UR1VisionDonePulse := FALSE;
    UR1VisionDoneUnitID := 0;

    UR1DonePulse := FALSE;
    UR1DoneUnitID := 0;

    UR2DonePulse := FALSE;
    UR2DoneUnitID := 0;

    ActionStep := 0;

END_CASE;



(* =========================================================
   3. 將目前命令資料輸出給PRG_PLCtoIPC_CMD
   ========================================================= *)

IPCCommandCode := ActiveCommandCode;
```

另外確認 `PRG_PLCtoIPC_CMD` 接受每一筆新任務時都有：

```pascal
IPC_CommandDone := FALSE;
```

否則上一筆保持的完成訊號會被下一筆任務誤判。

## Turn 01a02a45-8ddb-7e41-bace-90604a44232a

### 使用者

好了


### AI（commentary）

我現在以修正後的初始化等待條件重新測試；這次不會在Nachi初始化尚未完成時提早下單。

### AI（commentary）

初始化與前段流程已通過，現在正在等Nachi兩階段倒麵及CMD101完成；我會繼續看最後是否能進CMD102與注湯。

### AI（final_answer）

這次 `NoodleDropDoneHold` 已經生效：

```text
D8010 = 0x008C
```

其中：

- `D8010.2 = 1`：倒麵完成通知正在保持
- `D8010.7 = 1`：測試曾收到倒麵完成
- `D8010.6 = 0`：沒有收到CMD103拍照完成通知

因此目前卡住原因變成 `FB_AutoIPCAction` 的 `UR1VisionDonePulse` 也只維持一個Scan，`AutoBowlFlow` 沒有保存到，所以不會發CMD101。

建議一次把IPC三種完成通知都改成保持型。新增以下FB區域變數：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	UR1VisionDoneHold		BOOL		保持CMD103拍照完成通知
VAR	UR1VisionDoneHoldUnitID		DINT		保持CMD103完成的碗編號
VAR	UR1DoneHold		BOOL		保持CMD101完成通知
VAR	UR1DoneHoldUnitID		DINT		保持CMD101完成的碗編號
VAR	UR2DoneHold		BOOL		保持CMD102完成通知
VAR	UR2DoneHoldUnitID		DINT		保持CMD102完成的碗編號
```

把程式最上方的完成脈波清除改成：

```pascal
(* 完成通知保持到下一筆相同動作開始 *)
UR1VisionDonePulse := UR1VisionDoneHold;
UR1VisionDoneUnitID := UR1VisionDoneHoldUnitID;

UR1DonePulse := UR1DoneHold;
UR1DoneUnitID := UR1DoneHoldUnitID;

UR2DonePulse := UR2DoneHold;
UR2DoneUnitID := UR2DoneHoldUnitID;
```

選擇CMD102時先清除上一筆：

```pascal
UR2DoneHold := FALSE;
UR2DoneHoldUnitID := 0;
UR2DonePulse := FALSE;
UR2DoneUnitID := 0;
```

選擇CMD101時：

```pascal
UR1DoneHold := FALSE;
UR1DoneHoldUnitID := 0;
UR1DonePulse := FALSE;
UR1DoneUnitID := 0;
```

選擇CMD103時：

```pascal
UR1VisionDoneHold := FALSE;
UR1VisionDoneHoldUnitID := 0;
UR1VisionDonePulse := FALSE;
UR1VisionDoneUnitID := 0;
```

Step 20收到CMD103完成時改成：

```pascal
IF ActiveCommandCode = 103 THEN

    UR1VisionDoneHold := TRUE;
    UR1VisionDoneHoldUnitID := ActiveUnitID;

    UR1VisionDonePulse := TRUE;
    UR1VisionDoneUnitID := ActiveUnitID;

    UR1Active := FALSE;
    UR1CommandNo := 0;
```

CMD101完成：

```pascal
ELSIF ActiveCommandCode = 101 THEN

    UR1DoneHold := TRUE;
    UR1DoneHoldUnitID := ActiveUnitID;

    UR1DonePulse := TRUE;
    UR1DoneUnitID := ActiveUnitID;

    UR1Active := FALSE;
    UR1CommandNo := 0;
```

CMD102完成：

```pascal
ELSIF ActiveCommandCode = 102 THEN

    UR2DoneHold := TRUE;
    UR2DoneHoldUnitID := ActiveUnitID;

    UR2DonePulse := TRUE;
    UR2DoneUnitID := ActiveUnitID;

    UR2Active := FALSE;
```

開機初始化現在已確定正常完成，不是這次的阻塞原因。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Robot_Initialize.pdf" purpose="source"} :codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Initialize.pdf" purpose="source"}

修改後請全部編譯、下載並重置，再讓我測試。

## Turn 01a02a40-03fc-7571-b417-8deacd651a41

### 使用者

好了


### AI（commentary）

收到，我現在從乾淨狀態重新跑完整流程，會確認初始化、三種手臂交握、三個麵篩狀態、輸送帶四站與訂單FIFO是否一路完成。

### AI（commentary）

重置後仍停在同一點，表示不是殘留訂單。模擬器確實看到 `D12150.1`，但我模擬的「動作中」狀態位可能接錯。我要直接核對你的 `Robot_Initialize` 階梯圖實際使用哪一個 `D12100` bit；這一步會用PDF檢查方式讀初始化程式。

### AI（commentary）

已查到根因：初始化程式總時間約包含多段計時，測試程式先前只看到 `D12100` Ready 就太早開始下單；此時初始化還會清除 `D12150.8`，所以第一筆資料要求被蓋掉。我要把測試條件改成「`D12150.1`外部啟動已到位，而且Robot回到Ready」才開始訂單。你的PLC這部分不用改。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（final_answer）

根因確認了：測試程式太早開始下單，初始化流程尚在清除 `D12150.1～D12150.8`，導致第一筆Nachi資料要求被清掉。

我已改成必須同時符合才開始測試：

```text
D12150.1 = ON
D12100.0 StandBy = ON
D12100.2 Home = ON
```

這與你的初始化FB及呼叫方式一致。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Robot_Initialize.pdf" purpose="source"} :codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Initialize.pdf" purpose="source"}

剛才失敗的訂單仍留在PLC中，請再重置一次模擬PLC。完成後告訴我「好了」，我再完整測試。

## Turn 01a02a3a-923c-7481-9fb7-90283c112361

### 使用者

OK處理好了你試試看


### AI（commentary）

我現在重新跑完整流程，這次重點確認 `NoodleDropDoneHold` 能讓 `AutoBowlFlow` 接續發出CMD101，然後繼續測CMD102與注湯完成。

### AI（commentary）

這次倒麵保持邏輯還沒跑到；目前卡在開機初始化與第一筆Nachi交換重疊。`D12150=0x0002` 表示外部啟動仍保持，但模擬器沒有像真實Robot一樣回覆一次「動作中」，初始化可能尚未真正結束。我先補上開機外部啟動的Robot動作中回覆，再重跑，PLC程式先不用改。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（final_answer）

目前測到的新狀況是開機初始化尚未完成：

```text
D12150 = 0x0002
ActionStep = 20
Basket1.State = 30
```

代表PLC仍保持Nachi外部啟動，模擬Robot先前沒有回覆「動作中」。我已修正Python模擬器，現在會模擬：

```text
D12150.1外部啟動
→ D12100回覆動作中
→ 延遲
→ 回到Standby/Home
→ 初始化結束
```

但剛才中斷的訂單仍留在PLC裡。請再重置一次模擬PLC，完成後告訴我「好了」，我就立刻重跑完整測試。

## Turn 01a02a35-e31a-7141-8e65-16904e4502a4

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoNoodleActio…": C:\Users\Administrator\.codex/attachments/7a4b5d48-ee10-4d94-89e9-4bbc922ccbff/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我先核對你這份最新版 `FB_AutoNoodleAction`，尤其確認倒麵完成保持、UnitID，以及下一碗開始時清除的位置是否正確。

### AI（final_answer）

這份還是舊版，倒麵完成仍只保持一個PLC Scan，所以測試才收不到。請修改以下四個位置。

1. 新增FB區域變數

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

2. 程式最上方替換

把：

```pascal
(* 本FB產生的完成通知只保持一個PLC Scan *)
NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;
```

改成：

```pascal
(* 倒麵完成通知保持到下一個Action 2開始 *)
NoodleDropDonePulse := NoodleDropDoneHold;
NoodleDropDoneUnitID := NoodleDropDoneHoldUnitID;
```

3. 在選中新的Action 2時清除上一碗通知

放在：

```pascal
IF Selected THEN
```

下面：

```pascal
IF Selected THEN

    (* 新的甩麵任務開始，清除上一碗完成通知 *)
    NoodleDropDoneHold := FALSE;
    NoodleDropDoneHoldUnitID := 0;

    NoodleDropDonePulse := FALSE;
    NoodleDropDoneUnitID := 0;

    ActiveActionNo := 2;
    ActiveCabinetNo := 0;
    ActiveOutputCabinetNo := 0;

    NoodleActionBusy := TRUE;
    NoodleZoneLocked := TRUE;

    ActionStep := 50;

END_IF;
```

4. Step 85增加保持資料

把原本：

```pascal
NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

改成：

```pascal
(* 保存倒麵完成通知 *)
NoodleDropDoneHold := TRUE;
NoodleDropDoneHoldUnitID := ActiveUnitID;

(* 同時輸出給FB_AutoBowlFlow *)
NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

修改後效果：

```text
ActionStep 85完成
→ 保存UnitID
→ NoodleDropDonePulse持續ON
→ AutoBowlFlow一定能收到
→ 允許UR1 CMD101
→ 下一次Action 2開始時才清除
```

現在貼的這支程式還不能直接測；完成以上修改後需要「全部編譯、下載到模擬PLC、重置」。

## Turn 01a029e4-c640-7bd1-9709-f2a2119ace67

### 使用者

在測試一次


### AI（commentary）

我現在重新跑完整自動流程，會從初始化、落碗、CMD103、Nachi煮麵與甩麵，一路確認到CMD101、UR2及注湯。

### AI（commentary）

測試已啟動，目前正在等待各站的模擬完成回覆；我會看它實際停在哪一個狀態，不只看通訊是否成功。

### AI（commentary）

這次已經不是卡在 IPC CMD103；CMD103/203 已通過。現在卡在第二次 Nachi 資料交換：`FB_AutoNoodleAction ActionStep=55`，也就是「熟麵拿起來甩麵」送參數時，`ExchangeFinish` 一直沒有回來。我先檢查模擬器是否把連續兩次 `D12150.8` 資料要求當成同一次，避免誤判PLC程式。

### AI（commentary）

確認到這次是模擬器的交握時間問題：第二次資料交換時，模擬器只讓 `D12101.0` 短暫 ON，PLC 沒掃到，所以 `D12150.8` 一直保持。真實 Nachi 的資料完成應保持到 PLC 放掉資料要求；我會把模擬器改成這個交握方式，再重跑，這不會改你的 PLC 程式。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_peripheral_sim.py：update

### AI（commentary）

第二次重跑被測試程式自己的「初始化判定」擋住：上一次流程跑過後 `D12150` 已回到 `0`，但這不等於手臂未初始化；應改用 `D12100.0 StandBy + D12100.2 Home` 判斷可開始。這是重複測試條件問題，我會修正後再跑，不需要你重置PLC。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（commentary）

目前前段已在執行，這次我特別觀察第二次 Nachi 資料交換是否能完整完成，以及完成後 `NoodleDropDone` 是否真的讓CMD101獲准。

### AI（commentary）

現在可以確定不是 `D12101.0` 脈波太短；PLC仍停在交換FB內。我接著直接對照你現有的 `NashiRobot_Exchange` 階梯圖，確認它對 `Enable／StandBy／Fin` 的實際觸發條件，避免繼續猜測。這一步會使用PDF檢查方式讀你匯出的Robot程式。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（commentary）

我先不再塞新訂單，直接針對目前卡住的第二次交換啟動周邊模擬，觀察 `D12101.0` 是否真的寫入、PLC是否因此離開Step55。這樣能把問題縮小到交換FB或D位址更新。

### AI（final_answer）

測試結果：前段正常，問題仍在 `FB_AutoNoodleAction` 的倒麵完成通知。

已通過：

- HMI通訊、訂單進FIFO
- 落碗及X0.1
- UR1 CMD103／203
- Nachi拿生麵、煮麵、甩麵、倒麵
- `FB_AutoNoodleAction` 最後已回到 `ActionStep=0`

目前卡住：

```text
D8010 = 0x0008
```

只有 `IPC_CommandDone` ON，以下都沒有出現：

- `Auto_NoodleDropDonePulse`
- `Auto_NoodleDropDoneUnitID`
- 倒麵完成保持訊號

因此 `FB_AutoBowlFlow` 不知道麵已倒完，不會要求CMD101。

請確認 `FB_AutoNoodleAction` 的區域變數表確實有：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

不能只放在程式文字裡，也不要放成其他FB的區域變數。

並確認Step 85內有：

```pascal
NoodleDropDoneHold := TRUE;
NoodleDropDoneHoldUnitID := ActiveUnitID;

NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

程式最上方有：

```pascal
NoodleDropDonePulse := NoodleDropDoneHold;
NoodleDropDoneUnitID := NoodleDropDoneHoldUnitID;
```

我也對照了現有 `NashiRobot_Exchange`，資料交換會等待 `Fin` 並經過計時後完成，所以測試中短暫停在Step55是正常的，不是目前阻塞原因。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Robot.pdf" purpose="source"}

請加入這兩個區域變數後，全部編譯、下載到模擬PLC並重置，再告訴我「好了」，我會重新跑完整測試。

## Turn 01a028bc-e071-76c3-8890-081ede9dd89a

### 使用者

給我整支程式


### AI（final_answer）

以下是修正後完整的 `FB_AutoIPCAction`。已移除 Step 15 使用舊 `IPCCommandDone` 判斷完成的部分。

```pascal
(* =========================================================
   FB_AutoIPCAction
   全自動 IPC 指令執行器

   CMD103 → IPC回覆203 → UR1VisionDonePulse
   CMD101 → IPC回覆201 → UR1DonePulse
   CMD102 → IPC回覆202 → UR2DonePulse

   Seq、Ack、Timeout及ResponseCode
   由既有PRG_PLCtoIPC_CMD負責。

   注意：
   IPC_CommandDone會保持ON到下一筆任務開始，
   因此ActionStep 15不能直接用IPCCommandDone
   判斷本次任務完成。
   ========================================================= *)


(* =========================================================
   1. 每個PLC Scan共用處理
   ========================================================= *)

(* IPC命令Trigger只保持一個PLC Scan *)
IPCCommandTrigger := FALSE;


(* 以下完成訊號都只保持一個PLC Scan *)
UR1VisionDonePulse := FALSE;
UR1VisionDoneUnitID := 0;

UR1DonePulse := FALSE;
UR1DoneUnitID := 0;

UR2DonePulse := FALSE;
UR2DoneUnitID := 0;


(* 全自動模式的CMD103不自動接續CMD101。
   CMD101由AutoBowlFlow確認麵已倒入碗後另外要求。 *)
IPCPreCaptureThenFirst := FALSE;


(* 目前IPC配方固定使用0 *)
IPCCommandRecipeNo := 0;



(* =========================================================
   2. IPC全自動動作流程
   ========================================================= *)

CASE ActionStep OF


    0:
        (* -------------------------------------------------
           待機，等待ActionArbiter發出新的Grant
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        ActiveCommandCode := 0;
        ActiveUnitID := 0;

        AutoIPCError := FALSE;
        AutoIPCErrorCode := 0;


        (* 確認既有IPC通訊通道完全空閒 *)
        IF (IPCRequestValid = 0)
           AND (IPCBusy = 0)
           AND NOT IPCFirstMaterialPending THEN


            (* -----------------------------------------
               第一優先：UR2執行CMD102
               ----------------------------------------- *)

            IF UR2Grant
               AND (UR2GrantUnitID <> 0) THEN

                ActiveCommandCode := 102;
                ActiveUnitID := UR2GrantUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;

                UR2Active := TRUE;

                ActionStep := 10;


            (* -----------------------------------------
               第二優先：UR1執行CMD101
               ----------------------------------------- *)

            ELSIF UR1Grant
                  AND (UR1GrantUnitID <> 0) THEN

                ActiveCommandCode := 101;
                ActiveUnitID := UR1GrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 101;

                UR2Active := FALSE;

                ActionStep := 10;


            (* -----------------------------------------
               第三優先：UR1執行CMD103預先拍照
               ----------------------------------------- *)

            ELSIF UR1VisionGrant
                  AND (UR1VisionGrantUnitID <> 0) THEN

                ActiveCommandCode := 103;
                ActiveUnitID := UR1VisionGrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 103;

                UR2Active := FALSE;

                ActionStep := 10;

            END_IF;

        END_IF;



    10:
        (* -------------------------------------------------
           再次確認IPC通訊通道空閒後送出Trigger
           ------------------------------------------------- *)

        IF (IPCRequestValid = 0)
           AND (IPCBusy = 0)
           AND NOT IPCFirstMaterialPending THEN

            (* Trigger只保持一個PLC Scan *)
            IPCCommandTrigger := TRUE;

            (* 等待PLCtoIPC_CMD接收本次任務 *)
            ActionStep := 15;

        END_IF;



    15:
        (* -------------------------------------------------
           等待PLCtoIPC_CMD正式接收本次任務

           這裡不能判斷IPCCommandDone，
           因為IPCCommandDone可能仍保持上一筆的TRUE。

           必須看到RequestValid或Busy啟動，
           才能確認本次任務已經開始。
           ------------------------------------------------- *)

        IF (IPCRequestValid <> 0)
           OR (IPCBusy <> 0) THEN

            ActionStep := 20;

        END_IF;



    20:
        (* -------------------------------------------------
           本次IPC任務已經開始
           等待PLCtoIPC_CMD回報完成或錯誤
           ------------------------------------------------- *)

        IF IPCCommandDone THEN


            (* -----------------------------------------
               CMD103預先拍照完成
               ----------------------------------------- *)

            IF ActiveCommandCode = 103 THEN

                UR1VisionDonePulse := TRUE;
                UR1VisionDoneUnitID := ActiveUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;


            (* -----------------------------------------
               CMD101前三料完成
               ----------------------------------------- *)

            ELSIF ActiveCommandCode = 101 THEN

                UR1DonePulse := TRUE;
                UR1DoneUnitID := ActiveUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;


            (* -----------------------------------------
               CMD102後三料完成
               ----------------------------------------- *)

            ELSIF ActiveCommandCode = 102 THEN

                UR2DonePulse := TRUE;
                UR2DoneUnitID := ActiveUnitID;

                UR2Active := FALSE;

            END_IF;


            (* 本次IPC動作完成，解除手臂動作狀態 *)
            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;


        ELSIF IPCCommandError THEN

            (* IPC任務執行失敗。
               停止自動重送，避免重複夾料或投料。 *)

            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            AutoIPCError := TRUE;
            AutoIPCErrorCode :=
                IPCCommandErrorCode;

            ActionStep := 90;

        END_IF;



    90:
        (* -------------------------------------------------
           IPC錯誤保持

           必須收到ErrorReset才可以離開。
           不允許自動重送，避免重複執行動作。
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        AutoIPCError := TRUE;


        IF ErrorReset THEN

            AutoIPCError := FALSE;
            AutoIPCErrorCode := 0;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;

        END_IF;



ELSE

    (* -------------------------------------------------
       遇到未定義的ActionStep時安全回到待機
       ------------------------------------------------- *)

    IPCCommandTrigger := FALSE;

    UR1Active := FALSE;
    UR1CommandNo := 0;
    UR2Active := FALSE;

    ActiveCommandCode := 0;
    ActiveUnitID := 0;

    AutoIPCError := FALSE;
    AutoIPCErrorCode := 0;

    ActionStep := 0;

END_CASE;



(* =========================================================
   3. 將目前命令資料輸出給PRG_PLCtoIPC_CMD
   ========================================================= *)

IPCCommandCode := ActiveCommandCode;
```

同時確認 `PRG_PLCtoIPC_CMD` 在接受新任務並設定：

```pascal
PLCtoIPC_RequestValid := 1;
```

後面立刻有：

```pascal
(* 新任務開始，清除上一筆完成狀態 *)
IPC_CommandDone := FALSE;
IPC_CommandError := FALSE;
IPC_CommandErrorCode := 0;
```

這段在「一般 Trigger 任務」以及「自動建立 CMD101 任務」兩個位置都要有。

## Turn 01a028b7-c5f5-7903-805a-a1bc2ca7add2

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoIPCAction 全…": C:\Users\Administrator\.codex/attachments/27b1ec61-65ab-40a2-96c5-d8a52e227960/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我先直接檢查你這份最新的 `FB_AutoIPCAction`，重點會確認完成訊號能不能正確送到 `AutoBowlFlow`，以及為什麼流程停在 CMD103 後面。

### AI（commentary）

這份程式的主要流程方向對，但和你剛改成「`IPC_CommandDone` 保持 ON 到下一筆任務」之後，有一個舊完成訊號被誤判成新任務完成的風險。我再對照目前的 `PLCtoIPC_CMD` 接收條件，確認應該在哪一步加防呆。

### AI（final_answer）

這份 `FB_AutoIPCAction` 還要改一處，因為現在 `IPC_CommandDone` 會保持 ON，Step 15 可能把上一筆完成誤認成這一筆完成。

把 `CASE ActionStep OF` 裡面的 Step 15 整段換成：

```pascal
15:
    (* -------------------------------------------------
       等待 PLCtoIPC_CMD 正式接收本次任務

       IPC_CommandDone 可能仍保持上一筆的 TRUE，
       因此這裡不能用 IPCCommandDone 判斷完成。
       必須先確認 RequestValid 或 Busy 已經啟動。
       ------------------------------------------------- *)

    IF (IPCRequestValid <> 0)
        OR (IPCBusy <> 0) THEN

        (* 本次任務已被通訊程式接收 *)
        ActionStep := 20;

    ELSIF IPCCommandError THEN

        (* 任務尚未開始就發生錯誤 *)
        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        AutoIPCError := TRUE;
        AutoIPCErrorCode := IPCCommandErrorCode;

        ActionStep := 90;

    END_IF;
```

原本 Step 15 裡這段要整個刪除：

```pascal
ELSIF IPCCommandDone THEN
    ...
```

另外確認 `PRG_PLCtoIPC_CMD` 在「正式接受新任務」時，兩個地方都有：

```pascal
IPC_CommandDone := FALSE;
```

第一個位置是自動建立 101 任務時：

```pascal
PLCtoIPC_RequestValid := 1;

(* 新任務開始，清除上一筆完成狀態 *)
IPC_CommandDone := FALSE;
IPC_CommandError := FALSE;
IPC_CommandErrorCode := 0;
```

第二個位置是接收 `IPC_CommandTrigger` 時：

```pascal
PLCtoIPC_RequestValid := 1;

(* 新任務開始，清除上一筆完成狀態 *)
IPC_CommandDone := FALSE;
IPC_CommandError := FALSE;
IPC_CommandErrorCode := 0;
```

這樣流程才會是：

```text
Grant
→ 發出 Trigger
→ PLCtoIPC_CMD 接收並清除舊 Done
→ RequestValid/Busy 啟動
→ FB 進入 Step 20
→ 收到 201／202／203
→ IPC_CommandDone ON
→ 輸出正確的完成脈波
```

還有你上一張 `FB_AutoNoodleAction` 區域變數表沒有看到下面兩個變數，記得確認它們是該 FB 的區域 `VAR`：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

改完後請「全部編譯 → 下載到模擬 PLC → 重置」，再告訴我「好了」，我就重新跑完整流程測試。

## Turn 01a028b7-1da6-7473-87c6-fac15d78cd69

## Turn 01a028b6-15dd-7be2-b607-af2ec98cca41

### 使用者


# Files mentioned by the user:

## codex-clipboard-aa6df6ca-abc3-464b-aefe-83696afea084.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-aa6df6ca-abc3-464b-aefe-83696afea084.png

## codex-clipboard-ccdeeaeb-fad5-4684-a40d-d1864c0aa359.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-ccdeeaeb-fad5-4684-a40d-d1864c0aa359.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

找到問題了。第二張圖的 `FB_AutoNoodleAction` 區域變數裡，完全沒有這兩個變數：

```text
NoodleDropDoneHold
NoodleDropDoneHoldUnitID
```

所以目前模擬 PLC 執行的不是完整修改版，這也符合測試結果 `D8010.2／D8010.7=OFF`。

請在 `FB_AutoNoodleAction` 新增：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

注意：

- 類別一定是 `VAR`。
- 不要使用 `VAR_INPUT`、`VAR_OUTPUT` 或臨時變數。
- 位址保持 `N/A [Auto]`。
- 不要建立在全域變數表。

新增後依序執行：

1. 全部編譯。
2. 將最新程式重新下載／同步至 AS200 Simulator。
3. 重置模擬 PLC。

第一張圖的 `FB_AutoIPCAction` 變數宣告目前沒有明顯問題。完成上述動作後再測試。

