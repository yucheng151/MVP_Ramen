# 規劃自建點餐系統——原聊天匯出第 031 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a013f9-86e8-7230-a49c-00d93701819e

### 使用者

OK


### AI（final_answer）

下一步建立PLC的Unit FIFO。

1. 在「自定義資料型態」新增一個資料型態。
2. 名稱輸入：

```text
DUT_UnitFIFO
```

3. 類型選擇「結構」。
4. 按「確定」。

這次也是選「結構」；稍後會在結構內容裡，用程式文字定義`Unit[0..31]`陣列，不是在新增視窗選陣列。

建立好空白的`DUT_UnitFIFO`後再繼續。

## Turn 01a013f8-af4a-71f0-a19e-d37b1b579dee

### 使用者

給我碗整DUT


### AI（final_answer）

以下是完整的`DUT_Unit`，可以直接取代目前內容：

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;

  (* HMI指定的麵櫃格號。
     0表示未指定，1～10表示麵櫃位置。 *)
  NoodleCabinetNo : INT;

  (* HMI指定的麵條軟硬度。
     0未指定、1硬、2普通、3軟。 *)
  FirmnessNo : INT;

  (* 這一碗的整體製作狀態。
     0空資料
     10已進入FIFO、等待製作
     20製作中
     30完成、等待回覆HMI
     40 HMI已確認完成 *)
  JobState : INT;

  (* PLC分配的麵篩編號。
     0尚未分配、1～3表示麵篩編號。 *)
  NoodleBasketNo : INT;

  (* 碗在機台內的位置與狀態。
     0尚未落碗
     10落碗中
     20 X0.1落碗確認
     30落碗區前往X0.2
     40位於X0.2／UR1與倒麵位置
     50從X0.2前往X0.3
     60位於X0.3／UR2位置
     70從X0.3前往X0.4
     80位於X0.4／加湯位置
     90成品已送出 *)
  BowlState : INT;

  (* X0.2位置的UR1動作是否完成。
     FALSE未完成，TRUE已完成。 *)
  UR1Done : BOOL;

  (* 對應麵篩的麵是否已倒入這個碗。
     FALSE未完成，TRUE已完成。 *)
  NoodleDropDone : BOOL;

  (* X0.3位置的UR2動作是否完成。
     FALSE未完成，TRUE已完成。 *)
  UR2Done : BOOL;

  (* X0.4位置的加湯動作是否完成。
     FALSE未完成，TRUE已完成。 *)
  SoupDone : BOOL;
END_STRUCT
END_TYPE
```

各工作站的完成條件：

```text
X0.2完成 =
UR1Done = TRUE
AND NoodleDropDone = TRUE

X0.3完成 =
UR2Done = TRUE

X0.4完成 =
SoupDone = TRUE
```

當這一碗成品送出：

```text
BowlState = 90
JobState = 30
```

PLC回覆`UnitID`給HMI並收到ACK後：

```text
JobState = 40
```

接著才能從FIFO清除這一筆Unit。修改完成後編譯即可。

## Turn 01a013f8-5333-7db1-9ea9-1ad9b296f4b2

### 使用者

OK


### AI（final_answer）

下一步加入`X0.2`的UR1完成旗標：

```pascal
(* X0.2位置的UR1動作是否完成。
   FALSE未完成，TRUE已完成。 *)
UR1Done : BOOL;
```

加在`BowlState`下面：

```pascal
  (* X0.2位置的UR1動作是否完成。
     FALSE未完成，TRUE已完成。 *)
  UR1Done : BOOL;
```

完成後編譯。

## Turn 01a013f7-4e59-7fd2-b439-f80eeb0aa52b

### 使用者

OK


### AI（final_answer）

下一步加入碗目前所在位置：

```pascal
(* 碗在輸送帶上的位置與狀態。
   0尚未落碗
   10落碗中
   20 X0.1落碗完成
   30前往X0.2
   40位於X0.2
   50前往X0.3
   60位於X0.3
   70前往X0.4
   80位於X0.4
   90成品已送出 *)
BowlState : INT;
```

加在`NoodleBasketNo`下面：

```pascal
  (* PLC分配的麵篩編號。
     0尚未分配、1～3代表麵篩編號。 *)
  NoodleBasketNo : INT;

  (* 碗在輸送帶上的位置與狀態。
     0尚未落碗
     10落碗中
     20 X0.1落碗完成
     30前往X0.2
     40位於X0.2
     50前往X0.3
     60位於X0.3
     70前往X0.4
     80位於X0.4
     90成品已送出 *)
  BowlState : INT;
```

完成後編譯。

## Turn 01a013f6-e975-7c83-b5e1-fcbcfd896e46

### 使用者

ok


### AI（final_answer）

下一步加入這碗被分配到哪一個麵篩：

```pascal
(* PLC分配的麵篩編號。
   0尚未分配、1～3代表麵篩編號。 *)
NoodleBasketNo : INT;
```

完整內容：

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;

  (* HMI指定的麵櫃格號。
     0表示未指定，1～10表示麵櫃位置。 *)
  NoodleCabinetNo : INT;

  (* HMI指定的麵條軟硬度。
     0未指定、1硬、2普通、3軟。 *)
  FirmnessNo : INT;

  (* 這一碗的整體製作狀態。
     0空資料、10等待製作、20製作中、
     30完成待回覆、40已回覆HMI。 *)
  JobState : INT;

  (* PLC分配的麵篩編號。
     0尚未分配、1～3代表麵篩編號。 *)
  NoodleBasketNo : INT;
END_STRUCT
END_TYPE
```

完成後編譯。

## Turn 01a013f6-6e44-7b52-a33d-08dc604674b6

### 使用者

ok


### AI（final_answer）

下一步加入整碗製作狀態：

```pascal
(* 這一碗的整體製作狀態。
   0空資料、10等待製作、20製作中、
   30完成待回覆、40已回覆HMI。 *)
JobState : INT;
```

完整內容：

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;

  (* HMI指定的麵櫃格號。
     0表示未指定，1～10表示麵櫃位置。 *)
  NoodleCabinetNo : INT;

  (* HMI指定的麵條軟硬度。
     0未指定、1硬、2普通、3軟。 *)
  FirmnessNo : INT;

  (* 這一碗的整體製作狀態。
     0空資料、10等待製作、20製作中、
     30完成待回覆、40已回覆HMI。 *)
  JobState : INT;
END_STRUCT
END_TYPE
```

完成後編譯。

## Turn 01a013f6-1298-70c2-92f9-578be6933b8d

### 使用者

OM


### AI（final_answer）

下一步加入軟硬度：

```pascal
(* HMI指定的麵條軟硬度。
   0未指定、1硬、2普通、3軟。 *)
FirmnessNo : INT;
```

完整內容：

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;

  (* HMI指定的麵櫃格號。
     0表示未指定，1～10表示麵櫃位置。 *)
  NoodleCabinetNo : INT;

  (* HMI指定的麵條軟硬度。
     0未指定、1硬、2普通、3軟。 *)
  FirmnessNo : INT;
END_STRUCT
END_TYPE
```

完成後編譯。

## Turn 01a013f5-af46-74a1-8032-81f4e6c0cbfe

### 使用者

OK


### AI（final_answer）

下一步加入HMI指定的麵櫃格號：

```pascal
(* HMI指定的麵櫃格號。
   0表示未指定，1～10表示麵櫃位置。 *)
NoodleCabinetNo : INT;
```

完整內容：

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;

  (* HMI指定的麵櫃格號。
     0表示未指定，1～10表示麵櫃位置。 *)
  NoodleCabinetNo : INT;
END_STRUCT
END_TYPE
```

完成後編譯。

## Turn 01a013f5-58f4-72f2-a69a-1219e13a8d21

### 使用者

註釋


### AI（final_answer）

```pascal
(* 每一碗拉麵的製作資料結構 *)
TYPE DUT_Unit :
STRUCT
  (* HMI產生的每一碗唯一編號。
     0表示這筆資料目前沒有使用。 *)
  UnitID : DINT;
END_STRUCT
END_TYPE
```

## Turn 01a013f5-1cd2-7942-b847-7e614fa5a85e

### 使用者

OK


### AI（final_answer）

下一步先加入每一碗的唯一編號。

把預設的：

```pascal
Element1 : BOOL;
```

改成：

```pascal
(* HMI提供的每一碗唯一編號，0表示空資料 *)
UnitID : DINT;
```

目前內容應為：

```pascal
TYPE DUT_Unit :
STRUCT
  (* HMI提供的每一碗唯一編號，0表示空資料 *)
  UnitID : DINT;
END_STRUCT
END_TYPE
```

完成後編譯。

