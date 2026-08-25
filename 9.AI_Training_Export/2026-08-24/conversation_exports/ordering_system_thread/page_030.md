# 規劃自建點餐系統——原聊天匯出第 030 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a0140e-192b-7421-97b6-bef436bc5cb9

### 使用者


# Files pasted by the user:

## "(* ===================================================== *) (* HMItoPLC_Command…": C:\Users\Administrator\.codex/attachments/21650a95-cbdd-4138-ba0f-4d8c992b2c8d/pasted-text.txt

Pasted text contains the user's request.

## My request:



### AI（commentary）

我先讀你貼出的HMI命令程式，確認CMD解析、ACK及清除方式，再接著帶你加入`CMD 70`。

### AI（final_answer）

我看完目前的`HMItoPLC_Command`，可以直接在現有`CASE`裡加入`CMD 70`，既有的Command Index與ACK流程不用重寫。

第一步先在`HMItoPLC_Command`程式的「區域變數」新增：

```text
FIFO_SearchIndex       INT
FIFO_SearchCount       INT
FIFO_DuplicateFound    BOOL
```

用途：

```text
FIFO_SearchIndex
→ 搜尋UnitFIFO陣列的位置

FIFO_SearchCount
→ 計算已搜尋幾筆Unit

FIFO_DuplicateFound
→ 判斷HMI送來的UnitID是否已存在
```

這三個是「區域變數」，因為只有`HMItoPLC_Command`內部檢查重複Unit ID時使用。

新增完成後編譯；下一步再把`70:`的完整程式加入`CASE HMItoPLC_CMD_Code OF`。

## Turn 01a0140c-253a-7470-b5fc-df7b8c4ccc32

### 使用者


# Files mentioned by the user:

## codex-clipboard-feab9655-b3fe-4598-bf80-14f771fbbc16.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-feab9655-b3fe-4598-bf80-14f771fbbc16.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這三個全域變數建立正確：

```text
HMItoPLC_UnitID          D1020～D1021  DINT
HMItoPLC_UnitCabinetNo   D1022        INT
HMItoPLC_UnitFirmnessNo  D1023        INT
```

下一步要把`CMD 70`加入你現有的HMI命令接收流程。為避免破壞目前`D1000～D1002`的握手，請把PLC裡的`HMI [PRG]`匯出成PDF，或截圖目前處理命令代碼與ACK的完整階梯圖。我看過現有寫法後，再告訴你CMD 70要加在哪個區段。

## Turn 01a0140a-8576-7802-a25f-eb471f9eb2cb

### 使用者

全域還是區域變數


### AI（final_answer）

要建立成「全域變數」。

原因：

- HMI通訊程式要寫入。
- FIFO程式要讀取。
- 主流程和麵篩排程也可能需要查看。
- 必須指定固定PLC位址`D1020～D1023`。

請在「全域符號 → 主符號表」建立：

```text
HMI_UnitID           D1020  DINT
HMI_UnitCabinetNo    D1022  INT
HMI_UnitFirmnessNo   D1023  INT
```

區域變數只在單一程式內有效，不適合用來做HMI與PLC之間的通訊資料。

## Turn 01a01405-7b49-7053-8d36-52dfce45db7c

### 使用者

好了


### AI（final_answer）

下一步建立HMI送入每一碗資料的固定暫存器。

先在主符號表確認`D1020～D1023`目前沒有被使用；如果空白，新增：

```text
HMI_UnitID
位址：D1020
型態：DINT
```

`DINT`會占用：

```text
D1020＝UnitID低位元WORD
D1021＝UnitID高位元WORD
```

接著新增：

```text
HMI_UnitCabinetNo
位址：D1022
型態：INT
```

```text
HMI_UnitFirmnessNo
位址：D1023
型態：INT
```

最後對應為：

```text
D1020～D1021  每一碗UnitID
D1022        麵櫃格號1～10
D1023        軟硬度1～3
```

這三筆先建立並編譯；`D1000～D1002`繼續使用目前既有的命令握手。

## Turn 01a01405-40b2-7b03-a60b-970e0930b90e

### 使用者

不用沒關西照舊得命名


### AI（final_answer）

好，維持原本命名：

```text
UnitID      每一碗的編號
CookIndex   下一個要煮的FIFO位置
BowlIndex   下一個要落碗的FIFO位置
```

`CookIndex`和`BowlIndex`不是另外的產品編號。

初始化照原本寫：

```text
MOV 0  → UnitFIFO.Head
MOV 0  → UnitFIFO.Tail
MOV 0  → UnitFIFO.Count
MOV 0  → UnitFIFO.CookIndex
MOV 0  → UnitFIFO.BowlIndex
MOV 32 → UnitFIFO.Capacity
```

完成後編譯即可。

## Turn 01a01402-b2c2-7280-b8c0-03f3b606f289

### 使用者

煮麵編號不是跟碗的編號一樣嗎


### AI（final_answer）

對，煮麵使用的編號就是同一碗的`UnitID`，不會另外產生煮麵編號。

`CookIndex`不是煮麵編號，它只是FIFO陣列的位置，範圍只有`0～31`。

例如：

```text
UnitFIFO.Units[5].UnitID = 1005

CookIndex = 5
表示下一個要開始煮的是陣列第5格
真正的碗編號仍然是1005
```

開始煮麵時會複製：

```text
NoodleBasket_2.UnitID
= UnitFIFO.Units[5].UnitID
= 1005
```

為避免誤會，建議現在把名稱改清楚：

```pascal
(* 下一筆尚未分配麵篩的FIFO陣列位置，範圍0～31。 *)
NextCookIndex : INT;

(* 下一筆尚未執行落碗的FIFO陣列位置，範圍0～31。 *)
NextBowlIndex : INT;
```

所以`DUT_UnitFIFO`改成：

```pascal
TYPE DUT_UnitFIFO :
STRUCT
  Units : ARRAY [0..31] OF DUT_Unit;

  Head : INT;
  Tail : INT;
  Count : INT;
  Capacity : INT;

  NextCookIndex : INT;
  NextBowlIndex : INT;
END_STRUCT
END_TYPE
```

初始化也改成：

```text
MOV 0  → UnitFIFO.Head
MOV 0  → UnitFIFO.Tail
MOV 0  → UnitFIFO.Count
MOV 0  → UnitFIFO.NextCookIndex
MOV 0  → UnitFIFO.NextBowlIndex
MOV 32 → UnitFIFO.Capacity
```

結論：

```text
UnitID＝每一碗的真正編號
NextCookIndex＝FIFO裡下一筆煮麵資料的位置
NextBowlIndex＝FIFO裡下一筆落碗資料的位置
```

## Turn 01a013fe-c066-7040-be64-7a9e8f1763b0

### 使用者

OK


### AI（final_answer）

下一步初始化FIFO控制資料。

在`Initialize`程式相同的：

```text
SM402 OR ALM_Rst
```

條件下新增：

```text
MOV 0  → UnitFIFO.Head
MOV 0  → UnitFIFO.Tail
MOV 0  → UnitFIFO.Count
MOV 0  → UnitFIFO.CookIndex
MOV 0  → UnitFIFO.BowlIndex
MOV 32 → UnitFIFO.Capacity
```

不需要逐筆清除`Units[0..31]`，因為：

```text
Count = 0
```

就代表整個FIFO目前沒有有效資料。後續HMI加入新Unit時，會把該位置的全部欄位重新寫入。

完成後編譯。

## Turn 01a013fd-5d0d-70e2-82b0-5ab669906836

### 使用者

DUT_Unit呢


### AI（final_answer）

`DUT_Unit`已經被使用在`DUT_UnitFIFO`裡：

```pascal
Units : ARRAY [0..31] OF DUT_Unit;
```

所以不需要另外建立單獨的`DUT_Unit`全域變數。

建立：

```text
UnitFIFO : DUT_UnitFIFO
```

之後就自動得到32筆`DUT_Unit`：

```text
UnitFIFO.Units[0]
UnitFIFO.Units[1]
UnitFIFO.Units[2]
...
UnitFIFO.Units[31]
```

使用欄位的方式：

```pascal
UnitFIFO.Units[0].UnitID
UnitFIFO.Units[0].NoodleCabinetNo
UnitFIFO.Units[0].FirmnessNo
UnitFIFO.Units[0].JobState
UnitFIFO.Units[0].BowlState
```

`DUT_Unit`是「一碗的型態」，`UnitFIFO`才是實際保存32碗資料的全域變數。

後續HMI接收資料時，可能會另外建立：

```text
HMI_UnitBuffer : DUT_Unit
```

作為暫存區，但目前先不用建立。现在只新增：

```text
UnitFIFO : DUT_UnitFIFO
```

## Turn 01a013fc-3cfd-7002-a70b-7c4ab4000ca5

### 使用者

OK


### AI（final_answer）

下一步到「主符號表」新增一個全域變數：

```text
名稱：UnitFIFO
類型：DUT_UnitFIFO
位址：N/A［Auto］
初始值：N/A
```

這一個變數裡面就包含：

```text
UnitFIFO.Units[0..31]
UnitFIFO.Head
UnitFIFO.Tail
UnitFIFO.Count
UnitFIFO.Capacity
UnitFIFO.CookIndex
UnitFIFO.BowlIndex
```

新增後先編譯。

## Turn 01a013fa-90a3-7472-9831-d025b3a19840

### 使用者

OK


### AI（final_answer）

把`DUT_UnitFIFO`內容改成下面這份：

```pascal
(* PLC內部每一碗Unit的先進先出佇列 *)
TYPE DUT_UnitFIFO :
STRUCT
  (* Unit資料陣列，共可保存32碗。
     有效索引範圍為0～31。 *)
  Units : ARRAY [0..31] OF DUT_Unit;

  (* 最早進入且尚未完成HMI回覆的Unit位置。 *)
  Head : INT;

  (* 下一筆HMI Unit要寫入的位置。 *)
  Tail : INT;

  (* FIFO目前保存的Unit數量，範圍0～32。 *)
  Count : INT;

  (* FIFO最大容量，初始化設定為32。 *)
  Capacity : INT;

  (* 下一筆尚未分配麵篩的Unit位置。 *)
  CookIndex : INT;

  (* 下一筆尚未執行落碗的Unit位置。 *)
  BowlIndex : INT;
END_STRUCT
END_TYPE
```

用途：

```text
Head
→ 指向最早尚未完成回覆的Unit

Tail
→ 指向下一筆HMI資料要寫入的位置

CookIndex
→ 煮麵排程從這裡取得下一碗

BowlIndex
→ 落碗排程從這裡取得下一碗

Count
→ PLC目前保存多少碗

Capacity
→ 固定32
```

環形索引規則：

```text
索引加1
→ 如果超過31
→ 回到0
```

完成後編譯，這個陣列是寫在結構內容裡，不需要在資料型態選擇視窗找到「陣列」選項。

