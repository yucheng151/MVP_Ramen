# 規劃自建點餐系統——原聊天匯出第 035 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a013ae-5729-7d30-8c85-4821a8adfd45

### 使用者


# Files mentioned by the user:

## codex-clipboard-446aa2db-8978-4bae-b6d3-00b37c0e0bd1.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-446aa2db-8978-4bae-b6d3-00b37c0e0bd1.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這個畫面先選「結構」，名稱改成：

```text
DUT_Strainer
```

不要直接選「陣列」，因為要先定義「一個麵篩包含哪些資料」，之後再建立三個麵篩的陣列。

`DUT_Strainer`建議欄位：

```text
State                 UINT
NoodleTaskID          UDINT
NoodleTypeNo          UINT
FirmnessNo            UINT
NoodleCabinetNo       UINT
CookTimeSet           TIME
ReadySequence         UDINT
AssignedUnitID        UDINT
```

狀態定義：

```text
0   EMPTY
10  LOADING
20  COOK_STARTING
30  COOKING
40  COOKED
50  LIFTED_WAIT
60  SHAKING
70  STANDBY
80  DROPPING
90  DROP_COMPLETE
```

建立好`DUT_Strainer`後，到全域變數建立：

```pascal
Strainer : ARRAY[1..3] OF DUT_Strainer;
```

使用方式：

```pascal
Strainer[1].State
Strainer[1].FirmnessNo
Strainer[2].State
Strainer[2].AssignedUnitID
Strainer[3].CookTimeSet
```

接著再建立第二個自定義結構：

```text
DUT_Unit
```

欄位：

```text
UnitID                 UDINT
RecipeNo               UINT
NoodleTypeNo           UINT
FirmnessNo             UINT
NoodleCabinetNo        UINT
JobState               UINT
NoodleState            UINT
BowlState               UINT
AssignedStrainerNo     UINT
```

然後建立Unit FIFO陣列：

```pascal
UnitQueue : ARRAY[0..31] OF DUT_Unit;
```

最終結構就是：

```text
DUT_Strainer
└─ Strainer[1..3]

DUT_Unit
└─ UnitQueue[0..31]
```

這個視窗目前正確操作是：

1. 名稱輸入`DUT_Strainer`
2. 選擇「結構」
3. 按「確定」
4. 加入上面的麵篩欄位
5. 完成後再建立`Strainer[1..3]`陣列

「聯合」目前完全不需要使用。

### 使用者

一步一步來


### AI（final_answer）

第一步：

1. 名稱輸入：`DUT_Strainer`
2. 類型選擇：`結構`
3. 按「確定」

完成後把下一個畫面截圖給我，我再帶你做第二步。

## Turn 01a013a7-4cfe-7be2-b65f-d5eaadb8f1ea

### 使用者

我現在差麵杓的邏輯還沒寫我打算寫完之後直接把整個系統完成我是想了解這個架構要從哪邊開始寫不是要寫個半成品


### AI（final_answer）

了解，你要的是「正式系統應該按照什麼順序開發」，不是先交一套單碗版本。那就要先把底層資料架構寫好，再把各動作接上去，避免最後整套重寫。

你把麵篩單動邏輯完成後，正式系統建議依下面順序寫。

## 1. 先定義所有資料，不要先改D1400

第一個要完成的是PLC資料表與狀態編號。

### 每一碗Unit資料

```text
Unit_ID
Recipe_No
Noodle_Type_No
Firmness_No
Noodle_Cabinet_No
Job_State
Noodle_State
Bowl_State
Assigned_Strainer_No
```

### 三個麵篩資料

```text
Strainer[1..3]

State
Noodle_Task_ID
Noodle_Type_No
Firmness_No
Noodle_Cabinet_No
Cook_Time_Set
Ready_Sequence
Assigned_Unit_ID
```

### 工作站資料

```text
X0.2 Unit ID、State、Done
X0.3 Unit ID、State、Done
X0.4 Unit ID、State、Done
```

### FIFO控制資料

```text
FIFO Head
FIFO Tail
FIFO Count
FIFO Capacity
```

先把D與M位址完整分配好，後面所有階梯圖都只能使用這份表。

---

## 2. 寫Unit FIFO

這是整個正式系統的資料核心。

先完成以下功能：

```text
HMI送入Unit
→ 檢查Unit ID重複
→ 寫入FIFO Tail
→ Tail往下一格
→ Count加1
```

以及：

```text
最前面的Unit完成
→ 回覆Unit ID
→ 等HMI ACK
→ 清除FIFO Head
→ Head往下一格
→ Count減1
```

這時還不用啟動設備，但FIFO必須可以正確保存多筆Unit。

---

## 3. 寫三個麵篩的獨立狀態機

不要把三個麵篩寫進主流程步序，而是三個相同結構：

```text
Strainer1 State
Strainer2 State
Strainer3 State
```

每個麵篩自行處理：

```text
EMPTY
→ LOADING
→ COOKING
→ COOKED
→ LIFTED_WAIT
→ SHAKING
→ STANDBY
→ DROPPING
→ EMPTY
```

三個麵篩可以同時位於不同狀態，例如：

```text
麵篩1：軟麵煮麵中
麵篩2：硬麵已升起等待
麵篩3：普通麵正在甩麵
```

---

## 4. 寫煮麵需求產生器

PLC掃描FIFO，計算目前還需要準備哪些麵：

```text
FIFO裡有哪些尚未準備的Unit
→ 根據麵種＋軟硬度產生Noodle Task
→ 找空閒麵篩
→ 配置麵盒、煮麵時間
```

煮麵完成順序不保證FIFO，所以麵篩完成後進入Ready Pool：

```text
Strainer State = COOKED／LIFTED_WAIT／STANDBY
Assigned Unit ID = 0
```

倒麵時才根據：

```text
麵種相同
AND 軟硬度相同
AND 麵篩已準備好
```

將麵篩正式配給`X0.2`的Unit。

---

## 5. 寫共用動作仲裁器

各工作站不能直接控制機構，只能提出請求。

```text
Req_Cook_Start
Req_Shake
Req_Drop_Noodle
Req_UR1
Req_UR2
```

仲裁器依你的優先權選擇：

```text
1. 啟動煮麵
2. 甩麵
3. 倒麵
4. 小料動作
```

主動作編號：

```text
D_Action = 0   空閒
D_Action = 10  啟動煮麵
D_Action = 20  甩麵
D_Action = 30  倒麵
D_Action = 40  UR1小料
D_Action = 50  UR2小料
```

所有共用機構只能由這個仲裁器授權，這樣才不會同時啟動造成碰撞。

---

## 6. 寫落碗與碗的Unit追蹤

每次落碗必須綁定FIFO中的一個Unit ID：

```text
選擇下一個等待落碗的Unit
→ CMD 103
→ 落碗
→ X0.1確認
→ 記錄這個實體碗的Unit ID
```

碗不能只保存「有／沒有」，必須保存它是哪個Unit：

```text
X0.2_Unit_ID
X0.3_Unit_ID
X0.4_Unit_ID
```

碗不能互相超車，所以每次感測器新到站時，PLC取最早尚未通過該站的Unit ID。

---

## 7. 寫三個工作站狀態機

### X0.2

```text
碗到站
→ 保存Unit ID
→ 執行UR1需要的動作
→ 尋找軟硬度符合的已完成麵篩
→ 必要時甩麵
→ 倒麵進碗
→ X0.2 Done
```

### X0.3

```text
碗到站
→ 保存Unit ID
→ 執行UR2
→ 如果有下一碗且有煮好麵，請求預先甩麵
→ X0.3 Done
```

### X0.4

```text
碗到站
→ 保存Unit ID
→ 加湯
→ X0.4 Done
```

---

## 8. 最後寫輸送帶總控

輸送帶只負責兩件事：

```text
任一工作站偵測到新碗
→ 立即停止
```

以及：

```text
所有目前有碗的工作站都Done
→ 重新啟動
```

每個感測器需要`Seen`旗標：

```text
Sensor第一次ON
→ 停止輸送帶
→ Seen = ON

工作完成後允許離站
→ Sensor變OFF
→ 清除Seen與工作站狀態
```

這樣不會因為感測器持續ON而反覆停止。

---

## 9. 寫完成Unit回報

當完成加湯的碗離開`X0.4`：

```text
取得X0.4 Unit ID
→ Job State = COMPLETE_PENDING_ACK
→ 確認它是FIFO最前面的完成Unit
→ 回報HMI
→ 等HMI ACK
→ 清除FIFO資料
```

完成回報不能只打一個Pulse，必須保持到HMI確認收到。

---

## 10. 最後才接HMI與手機後台

PLC內部正式架構穩定後，HMI負責：

```text
接收手機訂單
→ 每碗產生Unit ID
→ 選擇麵櫃格號
→ 將Unit送入PLC FIFO
→ 接收完成Unit ID
→ 更新麵櫃庫存
→ 判斷整筆訂單完成
→ 通知手機
```

## PLC主程式最後應該長這樣

```text
MAIN

1. 讀取輸入與感測器上升／下降沿
2. 接收HMI命令
3. 管理Unit FIFO
4. 產生煮麵與工作站動作請求
5. 執行動作優先權仲裁
6. 執行Strainer 1狀態機
7. 執行Strainer 2狀態機
8. 執行Strainer 3狀態機
9. 執行落碗狀態機
10. 執行X0.2狀態機
11. 執行X0.3狀態機
12. 執行X0.4狀態機
13. 計算輸送帶運轉許可
14. 處理完成Unit ID回報
15. 統一輸出實體Y點
```

每個實體輸出`Y`只能在最後的輸出區寫一次，各模組只設定內部命令旗標，避免階梯圖出現重複線圈互相覆蓋。

所以，你完成麵篩單動後，第一個正式要寫的不是新主流程，而是：

```text
資料位址表
→ Unit FIFO
→ Strainer[1..3]狀態
→ 動作仲裁器
→ 工作站狀態機
→ 輸送帶總控
→ HMI通訊
```

這個順序完成後就是正式完整架構，不是需要丟掉的半成品。

## Turn 01a013a2-7625-7140-9306-e1b85f49c1de

### 使用者

好複雜依照我現在的進度應該從哪裡開始好


### AI（final_answer）

現在最應該先做的是「單碗端到端閉環」，先讓手機下單後，真的能驅動目前PLC的一碗流程，完成後再通知手機。

先固定以下條件：

```text
一次只製作一碗
固定使用一個麵篩
固定普通硬度
固定一格麵櫃
PLC沿用目前D1400單碗流程
```

## 第一階段：先完成一碗閉環

流程目標：

```text
手機下單
→ 後台產生Unit ID
→ HMI將Unit ID送給PLC
→ PLC執行目前單碗自動流程
→ X0.4加湯、成品離開
→ PLC回覆完成的Unit ID
→ HMI更新訂單
→ 手機顯示餐點完成
```

### 先做PLC通訊

PLC暫時只需要保存一個：

```text
Current_Unit_ID
```

HMI送出：

```text
CMD 70
Unit ID
Command Index
Command Valid
```

PLC收到後：

```text
PLC目前空閒
→ 保存Current Unit ID
→ 回覆接收成功
→ 啟動現有D1400單碗流程
```

完成時：

```text
D1400單碗流程完成
→ 回覆Complete Unit ID
→ 等HMI ACK
→ 清除Current Unit ID
→ 回到等待下一碗
```

這階段先不要做PLC FIFO。

## 第二階段：多筆訂單，但PLC仍一次一碗

訂單FIFO先放在HMI：

```text
Unit 1001
Unit 1002
Unit 1003
Unit 1004
```

HMI運作：

```text
送出Unit 1001
→ 等PLC回覆1001完成
→ 再送Unit 1002
→ 等PLC回覆1002完成
→ 再送Unit 1003
```

這樣手機已經可以下很多碗，只是機台暫時逐碗製作。

第二階段完成時，整套點餐系統就已經可以實際使用，只是速度還沒最佳化。

## 第三階段：把FIFO移入PLC

單碗通訊確認穩定後，再加入：

```text
PLC Unit FIFO
FIFO Head
FIFO Tail
FIFO Count
```

HMI可以提前送入多個Unit，PLC依序保存並製作。

此階段仍可以：

```text
一個麵篩
一個碗完成後才做下一碗
```

先確認FIFO與完成Unit ID不會混亂。

## 第四階段：多碗輸送帶

FIFO穩定後，再把現在的單一`D1400`流程拆成：

```text
X0.2工作站狀態
X0.3工作站狀態
X0.4工作站狀態
輸送帶啟停控制
```

達成：

```text
輸送帶上可以有多個碗
任一工作站到碗就停止
各站有碗就執行各站動作
全部完成後輸送帶再啟動
```

## 第五階段：三個麵篩

多碗輸送穩定後才加入：

```text
Strainer[1]
Strainer[2]
Strainer[3]
```

先全部使用相同煮麵時間，只測試：

```text
空閒麵篩分配
三份同時煮
煮好升起等待
正確倒入X0.2的碗
```

## 第六階段：軟硬度與麵櫃庫存

最後才加入：

```text
硬麵
普通
軟麵
```

以及：

```text
麵櫃1～10格庫存
HMI選擇取哪一格
庫存保留與扣除
不同軟硬度麵篩配對
```

## 目前立即要做的工作

建議現在只完成這四件事：

1. 確定HMI→PLC的單碗啟動暫存器。
2. PLC保存`Current Unit ID`並啟動現有單碗流程。
3. PLC完成後回覆同一個`Unit ID`。
4. HMI收到完成後，把該碗標記為完成。

第一個測試案例就用兩碗：

```text
手機訂2碗
→ HMI建立Unit 1001、1002
→ PLC先做1001並回覆1001
→ HMI再送1002
→ PLC完成後回覆1002
→ 手機顯示整筆訂單完成
```

先做到這個測試完全通過。三個麵篩、軟硬度、多碗輸送帶和PLC FIFO都先保留在後續版本，不要同時加入。

## Turn 01a013a1-6af3-7231-8f56-0cff2ebcb7e1

### 使用者

煮麵還要分軟硬三個


### AI（final_answer）

那就要把「麵的軟硬度」放進每一碗的Unit資料。此時煮好的麵不能只看麵種相同就交換，還必須軟硬度相同。

可以定義三種：

```text
Firmness_No = 1  硬麵
Firmness_No = 2  普通
Firmness_No = 3  軟麵
```

實際名稱和時間可在HMI設定。

## 每一碗增加的資料

```text
Unit_ID
Noodle_Type_No
Firmness_No
Noodle_Cabinet_No
Recipe_No
Bowl_State
Job_State
```

例如：

```text
Unit 1001
麵種：1
軟硬度：3（軟麵）
麵櫃：第4格
```

## PLC煮麵時間表

建議HMI設定三組時間，但PLC根據`Firmness_No`選擇：

```text
Cook_Time_Hard      硬麵時間
Cook_Time_Normal    普通時間
Cook_Time_Soft      軟麵時間
```

例如：

```text
硬麵      120秒
普通      150秒
軟麵      180秒
```

正式秒數再依實際測試調整。

PLC啟動煮麵時，將當下時間複製進麵篩資料：

```text
Strainer[2].Firmness_No = 3
Strainer[2].Cook_Time_Set = 180秒
```

這樣即使操作員之後修改HMI時間，已經在煮的麵也不會突然改變計時。

## 麵篩增加的資料

```text
Strainer_No
Noodle_Task_ID
Noodle_Type_No
Firmness_No
Noodle_Cabinet_No
Cook_Time_Set
State
Ready_Sequence
Assigned_Unit_ID
```

## 倒麵時的配對條件

碗到`X0.2`後，可用麵篩必須符合：

```text
麵篩已煮好
AND 尚未分配給其他碗
AND 麵種相同
AND 軟硬度相同
```

階梯圖條件概念：

```text
Strainer Ready
AND Strainer Assigned Unit ID = 0
AND Strainer Noodle Type = X0.2 Unit Noodle Type
AND Strainer Firmness = X0.2 Unit Firmness
→ 此麵篩可以倒入這個碗
```

## 不同軟硬度不能交換

例如：

```text
Unit 1001：軟麵
Unit 1002：硬麵

麵篩1：軟麵，還在煮
麵篩2：硬麵，已煮好
```

雖然麵篩2先煮好，但不能倒給`Unit 1001`：

```text
麵篩2硬麵 → 保持升起等待
Unit 1001 → 等麵篩1的軟麵煮好
麵篩1軟麵完成 → 倒入Unit 1001
下一步再把麵篩2硬麵倒入Unit 1002
```

如果兩碗軟硬度相同：

```text
Unit 1001：普通
Unit 1002：普通
```

則可以使用任何先煮好的普通麵麵篩。

## 排程要注意的問題

FIFO只控制碗的出餐順序：

```text
Unit 1001 → Unit 1002 → Unit 1003
```

三個麵篩則各自獨立計時：

```text
麵篩1：軟麵180秒
麵篩2：硬麵120秒
麵篩3：普通150秒
```

因此完成順序可能是：

```text
麵篩2 → 麵篩3 → 麵篩1
```

PLC必須允許先煮好的麵升起等待，但倒麵時仍要依照`X0.2`目前那個`Unit ID`需要的軟硬度來選擇。

後續若要提升速度，可以再做「預估完成時間排程」，讓軟麵提早啟動、硬麵晚一點啟動，使三份麵更接近FIFO順序完成；第一版先用軟硬度配對＋等待會比較穩定。

## Turn 01a0139e-d86b-72b0-a15a-8b5ece535da5

### 使用者

會有一個問題先下去煮的麵不一定先煮好


### AI（final_answer）

對，這是一個重要問題：Unit FIFO的順序不能直接拿來當「麵煮好順序」。

```text
先開始煮 ≠ 一定先煮好
```

所以要把「碗的FIFO」和「三個麵篩狀態」分開管理。

## 正確資料結構

```text
UnitQueue[]
管理碗與訂單順序，必須FIFO

Strainer[1..3]
管理三個麵篩，各自獨立煮麵，不保證完成順序
```

PLC不能寫成：

```text
FIFO Head是Unit 1001
→ 固定等待Unit 1001原本指定的麵篩
```

而應該在碗到`X0.2`時，查看三個麵篩哪一個已經準備好。

## 建議做法：麵到倒麵時才與碗綁定

如果目前所有麵盒與食譜相同，建議煮麵開始時先不要永久綁定碗的`Unit ID`。

麵篩保存：

```text
Strainer_No
Noodle_Task_ID
Recipe_No
Noodle_Cabinet_No
State
Ready_Sequence
Assigned_Unit_ID
```

其中：

```text
Assigned_Unit_ID = 0
代表這份麵還沒有分配給某一個碗
```

例如：

```text
麵篩1：先開始煮，還沒煮好
麵篩2：後開始煮，但先煮好
麵篩3：煮麵中
```

這時碗`Unit 1001`到達`X0.2`：

```text
PLC掃描麵篩1～3
→ 麵篩2已煮好
→ 食譜符合Unit 1001
→ 將麵篩2分配給Unit 1001
→ 甩麵
→ 倒進Unit 1001的碗
```

記錄變成：

```text
Unit 1001.Strainer_No = 2
Strainer[2].Assigned_Unit_ID = 1001
```

接著麵篩1煮好後，可以分配給下一碗`Unit 1002`。

## 實際例子

```text
Unit 1001需要一份普通麵
Unit 1002需要一份普通麵

麵篩1先開始煮
麵篩2後開始煮

實際結果：
麵篩2先煮好
```

因為食譜相同，可以這樣分配：

```text
Unit 1001 ← 麵篩2
Unit 1002 ← 麵篩1
```

碗的完成順序仍然是：

```text
1001 → 1002
```

## 如果麵的種類不同

如果`Unit 1001`與`Unit 1002`食譜不同，就不能互換：

```text
Unit 1001：細麵
Unit 1002：粗麵
```

選擇麵篩時必須同時符合：

```text
麵篩已煮好
AND Assigned Unit ID = 0
AND Recipe No符合目前X0.2的碗
```

沒有符合的麵篩，`X0.2`就保持等待。

## 煮好順序編號

每當一個麵篩煮好，PLC產生`Ready Sequence`：

```text
Ready Counter加1
→ 寫入該麵篩Ready Sequence
```

例如：

```text
麵篩2先煮好：Ready Sequence = 15
麵篩3第二個煮好：Ready Sequence = 16
麵篩1最後煮好：Ready Sequence = 17
```

當有兩個以上符合食譜的麵篩都已煮好，選擇`Ready Sequence`最小的，也就是先煮好的先使用。

## 階梯圖選擇條件

```text
麵篩可選 =
State為COOKED、LIFTED_WAIT或STANDBY
AND Assigned_Unit_ID = 0
AND Recipe_No符合X0.2的Unit
```

排程變成：

```text
X0.2有碗
→ 取得這個碗的Unit ID與Recipe No
→ 掃描Strainer[1..3]
→ 找出已煮好且食譜相同的麵篩
→ 選Ready Sequence最小的麵篩
→ 綁定Unit ID
→ 甩麵
→ 倒麵
```

因此前面的設計要修正為：

```text
煮麵開始時：
只建立Noodle Task，不永久指定碗

倒麵前：
才將煮好的麵篩與X0.2的Unit ID正式綁定
```

這樣即使後煮的麵先完成，也不會卡住整條輸送帶；同時仍能維持碗與訂單的FIFO順序。

## Turn 01a0139a-ceb2-7fc2-bbb4-79360fe89cac

### 使用者

那我主流成怎麼規劃用階梯圖的畫


### AI（final_answer）

用階梯圖時，不建議再把全部動作寫成現在這種單一`D1400：10→20→30…`，因為多碗、三個麵篩和三個工作站會同時進行。

主程式應改成「總控＋多個獨立狀態機」。

## 一、主流程D1400只管運轉模式

```text
D1400 = 0     自動待機
D1400 = 10    初始化FIFO與各工作站
D1400 = 100   自動生產運轉
D1400 = 900   等待機台內現有碗做完
D1400 = 990   自動流程結束
```

概念階梯圖：

```text
| 自動模式  CMD71  D1400=0 |
|----[ ]------[ ]------[=]----------------[MOV 10 D1400]----|

| D1400=10  初始化完成 |
|----[=]-------[ ]-------------------------[MOV 100 D1400]---|

| D1400=100 |
|----[=]-----------------------------------( M_Auto_Run )----|

| D1400=900  FIFO空  機台內碗數=0 |
|----[=]-------[=]----------[=]-------------[MOV 990 D1400]---|
```

`D1400=100`期間，不是依序走固定步驟，而是每次PLC掃描都執行以下模組：

```text
1. HMI命令接收
2. Unit FIFO管理
3. 動作請求產生
4. 動作優先權排程
5. 麵篩1～3狀態控制
6. X0.2工作站控制
7. X0.3工作站控制
8. X0.4工作站控制
9. 落碗控制
10. 輸送帶控制
11. 完成Unit ID回報
```

## 二、三個麵篩各自一個狀態

```text
D1900  Strainer1_State
D1910  Strainer2_State
D1920  Strainer3_State
```

狀態共用相同定義：

```text
0   EMPTY
10  等待放麵
20  煮麵啟動中
30  煮麵中
40  煮好
50  升起等待
60  甩麵中
70  Standby
80  倒麵中
90  倒麵完成
```

每個麵篩還要保存：

```text
Unit ID
麵櫃格號
煮麵計時
完成旗標
```

例如麵篩1：

```text
D1900  State
D1901  Unit ID Low
D1902  Unit ID High
D1903  麵櫃格號
D1904  煮麵時間
D1905  動作完成旗標
```

## 三、產生動作請求

PLC不要直接看到條件就啟動設備，而是先產生請求：

```text
M2010  Req_Cook_Start
M2011  Req_Shake
M2012  Req_Drop_Noodle
M2013  Req_UR1
M2014  Req_UR2
M2015  Req_Add_Soup
```

### 煮麵請求

```text
| 自動運轉  FIFO有待煮Unit  任一麵篩空閒 |
|----[ ]----------[ ]------------[ ]--------( M2010 )----|
```

### 甩麵請求

```text
| 麵篩1煮好且需要甩麵 |
|----[ D1900=40或50 ]------------------------( M2011 )----|
```

三個麵篩的條件做OR：

```text
Strainer1需要甩麵
OR Strainer2需要甩麵
OR Strainer3需要甩麵
→ Req_Shake
```

### 倒麵請求

```text
| X0.2有碗  UR1完成  對應麵篩Standby |
|----[ ]-------[ ]------------[ ]------------( M2012 )----|
```

## 四、動作優先權排程

使用一個共用動作編號：

```text
D1930  Active_Action

0   沒有動作
10  啟動煮麵
20  甩麵
30  倒麵
40  UR1小料
50  UR2小料
```

階梯圖由上往下排列，最高優先權放最上面。

### 第一優先：啟動煮麵

```text
| Active=0  ReqCook  麵篩有空  UR1沒動  UR2沒動 |
|----[=]------[ ]------[ ]-------[/]------[/]----[MOV 10 D1930]--|
```

### 第二優先：甩麵

```text
| Active=0  ReqShake |
|----[=]------[ ]----------------------------[MOV 20 D1930]--|
```

### 第三優先：倒麵

```text
| Active=0  ReqDropNoodle |
|----[=]------[ ]----------------------------[MOV 30 D1930]--|
```

### 第四優先：UR1小料

```text
| Active=0  ReqUR1 |
|----[=]------[ ]----------------------------[MOV 40 D1930]--|
```

### 第五優先：UR2小料

```text
| Active=0  ReqUR2 |
|----[=]------[ ]----------------------------[MOV 50 D1930]--|
```

因為PLC由上往下掃描，第一條成立後`D1930`就不再等於0，下面的動作當次掃描就不會被選中。

## 五、啟動煮麵時分配麵篩

第一版可以先使用麵篩1→2→3的順序：

```text
| Active=10  Strainer1空閒 |
|----[=]----------[=]----------------( 選擇麵篩1 )----|

| Active=10  Strainer1不空  Strainer2空閒 |
|----[=]----------[/]----------[=]--------( 選擇麵篩2 )----|

| Active=10  Strainer1不空  Strainer2不空  Strainer3空閒 |
|----[=]----------[/]----------[/]----------[=]--( 選擇麵篩3 )--|
```

選到麵篩後：

```text
FIFO取得最早待煮Unit
→ 將Unit ID寫進該麵篩
→ 將麵櫃格號寫進該麵篩
→ Unit資料寫回Strainer No
→ 麵篩狀態改成10
→ 執行取麵與煮麵啟動
```

煮麵啟動完成：

```text
| Active=10  煮麵啟動完成 |
|----[=]------------[ ]----------------[MOV 0 D1930]----|
|----[=]------------[ ]----------------[MOV 30 麵篩State]|
```

`D1930`回到0後，排程器才選擇下一個動作。

## 六、三個工作站分開寫狀態

```text
D1940  X0.2工作站State
D1950  X0.3工作站State
D1960  X0.4工作站State
```

### X0.2

```text
0   沒有碗
10  碗新到站
20  請求UR1
30  UR1執行中
40  等待對應麵
50  請求甩麵
60  請求倒麵
70  倒麵中
80  X0.2完成
```

### X0.3

```text
0   沒有碗
10  碗新到站
20  請求UR2
30  UR2執行中
40  X0.3完成
```

### X0.4

```text
0   沒有碗
10  碗新到站
20  加湯中
30  加湯完成
```

## 七、輸送帶停止與重新啟動

新增到站鎖存，避免感測器一直亮造成重複停止：

```text
M2100  X0.2已偵測
M2101  X0.3已偵測
M2102  X0.4已偵測
M2110  Conveyor_Stop_Request
```

新碗到`X0.2`：

```text
| X0.2  尚未鎖存 |
|----[ ]----[/M2100]----------------(SET M2100)----|
|----[ ]----[/M2100]----------------(SET M2110)----|
|----[ ]----[/M2100]----------------[MOV 10 D1940]-|
```

`X0.3`、`X0.4`使用相同方式。

輸送帶停止：

```text
| 任一站要求停止 |
|----[ M2110 ]------------------------( 輸送帶停止 )----|
```

全部有碗工作站完成後：

```text
X0.2沒有碗 OR X0.2 State=80
AND
X0.3沒有碗 OR X0.3 State=40
AND
X0.4沒有碗 OR X0.4 State=30
→ 允許輸送帶運轉
```

階梯圖概念：

```text
| AutoRun  X02許可  X03許可  X04許可 |
|----[ ]------[ ]------[ ]------[ ]--------(輸送帶運轉)----|
```

碗離開感測器後才清除該站：

```text
| X0.2 OFF  X0.2已完成 |
|----[/]---------[ ]----------------(RST M2100)----|
|----[/]---------[ ]----------------[MOV 0 D1940]--|
```

## 八、完成Unit ID回覆

`X0.4`加湯完成後，碗離開感測器：

```text
取得該碗Unit ID
→ Job State設為完成待回覆
→ 檢查它是否為FIFO Head
→ 回覆Unit ID給HMI
→ 等待HMI ACK
→ 清除FIFO Head
→ Head往下一格
```

主架構最後會是：

```text
D1400只管自動模式
D1930負責動作優先權
D1900／1910／1920負責三個麵篩
D1940負責X0.2
D1950負責X0.3
D1960負責X0.4
FIFO陣列負責每一碗Unit ID
```

這樣才能在階梯圖裡同時管理三份麵、多個碗和三個工作站，又不會把所有動作卡在一條主步序裡。上述D與M位址是架構提案，正式配置前要先確認PLC現有使用範圍。

## Turn 01a01399-ad57-7e50-8330-5bf36652797c

### 使用者

我是指麵篩的部分


### AI（final_answer）

了解，你是問「三個麵篩」要不要做陣列。

答案是：要做成`Strainer[1..3]`狀態陣列，但不是FIFO，也不是堆疊。因為三個麵篩是三個固定的實體資源，每個麵篩一次只能綁定一碗。

```text
Strainer[1]  麵篩1目前狀態
Strainer[2]  麵篩2目前狀態
Strainer[3]  麵篩3目前狀態
```

每個麵篩保存：

```text
State               麵篩狀態
Unit_ID             目前對應哪一碗
Noodle_Cabinet_No   麵盒來自哪一格
Cook_Time           煮麵時間
Cooker_Done         煮麵完成
Shake_Done          甩麵完成
```

狀態可以定義為：

```text
0  EMPTY           空閒
10 LOADING         正在放入麵盒
20 COOKING         煮麵中
30 COOKED          已煮好
40 LIFTED_WAIT     已升起等待
50 SHAKING         甩麵中
60 STANDBY         甩麵完成、等待倒麵
70 DROPPING        正在倒麵進碗
```

如果使用ST：

```pascal
TYPE StrainerRecord :
STRUCT
    State              : INT;
    Unit_ID            : DINT;
    Noodle_Cabinet_No  : INT;
    Cook_Time          : INT;
    Cooker_Done        : BOOL;
    Shake_Done         : BOOL;
END_STRUCT
END_TYPE

VAR_GLOBAL
    Strainer : ARRAY[1..3] OF StrainerRecord;
END_VAR
```

PLC分配時：

```text
FIFO取得下一個待煮Unit
→ 尋找State = EMPTY的麵篩
→ 找到麵篩2
→ Strainer[2].Unit_ID = 1005
→ Strainer[2].Noodle_Cabinet_No = 4
→ Strainer[2].State = LOADING
```

同時反向寫回Unit資料：

```text
UnitQueue[1005].Strainer_No = 2
```

因此會形成雙向對應：

```text
Unit 1005 → 使用麵篩2
麵篩2 → 現在處理Unit 1005
```

倒麵完成後才能釋放：

```text
Strainer[2].State = EMPTY
Strainer[2].Unit_ID = 0
Strainer[2].Noodle_Cabinet_No = 0
```

所以資料結構應該分成：

```text
UnitQueue[]       每一碗的FIFO陣列
Strainer[1..3]    三個固定麵篩的狀態陣列
```

PLC先從`UnitQueue`取出最早的待煮Unit，再從`Strainer[1..3]`找一個空閒麵篩配給它。

## Turn 01a01398-7f17-74c1-9ddd-29185eecd017

### 使用者


# Response annotations:
Each item contains text selected from an earlier Codex response and may include a user comment. Treat items as Annotation 1, Annotation 2, and so on in array order. Use every selection as context and address every comment. For every annotation you address, include its inline directive `:codex-annotation{index="N"}`, where N is its one-based array position (for example, `:codex-annotation{index="1"}`). Do not use unstructured annotation labels.
<response-annotations>
[{"text":"Unit_ID               1005\nNoodle_Cabinet_No     4\nStrainer_No           2\nNoodle_State          煮麵中\nBowl_State            等待落碗"}]
</response-annotations>

## My request:
這要做一個陣列堆嗎


### AI（final_answer）

對，這些資料要做成「Unit陣列」，但不是堆疊（Stack），而是先進先出的環形佇列（FIFO Queue）。:codex-annotation{index="1"}

概念如下：

```text
UnitQueue[0]
UnitQueue[1]
UnitQueue[2]
...
UnitQueue[31]
```

每一格保存一碗的完整資料：

```text
Unit_ID
Noodle_Cabinet_No
Strainer_No
Noodle_State
Bowl_State
Job_State
```

如果PLC支援ST結構，可以規劃為：

```pascal
TYPE UnitRecord :
STRUCT
    Unit_ID            : DINT;
    Noodle_Cabinet_No  : INT;
    Strainer_No        : INT;
    Noodle_State       : INT;
    Bowl_State         : INT;
    Job_State          : INT;
END_STRUCT
END_TYPE

VAR_GLOBAL
    UnitQueue : ARRAY[0..31] OF UnitRecord;

    FIFO_Head  : INT;
    FIFO_Tail  : INT;
    FIFO_Count : INT;
END_VAR
```

資料進來時：

```text
HMI指定：
Unit_ID = 1005
Noodle_Cabinet_No = 4

PLC剛接收時：
Strainer_No = 0
Noodle_State = 等待煮麵
Bowl_State = 等待落碗
```

PLC準備煮麵時才分配麵篩：

```text
麵篩2空閒
→ Strainer_No = 2
→ Noodle_State = 煮麵中
```

如果PLC主要使用梯形圖，就用連續D暫存器模擬陣列。例如每一碗使用10個WORD：

```text
UnitQueue[0]：D1520～D1529
UnitQueue[1]：D1530～D1539
UnitQueue[2]：D1540～D1549
...
UnitQueue[31]：D1830～D1839
```

每筆配置：

```text
+0～+1  Unit ID（32位元）
+2     麵櫃格號
+3     麵篩號
+4     麵狀態
+5     碗狀態
+6     工作狀態
+7     食譜編號
+8     完成旗標
+9     保留
```

FIFO控制：

```text
FIFO_Head   最早尚未完成回覆的Unit
FIFO_Tail   下一筆寫入位置
FIFO_Count  目前陣列內的Unit數
```

新增一碗：

```text
寫入UnitQueue[FIFO_Tail]
→ Tail = Tail + 1
→ 超過31就回到0
→ Count = Count + 1
```

完成並收到HMI確認：

```text
清除UnitQueue[FIFO_Head]
→ Head = Head + 1
→ 超過31就回到0
→ Count = Count - 1
```

因此最準確的名稱是「Unit環形FIFO陣列」，不是堆疊。堆疊是後進先出，會讓後下單的碗先做，不符合你的需求。

## Turn 01a01397-a8af-7dc0-860d-24d19213e34b

### 使用者

那我要用哪個麵篩拿哪個麵盒誰決定


### AI（final_answer）

應該分成兩個決定者：

- 「拿哪一格麵盒」由HMI後台決定。
- 「使用哪一個麵篩」由PLC即時決定。

原因是HMI知道麵櫃庫存，PLC才知道當下哪個麵篩空閒。

## 分工方式

```text
HMI後台
→ 根據麵櫃1～10格的剩餘數量
→ 選擇Noodle_Cabinet_No
→ 將這個格號跟Unit ID一起送給PLC

PLC
→ 按Unit ID的FIFO順序取出任務
→ 查看麵篩1～3哪一個空閒
→ 指派Cooker／Strainer No
→ 將麵櫃格號與麵篩號交給取麵手臂
```

例如：

```text
Unit ID：1005
HMI指定麵櫃：第4格
PLC分配麵篩：第2篩

最終配對：
Unit 1005
→ 麵櫃4
→ 麵篩2
→ 對應的碗1005
```

PLC的FIFO資料必須保存：

```text
Unit_ID               1005
Noodle_Cabinet_No     4
Strainer_No           2
Noodle_State          煮麵中
Bowl_State            等待落碗
```

## HMI選麵盒

第一版可以使用最簡單的規則：

```text
從麵櫃第1格開始找
→ 找到第一個剩餘數量大於0的格子
→ 保留一盒
→ 將格號送給PLC
```

例如庫存：

```text
第1格：0盒
第2格：0盒
第3格：5盒
第4格：8盒
```

下一碗就指定第3格。

但HMI送出任務時，不要立刻把實際庫存扣掉，建議分成：

```text
Stock_Qty       實際庫存
Reserved_Qty    已派工但尚未取出的數量
Available_Qty   Stock_Qty - Reserved_Qty
```

流程：

```text
HMI選擇第3格
→ Reserved加1
→ Unit ID與第3格送給PLC
→ PLC取麵完成後回報Unit ID＋第3格
→ HMI將Stock減1
→ Reserved減1
```

這樣連續派出三碗時，不會重複使用同一盒庫存。

## PLC選麵篩

PLC每次準備啟動煮麵時：

```text
FIFO有待煮Unit
→ 檢查麵篩1
→ 空閒就使用麵篩1
→ 否則檢查麵篩2
→ 否則檢查麵篩3
→ 三個都忙就等待
```

也可以使用輪替方式：

```text
上次使用麵篩1
→ 下次優先找麵篩2
→ 再下次優先找麵篩3
```

輪替方式能讓三個麵篩使用次數比較平均。

## 最終送給手臂的資料

當PLC確認UR1、UR2都停止，而且取得煮麵啟動權後，PLC送出：

```text
Unit ID
Noodle Cabinet No
Strainer No
Action No
Command Index
Command Valid
```

因此最後責任是：

```text
HMI：決定拿哪一格麵盒
PLC：決定放進哪一個麵篩
手臂：按照PLC給的「麵櫃格號＋麵篩號」執行
```

這個分工最穩定，因為HMI不用猜機台當下哪個麵篩空閒，PLC也不用管理麵櫃長期庫存。

## Turn 01a01396-0b34-7050-8274-23abf6c1b16b

### 使用者

我的動作層級會是煮麵優先然後再來才是甩麵再來才是倒麵小料這些的


### AI（final_answer）

了解，你的PLC要做「動作優先權排程」，順序是：

```text
第一優先：啟動煮麵
第二優先：甩麵／瀝水
第三優先：倒麵進碗
第四優先：小料動作
第五優先：其他動作
```

但優先權只在「目前動作做完、準備選下一個動作」時判斷，不能把正在執行的UR或機構動作中途停止。

## PLC選擇動作的邏輯

```text
目前共用機構沒有執行動作
→ 檢查是否有煮麵啟動需求
→ 沒有才檢查甩麵需求
→ 沒有才檢查倒麵需求
→ 沒有才檢查小料需求
→ 都沒有就保持等待
```

建議PLC建立請求旗標：

```text
Req_Cook_Start       請求啟動煮麵
Req_Shake_Noodle     請求甩麵
Req_Drop_Noodle      請求倒麵進碗
Req_UR1_Material     請求UR1小料
Req_UR2_Material     請求UR2小料
Req_Add_Soup         請求加湯
```

核心判斷可以寫成：

```text
IF Motion_Busy = OFF THEN

    IF Req_Cook_Start
       AND Cooker有空位
       AND UR1沒有動
       AND UR2沒有動
    THEN
        執行煮麵啟動

    ELSE IF Req_Shake_Noodle THEN
        執行甩麵／瀝水

    ELSE IF Req_Drop_Noodle THEN
        執行倒麵進碗

    ELSE IF Req_UR1_Material THEN
        執行UR1小料

    ELSE IF Req_UR2_Material THEN
        執行UR2小料

    END_IF

END_IF
```

## 執行中的動作不能被插隊

例如UR1正在放小料，此時產生新的煮麵需求：

```text
UR1小料執行中
→ 煮麵請求設為等待
→ UR1完成
→ UR1停止
→ PLC重新檢查優先權
→ 煮麵優先，所以先啟動煮麵
→ 煮麵啟動完成
→ 再處理甩麵、倒麵或其他動作
```

## 優先權與FIFO的關係

兩者要分開：

```text
動作種類選擇：依優先權
同一種動作有多碗等待：依Unit ID的FIFO順序
```

例如：

```text
Unit 1001：等待小料
Unit 1002：等待甩麵
Unit 1003：等待啟動煮麵
```

PLC會執行：

```text
1. Unit 1003 啟動煮麵
2. Unit 1002 甩麵
3. Unit 1001 小料
```

但碗在輸送帶上不能互相超車，因此最後完成回覆仍然是：

```text
Unit 1001 → Unit 1002 → Unit 1003
```

「動作可以依優先權插隊」，但「成品完成順序仍然依FIFO」。

另外，加湯如果與煮麵、甩麵及UR沒有共用碰撞區，可以在`X0.4`獨立同時執行，不需要排進同一個動作鎖。輸送帶則必須等所有目前有碗的工作站完成，才可以重新啟動。

