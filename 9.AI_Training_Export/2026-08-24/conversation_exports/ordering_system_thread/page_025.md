# 規劃自建點餐系統——原聊天匯出第 025 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a01879-c88b-7190-b748-38c6cb0cdd31

### 使用者

要給HMI才寫在全域變數


### AI（final_answer）

對，你這個規劃可以：只有需要給HMI讀寫、或通訊PRG直接存取的資料才放全域變數。

這些自動流程內部訊號全部放在 `AutoMain` 的區域變數：

```pascal
Auto_RightmostStation : INT;
(* 最右端尚未完成的碗所在站 *)

Auto_UR1Active : BOOL;
(* UR1指令已送出，等待201完成回覆 *)

Auto_UR2Active : BOOL;
(* UR2指令已送出，等待202完成回覆 *)

Auto_NoodleZoneLocked : BOOL;
(* Nachi煮麵手臂目前占用干涉區 *)

Auto_NoodleLoadGrant : BOOL;
(* 仲裁器允許拿生麵進鍋 *)

Auto_NoodleShakeGrant : BOOL;
(* 仲裁器允許拿熟麵並甩麵 *)
```

然後在 `AutoMain` 裡用接腳把各FB串起來即可：

```text
AutoBowlFlow輸出 RightmostStation
                ↓
Auto_RightmostStation
                ↓
FB_ActionArbiter
                ↓
Auto_NoodleLoadGrant / Auto_NoodleShakeGrant
                ↓
後續Nachi動作執行FB
```

現有的感測器、IPC回覆201／202、`Robot_Idle` 等資料可以維持原本全域變數；新的自動控制中間結果不必額外占用D暫存器。

但要確保在 `Machine_Mode = 2` 時，UR1、UR2只能經過自動流程的允許訊號啟動，不能有其他PRG繞過 `FB_ActionArbiter` 下指令。

## Turn 01a01878-c88e-7a52-933a-fdfba415ca97

### 使用者

應該寫在區域變數也可以拔


### AI（final_answer）

可以，若只在 `AutoMain` 裡面的FB之間傳遞，就放在 `AutoMain` 區域變數即可。

建議這樣分：

```pascal
(* AutoMain 區域變數 *)
Auto_NoodleLoadGrant  : BOOL;
Auto_NoodleShakeGrant : BOOL;
```

這兩個只是 `FB_ActionArbiter` 傳給後續動作FB的允許訊號，放區域最合適。

以下建議保留全域：

```pascal
Auto_RightmostStation : INT;
Auto_UR1Active        : BOOL;
Auto_UR2Active        : BOOL;
Auto_NoodleZoneLocked : BOOL;
```

原因是：

- `RightmostStation` 之後會由輸送帶／感測器流程更新。
- `UR1Active`、`UR2Active` 會由IPC通訊的CMD送出及201、202完成回覆更新。
- `NoodleZoneLocked` 是三支手臂共同使用的防撞連鎖。

它們不只屬於 `AutoMain`，其他PRG也要讀寫，所以用全域比較安全。

簡單判斷方式：

```text
只在AutoMain內部傳遞 → 區域變數
其他PRG、通訊或HMI也要使用 → 全域變數
FB本身的接腳 → FB的VAR_INPUT／VAR_OUTPUT
```

因此現在先把兩個 Grant 建立在 `AutoMain` 區域變數，其他四個建立為全域變數。

## Turn 01a01876-6840-7e01-81a8-6e9718f7f69c

### 使用者

註釋寫完了再來呢


### AI（final_answer）

接下來先寫 `FB_ActionArbiter` 第一階段程式：只仲裁「拿生麵進鍋」與「拿熟麵甩麵」，暫時不發手臂CMD。

把以下程式放進 `FB_ActionArbiter` 的 ST 內容：

```pascal
(* =========================================================
   全自動動作仲裁器－第一階段
   功能：
   1. 每個掃描週期先關閉所有允許訊號
   2. 輸送帶運送途中，利用空檔處理煮麵相關動作
   3. 拿生麵進鍋優先於拿熟麵甩麵
   4. Nachi、UR1、UR2必須符合安全條件
   ========================================================= *)


(* 每次PLC掃描先清除輸出，避免允許訊號一直保持 *)
NoodleLoadGrant := FALSE;
NoodleShakeGrant := FALSE;


(* ---------------------------------------------------------
   RightmostStation = 0：
   目前沒有碗停在工作站，或輸送帶正在運送途中，
   此時可利用空檔執行煮麵手臂動作。
   --------------------------------------------------------- *)
IF RightmostStation = 0 THEN

    (* Nachi必須待機，UR1、UR2不可正在動作，
       而且煮麵手臂干涉區不可被占用 *)
    IF RobotIdle
       AND NOT UR1Active
       AND NOT UR2Active
       AND NOT NoodleZoneLocked THEN

        (* 第一優先：有麵篩等待拿生麵進鍋
           State = 20 表示已排定，等待煮麵手臂拿生麵 *)
        IF (NoodleBasket_1.State = 20)
           OR (NoodleBasket_2.State = 20)
           OR (NoodleBasket_3.State = 20) THEN

            NoodleLoadGrant := TRUE;

        (* 第二優先：沒有生麵要進鍋時，
           才檢查是否有煮好的麵等待拿起及甩麵
           State = 50 表示煮麵完成，等待甩麵 *)
        ELSIF (NoodleBasket_1.State = 50)
           OR (NoodleBasket_2.State = 50)
           OR (NoodleBasket_3.State = 50) THEN

            NoodleShakeGrant := TRUE;

        END_IF;

    END_IF;

END_IF;
```

這段目前只會產生兩個「允許」：

```text
NoodleLoadGrant  = 可以開始拿生麵進鍋
NoodleShakeGrant = 可以開始拿熟麵並甩麵
```

不會直接呼叫 `NashiRobot_Exchange`，也不會改變麵篩狀態。

下一步是在 `AutoMain` 的 `ActionArbiter_Inst` 接腳接上：

```text
RightmostStation ← Auto_RightmostStation
RobotIdle        ← 既有的 Robot_Idle
UR1Active        ← Auto_UR1Active
UR2Active        ← Auto_UR2Active
NoodleZoneLocked ← Auto_NoodleZoneLocked

NoodleLoadGrant  → Auto_NoodleLoadGrant
NoodleShakeGrant → Auto_NoodleShakeGrant
```

若這些全域變數還沒有，就先新增：

```pascal
Auto_RightmostStation : INT;
Auto_UR1Active        : BOOL;
Auto_UR2Active        : BOOL;
Auto_NoodleZoneLocked : BOOL;
Auto_NoodleLoadGrant  : BOOL;
Auto_NoodleShakeGrant : BOOL;
```

完成後先編譯；這一步通過，我們下一步就寫「收到 `NoodleLoadGrant` 後，找出是哪一個麵篩，呼叫既有 `NashiRobot_Exchange` 執行 Action 1」。

## Turn 01a01872-e215-7442-a340-b17598909173

### 使用者

FB_ActionArbiter 這個FB給註釋


### AI（final_answer）

`FB_ActionArbiter` 的中文註釋可以寫：

```pascal
(* 全自動動作仲裁器：
   根據輸送帶最右端碗所在站別、Nachi煮麵手臂狀態、
   UR1及UR2執行狀態，決定目前允許執行哪一個動作。

   本FB只負責發出動作允許訊號，不直接控制手臂、輸送帶或電磁閥，
   避免Nachi、UR1及UR2同時進入干涉區而發生碰撞。

   動作優先順序：
   1. 煮麵手臂拿生麵進鍋
   2. 煮麵手臂拿熟麵並甩麵至待機位置
   3. 最右端停站碗的製作動作
      40 = 注湯／完成出料
      30 = UR2
      20 = 放麵完成後執行UR1
      10 = 落碗

   當輸送帶尚未到站時，可利用空檔進行拿生麵進鍋，
   或拿熟麵、甩麵並停在待機位置。
*)
```

FB介面變數註釋：

```pascal
VAR_INPUT
    RightmostStation : INT;
    (* 輸送帶上最右端尚未完成的碗所在站：
       0  = 沒有碗停站／輸送帶運轉中
       10 = 落碗站
       20 = 放麵及UR1站
       30 = UR2站
       40 = 注湯及成品出料站
    *)

    RobotIdle : BOOL;
    (* Nachi煮麵手臂待機狀態：
       TRUE  = 手臂目前沒有執行動作
       FALSE = 手臂正在執行動作
    *)

    UR1Active : BOOL;
    (* UR1動作執行狀態：
       PLC送出UR1指令後設為TRUE；
       收到UR1完成回覆201後設為FALSE
    *)

    UR2Active : BOOL;
    (* UR2動作執行狀態：
       PLC送出UR2指令後設為TRUE；
       收到UR2完成回覆202後設為FALSE
    *)

    NoodleZoneLocked : BOOL;
    (* 煮麵手臂干涉區占用狀態：
       TRUE  = Nachi正在干涉區內移動，禁止UR1及UR2啟動
       FALSE = Nachi已離開干涉區，其他手臂可依條件啟動

       熟麵甩好並停在等待位置時可以為FALSE；
       要執行倒麵進碗前，必須重新設為TRUE。
    *)
END_VAR
```

目前第一階段的輸出：

```pascal
VAR_OUTPUT
    NoodleLoadGrant : BOOL;
    (* 允許煮麵手臂拿生麵盒並將生麵放入指定麵篩 *)

    NoodleShakeGrant : BOOL;
    (* 允許煮麵手臂拿起已煮好的麵、甩麵，
       並停在等待倒麵的位置 *)
END_VAR
```

之後處理四個輸送帶站時，再加入：

```pascal
    NoodleDropGrant : BOOL;
    (* 允許將已甩好的麵倒入到位的碗中 *)

    UR1Grant : BOOL;
    (* 允許UR1啟動；必須先確認該碗已經完成放麵 *)

    UR2Grant : BOOL;
    (* 允許UR2啟動 *)

    SoupGrant : BOOL;
    (* 允許最右端碗執行注湯 *)

    BowlDropGrant : BOOL;
    (* 允許落下一個新碗 *)
```

最短的符號表註釋則寫：

```text
FB_ActionArbiter：全自動動作仲裁及手臂防碰撞允許控制
```

重點是這個FB只回答「現在誰可以做」，實際下CMD及等待完成回覆交給後續的動作執行FB。

## Turn 01a0186f-2922-7183-951e-49ad04906158

### 使用者

40=注湯&結束??


### AI（final_answer）

對，`40` 代表「碗目前位於最右端的注湯／出料站」，不是表示注湯和訂單完成同時發生。

建議流程：

```text
RightmostStation = 40
        ↓
SoupDone = FALSE
        ↓
執行注湯
        ↓
收到注湯完成訊號
        ↓
SoupDone := TRUE
JobState := 100       // 此碗製作完成
回傳 UnitID 給 HMI
        ↓
碗離開感測器
        ↓
RightmostStation := 0
```

所以站別定義維持：

```pascal
0  := 輸送中／目前沒有碗停站
10 := 落碗站
20 := 放麵及UR1站
30 := UR2站
40 := 注湯及完成出料站
```

更精確的註釋可以寫：

```pascal
RightmostStation : INT;
(* 最右端尚未完成的碗所在站：
   0  = 無碗停站／輸送帶移動中
   10 = 落碗站
   20 = 放麵及UR1站
   30 = UR2站
   40 = 注湯／成品出料站
*)
```

真正是否完成，仍由該碗的：

```pascal
UnitFIFO.Units[x].SoupDone
UnitFIFO.Units[x].JobState
```

來判斷。也就是 `40 ≠ 已完成`，而是「現在輪到最終注湯站處理」。

## Turn 01a01852-f129-7201-8872-f6340d54e916

### 使用者


# Files mentioned by the user:

## codex-clipboard-22ca8265-c89f-4b6a-b081-7a905277e5b5.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-22ca8265-c89f-4b6a-b081-7a905277e5b5.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這個呼叫順序正確：

```text
網路1：FB_AutoScheduler
網路2：FB_ActionArbiter
```

接下來在 `FB_ActionArbiter` 建立第一階段介面。

### VAR_INPUT

```pascal
RightmostStation : INT;   (* 0=運送中，10=落碗，20=放麵&UR1，30=UR2，40=注湯 *)
RobotIdle        : BOOL;  (* 既有Nachi Robot_Idle *)
UR1Active        : BOOL;  (* UR1命令已發出，尚未收到201 *)
UR2Active        : BOOL;  (* UR2命令已發出，尚未收到202 *)
NoodleZoneLocked : BOOL;  (* Nachi正在干涉區內動作 *)
```

### VAR_OUTPUT

```pascal
NoodleLoadGrant  : BOOL;  (* 允許拿生麵進鍋 *)
NoodleShakeGrant : BOOL;  (* 允許拿熟麵並甩麵 *)
```

現在先建立這七個變數。後面的：

```text
NoodleDropGrant
UR1Grant
UR2Grant
SoupGrant
BowlDropGrant
```

等 `AutoBowlFlow` 建立四站請求後再加入。

`AutoMain` 之後會把現有訊號接到輸入端，並把兩個 Grant 輸出接到自動動作控制。

## Turn 01a01850-9b49-7a10-8717-fa2021664d04

### 使用者

OK


### AI（final_answer）

下一步建立：

```text
名稱：FB_ActionArbiter
類型：功能塊 FB
語言：ST
```

目前先保持空白，不建立變數。

在 `AutoMain` 區域變數新增：

```pascal
ActionArbiter_Inst : FB_ActionArbiter;
```

在 `AutoScheduler_Inst` 下方新增第二個網路：

```text
Machine_Mode = 2
──────────────[ ActionArbiter_Inst ]
                 En
```

呼叫順序保持：

```text
網路1：AutoScheduler_Inst
網路2：ActionArbiter_Inst
```

這樣每個掃描週期會先更新訂單與麵篩狀態，再進行動作仲裁。完成並編譯後，下一步才加入仲裁器的輸入、輸出及四站優先邏輯。

## Turn 01a0184f-b61c-7440-bc45-1aec002c191b

### 使用者


# Files mentioned by the user:

## codex-clipboard-9200a881-ad82-4bef-acb4-dfaf0b1d815d.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-9200a881-ad82-4bef-acb4-dfaf0b1d815d.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這個畫法正確：

- `AutoScheduler_Inst` 類型是 `FB_AutoScheduler`
- `Machine_Mode = 2` 的比較結果接到 FB 的 `En`
- `Eno` 不接沒問題
- Mode 2期間會每個掃描週期持續執行排程器

現在請做兩件事：

1. 編譯確認沒有錯誤。
2. 編譯成功後，刪除或停用原本的 `AutoScheduler [PRG,ST]`，避免兩份排程同時執行。

紅色虛線外框看起來是目前選取中的功能塊，不一定代表錯誤；以編譯結果為準。

下一步建立：

```text
FB_ActionArbiter
類型：FB
語言：ST
```

再由這支 `AutoMain` 的下一個網路，在 `Machine_Mode = 2` 時持續呼叫。

## Turn 01a0184c-c0f4-7c61-becc-5ea3f1118750

### 使用者

給我程式


### AI（final_answer）

先建立 `FB_AutoScheduler [FB,ST]`，它沒有額外輸入輸出；由 `AutoMain` 的 `Machine_Mode = 2` 接點控制 `En`。

### FB區域變數

```pascal
CurrentUnitIndex : INT;
SelectedCookTime : INT;
Assigned         : BOOL;

StartSearchIndex : INT;
StartSearchCount : INT;
StartSelected    : BOOL;
```

### FB_AutoScheduler完整程式

```pascal
(* =========================================================
   FB：FB_AutoScheduler

   功能：
   1. 將FIFO等待訂單分配給空閒麵篩
   2. 根據軟硬度設定煮麵時間
   3. 按照FIFO順序產生下一筆拿生麵請求

   注意：
   1. 此FB只在Machine_Mode = 2時由AutoMain呼叫
   2. 此FB不判斷Robot_Idle
   3. 此FB不啟動任何實際機械動作
   4. State 20只代表等待ActionArbiter許可
   ========================================================= *)


(* 每次CALL先清除本次掃描的暫存結果 *)
Assigned := FALSE;
StartSelected := FALSE;
SelectedCookTime := 0;


(* =========================================================
   第一部分：將FIFO訂單分配給空閒麵篩
   ========================================================= *)

IF UnitFIFO.Count > 0 THEN

    (* 取得下一筆尚未分配麵篩的訂單 *)
    CurrentUnitIndex := UnitFIFO.CookIndex;


    (* JobState = 10：訂單等待分配麵篩 *)
    IF UnitFIFO.Units[CurrentUnitIndex].JobState = 10 THEN


        (* -------------------------------------------------
           根據FirmnessNo選擇TMR的S2設定值

           1 = 硬麵
           2 = 正常
           3 = 軟麵
           ------------------------------------------------- *)

        CASE UnitFIFO.Units[CurrentUnitIndex].FirmnessNo OF

            1:
                SelectedCookTime := CookTime_Hard_Set;

            2:
                SelectedCookTime := CookTime_Normal_Set;

            3:
                SelectedCookTime := CookTime_Soft_Set;

        ELSE

            (* CMD70已檢查，正常不會進入這裡 *)
            SelectedCookTime := CookTime_Normal_Set;

        END_CASE;



        (* -------------------------------------------------
           尋找空閒麵篩
           固定分配順序：1 → 2 → 3
           ------------------------------------------------- *)


        (* ---------- 麵篩1 ---------- *)
        IF NoodleBasket_1.State = 0 THEN

            NoodleBasket_1.UnitID :=
                UnitFIFO.Units[CurrentUnitIndex].UnitID;

            NoodleBasket_1.NoodleCabinetNo :=
                UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;

            NoodleBasket_1.FirmnessNo :=
                UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;

            NoodleBasket_1.CookTimeSet :=
                SelectedCookTime;

            (* 記錄這碗使用麵篩1 *)
            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 1;

            (* 所有資料寫完後才改State *)
            NoodleBasket_1.State := 10;

            Assigned := TRUE;



        (* ---------- 麵篩2 ---------- *)
        ELSIF NoodleBasket_2.State = 0 THEN

            NoodleBasket_2.UnitID :=
                UnitFIFO.Units[CurrentUnitIndex].UnitID;

            NoodleBasket_2.NoodleCabinetNo :=
                UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;

            NoodleBasket_2.FirmnessNo :=
                UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;

            NoodleBasket_2.CookTimeSet :=
                SelectedCookTime;

            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 2;

            NoodleBasket_2.State := 10;

            Assigned := TRUE;



        (* ---------- 麵篩3 ---------- *)
        ELSIF NoodleBasket_3.State = 0 THEN

            NoodleBasket_3.UnitID :=
                UnitFIFO.Units[CurrentUnitIndex].UnitID;

            NoodleBasket_3.NoodleCabinetNo :=
                UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;

            NoodleBasket_3.FirmnessNo :=
                UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;

            NoodleBasket_3.CookTimeSet :=
                SelectedCookTime;

            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 3;

            NoodleBasket_3.State := 10;

            Assigned := TRUE;

        END_IF;



        (* -------------------------------------------------
           成功分配後更新訂單及CookIndex
           ------------------------------------------------- *)

        IF Assigned THEN

            (* JobState = 20：訂單已進入處理中 *)
            UnitFIFO.Units[CurrentUnitIndex].JobState := 20;

            (* 指向下一筆等待分配的訂單 *)
            UnitFIFO.CookIndex := UnitFIFO.CookIndex + 1;

            (* 環形FIFO索引回到0 *)
            IF UnitFIFO.CookIndex >= UnitFIFO.Capacity THEN
                UnitFIFO.CookIndex := 0;
            END_IF;

        END_IF;

    END_IF;

END_IF;



(* =========================================================
   第二部分：按照FIFO順序產生拿生麵請求

   State 10：
   已分配麵篩，尚未成為目前等待中的煮麵任務

   State 20：
   已成為下一筆拿生麵請求，等待ActionArbiter許可

   State 30：
   拿生麵進鍋動作執行中
   ========================================================= *)


(* 目前只能有一個麵篩處於State 20或30 *)
IF (NoodleBasket_1.State <> 20)
   AND (NoodleBasket_1.State <> 30)
   AND (NoodleBasket_2.State <> 20)
   AND (NoodleBasket_2.State <> 30)
   AND (NoodleBasket_3.State <> 20)
   AND (NoodleBasket_3.State <> 30) THEN


    (* 從FIFO最前端開始搜尋 *)
    StartSearchIndex := UnitFIFO.Head;
    StartSearchCount := 0;


    WHILE (StartSearchCount < UnitFIFO.Count)
          AND (NOT StartSelected) DO


        (* JobState 20代表已分配麵篩且正在處理 *)
        IF UnitFIFO.Units[StartSearchIndex].JobState = 20 THEN


            (* 讀取這筆訂單使用的麵篩 *)
            CASE UnitFIFO.Units[StartSearchIndex].NoodleBasketNo OF


                (* ---------- 麵篩1 ---------- *)
                1:

                    IF (NoodleBasket_1.State = 10)
                       AND
                       (NoodleBasket_1.UnitID =
                        UnitFIFO.Units[StartSearchIndex].UnitID) THEN

                        (* 產生拿生麵請求 *)
                        NoodleBasket_1.State := 20;

                        StartSelected := TRUE;

                    END_IF;



                (* ---------- 麵篩2 ---------- *)
                2:

                    IF (NoodleBasket_2.State = 10)
                       AND
                       (NoodleBasket_2.UnitID =
                        UnitFIFO.Units[StartSearchIndex].UnitID) THEN

                        NoodleBasket_2.State := 20;

                        StartSelected := TRUE;

                    END_IF;



                (* ---------- 麵篩3 ---------- *)
                3:

                    IF (NoodleBasket_3.State = 10)
                       AND
                       (NoodleBasket_3.UnitID =
                        UnitFIFO.Units[StartSearchIndex].UnitID) THEN

                        NoodleBasket_3.State := 20;

                        StartSelected := TRUE;

                    END_IF;

            END_CASE;

        END_IF;



        (* 搜尋下一個FIFO位置 *)
        StartSearchIndex := StartSearchIndex + 1;


        (* 環形FIFO索引回到0 *)
        IF StartSearchIndex >= UnitFIFO.Capacity THEN
            StartSearchIndex := 0;
        END_IF;


        StartSearchCount := StartSearchCount + 1;

    END_WHILE;

END_IF;
```

### AutoMain設定

新增：

```text
名稱：AutoMain
類型：PRG
語言：LD
```

在 `AutoMain` 區域變數建立 FB 實例：

```pascal
AutoScheduler_Inst : FB_AutoScheduler;
```

階梯圖呼叫：

```text
      Machine_Mode = 2
──────────────[ AutoScheduler_Inst ]
                 En
```

這個 FB 沒有額外輸入；`Machine_Mode = 2` 成立期間，每個掃描週期都會執行。

編譯成功後，停用或刪除原本的：

```text
AutoScheduler [PRG,ST]
```

不能讓 PRG 與 FB 版本同時執行，否則同一筆訂單可能被重複分配。

## Turn 01a0184b-5538-7233-9554-d6011cbfc201

### 使用者

如果只有自動模式才會用就寫在FB


### AI（final_answer）

對，依照你的規劃，我剛才叫你建立 `ActionArbiter [PRG]` 是錯的。

只有多碗自動模式使用的功能都應寫成 FB，由全自動主程式持續 CALL：

```text
AutoMain [PRG,LD]
│
├─ FB_AutoScheduler [FB,ST]
├─ FB_ActionArbiter [FB,ST]
├─ FB_AutoBowlFlow [FB,ST]
└─ 呼叫既有NashiRobot FB
```

執行方式：

```text
Machine_Mode = 2
→ 每個PLC掃描週期持續CALL這些FB
```

不是有動作時只 CALL 一次；只要維持在 Mode 2，排程器與仲裁器就要每個掃描持續執行。

這也代表目前的：

```text
AutoScheduler [PRG,ST]
```

應該改為：

```text
FB_AutoScheduler [FB,ST]
```

處理方式：

1. 新增 `FB_AutoScheduler`，類型選「功能塊」、語言選 ST。
2. 把目前 `AutoScheduler PRG` 的程式與區域變數複製進去。
3. 新增 `AutoMain [PRG,LD]`。
4. 在 `Machine_Mode = 2` 條件下持續 CALL `FB_AutoScheduler`。
5. 編譯成功後，停用或刪除原本的 `AutoScheduler PRG`，不能兩支同時執行。

後續 `ActionArbiter` 也建立成：

```text
FB_ActionArbiter [FB,ST]
```

由 `AutoMain` 在 Mode 2持續呼叫。`SemiAuto`、通訊、警報、EMC及共用底層控制則繼續保持 PRG。

