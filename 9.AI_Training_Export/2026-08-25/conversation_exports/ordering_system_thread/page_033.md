# 規劃自建點餐系統——原聊天匯出第 033 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a013d3-0ed1-7841-a17b-f899f778c216

### 使用者


# Files mentioned by the user:

## Print_Initialize.pdf: C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Initialize.pdf

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（commentary）

我會用PDF工具檢查你目前的`Initialize`階梯圖，確認現有初始化條件後，再告訴你下一條該加在哪裡。

### AI（final_answer）

我看過目前的初始化程式；它使用`SM402`和`ALM_Rst`兩個並聯條件做初始化。:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print_Initialize.pdf" purpose="source"}

下一步只先初始化三個麵篩的`State`。

在`Initialize`新增一個區段，左側條件照現有寫法：

```text
SM402
  OR
ALM_Rst
```

右側放三個`MOVE`：

```text
MOVE 0 → NoodleBasket_1.State
MOVE 0 → NoodleBasket_2.State
MOVE 0 → NoodleBasket_3.State
```

概念如下：

```text
         +----[MOVE 0  NoodleBasket_1.State]
SM402 ---|
         +----[MOVE 0  NoodleBasket_2.State]
ALM_Rst--|
         +----[MOVE 0  NoodleBasket_3.State]
```

也就是PLC第一次RUN，或執行`ALM_Rst`時，三個麵篩都回到：

```text
State = 0  空閒
```

先只加這三個`MOVE`，其他欄位暫時不用動。完成後編譯，再把新增的階梯圖截圖給我。

## Turn 01a013d0-225f-7902-a494-21688a071a5b

### 使用者


# Files mentioned by the user:

## codex-clipboard-e433b555-365d-4f71-84b7-512f2db2a862.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-e433b555-365d-4f71-84b7-512f2db2a862.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

現在正確了：

```text
NoodleBasket_1 → DUT_NoodleBasket
NoodleBasket_2 → DUT_NoodleBasket
NoodleBasket_3 → DUT_NoodleBasket
```

下一步要初始化三個麵篩的資料。請先打開左側的`Initialize [PRG]`，把現有階梯圖畫面截圖給我。我會依你目前使用的初始化接點，逐條帶你加入，不先猜PLC的首次掃描訊號。

## Turn 01a013cb-8c75-7470-81c7-938e861ad6b4

### 使用者


# Files mentioned by the user:

## codex-clipboard-79680d99-84c3-4a0d-8abc-4407228f3f11.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-79680d99-84c3-4a0d-8abc-4407228f3f11.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

變數名稱正確，但右邊的資料型態設錯了。

目前看起來是：

```text
DUT_NoodleBasket1
DUT_NoodleBasket2
DUT_NoodleBasket3
```

三個麵篩應共用同一個結構型態：

```text
NoodleBasket_1    DUT_NoodleBasket
NoodleBasket_2    DUT_NoodleBasket
NoodleBasket_3    DUT_NoodleBasket
```

請把三列的資料型態全部改成：

```text
DUT_NoodleBasket
```

不需要建立`DUT_NoodleBasket1／2／3`三種型態。修改後重新編譯。

## Turn 01a013c8-1354-7461-9ee6-66d90d891a44

### 使用者

結構 列舉 聯合


### AI（final_answer）

你說得對，我剛才看錯了；中間是「列舉」，不是「陣列」。

這個畫面請選「結構」。

我們會建立一個外層結構，裡面放三個麵篩陣列：

```pascal
TYPE DUT_NoodleBasketArray :
STRUCT
  Basket : ARRAY [1..3] OF DUT_NoodleBasket;
END_STRUCT
END_TYPE
```

之後使用方式是：

```pascal
NoodleBaskets.Basket[1].State
NoodleBaskets.Basket[2].State
NoodleBaskets.Basket[3].State
```

現在先選「結構」，再按「確定」。

### 使用者

馬的哪來陣列


### AI（final_answer）

抱歉，是我把「列舉」看成「陣列」了。這個視窗沒有陣列選項。

現在請取消建立`DUT_NoodleBasketArray`。只有三個麵篩，用階梯圖直接建立三個結構變數更簡單：

```text
NoodleBasket_1    DUT_NoodleBasket
NoodleBasket_2    DUT_NoodleBasket
NoodleBasket_3    DUT_NoodleBasket
```

之後使用：

```pascal
NoodleBasket_1.State
NoodleBasket_2.State
NoodleBasket_3.State
```

所以現在回到主符號表，把原本的`NoodleBasket`改成`NoodleBasket_1`，再新增`NoodleBasket_2`和`NoodleBasket_3`，三個資料型態都選`DUT_NoodleBasket`。不需要再建立新的自定義資料型態。

## Turn 01a013c7-25a6-75e1-8fa5-0cf312bb9c60

### 使用者

結構??


### AI（final_answer）

這次要選「陣列」。

原因：

```text
DUT_NoodleBasket
＝結構
＝一個麵篩的資料
```

現在建立的：

```text
DUT_NoodleBasketArray
＝陣列
＝三個麵篩
```

最後關係：

```text
DUT_NoodleBasketArray
├─ DUT_NoodleBasket［1］
├─ DUT_NoodleBasket［2］
└─ DUT_NoodleBasket［3］
```

所以這個畫面請選「陣列」，再按「確定」。

## Turn 01a013c6-d60a-7501-863c-745eaa0108f7

### 使用者


# Files mentioned by the user:

## codex-clipboard-911c5898-448f-4996-b4b5-b470c905f796.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-911c5898-448f-4996-b4b5-b470c905f796.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

名稱正確。

現在：

1. 選擇「陣列」。
2. 按「確定」。

下一個畫面會讓你設定陣列範圍與元素型態。

## Turn 01a013c5-b8aa-74e3-8511-3e3675862fc4

### 使用者


# Files mentioned by the user:

## codex-clipboard-817881dc-59f8-4fb6-a195-de951bdb0879.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-817881dc-59f8-4fb6-a195-de951bdb0879.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

這個視窗不能直接建立陣列，所以先按「取消」。

接著：

1. 左側「自定義資料型態」按右鍵。
2. 選擇新增自定義資料型態。
3. 名稱輸入：

```text
DUT_NoodleBasketArray
```

4. 類型選擇「陣列」。
5. 按「確定」。

先做到這裡，出現陣列定義畫面後再給我看。

## Turn 01a013c4-2230-7cd3-89d7-25af499e34fa

### 使用者


# Files mentioned by the user:

## codex-clipboard-41687847-3b9a-46e7-9ea5-5712d0f8e3f7.png: C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-41687847-3b9a-46e7-9ea5-5712d0f8e3f7.png

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（final_answer）

目前這一列建立的是「單一麵篩」，還不是三個麵篩陣列。

請雙擊資料型態欄位的：

```text
DUT_NoodleBasket
```

改成：

```pascal
ARRAY [1..3] OF DUT_NoodleBasket
```

變數名稱維持：

```text
NoodleBasket
```

完成後應代表：

```text
NoodleBasket[1]  麵篩1
NoodleBasket[2]  麵篩2
NoodleBasket[3]  麵篩3
```

如果資料型態欄位不允許直接輸入`ARRAY`，先不要改其他地方，把跳出的選擇畫面截圖給我。

## Turn 01a013c2-af8d-7a30-9c35-5fc65abb68ab

### 使用者

好了再來呢


### AI（final_answer）

下一步建立三個麵篩的實際陣列。

1. 左側專案樹展開「全域符號」。
2. 打開「主符號表」。
3. 新增一筆全域變數：

```text
名稱：NoodleBasket
資料型態：ARRAY [1..3] OF DUT_NoodleBasket
```

初始值和位址先留空。

完成後編譯。之後就可以使用：

```pascal
NoodleBasket[1].State
NoodleBasket[2].State
NoodleBasket[3].State
```

建立完成後，把主符號表畫面給我看，再進行下一步。

## Turn 01a013c0-cd3e-79a2-86e6-6ff049ef0ef8

### 使用者

TIME有問題


### AI（final_answer）

那就不要在結構裡使用`TIME`，改用`DINT`保存毫秒數。

把：

```pascal
CookTimeSet : TIME;
```

改成：

```pascal
(* 本次煮麵時間，單位為毫秒 *)
CookTimeSet : DINT;
```

例如：

```text
硬麵120秒   = 120000
普通150秒   = 150000
軟麵180秒   = 180000
```

完整定義：

```pascal
TYPE DUT_NoodleBasket :
STRUCT
  (* 麵篩目前狀態 *)
  State : INT;

  (* 煮麵任務編號，0表示沒有任務 *)
  NoodleTaskID : DINT;

  (* 麵櫃格號：1～10，0表示未指定 *)
  NoodleCabinetNo : INT;

  (* 軟硬度：0未指定、1硬、2普通、3軟 *)
  FirmnessNo : INT;

  (* 本次煮麵時間，單位為毫秒 *)
  CookTimeSet : DINT;

  (* 煮好順序，數字越小表示越早煮好 *)
  ReadySequence : DINT;

  (* 分配給哪一碗，0表示尚未分配 *)
  AssignedUnitID : DINT;
END_STRUCT
END_TYPE
```

後續接計時器時，再把毫秒值轉成計時器需要的格式。

