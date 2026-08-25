# 規劃自建點餐系統——原聊天匯出第 023 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a018b9-0ce0-77f1-877a-4de34fd9ebb7

### 使用者

FB_AutoNoodleAction給我整個


### AI（final_answer）

可以。先補一個必要輸入，確保待機中的熟麵只會倒進相同 `UnitID` 的碗：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	NoodleDropGrantUnitID		DINT		目前允許倒麵之碗編號，必須與ActiveUnitID相同
```

以下是完整 `FB_AutoNoodleAction`，目前依你的要求先不處理異常復歸。

```pascal
(* =========================================================
   FB_AutoNoodleAction
   全自動Nachi煮麵手臂動作流程

   Action 1：
   拿生麵盒 → 放入指定麵篩 → 等待D12103.0
   → 等待RobotIdle → 完成

   Action 2：
   拿起熟麵及甩麵 → 等待D12103.0
   → 停在等待位置
   → 等待正確UnitID的碗到位
   → 開啟間隔動作允許
   → 倒麵進碗 → 等待D12103.0
   → 等待RobotIdle → 完成
   ========================================================= *)


(* ---------------------------------------------------------
   每個PLC Scan的共用處理
   --------------------------------------------------------- *)

(* 此輸出由本FB產生，因此每個Scan先清除 *)
NoodleDropDonePulse := FALSE;
NoodleDropDoneUnitID := 0;

(* 本次掃描尚未選定麵篩 *)
Selected := FALSE;


(* =========================================================
   Nachi動作狀態流程
   ========================================================= *)

CASE ActionStep OF

    0:
        (* =================================================
           待機：選擇下一個Nachi動作
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        NoodleActionBusy := FALSE;
        NoodleZoneLocked := FALSE;

        ActiveActionNo := 0;
        ActiveBasketNo := 0;
        ActiveUnitID := 0;
        ActiveCabinetNo := 0;
        ActiveOutputCabinetNo := 0;


        (* ---------------------------------------------
           第一優先：拿生麵並放入指定麵篩
           --------------------------------------------- *)

        IF NoodleLoadGrant
           AND RobotIdle
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN


            (* 找出等待拿生麵的麵篩 *)
            IF NoodleBasket_1.State = 20 THEN

                ActiveBasketNo := 1;
                ActiveUnitID :=
                    NoodleBasket_1.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_1.NoodleCabinetNo;

                (* 空麵盒出口目前暫時固定使用1號 *)
                ActiveOutputCabinetNo := 1;

                NoodleBasket_1.State := 30;
                Selected := TRUE;


            ELSIF NoodleBasket_2.State = 20 THEN

                ActiveBasketNo := 2;
                ActiveUnitID :=
                    NoodleBasket_2.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_2.NoodleCabinetNo;

                ActiveOutputCabinetNo := 1;

                NoodleBasket_2.State := 30;
                Selected := TRUE;


            ELSIF NoodleBasket_3.State = 20 THEN

                ActiveBasketNo := 3;
                ActiveUnitID :=
                    NoodleBasket_3.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_3.NoodleCabinetNo;

                ActiveOutputCabinetNo := 1;

                NoodleBasket_3.State := 30;
                Selected := TRUE;

            END_IF;


            IF Selected THEN

                ActiveActionNo := 1;

                NoodleActionBusy := TRUE;
                NoodleZoneLocked := TRUE;

                (* 啟動Action 1資料交換 *)
                ActionStep := 10;

            END_IF;


        (* ---------------------------------------------
           第二優先：拿起熟麵並甩麵
           --------------------------------------------- *)

        ELSIF NoodleShakeGrant
           AND RobotIdle
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN


            (* 找出煮麵完成的麵篩 *)
            IF NoodleBasket_1.State = 50 THEN

                ActiveBasketNo := 1;
                ActiveUnitID :=
                    NoodleBasket_1.UnitID;

                NoodleBasket_1.State := 60;
                Selected := TRUE;


            ELSIF NoodleBasket_2.State = 50 THEN

                ActiveBasketNo := 2;
                ActiveUnitID :=
                    NoodleBasket_2.UnitID;

                NoodleBasket_2.State := 60;
                Selected := TRUE;


            ELSIF NoodleBasket_3.State = 50 THEN

                ActiveBasketNo := 3;
                ActiveUnitID :=
                    NoodleBasket_3.UnitID;

                NoodleBasket_3.State := 60;
                Selected := TRUE;

            END_IF;


            IF Selected THEN

                ActiveActionNo := 2;
                ActiveCabinetNo := 0;
                ActiveOutputCabinetNo := 0;

                NoodleActionBusy := TRUE;
                NoodleZoneLocked := TRUE;

                (* 啟動Action 2資料交換 *)
                ActionStep := 50;

            END_IF;

        END_IF;


    10:
        (* =================================================
           Action 1：啟動NashiRobot_Exchange
           ================================================= *)

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;
        RobotIntervalPermit := FALSE;

        ExchangeEnable := TRUE;

        (* 下一個Scan開始等待Exchange完成 *)
        ActionStep := 20;


    20:
        (* =================================================
           Action 1：等待指令資料交換完成
           ================================================= *)

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;
        RobotIntervalPermit := FALSE;

        ExchangeEnable := TRUE;


        IF ExchangeFinish THEN

            ExchangeEnable := FALSE;

            (* 指令資料已經送給Nachi，
               接著等待實際放生麵完成訊號 *)
            ActionStep := 30;

        END_IF;


    30:
        (* =================================================
           Action 1：等待放生麵完成D12103.0
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;


        IF RobotActionFinish THEN

            (* 生麵已經放入鍋中，開始煮麵計時 *)
            CASE ActiveBasketNo OF

                1:
                    NoodleBasket_1.State := 40;

                2:
                    NoodleBasket_2.State := 40;

                3:
                    NoodleBasket_3.State := 40;

            END_CASE;

            (* 完成訊號已收到，再等待手臂Idle *)
            ActionStep := 35;

        END_IF;


    35:
        (* =================================================
           Action 1：等待Nachi回到Idle
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;


        IF RobotIdle THEN

            NoodleActionBusy := FALSE;
            NoodleZoneLocked := FALSE;

            ActiveActionNo := 0;

            ActionStep := 0;

        END_IF;


    50:
        (* =================================================
           Action 2：啟動NashiRobot_Exchange
           ================================================= *)

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;
        RobotIntervalPermit := FALSE;

        ExchangeEnable := TRUE;

        (* 下一個Scan開始等待Exchange完成 *)
        ActionStep := 55;


    55:
        (* =================================================
           Action 2：等待指令資料交換完成
           ================================================= *)

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;
        RobotIntervalPermit := FALSE;

        ExchangeEnable := TRUE;


        IF ExchangeFinish THEN

            ExchangeEnable := FALSE;

            (* 指令資料已送給Nachi，
               接著等待熟麵拿起及甩麵完成 *)
            ActionStep := 60;

        END_IF;


    60:
        (* =================================================
           Action 2第一階段：
           等待拿起熟麵及甩麵完成D12103.0
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;


        IF RobotActionFinish THEN

            (* 熟麵已經甩好，Nachi停在等待位置 *)
            CASE ActiveBasketNo OF

                1:
                    NoodleBasket_1.State := 70;

                2:
                    NoodleBasket_2.State := 70;

                3:
                    NoodleBasket_3.State := 70;

            END_CASE;

            (* 等待位置不占用輸送帶共用區域 *)
            NoodleZoneLocked := FALSE;

            ActionStep := 70;

        END_IF;


    70:
        (* =================================================
           Action 2等待階段：
           熟麵已甩好，等待對應UnitID的碗到位
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        (* Nachi仍在Action 2流程內，但位於安全等待位置 *)
        NoodleActionBusy := TRUE;
        NoodleZoneLocked := FALSE;


        (* 確認：
           1. 碗已經到達放麵位置
           2. 到位碗的UnitID正確
           3. 上一個D12103.0已經OFF
           4. UR2沒有動作
           5. UR1若在拍照可以並行，但CMD101不可並行 *)
        IF NoodleDropGrant
           AND
           (NoodleDropGrantUnitID =
            ActiveUnitID)
           AND NOT RobotActionFinish
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN

            (* 重新鎖定共用干涉區 *)
            NoodleZoneLocked := TRUE;

            (* 允許Nachi執行Action 2第二階段 *)
            RobotIntervalPermit := TRUE;

            CASE ActiveBasketNo OF

                1:
                    NoodleBasket_1.State := 80;

                2:
                    NoodleBasket_2.State := 80;

                3:
                    NoodleBasket_3.State := 80;

            END_CASE;

            ActionStep := 80;

        END_IF;


    80:
        (* =================================================
           Action 2第二階段：
           等待熟麵倒入碗中完成D12103.0
           ================================================= *)

        ExchangeEnable := FALSE;

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;

        (* 在倒麵完成前保持間隔動作允許 *)
        RobotIntervalPermit := TRUE;


        IF RobotActionFinish THEN

            (* 倒麵動作已經完成 *)
            RobotIntervalPermit := FALSE;

            (* 完成訊號已收到，再等待手臂Idle *)
            ActionStep := 85;

        END_IF;


    85:
        (* =================================================
           Action 2：等待Nachi回到Idle
           ================================================= *)

        ExchangeEnable := FALSE;
        RobotIntervalPermit := FALSE;

        NoodleActionBusy := TRUE;
        NoodleZoneLocked := TRUE;


        IF RobotIdle THEN

            (* 整個倒麵流程完全結束 *)
            CASE ActiveBasketNo OF

                1:
                    NoodleBasket_1.State := 90;

                2:
                    NoodleBasket_2.State := 90;

                3:
                    NoodleBasket_3.State := 90;

            END_CASE;

            (* 通知碗流程此UnitID已完成放麵 *)
            NoodleDropDonePulse := TRUE;
            NoodleDropDoneUnitID := ActiveUnitID;

            NoodleActionBusy := FALSE;
            NoodleZoneLocked := FALSE;

            ActiveActionNo := 0;

            ActionStep := 0;

        END_IF;


ELSE

    (* =====================================================
       未定義步驟：回到待機
       尚未加入正式異常復歸流程
       ===================================================== *)

    ExchangeEnable := FALSE;
    RobotIntervalPermit := FALSE;

    NoodleActionBusy := FALSE;
    NoodleZoneLocked := FALSE;

    ActiveActionNo := 0;
    ActionStep := 0;

END_CASE;


(* =========================================================
   既有NashiRobot_Exchange功能塊
   每個PLC Scan只呼叫一次
   ========================================================= *)

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
    AlarmCode => ExchangeAlarmCode
);
```

目前動作步驟：

```text
0  = 待機及選擇任務

10 = 啟動Action 1資料交換
20 = 等待Action 1資料交換完成
30 = 等待放生麵完成
35 = 等待Nachi回到Idle

50 = 啟動Action 2資料交換
55 = 等待Action 2資料交換完成
60 = 等待甩麵完成
70 = 熟麵在安全位置等待碗
80 = 執行倒麵進碗
85 = 等待Nachi回到Idle
```

注意：`RobotIntervalPermit` 暫時不要直接接上 `D12150.9` 運轉。舊 `SemiAuto` 也會控制這個Bit，後續要用單一模式選擇邏輯處理：

```text
Mode 10 → 舊單碗流程控制D12150.9
Mode 2  → Auto_RobotIntervalPermit控制D12150.9
```

否則兩支程式同時寫入同一個Bit，會受PLC掃描順序影響。

## Turn 01a018b7-a9c8-7493-ad05-6f9fa72738ea

### 使用者

這樣不用記數嗎會不會互相影響


### AI（final_answer）

不用計數，因為 `ActionStep` 本身就在記錄目前是第幾次完成訊號。只要每個步驟只接受自己應該收到的 `D12103.0`，就不會互相影響。

```text
ActionStep=30
收到D12103.0 → 只能解釋成「放生麵完成」

ActionStep=60
收到D12103.0 → 只能解釋成「甩麵完成」

ActionStep=80
收到D12103.0 → 只能解釋成「倒麵完成」
```

流程隔離方式：

```pascal
CASE ActionStep OF

    30:
        (* Action 1：等待放生麵完成 *)
        IF RobotActionFinish THEN

            (* 麵已經放入鍋中 *)
            ActionStep := 35;

        END_IF;


    35:
        (* 完成訊號已收到，再等待手臂Idle *)
        IF RobotIdle THEN

            NoodleActionBusy := FALSE;
            NoodleZoneLocked := FALSE;
            ActionStep := 0;

        END_IF;


    60:
        (* Action 2第一階段：等待甩麵完成 *)
        IF RobotActionFinish THEN

            (* 手臂停在等待位置 *)
            NoodleZoneLocked := FALSE;
            ActionStep := 70;

        END_IF;


    70:
        (* 等待碗到位以及允許倒麵
           同時確認上一個完成訊號已經OFF *)
        IF NoodleDropGrant
           AND NOT RobotActionFinish THEN

            NoodleZoneLocked := TRUE;
            RobotIntervalPermit := TRUE;
            ActionStep := 80;

        END_IF;


    80:
        (* Action 2第二階段：等待倒麵完成 *)
        IF RobotActionFinish THEN

            RobotIntervalPermit := FALSE;

            NoodleDropDonePulse := TRUE;
            NoodleDropDoneUnitID := ActiveUnitID;

            ActionStep := 85;

        END_IF;


    85:
        (* 倒麵完成後等待手臂回到Idle *)
        IF RobotIdle THEN

            NoodleActionBusy := FALSE;
            NoodleZoneLocked := FALSE;
            ActionStep := 0;

        END_IF;

END_CASE;
```

不會互相影響的原因：

- 每次只執行一個 `ActionStep`。
- 第一次甩麵完成後會進入Step 70。
- Step 70要求 `RobotActionFinish=FALSE` 才能允許第二階段。
- 第二個完成訊號只有開啟 `D12150.9` 後才會出現。
- Action 1與Action 2不能同時執行。

所以不需要 `ActionFinishCount`；`ActionStep` 就已經取代計數功能。

## Turn 01a018b4-f900-7882-a403-747b38b19888

### 使用者

倒麵完成脈波只保持一個PLC Scan 他會自己RST


### AI（final_answer）

對，如果 `D12103.0` 本身只出現一次並由手臂端自動RST，就不需要再做上升沿判斷。

可以刪除這三個內部變數：

```text
ActionFinishLast
ActionFinishPulse
ActionFinishCount
```

也刪除程式：

```pascal
ActionFinishPulse :=
    RobotActionFinish
    AND NOT ActionFinishLast;

ActionFinishLast := RobotActionFinish;
```

後續直接依 `ActionStep` 判斷：

```pascal
IF RobotActionFinish THEN
    (* 本階段完成 *)
END_IF;
```

同一個 `D12103.0` 的意思由步驟區分：

```text
ActionStep 30收到D12103.0
→ 放生麵完成

ActionStep 60收到D12103.0
→ 熟麵甩麵完成，進入等待位置

ActionStep 80收到D12103.0
→ 倒麵進碗完成
```

不過 `NoodleDropDonePulse` 是我們自己建立的FB輸出，不是手臂的 `D12103.0`，BOOL不會自行RST。因此仍要在每個Scan開始時寫：

```pascal
NoodleDropDonePulse := FALSE;
```

只有倒麵完成的那個Scan設為TRUE：

```pascal
IF RobotActionFinish THEN

    NoodleDropDonePulse := TRUE;
    NoodleDropDoneUnitID := ActiveUnitID;

END_IF;
```

下一個PLC Scan執行頂端的 `FALSE`，它就只會保持一個Scan。第一段程式中的所有 `ActionFinishCount := 0` 也可以一起刪掉。

### 使用者

他只有ON一下然後OFF


### AI（final_answer）

了解，`D12103.0` 的訊號形式是：

```text
OFF → ON一下 → 自動OFF
```

所以直接使用 `RobotActionFinish` 即可，不需要上升沿程式，也不需要計數。

刪除：

```text
ActionFinishLast
ActionFinishPulse
ActionFinishCount
```

FB程式開頭只保留：

```pascal
(* 自己產生的倒麵完成通知，每個Scan先清除 *)
NoodleDropDonePulse := FALSE;

(* 本次掃描尚未選定麵篩 *)
Selected := FALSE;
```

之後依所在步驟直接判斷：

```pascal
IF RobotActionFinish THEN
    (* 目前ActionStep的動作階段完成 *)
END_IF;
```

因為三個訊號分別出現在不同步驟，所以不會混淆：

```text
Step 30 → 放生麵完成
Step 60 → 甩麵完成
Step 80 → 倒麵完成
```

`D12103.0` 自己OFF；只有我們建立的 `NoodleDropDonePulse` 需要在程式開頭清除。

## Turn 01a018b2-c3dc-7333-911c-6f6342c883e1

### 使用者


# Files mentioned by the user:

## codex-clipboard-12bad620-3eba-444f-bb03-b329094fb76d.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-12bad620-3eba-444f-bb03-b329094fb76d.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這張畫面正確：

- `NashiExchange_Inst` 型態是 `NashiRobot_Exchange`
- `ActiveOutputCabinetNo` 是 `INT`
- `ExchangeAlarmCode` 是 `INT`

現在開始寫 `FB_AutoNoodleAction` 第一段：完成訊號上升沿與 `ActionStep=0` 選擇任務。

```pascal
(* =========================================================
   每個PLC Scan的共用處理
   ========================================================= *)

(* 倒麵完成脈波只保持一個PLC Scan *)
NoodleDropDonePulse := FALSE;

(* 取得D12103.0的上升沿 *)
ActionFinishPulse :=
    RobotActionFinish
    AND NOT ActionFinishLast;

ActionFinishLast := RobotActionFinish;

(* 本次掃描尚未選定麵篩 *)
Selected := FALSE;


(* =========================================================
   Nachi全自動動作流程
   ========================================================= *)

CASE ActionStep OF

    0:
        (* -------------------------------------------------
           待機及選擇下一個Nachi動作
           ------------------------------------------------- *)

        NoodleActionBusy := FALSE;
        NoodleZoneLocked := FALSE;
        RobotIntervalPermit := FALSE;
        ExchangeEnable := FALSE;

        ActiveActionNo := 0;
        ActionFinishCount := 0;


        (* 第一優先：拿生麵並放入麵篩 *)
        IF NoodleLoadGrant
           AND RobotIdle
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN

            (* 尋找等待拿生麵的麵篩 *)
            IF NoodleBasket_1.State = 20 THEN

                ActiveBasketNo := 1;
                ActiveUnitID :=
                    NoodleBasket_1.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_1.NoodleCabinetNo;

                (* 空麵盒出口目前先使用1號 *)
                ActiveOutputCabinetNo := 1;

                NoodleBasket_1.State := 30;
                Selected := TRUE;

            ELSIF NoodleBasket_2.State = 20 THEN

                ActiveBasketNo := 2;
                ActiveUnitID :=
                    NoodleBasket_2.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_2.NoodleCabinetNo;

                ActiveOutputCabinetNo := 1;

                NoodleBasket_2.State := 30;
                Selected := TRUE;

            ELSIF NoodleBasket_3.State = 20 THEN

                ActiveBasketNo := 3;
                ActiveUnitID :=
                    NoodleBasket_3.UnitID;
                ActiveCabinetNo :=
                    NoodleBasket_3.NoodleCabinetNo;

                ActiveOutputCabinetNo := 1;

                NoodleBasket_3.State := 30;
                Selected := TRUE;

            END_IF;


            IF Selected THEN

                ActiveActionNo := 1;
                NoodleActionBusy := TRUE;
                NoodleZoneLocked := TRUE;
                ActionFinishCount := 0;

                (* 進入Action 1資料交換步驟 *)
                ActionStep := 10;

            END_IF;


        (* 第二優先：拿起熟麵並甩麵 *)
        ELSIF NoodleShakeGrant
           AND RobotIdle
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN

            (* 尋找已經煮好的麵篩 *)
            IF NoodleBasket_1.State = 50 THEN

                ActiveBasketNo := 1;
                ActiveUnitID :=
                    NoodleBasket_1.UnitID;
                NoodleBasket_1.State := 60;
                Selected := TRUE;

            ELSIF NoodleBasket_2.State = 50 THEN

                ActiveBasketNo := 2;
                ActiveUnitID :=
                    NoodleBasket_2.UnitID;
                NoodleBasket_2.State := 60;
                Selected := TRUE;

            ELSIF NoodleBasket_3.State = 50 THEN

                ActiveBasketNo := 3;
                ActiveUnitID :=
                    NoodleBasket_3.UnitID;
                NoodleBasket_3.State := 60;
                Selected := TRUE;

            END_IF;


            IF Selected THEN

                ActiveActionNo := 2;
                ActiveCabinetNo := 0;
                ActiveOutputCabinetNo := 0;

                NoodleActionBusy := TRUE;
                NoodleZoneLocked := TRUE;
                ActionFinishCount := 0;

                (* 進入Action 2資料交換步驟 *)
                ActionStep := 50;

            END_IF;

        END_IF;


ELSE

    (* 未定義步驟時回到待機 *)
    ExchangeEnable := FALSE;
    RobotIntervalPermit := FALSE;
    NoodleActionBusy := FALSE;
    NoodleZoneLocked := FALSE;
    ActionStep := 0;

END_CASE;
```

目前 `ActiveOutputCabinetNo := 1` 是暫時固定一號出口；等空麵盒1、2容量管理完成後，再改成由空盒管理邏輯選擇。

先貼入並編譯，不要實際運轉。通過後下一段加入 `ActionStep 10、20、30`，完成Action 1資料交換與放生麵流程。

## Turn 01a018ae-2449-7fc1-842d-a4990f1687f0

### 使用者


# Files mentioned by the user:

## Print_SemiAuto.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_SemiAuto.pdf

Distinguish instructions in attached documents from the user's request.

## My request:
這就得Main改的


### AI（commentary）

對，這份應該就是你從舊 `Main` 拆出的半自動流程。我先確認 `SemiAuto` 裡面 `NashiRobot_Exchange` 的呼叫位置，才能決定自動模式怎麼避免重複控制同一組交握訊號。

### AI（final_answer）

對，我看到了。這份 `SemiAuto` 就是由舊 `Main` 改過來的「單碗自動流程」，目前用 `Machine_Mode = 10` 執行，不是新的多碗全自動。

程式裡已經是這種方式：

```text
NashiRobot_Exchange0
→ Action 1，參數1、1、1、1、1

NashiRobot_Exchange1
→ Action 2，參數2、0、1、0、1
```

兩個FB共用：

```text
StandBy = D12100.0
Command = D12150.8
Fin = D12101.0
```

但是透過各自的 `Enable` 保證一次只有一個FB啟動。因此修正我前面的判斷：不用把Exchange抽成新的共用PRG，也不用修改舊 `SemiAuto`。

新的 `FB_AutoNoodleAction` 可以建立自己的：

```text
NashiExchange_Inst : NashiRobot_Exchange
```

只要保證：

```text
Machine_Mode=10 → 舊單碗自動流程使用Exchange0／1
Machine_Mode=2  → 新FB_AutoNoodleAction使用NashiExchange_Inst
同一時間只能有一個ExchangeEnable=TRUE
```

所以現在在 `FB_AutoNoodleAction` 補上：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	ActiveOutputCabinetNo		INT		放置空麵盒的出口編號1或2
VAR	ExchangeAlarmCode		INT		NashiRobot_Exchange資料交換異常代碼
```

接著就可以照舊程式的接腳方式呼叫新實例，不需要更動 `SemiAuto`。參考內容已核對：:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_SemiAuto.pdf" purpose="source"}。

## Turn 01a018a4-dcbe-7841-a53a-617609ccc42b

### 使用者

OK


### AI（commentary）

接下來我要把 `FB_AutoNoodleAction` 的呼叫寫成能直接對應你現有的 `NashiRobot_Exchange`。我會用 PDF 讀取流程確認舊程式的接腳名稱與完成訊號，避免憑名稱猜測。

### 使用者


# Files pasted by the user:

## "(* ===================================================== *) (* Robot_Manual_Con…": C:\Users\Administrator\.codex/attachments/1690b991-9160-46f1-a327-e21cc5863863/pasted-text.txt

## My request:
Robot_Manual_Control給你參考


### AI（commentary）

這份手動控制程式可以直接確認既有 `NashiRobot_Exchange` 的實際啟動方式；我會以它為準，不另外改你的舊FB。

### AI（final_answer）

這份參考很重要，已確認 `NashiRobot_Exchange` 的正確接腳與參數：

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
    AlarmCode => ExchangeAlarmCode
);
```

因此剛才的完整VAR還要補兩個：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	ActiveOutputCabinetNo		INT		放置空麵盒的出口編號1或2
VAR	ExchangeAlarmCode		INT		NashiRobot_Exchange資料交換異常代碼
```

參數對應為：

```text
Parameter1 = 動作編號：1拿生麵、2熟麵甩麵及倒麵
Parameter2 = 生麵櫃編號1～10；Action 2固定0
Parameter3 = 麵篩編號1～3
Parameter4 = 空麵盒出口1～2；Action 2固定0
Parameter5 = 麵種，目前固定1
```

另外再次確認兩種完成：

```text
ExchangeFinish
= 指令資料交換完成，不能當成手臂動作完成

D12103.0
= 實際動作階段完成
```

還有一個執行安全重點：`Robot_Manual_Control` 底部目前每個Scan都會呼叫 `NashiRobot_Exchange0`，即使 `Enable` 是FALSE。自動流程加入另一個實例前，必須確保 `Machine_Mode=2` 時手動／半自動的Exchange實例不會同時操作相同的 `D12150.8`、`D12101.0`。我們會在寫呼叫前先處理「每個模式只能有一個Nashi Exchange呼叫者」。

我也比對了現有Main列印內容：:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Main.pdf" purpose="source"}。

## Turn 01a018a4-4cfa-7e62-84a2-9fecef346d21

### 使用者

UR1ZoneActive是要建立變數嗎


### AI（final_answer）

不用建立，直接用現有兩個輸入判斷即可：

```pascal
UR1Active AND (UR1CommandNo = 101)
```

例如Nachi啟動的安全條件：

```pascal
AND NOT (UR1Active AND (UR1CommandNo = 101))
AND NOT UR2Active
```

效果是：

```text
UR1Active=TRUE、UR1CommandNo=101 → 阻擋Nachi
UR1Active=TRUE、UR1CommandNo=103 → 不阻擋Nachi
UR2Active=TRUE                   → 阻擋Nachi
```

`UR1ZoneActive` 只是方便說明這個條件的名稱，不是必要變數，所以目前不要新增。

## Turn 01a018a1-b6a4-7700-97a4-c7a94220cd6b

### 使用者

FB_AutoNoodleAction再給我一次完整的VAR


### AI（final_answer）

以下是依目前確認的完整動作流程，`FB_AutoNoodleAction` 所需的全部變數。`Address` 和 `Initial Value` 留空。

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	NoodleLoadGrant		BOOL		允許拿生麵並放入指定麵篩
VAR_INPUT	NoodleShakeGrant		BOOL		允許拿起熟麵、甩麵並停在等待位置
VAR_INPUT	NoodleDropGrant		BOOL		碗已到放麵位置且防撞條件成立，允許將麵倒入碗中
VAR_INPUT	RobotIdle		BOOL		Nachi煮麵手臂目前位於待機狀態
VAR_INPUT	RobotActionFinish		BOOL		Nachi動作階段完成訊號D12103.0，依ActionStep判斷為放生麵、甩麵或倒麵完成
VAR_INPUT	UR1Active		BOOL		UR1目前正在執行CMD101或CMD103
VAR_INPUT	UR1CommandNo		INT		UR1目前指令：0=無、101=前三料、103=預先拍照
VAR_INPUT	UR2Active		BOOL		UR2目前正在執行CMD102
VAR_OUTPUT	NoodleZoneLocked		BOOL		Nachi煮麵手臂目前占用共用干涉區
VAR_OUTPUT	NoodleActionBusy		BOOL		全自動Nachi動作流程正在執行
VAR_OUTPUT	RobotIntervalPermit		BOOL		Nachi間隔動作允許，輸出至D12150.9使手臂將麵倒入碗中
VAR_OUTPUT	NoodleDropDonePulse		BOOL		熟麵倒入碗中完成脈波，只保持一個PLC Scan
VAR_OUTPUT	NoodleDropDoneUnitID		DINT		本次完成倒麵所對應的碗編號
VAR	ActionStep		INT		全自動Nachi動作執行步驟
VAR	ActiveActionNo		INT		目前Nachi動作編號：0=無、1=拿生麵、2=拿熟麵甩麵及倒麵
VAR	ActiveBasketNo		INT		目前操作的麵篩編號1至3
VAR	ActiveUnitID		DINT		目前操作的碗編號
VAR	ActiveCabinetNo		INT		目前拿取生麵的麵櫃編號
VAR	Selected		BOOL		本次掃描是否已選定麵篩
VAR	ExchangeEnable		BOOL		啟動NashiRobot_Exchange資料交換
VAR	ExchangeFinish		BOOL		NashiRobot_Exchange指令資料交換完成
VAR	ActionFinishLast		BOOL		D12103.0上一個PLC Scan的狀態
VAR	ActionFinishPulse		BOOL		D12103.0上升沿脈波，只保持一個PLC Scan
VAR	ActionFinishCount		INT		目前Nachi Action已收到的動作階段完成次數
VAR	NashiExchange_Inst		NashiRobot_Exchange		既有Nashi手臂指令資料交換功能塊實例
```

其中防撞判斷使用：

```pascal
(* CMD101占用共用區域，CMD103拍照不占用 *)
UR1ZoneActive :=
    UR1Active AND (UR1CommandNo = 101);
```

不需要另外建立 `UR1ZoneActive` 變數，也可以直接在程式條件中判斷。

`RobotIntervalPermit` 之後接到現有的 `D12150.9` 符號；在甩麵等待階段保持關閉，碗到位且取得 `NoodleDropGrant` 後才打開。

## Turn 01a018a0-517f-7473-9d3f-ad1b6931ddbc

### 使用者

還有idle共同判斷


### AI（final_answer）

對，最後完成不能只看 `D12103.0`，還要共同確認 `RobotIdle`。

但不要直接寫：

```pascal
ActionFinishPulse AND RobotIdle
```

因為兩個訊號可能不在同一個PLC Scan出現。正確方式是先記住完成次數，再等待 `RobotIdle`。

### Action 1：放生麵

```text
開始前確認RobotIdle
→ 執行Action 1
→ 收到D12103.0上升沿
→ ActionFinishCount = 1
→ 等待RobotIdle
→ 確認Action 1完全結束
→ 解除干涉區鎖定
```

程式步驟：

```pascal
(* 放生麵完成訊號已收到，等待手臂回到Idle *)
IF (ActionFinishCount >= 1)
   AND RobotIdle THEN

    NoodleActionBusy := FALSE;
    NoodleZoneLocked := FALSE;
    ActionStep := 0;

END_IF;
```

煮麵計時可以在收到 `D12103.0` 時開始，因為此時麵已經放入鍋中；但手臂鎖定必須等 `RobotIdle` 才解除。

### Action 2：甩麵及倒麵

第一個完成訊號是例外，不能等 `RobotIdle`：

```text
第一次D12103.0
→ 代表甩麵完成
→ 手臂停在等待位置
→ ActionFinishCount = 1
→ State = 70
→ 解除干涉區鎖定
```

因為手臂正在等待倒麵允許，此時通常不會是 `RobotIdle`。

收到放麵允許後：

```text
重新鎖定干涉區
→ 開啟D12150.9
→ 手臂倒麵進碗
→ 第二次D12103.0
→ ActionFinishCount = 2
→ 等待RobotIdle
→ 整個Action 2完成
```

最後判斷：

```pascal
(* 倒麵完成訊號已收到，等待手臂回到Idle *)
IF (ActionFinishCount >= 2)
   AND RobotIdle THEN

    NoodleActionBusy := FALSE;
    NoodleZoneLocked := FALSE;
    ActionFinishCount := 0;
    ActionStep := 0;

END_IF;
```

完整原則是：

```text
啟動手臂動作前：必須確認RobotIdle

Action 1最終完成：
D12103.0完成事件已記錄 AND RobotIdle

Action 2甩麵完成：
第一次D12103.0，不判斷RobotIdle，進入等待位置

Action 2最終完成：
第二次D12103.0已記錄 AND RobotIdle
```

這樣即使 `D12103.0` 先消失、`RobotIdle` 下一個掃描才出現，也不會漏掉完成判斷。

## Turn 01a0189c-4a40-7bf1-b786-cc45aa42dd15

### 使用者

手臂在放生麵結束會有一個結束訊號然後在哪起來甩完會有另一個訊號在放完碗會在有一個訊號D12103.0


### AI（final_answer）

了解，三個完成事件都是同一個訊號 `D12103.0`，只是出現時所在的流程步驟不同：

```text
Action 1：
放生麵完成
→ D12103.0 第一次上升沿

Action 2：
拿起熟麵並甩麵完成
→ D12103.0 第一次上升沿
→ 手臂停在等待位置
→ PLC允許倒麵
→ 將麵放入碗完成
→ D12103.0 第二次上升沿
```

因此不能只看 `D12103.0 = TRUE`，必須搭配 `ActionStep` 判斷它代表哪個完成事件。

變數註釋改成：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR_INPUT	RobotActionFinish		BOOL		Nachi動作階段完成訊號D12103.0，依ActionStep判斷為放生麵、甩麵或倒麵完成
VAR	ActionFinishLast		BOOL		D12103.0上一掃描狀態，用於取得上升沿
VAR	ActionFinishPulse		BOOL		D12103.0動作階段完成上升沿，只保持一個PLC Scan
VAR	ActionFinishCount		INT		Nachi目前Action內已收到的動作完成次數
```

每個PLC Scan先取得上升沿：

```pascal
ActionFinishPulse :=
    RobotActionFinish
    AND NOT ActionFinishLast;

ActionFinishLast := RobotActionFinish;
```

後續步驟規劃：

```text
ActionStep = 30
執行拿生麵進鍋
收到一次ActionFinishPulse
→ 麵篩State改為40，開始煮麵計時

ActionStep = 60
執行拿熟麵及甩麵
收到第一次ActionFinishPulse
→ 麵篩State改為70
→ 手臂停在等待位置
→ 解除NoodleZoneLocked

ActionStep = 70
等待對應碗到達放麵位置
→ 等待NoodleDropGrant

ActionStep = 80
送出間隔動作允許訊號D12150.9
→ 手臂將麵倒進碗
收到第二次ActionFinishPulse
→ 麵篩State改為90
→ 倒麵完成
```

`Action 2` 必須增加計數，是因為同一次手臂指令會收到兩次 `D12103.0`。`Action 1` 只需要一次。

