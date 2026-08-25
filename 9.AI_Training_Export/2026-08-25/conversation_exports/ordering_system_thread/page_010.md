# 規劃自建點餐系統——原聊天匯出第 010 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a028b2-b5c9-7502-83b4-fea63cf0254a

### 使用者

好了


### AI（commentary）

收到，重新測試。這次會在模擬輸入保持開啟的狀態下直接擷取 `D8010`。

### AI（final_answer）

這次模擬輸入確實有開：

```text
D8000 = 16#0005
bit0 Simulation_Mode = ON
bit2 X0.2模擬輸入 = ON
```

診斷結果：

```text
D8010 = 16#0008
```

只有 `D8010.3 IPC_CommandDone` 為 ON，代表 IPC 203 已完成並保持成功。但以下都沒有產生：

```text
D8010.2 Auto_NoodleDropDonePulse = OFF
D8010.6 UR1VisionDonePulse曾發生 = OFF
D8010.7 NoodleDropDonePulse曾發生 = OFF
```

現在先不要再修改邏輯。請在目前 PLC 線上狀態截圖：

1. `FB_AutoIPCAction` 的區域變數，尤其是：

```text
ActionStep
ActiveCommandCode
ActiveUnitID
IPCCommandDone輸入
```

2. `FB_AutoNoodleAction` 的區域變數：

```text
ActionStep
NoodleDropDoneHold
NoodleDropDoneHoldUnitID
NoodleDropDonePulse
```

因為 `State=90` 已證明 Step 85 執行過；如果 `NoodleDropDoneHold` 仍是 FALSE，就代表模擬 PLC 執行的不是剛修改的 FB，或該變數宣告方式不正確。

## Turn 01a028ae-2e31-7b02-8337-9a8fe2b27b59

### 使用者

好了


### AI（commentary）

收到，開始診斷測試。這次除了完整流程，會讀取 `D8010` 的各位元，直接確認 CMD101 卡在哪個條件。

### AI（final_answer）

診斷結果：

```text
D8010 = 0
NoodleBasket_1.State = 90
FIFO = 1
```

`State=90` 證明 Step 85 確實執行過，所以正常情況下：

```text
D8010.2 = 1  NoodleDropDone保持輸出
D8010.7 = 1  曾經發生倒麵完成
```

但兩者都是 0，代表目前不是 BowlFlow 判斷問題，而是下面其中一項：

- `NoodleDropDoneHold` 被建成非保持型變數。
- `Auto_NoodleDropDonePulse` 的輸出接線不正確。
- D8010 診斷梯級沒有執行或下載到模擬 PLC。
- `SM402 → RST D8010` 梯級接法造成持續清除。

先不要重置。請在線監控並截圖以下位置：

```text
NoodleDropDoneHold
NoodleDropDoneHoldUnitID
Auto_NoodleDropDonePulse
Auto_NoodleDropDoneUnitID
IPC_CommandDone
D8010診斷梯級
```

特別確認 `NoodleDropDoneHold` 的 Class 是 `VAR`，不是 `VAR_TEMP`。目前 PLC 正停在問題狀態，現在截圖最容易直接找到哪一層斷掉。

### 使用者

你要開啟模擬輸入


### AI（commentary）

你說得對，我剛才是在測試結束後才讀 `D8010`，而測試程式的 `finally` 已經把模擬輸入恢復關閉，所以這個讀值不能用來判斷。我要改成在模擬輸入仍為 ON、流程仍卡住時就讀取 `D8000／D8010`。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_full_auto_flow_test.py：update

### AI（final_answer）

測試程式已修正：

- 開啟模擬模式時保留原本已設定的其他模擬輸入。
- 流程卡住當下、模擬輸入仍為 ON 時直接讀取 `D8000` 和 `D8010`。
- 不再使用測試結束、模擬輸入關閉後的錯誤讀值。

目前上一輪流程仍卡住，請重置 PLC 模擬器後回覆「好了」，我馬上重新測試。

## Turn 01a028ac-f4b2-7773-88be-539934d4ea51

### 使用者

好


### AI（final_answer）

新增 `D8010` 診斷並編譯、重置 PLC 後，回覆「好了」，我立即重新測試並解析每個旗標。

## Turn 01a028a6-73ee-7790-924e-198ddf940c62

### 使用者

在測試一次


### AI（commentary）

收到，開始第六輪完整測試。這次確認保持型 `IPC_CommandDone` 能讓203完成寫入 `UR1VisionDone`，接著產生CMD101並一路跑完。

### AI（final_answer）

第六輪仍停在相同位置：

```text
倒麵完成：PASS
Nachi回到Step 0：PASS
CMD103／203：PASS
CMD101：未產生
FIFO：仍為1
```

現在不要再改控制邏輯，先增加 `D8010` 診斷，確認是哪個條件沒進去。

在 `MainAuto` 增加以下監控接點：

```text
Auto_NoodleDropRequest      → D8010.0 一般線圈
Auto_UR1Request             → D8010.1 一般線圈
Auto_NoodleDropDonePulse    → D8010.2 一般線圈
IPC_CommandDone             → D8010.3 一般線圈
Auto_UR1VisionRequest       → D8010.4 一般線圈
Auto_UR1Grant               → D8010.5 一般線圈
Auto_UR1VisionDonePulse     → D8010.6 SET線圈
Auto_NoodleDropDonePulse    → D8010.7 SET線圈
```

初始化增加：

```text
SM402 → RST D8010
```

其中：

- `D8010.6`：記錄203完成通知是否曾經產生。
- `D8010.7`：記錄倒麵完成通知是否曾經產生。
- 使用 SET 是為了避免一個 Scan 的訊號被測試程式漏讀。

編譯並重置後再測，我就能直接從 `D8010` 判斷是 `UR1VisionDone`、`NoodleDropDone`，還是 `UR1Request` 的問題。

## Turn 01a028a1-a257-79f2-b6e3-308ff02dbbfb

### 使用者


# Files pasted by the user:

## "(* ===================================================== *) (* PRG_PLCtoIPC_Com…": C:\Users\Administrator\.codex/attachments/b0466aab-e742-499f-8cd4-25b16a7bb7b8/pasted-text.txt

## My request:
改給我


### AI（commentary）

我會直接依照你這份完整 `PRG_PLCtoIPC_CMD` 修改，保留原有交握，只把 `IPC_CommandDone` 改成可靠的保持狀態。

### AI（final_answer）

下面是修改完成的完整 `PRG_PLCtoIPC_Command`。新增的地方標示為「新任務開始，清除上一筆完成狀態」。

```pascal
(* ===================================================== *)
(* PRG_PLCtoIPC_Command                                  *)
(*                                                       *)
(* CommandCode：                                         *)
(* 101 = 投放前三種料                                    *)
(* 102 = 投放後三種料                                    *)
(* 103 = 預先拍照                                        *)
(*                                                       *)
(* ResponseCode：                                        *)
(* 201 = 前三料完成                                      *)
(* 202 = 後三料完成                                      *)
(* 203 = 預先拍照完成                                    *)
(* 901 = IPC 任務失敗                                    *)
(*                                                       *)
(* 複合流程：                                            *)
(* IPC_PreCaptureThenFirst = TRUE                        *)
(* 103 拍照 → 203 完成 → 101 前三料 → 201 完成          *)
(*                                                       *)
(* IPC_CommandDone改為保持型：                           *)
(* 完成後保持TRUE，下一筆有效任務開始才清除              *)
(* ===================================================== *)


(* ----------------------------------------------------- *)
(* PLC開機初始化                                         *)
(* ----------------------------------------------------- *)

IF SM402 THEN

    IPC_CommandDone := FALSE;

END_IF;


(* ----------------------------------------------------- *)
(* 0. 拍照完成後，自動建立前三料任務                     *)
(* ----------------------------------------------------- *)

IF IPC_FirstMaterialPending
   AND (PLCtoIPC_RequestValid = 0)
   AND (IPCtoPLC_Busy = 0) THEN

    (* 新任務開始，清除上一筆完成狀態 *)
    IPC_CommandDone := FALSE;

    (* 建立新任務Seq *)
    IF PLCtoIPC_RequestSeq = 16#FFFF THEN

        PLCtoIPC_RequestSeq := 0;

    ELSE

        PLCtoIPC_RequestSeq :=
            PLCtoIPC_RequestSeq + 1;

    END_IF;

    (* IPC 101：夾取前三料 *)
    PLCtoIPC_RequestCode := 101;
    PLCtoIPC_RecipeNo := 0;
    PLCtoIPC_RequestValid := 1;

    IPC_AckTimeout := 0;
    IPC_WorkTimeout := 0;

    IPC_FirstMaterialPending := FALSE;

END_IF;


(* ----------------------------------------------------- *)
(* 1. 接收新IPC任務                                      *)
(* ----------------------------------------------------- *)

IF IPC_CommandTrigger
   AND NOT IPC_CommandTriggerLast THEN

    IF (PLCtoIPC_RequestValid = 0)
       AND (IPCtoPLC_Busy = 0)
       AND (IPC_FirstMaterialPending = FALSE) THEN

        IF (IPC_CommandCode = 101)
           OR (IPC_CommandCode = 102)
           OR (IPC_CommandCode = 103) THEN

            (* 新任務開始，清除上一筆完成狀態 *)
            IPC_CommandDone := FALSE;

            (* 任務流水號+1，65535後回到0 *)
            IF PLCtoIPC_RequestSeq = 16#FFFF THEN

                PLCtoIPC_RequestSeq := 0;

            ELSE

                PLCtoIPC_RequestSeq :=
                    PLCtoIPC_RequestSeq + 1;

            END_IF;

            (* 建立PLC → IPC任務 *)
            PLCtoIPC_RequestCode :=
                IPC_CommandCode;

            PLCtoIPC_RecipeNo :=
                IPC_CommandRecipeNo;

            PLCtoIPC_RequestValid := 1;

            (* 清除上一筆錯誤 *)
            IPC_CommandError := FALSE;
            IPC_CommandErrorCode := 0;

            IPC_AckTimeout := 0;
            IPC_WorkTimeout := 0;

        ELSE

            IPC_CommandError := TRUE;
            IPC_CommandErrorCode := 401;
            (* 不支援的IPC命令碼 *)

        END_IF;

    ELSE

        IPC_CommandError := TRUE;
        IPC_CommandErrorCode := 402;
        (* IPC前一筆任務仍在執行 *)

    END_IF;

    (* 本Program已接收Trigger，統一清除 *)
    IPC_CommandTrigger := FALSE;

END_IF;


(* 保存Trigger狀態，供下一Scan判斷上升沿 *)
IPC_CommandTriggerLast := IPC_CommandTrigger;


(* ----------------------------------------------------- *)
(* 2. PLC已發出IPC任務                                   *)
(* ----------------------------------------------------- *)

IF PLCtoIPC_RequestValid = 1 THEN

    (* 尚未收到IPC Ack *)
    IF IPCtoPLC_AckSeq <> PLCtoIPC_RequestSeq THEN

        TMR(IPC_AckTimeout, 30);
        IPC_WorkTimeout := 0;

        IF IPC_AckTimeout THEN

            PLCtoIPC_RequestValid := 0;
            IPC_CommandDone := FALSE;

            (* 若拍照失敗，中止拍照→前三料流程 *)
            IF PLCtoIPC_RequestCode = 103 THEN

                IPC_PreCaptureThenFirst := FALSE;
                IPC_FirstMaterialPending := FALSE;

            END_IF;

            IPC_CommandError := TRUE;
            IPC_CommandErrorCode := 501;
            (* IPC Ack Timeout *)

        END_IF;


    (* IPC已Ack，等待IPC執行完成 *)
    ELSE

        IPC_AckTimeout := 0;

        TMR(IPC_WorkTimeout, 300);

        (* ResponseSeq必須對應本次任務Seq *)
        IF IPCtoPLC_ResponseSeq =
           PLCtoIPC_RequestSeq THEN

            (* IPC 101：前三料完成 *)
            IF (PLCtoIPC_RequestCode = 101)
               AND (IPCtoPLC_ResponseCode = 201) THEN

                PLCtoIPC_RequestValid := 0;
                IPC_WorkTimeout := 0;

                (* 完成狀態保持到下一筆任務開始 *)
                IPC_CommandDone := TRUE;
                IPC_CommandError := FALSE;
                IPC_CommandErrorCode := 0;


            (* IPC 102：後三料完成 *)
            ELSIF (PLCtoIPC_RequestCode = 102)
                  AND (IPCtoPLC_ResponseCode = 202) THEN

                PLCtoIPC_RequestValid := 0;
                IPC_WorkTimeout := 0;

                IPC_CommandDone := TRUE;
                IPC_CommandError := FALSE;
                IPC_CommandErrorCode := 0;


            (* IPC 103：預先拍照完成 *)
            ELSIF (PLCtoIPC_RequestCode = 103)
                  AND (IPCtoPLC_ResponseCode = 203) THEN

                PLCtoIPC_RequestValid := 0;
                IPC_WorkTimeout := 0;

                IF IPC_PreCaptureThenFirst THEN

                    (* 下一個Scan自動建立IPC 101前三料 *)
                    IPC_PreCaptureThenFirst := FALSE;
                    IPC_FirstMaterialPending := TRUE;

                ELSE

                    (* 單獨拍照命令完成 *)
                    IPC_CommandDone := TRUE;
                    IPC_CommandError := FALSE;
                    IPC_CommandErrorCode := 0;

                END_IF;


            (* IPC回報執行失敗 *)
            ELSIF IPCtoPLC_ResponseCode >= 900 THEN

                PLCtoIPC_RequestValid := 0;
                IPC_WorkTimeout := 0;
                IPC_CommandDone := FALSE;

                (* 若拍照失敗，中止拍照→前三料流程 *)
                IF PLCtoIPC_RequestCode = 103 THEN

                    IPC_PreCaptureThenFirst := FALSE;
                    IPC_FirstMaterialPending := FALSE;

                END_IF;

                IPC_CommandError := TRUE;

                IF IPCtoPLC_ErrorCode <> 0 THEN

                    IPC_CommandErrorCode :=
                        IPCtoPLC_ErrorCode;

                ELSE

                    IPC_CommandErrorCode :=
                        IPCtoPLC_ResponseCode;

                END_IF;

            END_IF;


        ELSIF IPC_WorkTimeout THEN

            PLCtoIPC_RequestValid := 0;
            IPC_CommandDone := FALSE;

            (* 若拍照Timeout，中止拍照→前三料流程 *)
            IF PLCtoIPC_RequestCode = 103 THEN

                IPC_PreCaptureThenFirst := FALSE;
                IPC_FirstMaterialPending := FALSE;

            END_IF;

            IPC_CommandError := TRUE;
            IPC_CommandErrorCode := 502;
            (* IPC工作Timeout *)

        END_IF;

    END_IF;


ELSE

    (* 無IPC任務時停止Timer *)
    IPC_AckTimeout := 0;
    IPC_WorkTimeout := 0;

END_IF;
```

這版不需要新增變數。編譯通過後重置 PLC，再進行下一輪測試。

## Turn 01a02897-593e-7532-892b-d34a1a7b1c3d

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoBowlFlow 第一…": C:\Users\Administrator\.codex/attachments/ad2ec33d-c4db-404d-95f2-961018fdaa15/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我現在檢查完整的 `FB_AutoBowlFlow`，會直接沿著同一個 UnitID 追蹤 `203完成 → 倒麵完成 → UR1Request` 的條件。

### AI（final_answer）

找到真正原因了：`FB_AutoBowlFlow` 的判斷邏輯是正確的。

CMD101 必須滿足：

```pascal
NoodleDropDone = TRUE
AND UR1VisionDone = TRUE
```

現在倒麵完成已保持，所以缺的是 `UR1VisionDone`。

問題在 `PRG_PLCtoIPC_CMD` 最上面：

```pascal
(* Done只保持一個PLC Scan *)
IPC_CommandDone := FALSE;
```

`IPC_CommandDone` 只亮一個 Scan，`FB_AutoIPCAction` 可能因程式執行順序漏接，導致收到203卻沒有產生 `UR1VisionDonePulse`。

### 修改 `PRG_PLCtoIPC_CMD`

把每個 Scan 清除：

```pascal
IPC_CommandDone := FALSE;
```

刪除，改成開機清除：

```pascal
(* PLC開機初始化 *)
IF SM402 THEN

    IPC_CommandDone := FALSE;

END_IF;
```

在「接收新 IPC 任務」成功接受命令的位置加入：

```pascal
(* 新任務開始，清除上一筆完成狀態 *)
IPC_CommandDone := FALSE;
```

放在這裡：

```pascal
IF (PLCtoIPC_RequestValid = 0) AND
   (IPCtoPLC_Busy = 0) AND
   (IPC_FirstMaterialPending = FALSE) THEN

    (* 新任務開始，清除上一筆完成狀態 *)
    IPC_CommandDone := FALSE;

    IF (IPC_CommandCode = 101) OR
       (IPC_CommandCode = 102) OR
       (IPC_CommandCode = 103) THEN
```

另外，自動建立101任務的區段也加入：

```pascal
IF IPC_FirstMaterialPending AND
   (PLCtoIPC_RequestValid = 0) AND
   (IPCtoPLC_Busy = 0) THEN

    IPC_CommandDone := FALSE;

    (* 以下維持原程式 *)
```

完成時原本的程式不變：

```pascal
IPC_CommandDone := TRUE;
```

這樣 `IPC_CommandDone` 會保持 TRUE，直到下一筆 IPC 命令真正開始，不會再因程式掃描順序漏接。

目前不用再改 `FB_AutoBowlFlow`。修改、編譯並重置後再測一次。

## Turn 01a02894-7d52-7de0-92cd-3f2899718f29

### 使用者

好了


### AI（commentary）

收到，開始第五輪完整測試。這次重點確認完成通知能讓碗流程產生 UR1 CMD101，並繼續跑到 UR2、注湯與 FIFO 完成。

### AI（commentary）

第五輪仍沒有產生 CMD101，所以「完成通知只維持一個 Scan」不是唯一原因。Nachi 已完成並回到 Step 0；接下來要查 `FB_AutoBowlFlow` 是否把 `NoodleDropDone` 和 `UR1VisionDone` 都寫進同一個 UnitID。先從你先前提供的程式中找完整的 Request 產生區段。

### AI（final_answer）

第五輪結果仍卡在 UR1 CMD101，但現在已確認：

```text
NoodleBasket_1.State = 90   ← 倒麵完成
ActionStep = 0              ← Nachi流程結束
D1201 = 103                 ← 最後命令仍是拍照
D1203 = 0                   ← 沒有新IPC Request
D1303 = 203                 ← 拍照已完成
FIFO = 1                    ← 訂單尚未完成
```

所以問題已縮小到 `FB_AutoBowlFlow`：

```text
NoodleDropDone／UR1VisionDone
        ↓
產生 Auto_UR1Request
```

其中某個條件沒有成立。請把目前完整的 `FB_AutoBowlFlow` ST 程式貼給我，尤其是第10段後面產生以下 Request 的部分：

```pascal
NoodleDropRequest
UR1VisionRequest
UR1Request
UR2Request
SoupRequest
RightmostStation
```

先不用再次重置 PLC；我看完程式再一次修正，避免繼續猜測。

## Turn 01a02893-4e0a-79f0-a09f-11cd0a5dea10

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoNoodleActio…": C:\Users\Administrator\.codex/attachments/a2cf6750-3db9-4a43-8f6d-064c8e416473/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我檢查這個新版本，逐項確認保持變數、Action 2 清除位置及 Step 85 完成通知是否都放對。

### AI（final_answer）

這一版修改正確，三個位置都有完成：

- 共用處理改為輸出 `NoodleDropDoneHold`。
- 選擇下一個 Action 2 時清除舊通知。
- Step 85 保存 `ActiveUnitID` 並保持完成通知。

只要確認區域變數存在：

```text
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

現在可以編譯。編譯通過後重置 PLC，再告訴我開始下一輪測試。

## Turn 01a0288f-e55b-7f01-b122-c7f144c22e06

### 使用者

好了接著改程式


### AI（final_answer）

好，現在改 `FB_AutoNoodleAction`，共三處。

第一處：每個 Scan 的共用處理

找到：

```pascal
NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;
```

改成：

```pascal
(* 倒麵完成通知保持到下一次Action 2開始 *)
NoodleDropDonePulse := NoodleDropDoneHold;
NoodleDropDoneUnitID := NoodleDropDoneHoldUnitID;
```

第二處：選擇新的 Action 2

在 Action 2 的：

```pascal
IF Selected THEN
```

裡面最前面加入：

```pascal
(* 新的倒麵任務開始，清除上一碗完成通知 *)
NoodleDropDoneHold := FALSE;
NoodleDropDoneHoldUnitID := 0;

NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;
```

完整部分變成：

```pascal
IF Selected THEN

    (* 清除上一碗的倒麵完成通知 *)
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

第三處：Step 85 完成倒麵

找到：

```pascal
NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

改成：

```pascal
(* 保存完成通知，避免AutoBowlFlow漏掉一個Scan脈波 *)
NoodleDropDoneHold := TRUE;
NoodleDropDoneHoldUnitID := ActiveUnitID;

NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

新增區域變數：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

改完後先編譯。編譯通過再重置 PLC，我接著重新測試。

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_AutoNoodleActio…": C:\Users\Administrator\.codex/attachments/830a313f-50cc-428e-a6c2-4a024a5d9780/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我會直接檢查你現在這份 `FB_AutoNoodleAction`，確認三處保持通知的修改是否完整，以及有沒有造成下一碗或 Action 1 被影響。

### AI（final_answer）

你貼的這份還是舊版，三處都還沒修改。

### 1. 共用處理

把：

```pascal
(* 本FB產生的完成通知只保持一個PLC Scan *)
NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;
```

改成：

```pascal
(* 保持倒麵完成通知，避免FB_AutoBowlFlow漏接 *)
NoodleDropDonePulse := NoodleDropDoneHold;
NoodleDropDoneUnitID := NoodleDropDoneHoldUnitID;
```

### 2. Action 2 的 `IF Selected THEN`

改成：

```pascal
IF Selected THEN

    (* 新任務開始，清除上一碗的完成通知 *)
    NoodleDropDoneHold := FALSE;
    NoodleDropDoneHoldUnitID := 0;

    NoodleDropDonePulse := FALSE;
    NoodleDropDoneUnitID := 0;

    ActiveActionNo := 2;
    ActiveCabinetNo := 0;
    ActiveOutputCabinetNo := 0;

    NoodleActionBusy := TRUE;
    NoodleZoneLocked := TRUE;

    (* 進入Action 2資料交換 *)
    ActionStep := 50;

END_IF;
```

### 3. Step 85

把：

```pascal
(* 通知碗流程此UnitID已完成放麵 *)
NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

改成：

```pascal
(* 保存倒麵完成通知 *)
NoodleDropDoneHold := TRUE;
NoodleDropDoneHoldUnitID := ActiveUnitID;

(* 輸出給FB_AutoBowlFlow *)
NoodleDropDonePulse := TRUE;
NoodleDropDoneUnitID := ActiveUnitID;
```

並確認區域變數已新增：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持倒麵完成的碗編號
```

其他程式不用改。修改完先編譯。

## Turn 01a02885-c464-7eb2-afca-b48bd84a5dac

### 使用者

所以現在是要改成程式

### AI（final_answer）

對，要改 PLC 程式，但不用改 IPC 交握。

只改 `FB_AutoNoodleAction`：把 `NoodleDropDonePulse` 從「只亮一個 Scan」改成「保持到下一次 Action 2 開始」。

新增兩個區域變數：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	NoodleDropDoneHold		BOOL		保持倒麵完成通知
VAR	NoodleDropDoneHoldUnitID		DINT		保持完成碗編號
```

其他維持：

- `FB_AutoBowlFlow` 不用改。
- `FB_AutoIPCAction` 不用改。
- `PLCtoIPC_CMD` 交握不用改。
- Python 模擬器不用再改。

照上一則提供的三處程式修改，編譯並重置 PLC 後再測試。

