# 規劃自建點餐系統——原聊天匯出第 001 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a02dc5-6c29-7473-8cdb-05200328f71c

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB：FB_AutoSchedule…": C:\Users\Administrator\.codex/attachments/9592d982-a054-40db-91b4-90f28836fa0d/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我會直接檢查你貼的最新版 `FB_AutoScheduler`，確認 `FirmnessNo` 是否已經保存、`CookTimeSet` 現在在哪裡賦值，以及三個麵篩是否會各自取得正確的軟硬時間。

### AI（final_answer）

看完這支 `FB_AutoScheduler`，軟硬度對應煮麵時間其實已經寫好了，這部分邏輯正確。

流程是：

```text
訂單 FirmnessNo
        ↓
選擇 CookTime_Hard／Normal／Soft_Set
        ↓
SelectedCookTime
        ↓
NoodleBasket_x.CookTimeSet
        ↓
Noodlebasket PRG 的 TMR S2
```

對應關係：

```iecst
FirmnessNo = 1
→ SelectedCookTime := CookTime_Hard_Set;

FirmnessNo = 2
→ SelectedCookTime := CookTime_Normal_Set;

FirmnessNo = 3
→ SelectedCookTime := CookTime_Soft_Set;
```

分配麵篩時，也已經正確保存：

```iecst
NoodleBasket_1.FirmnessNo :=
    UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;

NoodleBasket_1.CookTimeSet :=
    SelectedCookTime;
```

麵篩2、3也都有相同處理。

所以現在要確認的是這三個設定值：

```text
CookTime_Hard_Set
CookTime_Normal_Set
CookTime_Soft_Set
```

如果是 `TMR` 100 ms基準，建議測試設定：

```text
CookTime_Hard_Set   = 400    約40秒
CookTime_Normal_Set = 500    約50秒
CookTime_Soft_Set   = 600    約60秒
```

注意：

```text
500不是500 ms
500 × 100 ms = 50秒
```

線上監控時看這些變數：

```text
CookTime_Hard_Set
CookTime_Normal_Set
CookTime_Soft_Set
SelectedCookTime

NoodleBasket_1.FirmnessNo
NoodleBasket_1.CookTimeSet

NoodleBasket_2.FirmnessNo
NoodleBasket_2.CookTimeSet

NoodleBasket_3.FirmnessNo
NoodleBasket_3.CookTimeSet
```

另外，Scheduler 這段：

```iecst
(* 目前只能有一個麵篩處於State 20或30 *)
```

是正確的。因為 Nachi 一次只能執行一個「拿生麵放入麵篩」動作；第一個麵篩進入 State 40 後，Scheduler 才把下一個麵篩從 State 10 改成 State 20。最後應該依序形成：

```text
40、20、10
40、40、20
40、40、40
```

前面修改過的 `FB_ActionArbiter` 會負責在碗停於第二站等待時，繼續處理其他 State 20 麵篩。現在主要只要確認三個 `CookTime_*_Set` 的實際數值與 VAR 接線。

## Turn 01a02dc1-fe8f-7b32-825a-bd42dce26191

### 使用者


# Files mentioned by the user:

## Print_Noodlebasket.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print_Noodlebasket.pdf

Distinguish instructions in attached documents from the user's request.

## My request:
你看到的是舊版這是新板


### AI（commentary）

了解，剛才讀到的是舊匯出內容。我現在重新載入同一路徑的新版 PDF，確認最新版裡的煮麵計時、TMR 接線和設定值位置。因為檔案已被覆蓋，我會重新渲染，不沿用剛才的畫面。

### AI（final_answer）

對，這次看到的是新版，我前面判斷需要更正。新版已經把三個麵篩的煮麵計時寫在 `Noodlebasket PRG` 裡。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Noodlebasket.pdf" purpose="source"}

目前結構是：

```text
麵篩1：NoodleBasket1_CookTimer → T8
麵篩2：NoodleBasket2_CookTimer → T9
麵篩3：NoodleBasket3_CookTimer → T10
```

煮麵流程：

```text
NoodleBasket_x.State = 40
        ↓
TMR
S1 = NoodleBasketx_CookTimer
S2 = NoodleBasket_x.CookTimeSet
        ↓
計時完成
        ↓
MOV 50 → NoodleBasket_x.State
```

所以真正控制時間的是：

```iecst
NoodleBasket_1.CookTimeSet
NoodleBasket_2.CookTimeSet
NoodleBasket_3.CookTimeSet
```

不是 `T8／T9／T10` 本身。`T8～T10` 只是三個獨立計時器。

軟硬度設定應在「訂單分配到麵篩」時寫入：

```text
FirmnessNo = 1 → 硬麵 → CookTimeSet較短
FirmnessNo = 2 → 正常 → CookTimeSet正常
FirmnessNo = 3 → 軟麵 → CookTimeSet較長
```

例如：

```iecst
CASE NoodleBasket_1.FirmnessNo OF

    1:
        NoodleBasket_1.CookTimeSet := 400;  (* 硬：40秒 *)

    2:
        NoodleBasket_1.CookTimeSet := 500;  (* 正常：50秒 *)

    3:
        NoodleBasket_1.CookTimeSet := 600;  (* 軟：60秒 *)

ELSE

    NoodleBasket_1.CookTimeSet := 500;

END_CASE;
```

這段不應放在 `Noodlebasket PRG`，而應放在 `FB_AutoScheduler` 分配麵篩的位置。`Noodlebasket PRG` 只負責使用已設定好的 `CookTimeSet` 計時。

線上確認時直接監看這六項：

```text
NoodleBasket_1.CookTimeSet
NoodleBasket_2.CookTimeSet
NoodleBasket_3.CookTimeSet
T8
T9
T10
```

目前若三個 `CookTimeSet` 都顯示500，代表軟硬度對應時間還沒有在 Scheduler 寫入。

## Turn 01a02db2-f7b4-7971-8aae-8aea917dfd28

### 使用者

煮麵時間在哪裡確認


### AI（commentary）

我會對照你目前的 `Print_Noodlebasket.pdf` 找到真正執行煮麵計時的梯圖位置，確認是在哪個 PRG、哪個 `TMR`，以及你應該看 S1 還是 S2。因為是梯圖 PDF，我會用 PDF 檢視流程確認畫面，不會猜變數位置。

### 使用者

跟設定


### AI（commentary）

我會一起確認兩件事：煮麵時間目前在哪一段程式判斷，以及要在哪個設定值修改，避免再把 `500` 當成 500 ms。

### 使用者

軟硬應該對應不一樣的時間


### AI（final_answer）

對，軟、正常、硬必須對應不同煮麵時間。

我確認目前的 `Noodlebasket PRG` 只有控制三個麵篩的升降輸出 `Y0.1～Y0.6`，裡面沒有煮麵計時。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Noodlebasket.pdf" purpose="source"}

煮麵時間應該放在 `FB_AutoScheduler`，由它持續判斷三個麵篩的 `State = 40`，而不是放在 `FB_AutoNoodleAction`。

建議設定：

```text
FirmnessNo = 1 → 硬麵
FirmnessNo = 2 → 正常
FirmnessNo = 3 → 軟麵
```

如果 TMR 基準是100 ms，正式時間範例：

```text
硬麵    S2 = 400    → 40秒
正常    S2 = 500    → 50秒
軟麵    S2 = 600    → 60秒
```

目前你下單使用的軟硬設定已經存在：

```text
HMItoPLC_UnitFirmnessNo
D1023
INT
```

但還需要完成兩件事：

1. `DUT_NoodleBasket` 增加：

```iecst
FirmnessNo : INT;   (* 1=硬、2=正常、3=軟 *)
CookTimeSet : INT;  (* 此麵篩本次煮麵時間 *)
```

2. `FB_AutoScheduler` 分配麵篩時設定時間：

```iecst
CASE NoodleBasket_1.FirmnessNo OF

    1:
        NoodleBasket_1.CookTimeSet := 400;

    2:
        NoodleBasket_1.CookTimeSet := 500;

    3:
        NoodleBasket_1.CookTimeSet := 600;

ELSE

    (* 未指定時使用正常硬度 *)
    NoodleBasket_1.CookTimeSet := 500;

END_CASE;
```

麵篩進入 `State 40` 後：

```iecst
IF NoodleBasket_1.State = 40 THEN

    TMR(
        Basket1CookTimer,
        NoodleBasket_1.CookTimeSet
    );

    IF Basket1CookTimer THEN

        NoodleBasket_1.State := 50;

    END_IF;

ELSE

    Basket1CookTimer := FALSE;

END_IF;
```

麵篩2、麵篩3也要各自有獨立 Timer：

```text
Basket1CookTimer
Basket2CookTimer
Basket3CookTimer
```

不能共用同一個 Timer，否則三個麵篩同時煮時會互相干擾。

若希望 HMI 可以調整三種時間，再建立三個固定 D 設定值，例如：

```text
CookTimeHardSet
CookTimeNormalSet
CookTimeSoftSet
```

D位址要先確認未占用，再正式指定。

## Turn 01a02dad-9415-7bc2-8feb-b7bffafbf357

### 使用者

給我整支


### AI（final_answer）

以下是已修正空白 `ELSIF` 問題的完整 `FB_ActionArbiter`：

```iecst
(* =========================================================
   FB_ActionArbiter
   全自動動作仲裁及手臂防碰撞控制

   功能：
   1. 將AutoBowlFlow的Request轉為安全Grant。
   2. Nachi、UR1及UR2進入共用區域前進行互鎖。
   3. CMD103拍照可與輸送帶及Nachi同時進行，
      但不可與UR2或UR1 CMD101同時執行。
   4. 碗比麵先到第二站時，仍允許對應麵篩
      繼續拿生麵、煮麵及甩麵。
   5. 對應麵篩煮麵期間，Nachi有空時可繼續
      替其他State 20麵篩放入生麵。
   ========================================================= *)


(* ---------------------------------------------------------
   1. 每個PLC Scan先清除所有Grant
   --------------------------------------------------------- *)

NoodleLoadGrant := FALSE;
NoodleShakeGrant := FALSE;

ConveyorRunGrant := FALSE;

BowlDropGrant := FALSE;
BowlDropGrantUnitID := 0;

UR1VisionGrant := FALSE;
UR1VisionGrantUnitID := 0;

NoodleDropGrant := FALSE;
NoodleDropGrantUnitID := 0;

UR1Grant := FALSE;
UR1GrantUnitID := 0;

UR2Grant := FALSE;
UR2GrantUnitID := 0;

SoupGrant := FALSE;
SoupGrantUnitID := 0;


(* ---------------------------------------------------------
   2. 找出倒麵Request所對應的麵篩狀態
   --------------------------------------------------------- *)

MatchingBasketFound := FALSE;
MatchingBasketState := 0;


IF NoodleDropRequest
   AND (NoodleDropRequestUnitID <> 0) THEN

    IF NoodleBasket_1.UnitID =
       NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_1.State;


    ELSIF NoodleBasket_2.UnitID =
          NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_2.State;


    ELSIF NoodleBasket_3.UnitID =
          NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_3.State;

    END_IF;

END_IF;


(* ---------------------------------------------------------
   3. 輸送帶運轉Grant

   CMD103不占用輸送帶區域，因此不阻擋輸送帶。
   Nachi拿生麵及甩麵也可在輸送途中執行。
   CMD101及CMD102執行時禁止輸送帶運轉。
   --------------------------------------------------------- *)

IF ConveyorRunRequest
   AND NOT UR2Active
   AND NOT
       (UR1Active AND
        (UR1CommandNo = 101)) THEN

    ConveyorRunGrant := TRUE;

END_IF;


(* ---------------------------------------------------------
   4. 落碗Grant

   BowlFlow已確認：
   1. 落碗位置為空
   2. 前一碗已到達X0.2
   3. 入口路段沒有其他碗
   --------------------------------------------------------- *)

IF BowlDropRequest
   AND NOT ConveyorRunRequest THEN

    BowlDropGrant := TRUE;
    BowlDropGrantUnitID :=
        BowlDropRequestUnitID;

END_IF;


(* ---------------------------------------------------------
   5. UR1 CMD103預先拍照Grant

   拍照可以與：
   - 輸送帶運轉
   - Nachi拿生麵
   - Nachi煮麵
   - Nachi甩麵

   同時執行。

   但不可與：
   - UR1 CMD101
   - UR2 CMD102
   同時執行。
   --------------------------------------------------------- *)

IF UR1VisionRequest
   AND NOT UR1Request
   AND NOT UR2Request
   AND NOT UR1Active
   AND NOT UR2Active THEN

    UR1VisionGrant := TRUE;
    UR1VisionGrantUnitID :=
        UR1VisionRequestUnitID;

END_IF;


(* ---------------------------------------------------------
   6. 注湯Grant

   注湯位於最右端站，與Nachi及拍照區域獨立。
   --------------------------------------------------------- *)

IF SoupRequest
   AND (RightmostStation = 40) THEN

    SoupGrant := TRUE;
    SoupGrantUnitID :=
        SoupRequestUnitID;

END_IF;


(* =========================================================
   7. 依最右端站別仲裁主要動作
   ========================================================= *)

CASE RightmostStation OF

    0:
        (* -------------------------------------------------
           輸送帶運送途中：
           利用空檔處理拿生麵或甩麵。

           優先順序：
           1. 拿生麵進鍋
           2. 拿熟麵並甩麵
           ------------------------------------------------- *)

        IF RobotIdle
           AND NOT NoodleZoneLocked
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN

            (* 第一優先：等待拿生麵進鍋 *)
            IF (NoodleBasket_1.State = 20)
               OR (NoodleBasket_2.State = 20)
               OR (NoodleBasket_3.State = 20) THEN

                NoodleLoadGrant := TRUE;


            (* 第二優先：煮麵完成，等待甩麵 *)
            ELSIF (NoodleBasket_1.State = 50)
               OR (NoodleBasket_2.State = 50)
               OR (NoodleBasket_3.State = 50) THEN

                NoodleShakeGrant := TRUE;

            END_IF;

        END_IF;


    20:
        (* -------------------------------------------------
           放麵及UR1站

           必須依序：
           1. 完成對應麵篩的煮麵
           2. 拿起熟麵並甩麵
           3. 將麵倒入碗
           4. UR1執行CMD101

           對應麵篩煮麵期間：
           Nachi若已回到Idle，可繼續替其他訂單
           將生麵放入State 20的麵篩。
           ------------------------------------------------- *)

        IF NoodleDropRequest
           AND MatchingBasketFound THEN

            (* -----------------------------------------
               對應麵篩State=20：
               等待拿生麵並放入鍋中
               ----------------------------------------- *)

            IF MatchingBasketState = 20 THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleLoadGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=30或40：

               State 30：
               對應麵篩正在執行放生麵動作。

               State 40：
               對應麵篩正在煮麵計時。

               如果Nachi已經回到Idle，而且還有其他
               State 20麵篩，繼續執行下一筆放生麵。

               MatchingBasket本身是State 30或40，
               所以FB_AutoNoodleAction會選擇其他
               State 20麵篩，不會重複選取。
               ----------------------------------------- *)

            ELSIF (MatchingBasketState = 30)
               OR (MatchingBasketState = 40) THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101))
                   AND
                       ((NoodleBasket_1.State = 20)
                        OR (NoodleBasket_2.State = 20)
                        OR (NoodleBasket_3.State = 20)) THEN

                    NoodleLoadGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=50：
               煮麵完成，等待拿起及甩麵
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 50 THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleShakeGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               State 60正在執行拿熟麵及甩麵，
               不符合其他條件時所有Grant維持FALSE。

               對應麵篩State=70：
               熟麵已甩好並停在安全等待位置，
               允許Nachi將熟麵倒入碗中。

               此時RobotIdle通常為FALSE，
               因此不判斷RobotIdle。
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 70 THEN

                IF NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleDropGrant := TRUE;
                    NoodleDropGrantUnitID :=
                        NoodleDropRequestUnitID;

                END_IF;

            (* State 80正在倒麵。
               不符合以上條件時所有Grant維持FALSE。 *)

            END_IF;


        (* ---------------------------------------------
           對應碗已完成放麵及CMD103，
           允許UR1執行CMD101。
           --------------------------------------------- *)

        ELSIF UR1Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN

            UR1Grant := TRUE;
            UR1GrantUnitID :=
                UR1RequestUnitID;

        END_IF;


    30:
        (* -------------------------------------------------
           UR2站：允許執行CMD102

           UR1與UR2只能擇一動作。
           Nachi占用干涉區時不可啟動UR2。
           ------------------------------------------------- *)

        IF UR2Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN

            UR2Grant := TRUE;
            UR2GrantUnitID :=
                UR2RequestUnitID;

        END_IF;

END_CASE;
```

## Turn 01a02dad-07bf-74c0-bf4b-bc7031b93ce7

### 使用者


# Files mentioned by the user:

## codex-clipboard-c5f4ebe2-b3ec-45a9-b5cc-162e661e9716.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-c5f4ebe2-b3ec-45a9-b5cc-162e661e9716.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

錯誤是因為 ISPSoft 不允許 `THEN` 後面只有註解。`State 60` 和 `State 80` 兩個分支沒有任何程式指令。

把 `MatchingBasketState = 50` 開始到內層 `END_IF`，改成下面這段：

```iecst
            (* -----------------------------------------
               對應麵篩State=50：
               煮麵完成，等待拿起及甩麵
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 50 THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleShakeGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               State 60正在甩麵，不符合以下條件，
               因此自然維持所有Grant為FALSE。
               
               對應麵篩State=70：
               熟麵已甩好並停在安全等待位置，
               允許Nachi將熟麵倒入碗中。
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 70 THEN

                IF NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleDropGrant := TRUE;
                    NoodleDropGrantUnitID :=
                        NoodleDropRequestUnitID;

                END_IF;

            (* State 80正在倒麵，不符合以上條件，
               自然維持所有Grant為FALSE。 *)

            END_IF;
```

也就是刪掉這兩個空分支：

```iecst
ELSIF MatchingBasketState = 60 THEN
    (* 只有註解 *)

ELSIF MatchingBasketState = 80 THEN
    (* 只有註解 *)
```

這樣第323行與第348行的錯誤會一起消失，功能不受影響。

## Turn 01a02daa-0495-78e1-a207-b7993d688fdc

### 使用者


# Files pasted by the user:

## "(* ========================================================= FB_ActionArbiter 全…": C:\Users\Administrator\.codex/attachments/5061b1ce-1c82-4e06-b100-ccab990cbf6f/pasted-text.txt

## My request:
整枝


### AI（commentary）

我會以你剛貼的最新版 `FB_ActionArbiter` 為底，保留現有所有互鎖，只修改 `RightmostStation = 20` 等待煮麵時可繼續裝填其他 State 20 麵篩，然後給你整支可直接貼入的程式。

### AI（final_answer）

以下是完整 `FB_ActionArbiter`。已加入：當對應麵篩處於 State 30／40 時，Nachi 有空就繼續替其他 State 20 麵篩放生麵。

```iecst
(* =========================================================
   FB_ActionArbiter
   全自動動作仲裁及手臂防碰撞控制

   功能：
   1. 將AutoBowlFlow的Request轉為安全Grant。
   2. Nachi、UR1及UR2進入共用區域前進行互鎖。
   3. CMD103拍照可與輸送帶及Nachi同時進行，
      但不可與UR2或UR1 CMD101同時執行。
   4. 碗比麵先到第二站時，仍允許對應麵篩
      繼續拿生麵、煮麵及甩麵。
   5. 對應麵篩煮麵期間，Nachi有空時可繼續
      替其他State 20麵篩放入生麵。
   ========================================================= *)


(* ---------------------------------------------------------
   1. 每個PLC Scan先清除所有Grant
   --------------------------------------------------------- *)

NoodleLoadGrant := FALSE;
NoodleShakeGrant := FALSE;

ConveyorRunGrant := FALSE;

BowlDropGrant := FALSE;
BowlDropGrantUnitID := 0;

UR1VisionGrant := FALSE;
UR1VisionGrantUnitID := 0;

NoodleDropGrant := FALSE;
NoodleDropGrantUnitID := 0;

UR1Grant := FALSE;
UR1GrantUnitID := 0;

UR2Grant := FALSE;
UR2GrantUnitID := 0;

SoupGrant := FALSE;
SoupGrantUnitID := 0;


(* ---------------------------------------------------------
   2. 找出倒麵Request所對應的麵篩狀態
   --------------------------------------------------------- *)

MatchingBasketFound := FALSE;
MatchingBasketState := 0;


IF NoodleDropRequest
   AND (NoodleDropRequestUnitID <> 0) THEN

    IF NoodleBasket_1.UnitID =
       NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_1.State;


    ELSIF NoodleBasket_2.UnitID =
          NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_2.State;


    ELSIF NoodleBasket_3.UnitID =
          NoodleDropRequestUnitID THEN

        MatchingBasketFound := TRUE;
        MatchingBasketState :=
            NoodleBasket_3.State;

    END_IF;

END_IF;


(* ---------------------------------------------------------
   3. 輸送帶運轉Grant

   CMD103不占用輸送帶區域，因此不阻擋輸送帶。
   Nachi拿生麵及甩麵也可在輸送途中執行。
   CMD101及CMD102執行時禁止輸送帶運轉。
   --------------------------------------------------------- *)

IF ConveyorRunRequest
   AND NOT UR2Active
   AND NOT
       (UR1Active AND
        (UR1CommandNo = 101)) THEN

    ConveyorRunGrant := TRUE;

END_IF;


(* ---------------------------------------------------------
   4. 落碗Grant

   BowlFlow已確認：
   1. 落碗位置為空
   2. 前一碗已到達X0.2
   3. 入口路段沒有其他碗
   --------------------------------------------------------- *)

IF BowlDropRequest
   AND NOT ConveyorRunRequest THEN

    BowlDropGrant := TRUE;
    BowlDropGrantUnitID :=
        BowlDropRequestUnitID;

END_IF;


(* ---------------------------------------------------------
   5. UR1 CMD103預先拍照Grant

   拍照可以與：
   - 輸送帶運轉
   - Nachi拿生麵
   - Nachi煮麵
   - Nachi甩麵

   同時執行。

   但不可與：
   - UR1 CMD101
   - UR2 CMD102
   同時執行。
   --------------------------------------------------------- *)

IF UR1VisionRequest
   AND NOT UR1Request
   AND NOT UR2Request
   AND NOT UR1Active
   AND NOT UR2Active THEN

    UR1VisionGrant := TRUE;
    UR1VisionGrantUnitID :=
        UR1VisionRequestUnitID;

END_IF;


(* ---------------------------------------------------------
   6. 注湯Grant

   注湯位於最右端站，與Nachi及拍照區域獨立。
   --------------------------------------------------------- *)

IF SoupRequest
   AND (RightmostStation = 40) THEN

    SoupGrant := TRUE;
    SoupGrantUnitID :=
        SoupRequestUnitID;

END_IF;


(* =========================================================
   7. 依最右端站別仲裁主要動作
   ========================================================= *)

CASE RightmostStation OF

    0:
        (* -------------------------------------------------
           輸送帶運送途中：
           利用空檔處理拿生麵或甩麵。

           優先順序：
           1. 拿生麵進鍋
           2. 拿熟麵並甩麵
           ------------------------------------------------- *)

        IF RobotIdle
           AND NOT NoodleZoneLocked
           AND NOT UR2Active
           AND NOT
               (UR1Active AND
                (UR1CommandNo = 101)) THEN

            (* 第一優先：等待拿生麵進鍋 *)
            IF (NoodleBasket_1.State = 20)
               OR (NoodleBasket_2.State = 20)
               OR (NoodleBasket_3.State = 20) THEN

                NoodleLoadGrant := TRUE;


            (* 第二優先：煮麵完成，等待甩麵 *)
            ELSIF (NoodleBasket_1.State = 50)
               OR (NoodleBasket_2.State = 50)
               OR (NoodleBasket_3.State = 50) THEN

                NoodleShakeGrant := TRUE;

            END_IF;

        END_IF;


    20:
        (* -------------------------------------------------
           放麵及UR1站

           必須依序：
           1. 完成對應麵篩的煮麵
           2. 拿起熟麵並甩麵
           3. 將麵倒入碗
           4. UR1執行CMD101

           對應麵篩煮麵期間：
           Nachi若已回到Idle，可繼續替其他訂單
           將生麵放入State 20的麵篩。
           ------------------------------------------------- *)

        IF NoodleDropRequest
           AND MatchingBasketFound THEN

            (* -----------------------------------------
               對應麵篩State=20：
               等待拿生麵並放入鍋中
               ----------------------------------------- *)

            IF MatchingBasketState = 20 THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleLoadGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=30或40：

               State 30：
               對應麵篩正在執行放生麵動作。

               State 40：
               對應麵篩正在煮麵計時。

               如果Nachi已經回到Idle，而且還有其他
               State 20麵篩，繼續執行下一筆放生麵。

               MatchingBasket本身是State 30或40，
               因此FB_AutoNoodleAction會選到其他
               State 20的麵篩，不會重複選取。
               ----------------------------------------- *)

            ELSIF (MatchingBasketState = 30)
               OR (MatchingBasketState = 40) THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101))
                   AND
                       ((NoodleBasket_1.State = 20)
                        OR (NoodleBasket_2.State = 20)
                        OR (NoodleBasket_3.State = 20)) THEN

                    NoodleLoadGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=50：
               煮麵完成，等待拿起及甩麵
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 50 THEN

                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleShakeGrant := TRUE;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=60：
               Nachi正在拿起熟麵並甩麵。
               等待D12103.0完成訊號。
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 60 THEN

                (* 等待甩麵完成，不發出其他Grant *)


            (* -----------------------------------------
               對應麵篩State=70：
               熟麵已甩好並停在安全等待位置，
               允許Nachi將熟麵倒入碗中。

               此時RobotIdle通常為FALSE，
               因此不判斷RobotIdle。
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 70 THEN

                IF NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT
                       (UR1Active AND
                        (UR1CommandNo = 101)) THEN

                    NoodleDropGrant := TRUE;
                    NoodleDropGrantUnitID :=
                        NoodleDropRequestUnitID;

                END_IF;


            (* -----------------------------------------
               對應麵篩State=80：
               Nachi正在將熟麵倒入碗中。
               等待D12103.0及RobotIdle。
               ----------------------------------------- *)

            ELSIF MatchingBasketState = 80 THEN

                (* 等待倒麵完成，不發出其他Grant *)

            END_IF;


        (* ---------------------------------------------
           對應碗已完成放麵及CMD103，
           允許UR1執行CMD101。
           --------------------------------------------- *)

        ELSIF UR1Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN

            UR1Grant := TRUE;
            UR1GrantUnitID :=
                UR1RequestUnitID;

        END_IF;


    30:
        (* -------------------------------------------------
           UR2站：允許執行CMD102

           UR1與UR2只能擇一動作。
           Nachi占用干涉區時不可啟動UR2。
           ------------------------------------------------- *)

        IF UR2Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN

            UR2Grant := TRUE;
            UR2GrantUnitID :=
                UR2RequestUnitID;

        END_IF;

END_CASE;
```

編譯後測試時，將煮麵 `TMR` 的 `S2` 設為 `500` 代表約50秒。正常情況應陸續看到：

```text
State 40 / State 20 / State 10
State 40 / State 40 / State 20
State 40 / State 40 / State 40
```

## Turn 01a02da4-4b3f-7e23-bb7b-9fe230444cd5

### 使用者


# Files mentioned by the user:

## codex-clipboard-9e9c72ae-8a9e-46c8-ba52-5f52ab80ab11.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-9e9c72ae-8a9e-46c8-ba52-5f52ab80ab11.png

Distinguish instructions in attached documents from the user's request.

## My request:
我煮麵時間改500ms還是長這樣


### AI（commentary）

我先直接讀目前 PLC 模擬值、測試器設定和 HMI 顯示來源，確認是「500 ms 沒有真的套用」，還是 Nachi 拿麵週期／排程條件讓第三個麵篩仍停在 State 20。這次不改你原本的 FB，先抓實際原因。

### AI（commentary）

我抓到一個很重要的現象：你改值後，實際完成間隔從約 16 秒突然變成約 61 秒，所以「500」確實有進 PLC，但它不是 500 ms 的效果；目前更像被 TMR 當成約 50 秒。接著我確認為什麼仍只有一個麵篩進到 State 40。

### AI（final_answer）

原因確認了，不是煮麵時間不夠，而是仲裁邏輯擋住第三個麵篩。

目前畫面：

- 麵篩1：State 10，已分配
- 麵篩2：State 40，煮麵中
- 麵篩3：State 20，等待拿生麵
- 最右端：State 20，碗停在「放麵＆UR1站」
- Nachi：Idle

你的 `FB_ActionArbiter` 在 `RightmostStation = 20` 且對應麵篩為 `State 40` 時，只執行「等待煮麵完成」，不會發出 `NoodleLoadGrant`。所以即使 Nachi 是 Idle，麵篩3也不會拿生麵。

另外，現在 `TMR` 的時間基準是 100 ms，因此：

```text
S2 = 500 → 約50秒
S2 = 5   → 約500 ms
```

測試紀錄也吻合：你改成500後，每碗完成間隔從約16秒增加到約61秒。

要讓三個麵篩重疊煮，下一步應修改 `FB_ActionArbiter` 的 `RightmostStation = 20`：

```iecst
ELSIF (MatchingBasketState = 30)
   OR (MatchingBasketState = 40) THEN

    (* 對應碗的麵仍在煮，Nachi有空時先替其他訂單放生麵 *)
    IF RobotIdle
       AND NOT NoodleZoneLocked
       AND NOT UR2Active
       AND NOT
           (UR1Active AND
            (UR1CommandNo = 101))
       AND
           ((NoodleBasket_1.State = 20)
            OR (NoodleBasket_2.State = 20)
            OR (NoodleBasket_3.State = 20)) THEN

        NoodleLoadGrant := TRUE;

    END_IF;
```

這樣麵篩2煮麵期間，Nachi會繼續把麵放進麵篩3；有更多已分配任務時，也會再處理麵篩1。這才會看到三個麵篩同時進入 `State 40`。

## Turn 01a02da0-ca09-7913-99c7-37c1b779f125

### 使用者

所以現在沒看到三個麵杓都有麵可能是因為煮麵占用的時間不夠久


### AI（final_answer）

對，很可能是煮麵時間太短。

三個麵篩是由同一支 Nachi 依序放入生麵：

`麵篩1下麵 → Nachi完成 → 麵篩2下麵 → 完成 → 麵篩3下麵`

如果麵篩1在麵篩3尚未完成下麵前就已煮好，畫面自然不會同時看到三個麵篩都有麵。

可以在模擬時暫時把煮麵時間延長到例如30～60秒。若看到：

- 麵篩1：State 40
- 麵篩2：State 40
- 麵篩3：State 40

就能證明三麵篩重疊煮麵正常。

如果延長後仍然只有一個麵篩進入 State 40，才需要檢查 AutoScheduler 是否只分配第一個麵篩。正式煮麵時間不要為了測試而改掉，最好另外設一個「模擬煮麵時間」。

## Turn 01a02d9f-e1a7-7da3-bd30-da5c92e6330c

### 使用者

我們現在煮麵的動作是會連續下的嗎


### AI（final_answer）

是，現在是「連續下麵、重疊煮麵」，但不是三個麵篩同一瞬間動作。

流程是：

1. Nachi把第一份生麵放入麵篩1。
2. Nachi完成並回到 Idle。
3. 若麵篩2已有訂單，立刻放第二份。
4. 接著再放麵篩3。
5. 三個麵篩可同時各自計時煮麵。

因此不必等第一碗完成，才開始第二碗。但以下情況會暫停連續下麵：

- 三個麵篩都被占用。
- Nachi尚未完成上一個動作。
- UR1正在執行CMD101或UR2正在動作，造成共用區域鎖定。
- 沒有後續訂單。

目前動作優先順序仍是：

`拿生麵下鍋 → 拿熟麵甩麵 → 倒麵進碗`

所以1000筆測試中，只要有空麵篩且安全條件成立，PLC就會繼續安排下一份生麵。

## Turn 01a02d94-c92c-7f92-bbc8-a15cf5be0047

### 使用者

好麻煩我希望的是一件自動狂送訂單我可以從介面看到每個編號到哪邊


### AI（commentary）

懂了，你要的不是手動按站點，而是「按一次開始，系統自動連續送訂單、模擬所有設備與站點」，HMI只負責即時顯示每個 UnitID 現在在哪裡。我要把工作台改成這種壓力測試模式，手動按 X0.1～X0.4 收到進階區。

### 使用者

跟我們剛剛跑1000次一樣


### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_1000_order_endurance_test.py：update

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_1000_order_endurance_test.py：update

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\simulation_control.py：update

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\ui_auto_page.py：update

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\ui_auto_page.py：update
- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\hmi_003_interface_test.py：update

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_1000_order_endurance_test.py：update

### AI（commentary）

現在已改成直接呼叫我們剛才驗證過的同一支 1000 碗耐久測試，不再另外做一套簡化邏輯。HMI會讀取測試器輸出的即時狀態表，把每個 UnitID 標成「尚未送出、FIFO等待、哪段輸送中、完成」。我正在做最後的相容性測試。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\ui_auto_page.py：update

### AI（commentary）

介面測試已通過，而且確定使用的就是先前那支 `1000碗滾動FIFO＋多站流水線耐久測試`。現在重開後，首頁會直接是「一鍵自動測試」，表格會列出每一個碗編號與目前位置。

### AI（final_answer）

已改成和剛才相同的1000筆耐久測試。

現在操作只剩：

1. 測試碗數預設 `1000`。
2. 按「一鍵開始自動狂送訂單」。
3. 之後不用再操作，系統會自動：

   - 滾動補充訂單
   - 自動落碗
   - 模擬 IPC、UR1、UR2、Nachi
   - 自動推進輸送帶四站
   - 檢查 FIFO 與完成順序

同一頁表格會列出每個 UnitID，目前狀態包含：

- 尚未送出
- FIFO等待
- 落碗→放麵／UR1
- 放麵／UR1→UR2
- UR2→注湯
- 完成

上方也會顯示已送數量、完成數量、FIFO、進度及最終 PASS／FAIL。HMI已重新開啟。

