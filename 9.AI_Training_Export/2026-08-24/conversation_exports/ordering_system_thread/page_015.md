# 規劃自建點餐系統——原聊天匯出第 015 頁

Thread ID：01a0128c-710d-7be2-9e8d-3e60d4f5b5d0
順序：API以最新到最舊分頁；本頁內依回傳順序保存。

## Turn 01a0236b-2f13-7b72-ac56-7d080142155a

### 使用者

好給我HM to PLC的區域變數


### AI（final_answer）

在新程式`HMItoPLC_Order（PRG, ST）`建立以下區域變數：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	HMItoPLC_UnitID	D1020	DINT		HMI送入的每碗唯一編號，占用D1020~D1021
VAR	HMItoPLC_UnitCabinetNo	D1022	INT		HMI指定麵櫃編號1~10
VAR	HMItoPLC_UnitFirmnessNo	D1023	INT		軟硬度：1軟、2正常、3硬
VAR	HMItoPLC_OrderIndex	D1024	WORD		HMI每送一筆新訂單加1
VAR	HMItoPLC_OrderValid	D1025	WORD		1=訂單資料有效，0=無新訂單
VAR	PLCtoHMI_OrderAckUnitID	D1130	DINT		PLC已處理的UnitID，占用D1130~D1131
VAR	PLCtoHMI_OrderAckIndex	D1132	WORD		PLC已處理的OrderIndex
VAR	PLCtoHMI_OrderFIFOCount	D1133	INT		回報目前UnitFIFOCount
VAR	PLCtoHMI_OrderResponseCode	D1134	INT		200=成功，400以上=拒絕
VAR	OrderLastIndex		WORD		上一筆已處理的OrderIndex
VAR	OrderNew		BOOL		本次Scan收到新訂單
VAR	SearchIndex		INT		FIFO重複UnitID搜尋索引
VAR	DuplicateFound		BOOL		FIFO中找到相同UnitID
```

注意：

- 不要再建立`D1021`，它屬於`HMItoPLC_UnitID`。
- 不要再建立`D1131`，它屬於`PLCtoHMI_OrderAckUnitID`。
- `UnitFIFO`與`UnitFIFOCount`使用既有全域變數，不要在這支PRG重複建立。
- 區域變數`OrderLastIndex`會保留前一次PLC Scan的值，不是每次掃描歸零。

## Turn 01a0236a-a326-7831-99dc-8293ca827fde

### 使用者

但D通訊變數仍要放全域，原因是HMI透過固定D位址存取，不是因為其他PLC程式需要它們。這樣可以把通訊層和自動流程分開。區域也可以用D


### AI（final_answer）

對，你說得對。ISPSoft的區域變數也能指定固定D位址，HMI一樣可以透過Modbus讀寫該D位址。

因此可以這樣規劃：

放在`PRG_HMItoPLC_Order`區域變數：

```text
D1020～D1025  HMI訂單輸入
D1130～D1134  PLC接單回覆
OrderLastIndex
SearchIndex
DuplicateFound
```

必須放全域：

```text
UnitFIFO
UnitFIFOCount
```

因為`UnitFIFO`和`UnitFIFOCount`需要同時被：

- `PRG_HMItoPLC_Order`寫入
- `FB_AutoScheduler`讀取及修改
- MainAuto與其他流程監看

所以結論是：通訊D變數可以放區域；真正需要跨程式共享的FIFO才放全域。其他程式看不到區域符號名稱，但仍能透過實體D位址存取。

## Turn 01a02369-a09e-7bd2-b797-879050c35c95

### 使用者

我是說有需要嗎


### AI（final_answer）

其他自動程式不需要直接使用這些D通訊變數。

- `D1020～D1025`：只給HMI與`PRG_HMItoPLC_Order`使用。
- `D1130～D1134`：只給`PRG_HMItoPLC_Order`回覆HMI。
- `AutoScheduler`不需要知道這些D位址，只使用`UnitFIFO`和`UnitFIFOCount`。

真正需要跨程式共用的只有：

```text
UnitFIFO
UnitFIFOCount
```

但D通訊變數仍要放全域，原因是HMI透過固定D位址存取，不是因為其他PLC程式需要它們。這樣可以把通訊層和自動流程分開。

## Turn 01a02368-d393-7281-8703-7b938aae3d3e

### 使用者

這些變數其他程式用的倒嗎


### AI（final_answer）

可以，只要建在「全域符號表」，其他PRG和FB都能使用。

資料流應該這樣：

```text
手機／HMI
  ↓ 寫入
D1020～D1025
  ↓
PRG_HMItoPLC_Order
  ↓ 接單成功後寫入
UnitFIFO、UnitFIFOCount
  ↓
FB_AutoScheduler
  ↓
落碗、煮麵、輸送帶、UR流程
```

各變數用途：

| 變數 | 誰寫入 | 誰讀取 |
|---|---|---|
| `HMItoPLC_UnitID` | HMI | `PRG_HMItoPLC_Order` |
| `HMItoPLC_UnitCabinetNo` | HMI | `PRG_HMItoPLC_Order` |
| `HMItoPLC_UnitFirmnessNo` | HMI | `PRG_HMItoPLC_Order` |
| `HMItoPLC_OrderIndex` | HMI | `PRG_HMItoPLC_Order` |
| `HMItoPLC_OrderValid` | HMI | `PRG_HMItoPLC_Order` |
| `PLCtoHMI_OrderAckUnitID` | `PRG_HMItoPLC_Order` | HMI |
| `PLCtoHMI_OrderAckIndex` | `PRG_HMItoPLC_Order` | HMI |
| `PLCtoHMI_OrderFIFOCount` | PLC | HMI |
| `UnitFIFO` | 收單程式及排程器 | `FB_AutoScheduler`等 |
| `UnitFIFOCount` | 收單程式 | `FB_AutoScheduler` |

重要規則：

- `D1020～D1025`只能由HMI寫，PLC只讀。
- `D1130～D1134`只能由PLC寫，HMI只讀。
- `UnitFIFO`、`UnitFIFOCount`必須是全域變數。
- `SearchIndex`、`DuplicateFound`、`OrderLastIndex`這類內部運算變數可以放在`PRG_HMItoPLC_Order`的區域變數。
- 不要讓兩支PRG同時寫同一個通訊變數，否則每個Scan可能互相覆蓋。

另外，`FB_AutoScheduler`會修改`UnitFIFO[x].State`，所以它的`UnitFIFO`介面應使用`VAR_IN_OUT`；若只是`VAR_INPUT`，FB裡修改的狀態可能無法寫回全域FIFO。

## Turn 01a02210-89f0-76f0-bc8f-3775ea39ec11

### 使用者

跟我說我該怎麼做


### AI（final_answer）

現在先不要改 `AutoScheduler`。第一步是把「HMI收單通訊區」建完整。

先將Simulator切回手動模式 `Machine_Mode=0`，保留 `X0.0 ON`。

接著在全域符號表新增／確認：

```text
Class	Identifiers	Address	Type	Initial Value	Comment
VAR	HMItoPLC_UnitID	D1020	DINT	0	HMI送入的每碗唯一編號
VAR	HMItoPLC_UnitCabinetNo	D1022	INT	0	HMI指定麵櫃編號1~10
VAR	HMItoPLC_UnitFirmnessNo	D1023	INT	0	軟硬度：1軟、2正常、3硬
VAR	HMItoPLC_OrderIndex	D1024	WORD	0	每送一筆訂單加1
VAR	HMItoPLC_OrderValid	D1025	WORD	0	1=有新訂單、0=無訂單
VAR	PLCtoHMI_OrderAckUnitID	D1130	DINT	0	PLC已接收的UnitID
VAR	PLCtoHMI_OrderAckIndex	D1132	WORD	0	PLC已處理的OrderIndex
VAR	PLCtoHMI_OrderFIFOCount	D1133	INT	0	目前FIFO訂單數量
VAR	PLCtoHMI_OrderResponseCode	D1134	INT	0	200=接單成功、其他=拒絕原因
```

注意：

- `D1020`是DINT，會占用`D1020～D1021`。
- `D1130`也是DINT，會占用`D1130～D1131`。
- 建立前先確認`D1024、D1025、D1130～D1134`目前沒有被其他變數占用。
- `UnitFIFO`與`UnitFIFOCount`維持全域變數。

這一步完成後，下一步新增持續執行的：

```text
PRG_HMItoPLC_Order（PRG、ST）
```

它負責把 `D1020～D1025`複製進 `UnitFIFO`，初始訂單狀態設定成 `State=10`。完成變數後傳畫面給我，我再給你整支收單程式。

## Turn 01a01ad6-4089-78d3-8caf-ac0e8099f7ec

### 使用者

ok交給你


### AI（commentary）

好，我接著做單碗全自動流程測試：切換自動模式、建立一筆訂單、模擬落碗與各站到位、檢查UR/Nachi交握和完成UnitID。因為X輸入必須由ISPSoft Simulator真正強制，我會使用Windows操作能力控制模擬器畫面，不再用Modbus假寫X點。

### AI（commentary）

基礎安全鏈已通過。我現在先從現有HMI命令切到自動模式並核對PLC的訂單輸入位址；ISPSoft視窗目前無法被自動操作工具直接鎖定，所以站點X輸入會先分開處理，不會用錯誤的Modbus寫法冒充到位。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_plc_integration_test.py：update

### AI（commentary）

自動模式已成功切換：`CMD32→302`、`D1109=2`，安全條件仍全部通過。現在進到收單階段；我會先核對你已建立的 `D1020～D1023` 與PLC FIFO入口，避免猜一個Valid位址直接寫壞資料。

### AI（commentary）

目前PLC自動模式本身正常，但真正的「自動收單入口」尚未接上：AutoScheduler只讀內部 `UnitFIFO`，現有HMI的13個自動欄位仍全部是未配置，因此不能安全地憑空猜Valid位址。我會再嘗試直接取得ISPSoft裝置監控；若能控制X0.1～X0.4，就先把既有落碗與四站動作分段驗證。

### AI（commentary）

ISPSoft是系統管理員權限視窗，自動操作工具無法取得它，所以我不會冒險點錯畫面。接下來我先把同一套單碗、三碗、不同熟度、非先煮先完成、UnitID與手臂互鎖模型全部重跑，並把「真PLC已驗證」和「尚缺通訊所以只能模型驗證」清楚分開。

### AI（commentary）

目前模型測試也全部通過，包括500組隨機多碗壓力測試。最後我再讀一次 `D1020～D1025`，確認現有PLC是否真的有收單Valid／Index入口在運作；這會決定能不能直接送第一碗，還是必須先補PLC收單副程式。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\VALIDATION_REPORT_2026-08-19.md：update

### AI（commentary）

測試已完成，我會把Simulator恢復到手動模式，避免在沒有訂單收單入口、也沒有X0.1～X0.4控制的情況下長時間停在Auto。這是測試收尾，不會改PLC程式。

### 使用者

d1020還沒寫


### AI（commentary）

對，這就確認了：`D1020`的收單邏輯還沒寫，所以目前只能驗證到「自動模式能進入」，不能真的建立第一碗進 `UnitFIFO`。剛才收尾的CMD30已送出，但讀回時測試工具用了錯的方法名稱；我現在只確認模式是否已安全回到手動。

### AI（final_answer）

對，既然 `D1020`收單邏輯還沒寫，真PLC的單碗自動流程目前只能測到這裡。

已通過：

- EMC與通訊
- CMD6復歸
- CMD32自動模式：`D1109=2`
- HMI全部介面測試
- 單碗、三碗、10碗及500組隨機邏輯模擬

下一步必須先新增PLC收單流程：

```text
D1020~D1021：UnitID（DINT）
D1022：麵櫃編號
D1023：軟硬度
再補：OrderIndex、OrderValid、ACK UnitID、ACK Index、FIFO Count
```

PLC收到新OrderValid後，才把資料複製進 `UnitFIFO`，AutoScheduler才會開始落碗。

目前Simulator仍是 `Machine_Mode=2`，但 `UnitFIFO`沒有訂單，所以不會自行啟動輸出。下一步應先寫 `PRG_HMItoPLC_Order`。

## Turn 01a01ad4-bdfb-73f3-8be5-2ddcb52d6a5d

### 使用者

在一次


### AI（commentary）

好，我現在重新跑完整整合測試，確認PLC已RUN、`X0.0`安全鏈、CMD6及EMC解除狀態。

### AI（commentary）

這次基礎整合已全部通過：PLC確實在RUN、CMD6成功、EMC已解除，`FAIL=0、BLOCKED=0`。也證實先前判斷正確——Modbus仍讀到X0.0為0，但PLC CPU內的強制X0.0已經有效，所以必須以 `D1108/D1207` 判定，而不能用Modbus的X讀值判定。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\VALIDATION_REPORT_2026-08-19.md：update

### AI（final_answer）

這次測試全部通過：

- PLC已正常RUN
- HMI心跳：PASS
- IPC心跳：PASS
- Nachi Standby、Home、Robot Idle：PASS
- CMD6：`Index=1、ACK=1、Response=201`
- EMC解除：PASS
- `D1108=0、D1207=0`
- `PLCStatus=1`
- `ConveyorAlarm=0`
- 最終：`FAIL=0、BLOCKED=0`

目前 `MachineMode=0`，所以尚未執行自動落碗、輸送帶、UR與注湯動作。下一步可切到 `MachineMode=2`，開始單碗完整流程模擬。

## Turn 01a01ad2-f85a-7dc3-9495-797047b02843

### 使用者

這樣呢


### AI（commentary）

我現在再測一次，直接看 `X0.0` 是否已成立，以及CMD6後 `D1108/D1207` 能不能解除。

### AI（commentary）

這次狀態有改變：EMC已經解除，但PLC主程式看起來沒有在掃描。因為心跳、IPC狀態、Robot Idle和CMD6交握同時全部停止。我再讀兩次PLC心跳，確認CPU現在是不是在STOP模式。

### 使用者

x0.0幫妳設好了


### AI（commentary）

有收到，`X0.0`已設定；但我剛讀到PLC心跳兩秒內完全沒有變化，表示CPU目前可能還在STOP。請先不用再改X0.0，我現在立刻確認一次RUN狀態與安全鏈。

### AI（final_answer）

`X0.0`收到，但目前PLC CPU仍在STOP：

- `D1100`兩秒內：`0 → 0`，心跳沒動
- `D1105=0`
- `D1108=0`只是因為程式沒有掃描，不能算EMC解除成功
- CMD6也不會被處理

請把AS200 Simulator切回「RUN」，同時保留 `X0.0` 強制ON。切換完成後跟我說「好了」，我再跑完整測試。

## Turn 01a01acc-a246-7cf2-877c-1179bab698d6

### 使用者

在測試一次


### AI（commentary）

好，我現在直接用修正版重新連線 AS200 Simulator 測試；這次會確認 `X0.0`、CMD6、EMC解除以及目前能否進入後續動作測試。

### AI（commentary）

重測仍被安全回路擋住：CMD6 已正常回覆，但 PLC 仍回報 EMC。這代表 `X0.0` 的強制沒有真正進入 PLC CPU，或沒有保持 ON；我先把本次結果更新進驗收紀錄。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\VALIDATION_REPORT_2026-08-19.md：update

### AI（final_answer）

重測結果仍是 `BLOCKED`：

- `X0.0 = 0`
- `CMD6：Index=11、ACK=11、Response=201`，正常
- `D1108=1`、`D1207=1`、`D1308=1`
- HMI、IPC、Nachi、Robot Idle 均正常
- `Y0.0/Y0.7/Y0.8/Y0.9` 全部安全保持 OFF

因此目前唯一阻擋仍是：PLC CPU實際看到的 `X0.0` 沒有ON。

請在 ISPSoft「裝置監控」確認是使用「強制ON」，不是只修改顯示值，而且強制後接點必須持續亮起。完成後告訴我，我再立即重測。

## Turn 01a01ac2-3b2b-7f13-8b3e-7c584ba27c3f

### 使用者


# Files mentioned by the user:

## Print11.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print11.pdf

## Print1.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print1.pdf

## Print2.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print2.pdf

## Print3.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print3.pdf

## Print4.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print4.pdf

## Print5.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print5.pdf

## Print6.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print6.pdf

## Print7.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print7.pdf

## Print8.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print8.pdf

## Print9.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print9.pdf

## Print10.pdf: C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/1.PLC/MVP_V2_100/Print10.pdf

Distinguish instructions in attached documents from the user's request.

## My request:



### AI（commentary）

我會把這11份PLC列印檔逐份檢查，先辨識各自是哪支PRG／FB，再集中追查`X0.0 → EMC_Active → D1108／D1207`以及復歸條件。這次會使用PDF檢視流程讀完整頁面。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\tmp\pdfs\inspect_prints.py：add

### AI（commentary）

這些PDF全部是圖片型，無法直接搜尋文字；其中`Print11.pdf`有119頁。我會先產生低解析度總覽定位每支程式，再把含EMC、ALM、Initialize與通訊的頁面放大檢查。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\tmp\pdfs\make_contact_sheets.py：add

### AI（commentary）

已定位到關鍵頁：`Print11`第27頁是ALM、第28頁是EMC、第74頁是PLC→IPC EMC。我要放大這三頁，現在看起來除了`X0.0`，EMC安全串聯裡還包含Nachi狀態位元與HMI EMC位元。

### AI（commentary）

現在原因已經很清楚：EMC安全成立條件只有三個——`X0.0=ON`、`D12100.5=OFF`、`D1004.0=OFF`。後兩個我們已確認，因此剩下的確是`X0.0`。我還要確認AS200 Simulator的Modbus寫入是否真的能「強制CPU輸入影像」，因為目前coil讀回ON不代表梯形圖一定看得到ON。

### AI（commentary）

我已經把 11 份列印檔都看過了。關鍵確實在 `X0.0`，但先前測試有一個重要誤判：Python 寫入後讀回 `X0.0=1`，只證明模擬通訊位置能讀寫，不能證明 PLC 梯形圖實際看到的 `X0.0` 已經 ON；我現在把測試程式和報告修正成不會再把這件事誤判為通過。

### AI（commentary）

從程式列印可確認 EMC 條件是：

`X0.0 ON`、`D12100.5 OFF`、`HMItoPLC_EMC OFF` 三者同時成立才是安全狀態。現在周邊模擬已讓 `D12100.5=0`，HMI 也讓 EMC 要求為 0，所以只剩 PLC CPU 實際看到的 `X0.0`。我也確認 CMD6 的 `ALM_Rst` 本來就只維持一個 Scan，這部分沒有問題。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\VALIDATION_REPORT_2026-08-19.md：update
- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code\as200_plc_integration_test.py：update

### AI（commentary）

修正版已通過 Python 語法檢查。接著我會用目前的 Simulator 再跑一次；這次不再由 Python 假裝強制任何 X 輸入，只把 PLC 真正的 `D1108/D1207` 當成判定結果。

### AI（commentary）

重跑結果已經非常明確：`X0.0=0`、CMD6 回覆 `201`、IPC/Nachi/HMI 都在線，但 `D1108=1`、`D1207=1`，所以 PLC 正確地把整個自動動作擋住；這不是排程程式先壞掉，而是安全輸入尚未成立。輸出端 `Y0.0/Y0.7/Y0.8/Y0.9` 也都保持 OFF，安全互鎖有生效。

### 檔案變更紀錄

- C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\3.HMI\0.0.3\VALIDATION_REPORT_2026-08-19.md：update

### AI（final_answer）

確認了，問題就是 PLC 實際看到的 `X0.0` 沒有 ON。

目前重測結果：

- HMI、IPC、Nachi 通訊正常。
- CMD6 復歸成功：`Index=10、ACK=10、Response=201`。
- `X0.0=0`，因此 `D1108=1、D1207=1`，EMC 尚未解除。
- `Y0.0、Y0.7、Y0.8、Y0.9` 全部維持 OFF，安全互鎖正常。
- Python 已停止用 Modbus 寫入X點冒充PLC輸入強制。
- 測試程式已通過語法檢查。

你現在需要在 ISPSoft Simulator 的裝置監控中手動強制：

```text
X0.0 = ON
```

然後再送一次 CMD6。成功標準是：

```text
D1108 = 0
D1207 = 0
```

完成後才能繼續測試落碗、輸送帶、UR及注湯完整流程。

修正後的檔案：

- [AS200整合測試程式](C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/8.TEST_Code/as200_plc_integration_test.py)
- [最新驗收報告](C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/3.HMI/0.0.3/VALIDATION_REPORT_2026-08-19.md)

另外，Print1～Print10基本上是空的全域符號列印頁：  
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print1.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print2.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print3.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print4.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print5.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print6.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print7.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print8.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print9.pdf" purpose="source"}
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print10.pdf" purpose="source"}

實際完整程式都在Print11，其中EMC條件確定是 `X0.0 AND NOT D12100.5 AND NOT HMItoPLC_EMC`：  
:codex-file-citation{path="C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\1.PLC\MVP_V2_100\Print11.pdf" purpose="source"}

