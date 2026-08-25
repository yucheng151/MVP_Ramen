# 規劃自建點餐系統——原聊天匯出第 027 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a017e8-8e07-7412-845b-9c043db6c320

### 使用者

還有UR打架的問題


### AI（final_answer）

對，三支手臂打架的問題要獨立處理，不能分散寫在 `AutoScheduler`、UR1、UR2各自的程式裡，否則很容易同一掃描週期同時啟動。

應新增：

```text
FB_ActionArbiter
→ 三支手臂的共用區仲裁
```

完整結構：

```text
AutoScheduler
→ 決定哪一碗、哪個麵篩

AutoMain
→ CALL各動作功能塊

FB_ActionArbiter
→ 決定這次允許哪支手臂啟動

FB_NoodleRobot
→ 煮麵手臂

FB_UR1
→ UR1

FB_UR2
→ UR2
```

### 仲裁規則

依照你前面決定的優先順序：

```text
1. 拿麵進鍋開始煮
2. 煮好後甩麵
3. 把麵倒入碗
4. UR1、UR2及小料動作
```

煮麵計時中沒有機械移動，所以不占用共用區。

### UR動作狀態

```text
送出UR1命令
→ UR1執行中
→ 收到201
→ UR1結束，不再移動

送出UR2命令
→ UR2執行中
→ 收到202
→ UR2結束，不再移動
```

### 煮麵手臂取得執行權

啟動條件：

```text
Robot_Idle = TRUE
AND UR1已收到201或尚未執行
AND UR2已收到202或尚未執行
AND 共用區沒有被占用
```

取得執行權後，必須立即鎖住：

```pascal
RobotZoneOwner := 1;
```

定義：

```pascal
RobotZoneOwner : INT;
```

```text
0 = 共用區空閒
1 = 煮麵手臂占用
```

UR1和UR2的命令送出條件都必須包含：

```pascal
RobotZoneOwner = 0
```

所以煮麵手臂動作期間，即使有碗到達X0.2或X0.3，也只能先記錄到站，不能馬上送出UR命令。

### 避免同一掃描同時啟動

`AutoMain` 的呼叫順序建議：

```text
1. 產生各動作Request
2. CALL FB_ActionArbiter
3. CALL FB_NoodleRobot
4. CALL FB_UR1
5. CALL FB_UR2
6. 寫入實際命令
```

仲裁器先決定誰取得執行權，再由功能塊送命令。

因此下一步新增 `AutoMain [PRG,LD]` 時，第一個呼叫應該是 `FB_ActionArbiter`。`AutoScheduler` 繼續只做訂單與麵篩分配，不加入任何UR防撞判斷。

### 使用者


# Response annotations:
Each item contains text selected from an earlier Codex response and may include a user comment. Treat items as Annotation 1, Annotation 2, and so on in array order. Use every selection as context and address every comment. For every annotation you address, include its inline directive `:codex-annotation{index="N"}`, where N is its one-based array position (for example, `:codex-annotation{index="1"}`). Do not use unstructured annotation labels.
<response-annotations>
[{"text":"Machine_Mode = 2\nAND Robot_Idle\nAND 某個麵篩State = 20\n→ 呼叫現有NashiRobot功能塊\n→ 傳入該麵篩的NoodleCabinetNo與麵篩編號"}]
</response-annotations>

## My request:
你只有想到這樣的話沒有考量UR手臂會動


### AI（final_answer）

你說得對，我引用的那段條件不完整，而且直接呼叫 `NashiRobot` 會有碰撞風險。`Robot_Idle` 只能證明煮麵手臂空閒，不能證明 UR1、UR2 沒有移動。:codex-annotation{index="1"}

正確流程應該是：

```text
麵篩State = 20
→ 只產生「拿麵進鍋請求」
→ 不直接呼叫NashiRobot
→ 先交給ActionArbiter判斷
```

需要記錄兩支 UR 是否還在執行：

```pascal
UR1_ActionActive : BOOL;
UR2_ActionActive : BOOL;
NoodleZoneLocked : BOOL;
```

### UR執行狀態

實際送出 UR1 命令時：

```pascal
UR1_ActionActive := TRUE;
```

確認收到 `201`：

```pascal
IF UR1_ActionActive
   AND IPC_ResponseValid
   AND (IPC_ResponseCode = 201) THEN

    UR1_ActionActive := FALSE;

END_IF;
```

UR2同理：

```pascal
(* 送出UR2命令 *)
UR2_ActionActive := TRUE;
```

```pascal
(* 收到UR2完成 *)
IF UR2_ActionActive
   AND IPC_ResponseValid
   AND (IPC_ResponseCode = 202) THEN

    UR2_ActionActive := FALSE;

END_IF;
```

### 拿麵進鍋的完整啟動條件

```pascal
NoodleLoadRequest :=
    (NoodleBasket_1.State = 20)
    OR (NoodleBasket_2.State = 20)
    OR (NoodleBasket_3.State = 20);
```

仲裁器只有在以下條件全部成立時，才能允許煮麵手臂啟動：

```pascal
IF NoodleLoadRequest
   AND Robot_Idle
   AND (NOT UR1_ActionActive)
   AND (NOT UR2_ActionActive)
   AND (NOT NoodleZoneLocked) THEN

    (* 先鎖住共用區 *)
    NoodleZoneLocked := TRUE;

    (* 再允許NashiRobot執行 *)
    NoodleLoadGrant := TRUE;

END_IF;
```

順序一定是：

```text
確認UR1已完成201
AND 確認UR2已完成202
AND NashiRobot目前Idle
    ↓
同一掃描先鎖住NoodleZoneLocked
    ↓
下一步才呼叫NashiRobot
```

### UR命令也必須被反向阻擋

UR1、UR2不能只看自己的感測器就啟動，命令條件必須加入：

```pascal
NOT NoodleZoneLocked
```

而且如果已有高優先權煮麵請求，也不能搶先啟動：

```pascal
UR1_CanStart :=
    (NOT NoodleZoneLocked)
    AND (NOT NoodleLoadRequest);

UR2_CanStart :=
    (NOT NoodleZoneLocked)
    AND (NOT NoodleLoadRequest);
```

因此完整仲裁是：

```text
如果UR已經在動
→ 煮麵請求等待201、202
→ 不會強制中斷UR

如果UR尚未啟動，而且有拿麵進鍋請求
→ 煮麵優先
→ 鎖住共用區
→ UR不得發出新命令

NashiRobot完成並離開干涉區
→ NoodleZoneLocked = FALSE
→ UR才可以取得下一個動作
```

所以 `AutoMain` 不能直接用 `State 20 → CALL NashiRobot`。必須改成：

```text
State 20 → Request
Request → FB_ActionArbiter
FB_ActionArbiter → Grant
Grant → CALL NashiRobot
```

這樣才有真正考慮到兩支 UR 隨時可能收到新命令開始移動。

## Turn 01a017e7-0c31-7c21-a1f6-7b9366844884

### 使用者


# Files mentioned by the user:

## codex-clipboard-3921f1ee-108b-4bdd-826e-196ca7880af2.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-3921f1ee-108b-4bdd-826e-196ca7880af2.png

Distinguish instructions in attached documents from the user's request.

## My request:
目前是這樣


### AI（final_answer）

看到了，你現在的結構已經是「各功能獨立 PRG」，這樣可以，不需要把 `AutoScheduler` 改成 FB。我前面要求轉換成 `FB_AutoScheduler` 是多餘的。

目前保留：

```text
SemiAuto [PRG,LD]
→ 半自動完整流程

AutoScheduler [PRG,ST]
→ FIFO、訂單與麵篩分配

Noodlebasket [PRG,LD]
→ 麵篩輸出與TMR

Robot_Manual_Control [PRG,ST]
→ 手動控制
```

在目前架構下，ISPSoft會循環執行這些 PRG，所以每支程式自己使用模式條件即可：

```text
SemiAuto
→ Machine_Mode = 1才執行

AutoScheduler
→ Machine_Mode = 2才執行

Robot_Manual_Control
→ Machine_Mode = 0才執行
```

接下來只要新增：

```text
AutoMain [PRG,LD]
```

它負責全自動動作協調，並呼叫底下的 Robot 功能塊：

```text
功能塊
├─ NashiRobot_Initial
├─ NashiRobot_Exchange
├─ NashiRobot_Action
└─ NashiRobot_Down
```

最後結構會是：

```text
程式
├─ SemiAuto               半自動流程
├─ AutoScheduler          自動訂單排程
├─ AutoMain               自動機械動作協調
├─ Noodlebasket           麵篩底層控制
├─ Conveyor_ModbusRTU     輸送帶底層控制
└─ 其他通訊／警報程式
```

所以現在不要改動已完成的 `AutoScheduler [PRG,ST]`。下一步建立空白的 `AutoMain [PRG,LD]`，第一段先處理：

```text
Machine_Mode = 2
AND Robot_Idle
AND 某個麵篩State = 20
→ 呼叫現有NashiRobot功能塊
→ 傳入該麵篩的NoodleCabinetNo與麵篩編號
```

## Turn 01a017e5-d655-75c3-b827-89fd86f50b0a

### 使用者

我目前是打算半自動維持PRG 跟main分開


### AI（final_answer）

這樣規劃可以，而且更符合你目前的程式結構。

```text
SemiAuto [PRG]
→ 保留原本單碗、線性步序
→ 只在Machine_Mode = 1執行

Main [PRG]
→ 作為全自動主程式
→ 只在Machine_Mode = 2時CALL各個全自動功能塊
```

建議專案結構：

```text
程式 PRG
├─ Initialize
├─ HMItoPLC_Command
├─ SemiAuto
├─ Main
└─ Noodlebasket

功能塊 FB
├─ FB_AutoScheduler
├─ FB_NoodleRobot
├─ FB_Conveyor
├─ FB_UR1
├─ FB_UR2
└─ FB_ActionArbiter
```

### SemiAuto PRG

把目前 `Main` 裡原本的單碗流程移到 `SemiAuto`：

```text
Main_step 10～90
落碗
輸送帶
IPC CMD103
UR1／201
UR2／202
X0.2、X0.3、X0.4
```

整支程式限制：

```pascal
Machine_Mode = 1
```

### Main PRG

新的 `Main` 不再寫單碗步序，只負責全自動功能塊呼叫：

```text
Machine_Mode = 2
    ↓
CALL FB_AutoScheduler
CALL FB_NoodleRobot
CALL FB_Conveyor
CALL FB_UR1
CALL FB_UR2
CALL FB_ActionArbiter
```

### Noodlebasket PRG

目前的麵篩輸出與三個 `TMR` 可以維持獨立 PRG，因為它是底層硬體控制，半自動和全自動都可能共用。

最重要的規則：

```text
SemiAuto只能在Mode 1寫動作命令
Main及自動功能塊只能在Mode 2寫動作命令
```

這樣兩套流程不會同時操作輸送帶、Robot或麵篩。

因此目前的 `AutoScheduler` 應該改成 `FB_AutoScheduler`，由新的全自動 `Main` 呼叫；`SemiAuto` 繼續保持獨立 PRG。

## Turn 01a017e3-73a7-70c2-8372-4678e260a43d

### 使用者

應該是寫好副程式我主程式只負責call


### AI（final_answer）

對，這個架構更正確。主程式不應該塞入所有動作流程，只負責模式判斷與呼叫各副程式。

我前面說在 `AutoMain` 裡直接寫四套流程需要修正成：

```text
Main
→ 只負責依序CALL各功能塊

各功能塊
→ 各自管理自己的Step與動作
```

建議架構：

```text
Main [PRG]
│
├─ FB_SemiAuto
│    └─ 原本單碗半自動流程
│
└─ 全自動模式
     ├─ FB_AutoScheduler
     ├─ FB_NoodleRobot
     ├─ FB_NoodleBasket
     ├─ FB_Conveyor
     ├─ FB_UR1
     ├─ FB_UR2
     └─ FB_ActionArbiter
```

各副程式負責：

```text
FB_AutoScheduler
→ FIFO、訂單分配、選擇下一個麵篩

FB_NoodleRobot
→ 拿麵盒、放麵進鍋、甩麵、倒麵

FB_NoodleBasket
→ 三個麵篩升降及TMR計時

FB_Conveyor
→ 落碗、多碗位置、輸送帶啟停

FB_UR1
→ X0.2站動作與201完成

FB_UR2
→ X0.3站動作與202完成

FB_ActionArbiter
→ 動作優先順序與三支手臂防撞
```

主程式概念只留下：

```text
Machine_Mode = 1
→ CALL FB_SemiAuto

Machine_Mode = 2
→ CALL FB_AutoScheduler
→ CALL FB_NoodleRobot
→ CALL FB_NoodleBasket
→ CALL FB_Conveyor
→ CALL FB_UR1
→ CALL FB_UR2
→ CALL FB_ActionArbiter
```

### AutoScheduler要調整

目前建立的 `AutoScheduler [PRG]` 程式不用丟掉，但正式架構建議改成：

```text
名稱：FB_AutoScheduler
類型：功能塊 FB
語言：ST
```

輸入：

```pascal
Enable : BOOL;
```

區域變數：

```pascal
CurrentUnitIndex : INT;
SelectedCookTime : INT;
Assigned         : BOOL;
StartSearchIndex : INT;
StartSearchCount : INT;
StartSelected    : BOOL;
```

把原本程式最外層：

```pascal
IF Machine_Mode = 2 THEN
```

改成：

```pascal
IF Enable THEN
```

在 `Main` 建立功能塊實例：

```pascal
AutoScheduler_Inst : FB_AutoScheduler;
```

階梯圖呼叫：

```text
Machine_Mode = 2
────────[AutoScheduler_Inst]
          Enable = TRUE
```

這樣 `Main` 只負責呼叫；FIFO搜尋、麵篩分配與內部變數全部留在 `FB_AutoScheduler` 裡。之後其他功能也按照同樣方式各自封裝，不會再把完整自動流程堆進主程式。

## Turn 01a017dc-d2d1-7f71-967e-50c2c9b8f78d

### 使用者

我想想喔我在想目前main 程式給半自動使用我們現在要做的新增一支程式


### AI（final_answer）

對，這樣規劃正確：

```text
Main
→ 保留原本的手動／半自動單碗測試流程

AutoScheduler
→ 管理訂單、FIFO、分配三個麵篩

AutoMain
→ 新增的全自動多碗動作控制程式
```

但是 `AutoMain` 不能再寫成原本 `Main_step 10～90` 那種單一路線，因為全自動會同時存在多個碗、三個麵篩與三支手臂。

建議新增：

```text
名稱：AutoMain
類型：PRG
語言：階梯圖
```

`AutoMain` 分別維護幾個獨立流程：

```pascal
NoodleRobot_Step : INT;  (* 煮麵手臂流程 *)
Conveyor_Step    : INT;  (* 落碗及輸送帶流程 *)
UR1_Step         : INT;  (* UR1流程 *)
UR2_Step         : INT;  (* UR2流程 *)
```

這些流程可以同時運行，例如：

```text
麵篩1正在煮麵
麵篩2等待煮麵手臂拿麵
輸送帶正在送碗到X0.2
UR1處理前一碗
UR2處理更前面的碗
```

程式分工：

```text
HMItoPLC_Command
    ↓ 接收訂單

AutoScheduler
    ↓ FIFO與麵篩分配

AutoMain
    ↓ 選擇及啟動實際動作

Noodlebasket
    ↓ 麵篩升降輸出與三個TMR
```

模式必須互斥：

```text
Machine_Mode = 1
→ 只允許原本Main的半自動流程

Machine_Mode = 2
→ 只允許AutoScheduler與AutoMain
```

原本 `Main` 裡還包含 `Machine_Mode = 2` 的自動分支；在正式啟用 `AutoMain` 前，要把這些舊自動分支關閉或改成只服務半自動，否則 `Main` 和 `AutoMain` 會同時寫輸送帶、Robot命令及落碗輸出。

下一步先建立空白的 `AutoMain` 階梯圖，暫時不要複製原本整支 `Main`。第一個要完成的是 `NoodleRobot_Step`：

```text
讀取麵篩State 20
→ 傳送麵櫃與麵篩編號
→ 啟動煮麵手臂
→ 等動作完成
→ 麵篩State 40
```

## Turn 01a017d9-bc96-7541-b211-2cbba61f3520

### 使用者

好


### AI（commentary）

下一步我先沿用你現有的 Robot 命令介面，不另外發明一套變數。我會核對目前 `Main` 裡第三支手臂的啟動、命令參數與完成訊號，再把 `State 20` 正確接上去。這一步只讀現有程式。

### AI（final_answer）

我確認了：`Robot_Idle` 確實已經存在，位址是 `D1124.0`，由手臂原點訊號 `D12100.2` 經過 `TMR 20` 後成立，所以 `AutoScheduler` 直接讀取它沒問題。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Main.pdf" purpose="source"}

但目前還不能準確寫 `State 20` 的發令程式，因為 `Print_Main` 裡 `NashiRobot_Exchange` 的五個輸入只顯示成 `Parameter...`，看不到實際名稱與用途。

下一步請打開：

```text
功能塊 → NashiRobot_Exchange
```

把它的：

- 五個 Parameter 名稱
- 命令編號定義
- Finish輸出條件

截圖給我。這樣我才能正確寫出：

```text
State 20
→ 傳入麵櫃編號
→ 傳入麵篩編號
→ 發出拿麵進鍋命令
→ 等Finish
→ State 40
```

不會誤用你原本的 Robot 通訊欄位。

## Turn 01a017d9-4416-7041-ab64-8def9a61c846

### 使用者

沒關西先這樣


### AI（final_answer）

好，先維持目前版本。

目前完成到：

```text
HMI訂單 → UnitFIFO
→ AutoScheduler分配三個麵篩
→ 依FIFO順序選出下一個拿麵任務
→ 選中的麵篩進入State 20
```

下一步再接 `State 20 → 發出拿麵進鍋命令 → 完成後State 40 → TMR開始計時`。

## Turn 01a017d8-e17f-7ef3-8bed-dc65dff12cfd

### 使用者

這樣呢


### AI（commentary）

我現在重新擷取 ISPSoft 視窗，確認你畫面上的區域變數和 `AutoScheduler` 程式。

### AI（final_answer）

還是看不到 ISPSoft 視窗；系統只偵測到它在執行，沒有可擷取的視窗，可能是 ISPSoft 以系統管理員權限開啟。

請直接把 `AutoScheduler` 畫面截圖貼上來，最好包含：

- 區域變數表
- ST 程式上半部
- 編譯訊息或錯誤列表

我就能逐項確認。

## Turn 01a017d7-1bd2-7f41-baa3-d289144cccea

### 使用者

你看一下我的螢幕畫面你確認一下


### AI（commentary）

我會用螢幕檢視功能查看你目前 ISPSoft 畫面，核對 `AutoScheduler` 的區域變數和程式內容。這個功能只用來查看與確認，先不替你修改。

### AI（final_answer）

目前偵測到 ISPSoft 正在執行，但它沒有提供可檢視的視窗，可能是最小化或被其他視窗遮住。

請先把 ISPSoft 還原並切到 `AutoScheduler` 畫面，停留在要我確認的位置，再跟我說「好了」，我就重新讀取螢幕確認。

## Turn 01a017d6-a4a4-7413-b7f8-43506644c25b

### 使用者

好


### AI（final_answer）

先將這版 `AutoScheduler` 貼上並編譯。

確認重點：

- `CookDone` 已從 DUT 和 AutoScheduler 移除。
- 三個 `CookTimer` 是 `Noodlebasket` 的區域 `TIMER`。
- 沒有新增重複的 UnitID、麵櫃編號或 Robot Busy。
- `Robot_Idle` 使用原有全域變數。

編譯完成後，下一步接 `State = 20` 的實際「指定麵櫃、指定麵篩、發出拿麵進鍋命令」流程。

