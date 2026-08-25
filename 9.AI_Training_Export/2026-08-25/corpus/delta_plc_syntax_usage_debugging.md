# 台達AS200／ISPSoft語法、使用方式與錯誤排查記憶

適用範圍：MVP Ramen候選PLC專案與其測試環境  
優先級：高  
原則：IEC 61131-3通用語法可作基線；台達專用指令、裝置範圍、通訊FB與版本差異必須由目標AS200／ISPSoft編譯器及同版手冊確認。

## 1. 工程環境

- PLC：台達AS系列／AS200專案。
- 開發工具：ISPSoft。
- PLC工程入口：`.isp`。
- 同版本需一起保存：`.isp`、`.bak`、`.hwc`、`.tag`、`.pnt`、`.ini`、`.ipc`、`.eiptag`、EDS及其他專案相依檔。
- `.pnt`與部分`.tag`是廠商格式，不能用一般文字編輯器可靠修改。
- `.~bak`是自動備份，不是正式release。

修改PLC前先複製完整版本資料夾並記錄before／after、修改原因、下載人、編譯結果及回復版本。

## 2. Structured Text基本語法

### 2.1 註解

專案使用IEC區塊註解：

```st
(* 這是PLC程式註解 *)
```

註解應說明「為什麼需要此互鎖或狀態」，不只重複程式表面行為。

### 2.2 指派

ST變數指派使用`:=`：

```st
ActiveUnitID := UR1GrantUnitID;
IPCCommandTrigger := FALSE;
```

比較使用`=`或`<>`：

```st
IF IPCBusy = 0 THEN
END_IF;

IF UnitID <> 0 THEN
END_IF;
```

不要把`=`誤寫成指派，也不要把其他語言的`==`帶進ST。

### 2.3 IF／ELSIF／ELSE

```st
IF condition_a THEN
    output_a := TRUE;
ELSIF condition_b THEN
    output_b := TRUE;
ELSE
    output_a := FALSE;
    output_b := FALSE;
END_IF;
```

MVP邏輯常用`AND`、`OR`、`NOT`組合互鎖。複合條件需加括號，避免優先級誤讀：

```st
IF (IPCRequestValid = 0)
    AND (IPCBusy = 0)
    AND NOT IPCFirstMaterialPending THEN
```

### 2.4 CASE狀態機

```st
CASE ActionStep OF
    0:
        (* Idle *)
    10:
        (* Wait channel *)
    20:
        (* Wait completion *)
    90:
        (* Error hold *)
ELSE
    (* 未定義step安全回待機 *)
    ActionStep := 0;
END_CASE;
```

每個Step應有：進入條件、保持條件、完成條件、timeout／error出口。`ELSE`必須把未定義狀態導向明確安全狀態，但不可在未知實體位置時直接重啟動作。

### 2.5 FOR與ARRAY

實際監看程式使用：

```st
FOR MonitorSearchIndex := 0 TO 15 DO
    IF UnitFIFO.Units[MonitorSearchIndex].UnitID <> 0 THEN
        (* 搜尋Unit *)
    END_IF;
END_FOR;
```

注意陣列上下界必須與宣告一致。每scan掃描大型陣列會增加scan time；增加FIFO容量後應重新量測PLC scan。

### 2.6 數值常數與位元旗標

十六進位常數範例：

```st
PLCtoHMI_AutoMonitorMagic := 16#A55A;
```

現行監看程式用加法組合互斥bit值：1、2、4、8……。只有在每個bit最多加一次時才安全；更通用的實作可使用經ISPSoft確認支援的位元操作。修改前須編譯確認型別與運算子。

### 2.7 單scan脈波

```st
DonePulse := FALSE;

IF completion_condition THEN
    DonePulse := TRUE;
END_IF;
```

先在每scan清FALSE，只有完成轉移當scan設TRUE。跨Modbus的接收端可能漏掉短pulse，因此重要事件還要保存UnitID與遞增Index。

## 3. 資料型別與暫存器

常用概念：

- `BOOL`：單一邏輯狀態。
- `WORD`：16-bit無號位元／數值容器。
- `INT`：16-bit有號整數。
- `DWORD`：32-bit位元／無號概念，實際符號性依宣告與工具。
- `DINT`：32-bit有號整數，占兩個連續D word。
- `STRUCT／DUT`：Unit、Basket等結構化資料。
- `ARRAY`：FIFO Units或多資源集合。

Modbus讀DINT時需確認word order。本專案Python測試採low word在前：

```text
raw = (high_word << 16) | low_word
```

寫入D1020的UnitID會占D1020與D1021；配置下一欄時不得重疊D1021。

## 4. Ladder與ST的分工

建議：

- Ladder：硬體I/O、簡單互鎖、模式允許、輸出線圈及現場維修容易監看的邏輯。
- ST／FB：FIFO、Unit資料、CASE狀態機、多資源排程、通訊協定與監看資料組裝。

同一輸出避免由多個POU重複寫入。若Ladder與ST都會寫同一變數，最終值取決於執行順序，容易出現「線上看到條件成立但輸出又被後面程式覆蓋」。應建立單一owner，其他模組只送Request／Grant。

## 5. ISPSoft正確使用流程

1. 確認目標資料夾及PLC版本，禁止直接修改不明正式版。
2. 用ISPSoft開啟`.isp`，確認硬體型號、模組、通訊與POU清單。
3. 先完整編譯基準版，保存原本warning／error。
4. 變更Tag、DUT、FB介面後，先修正所有呼叫端再編譯。
5. 檢查交叉參照：變數在哪裡被讀、寫、重複線圈或重複指派。
6. 將候選版下載到AS200 Simulator，不先連現場輸出。
7. 用Device Monitor觀察Step、UnitID、Seq、Ack、Busy、Response、timeout及Alarm。
8. 通過自動測試後才進入斷動力I/O、低速單步及實機FAT。
9. 上線前後各保存完整專案、checksum、PLC Run狀態與回復版本。

## 6. 編譯錯誤排查

### 6.1 Syntax Error

依序檢查：

- 每個statement是否有`;`。
- `IF`是否有`THEN`及`END_IF;`。
- `CASE`是否有`OF`、`ELSE`與`END_CASE;`。
- `FOR`是否有`DO`與`END_FOR;`。
- 指派是否使用`:=`。
- 括號是否成對。
- 變數名稱是否與宣告完全一致。
- 全形標點、智慧引號或不可見字元是否被貼入。

### 6.2 Unknown Identifier

- 確認是Global、Program local、FB input/output/inout或DUT member。
- 確認POU作用域與大小寫／拼字。
- 確認新Tag已加入正確resource／task。
- 若從另一版本複製ST，先比對該版本DUT與FB介面。

### 6.3 Type Mismatch

- BOOL不能直接當完整WORD使用，bit與word需明確轉換／遮罩。
- DINT占兩個word；不要把單一WORD直接當完整UnitID。
- INT有符號範圍，Seq與bit word通常更適合WORD語意。
- 比較或加法兩側型別不同時，使用ISPSoft支援的明確轉型並編譯確認。
- Modbus Python端的unsigned word與PLC有號型別要在邊界轉換。

### 6.4 Array／STRUCT錯誤

- 檢查索引上下界。
- 確認DUT member名稱與型別。
- FIFO Count不應超過陣列容量。
- 使用搜尋迴圈時仍要以UnitID有效性判斷空slot。

## 7. 線上邏輯錯誤排查

採「輸入→允許→狀態機→命令→回覆→下一步」逐層查，不要直接強制最後輸出。

### 7.1 命令沒有被接受

查：

1. Command／Order Valid是否成立。
2. Index／Seq是否真的比已ACK值新。
3. PLC是否在正確模式。
4. EMC／Alarm是否解除。
5. FIFO或通道是否有空間。
6. ACK是否更新但HMI讀錯位址。
7. 命令是否在同scan被其他POU清除。

### 7.2 狀態機卡住

同時監看：Step、Active UnitID、等待的感測器、Timer Done、Grant、Busy、Response Seq、Error Code。找出「唯一未成立的轉移條件」。不要直接改Step跳過，因為實體資源與UnitID可能未完成交接。

### 7.3 輸出不動

查：

- Request是否成立。
- Safety／Mode／Zone Grant是否成立。
- 最終線圈是否被後續POU覆寫。
- Y輸出映射與硬體模組是否正確。
- Simulator的X/Y Modbus位址是否使用AS200標準coil mapping。
- 現場則查端子、極性、電源、保護元件及安全回路。

### 7.4 輸出一直ON

- 找所有寫入點及Set/Reset線圈。
- 檢查完成／error出口是否清除Request。
- 檢查Step復歸但Active旗標未清。
- 檢查HMI或測試器是否持續重寫。
- 不可只在Monitor手動OFF，需找到下一scan再次寫ON的來源。

### 7.5 重複執行

- Valid未清或Index沒有去重。
- PLC ACK在資料複製前回覆，HMI太早送下一筆。
- IPC只看Code、不看Seq。
- HMI重啟後Index從0開始撞到舊ACK。
- timeout後自動重送不可逆任務。

### 7.6 完成錯配

- 完成只用pulse，沒有UnitID。
- Completed UnitID與Completion Index非同scan／同事件更新。
- HMI依FIFO順序猜完成者。
- DINT高低word讀反。
- Unit在站間轉移時上游先被清除或兩站同時持有。

## 8. 通訊錯誤排查

### HMI離線

依序查D1100是否變化、D1005是否跟隨、D1105判定、IP／port／device ID、防火牆及是否存在多個無仲裁Modbus client。

### IPC離線或一直Busy

查D1200／D1300心跳、D1203 Valid、D1202 Seq、D1301 Ack、D1302 Busy、D1303 Response、D1304 Response Seq、D1305 Error。確認Robot任務是否回傳及例外是否經finally清Busy。

### Nachi異常

查D12100狀態bits、D12101接收完成、D12102 Error、D12103 Action Complete、D12104 Index，以及D12150~D12156命令參數。不要由HMI寫入Robot區偽造正常狀態。

### 輸送帶異常

查命令、速度設定、D1104狀態、D1107 timeout、RTU站號／baud／parity／功能碼／設備位址、接線及PLC通訊FB Error。舊IO Excel不能作現行參數依據。

## 9. Timer與Timeout使用原則

每個外部動作都要有獨立Timer instance；輸入條件解除時確認Timer是否需要reset。timeout應保存Step、UnitID、命令與錯誤碼。Timer設定值需有時間單位且來自核准參數，不能混用scan count與毫秒。

### 9.1 V2_101 已核對的 TMR 用法

V2_101 的 ISPSoft 列印程式已確認本專案使用台達 `TMR`，不是 IEC `TON/TOF` 寫法：

- 梯圖：`S1` 接 TIMER 變數，`S2` 接時間設定值；例如 `Soup_Timer` 配 `50`。
- ST：`TMR(T_HMI_CommTimeout, 30);`。
- 專案既有註解與模擬觀察均以 100 ms 為一單位；設定 50 約為 5 秒、30 約為 3 秒。實機時間基準仍應以 AS200 CPU 與 ISPSoft 線上監看確認。

因此 AI 產生 V2_101 相容程式時，應優先複製上述 `TMR` 模式；除非另建 IEC FB 並完成編譯驗證，不應自行改寫成 `TON/TOF`。

### 9.2 V2_101 已核對的 MODRWE 接線模式

`Conveyor_ModbusRTU_Control` 的實際梯圖顯示 `MODRWE` 端子為 `S1、S2、S3、S4、S、n`，完成輸出 `D` 接 `M100`（`Com2_Comm_Done`）。已觀察到的專案實例包括：

- 初始化寫入：`S1=2, S2=1, S3=16#000F, S4=16#0003, S=D0.0, n=1`。
- 初始化讀取：`S1=2, S2=1, S3=16#0002, S4=16#0003, S=D0.3, n=1`。
- 速度寫入：`S1=2, S2=1, S3=16#0010, S4=16#0000, S=K100, n=1`。
- 狀態讀取：`S1=2, S2=1, S3=16#0002, S4=16#0007, S=D100.0, n=9`。

這些數值是 V2_101 程式的可重現接線證據；但僅由列印圖不能安全把 `S4` 抽象定義成所有功能碼都通用的單一語意。修改站號、功能／模式、設備位址或資料區時，必須以同版 ISPSoft 指令說明及編譯結果核對，並確認 `M100` 完成握手在下一筆命令前已復歸。

## 10. 強制與模擬注意事項

- AS200 Simulator的實體輸入映像應使用正確coil mapping或ISPSoft Force，不要把任意D暫存器當X。
- Force前記錄原值，測試後恢復。
- FIELD實機Force輸出可能造成機械動作，必須斷動力或有受控測試許可。
- Simulation Mode只允許Simulator；正式HMI應鎖定模擬頁。
- 測試專用D區不得成為正式安全旁路。

## 11. 建議的除錯紀錄格式

```text
PLC版本：MVP_V2_101 candidate
時間：
模式：Manual/Semi/Auto
UnitID：
Step：
輸入／感測器：
Grant／Busy：
Command Seq：
Ack Seq：
Response／Response Seq：
Timer ET／PT：
Alarm／Error Code：
預期：
實際：
修正：
重測結果：
```

## 12. AI生成PLC語法的驗收門檻

AI輸出必須：

1. 指定AS200、ISPSoft版本及POU語言。
2. 使用可編譯的ST／LD語法，不混入Python、C或其他PLC方言。
3. 列出所有新增變數、型別、作用域、初值與地址。
4. 不重疊DINT／DWORD連續word。
5. 不產生多重輸出owner。
6. 包含未定義Step、timeout、error與reset路徑。
7. 附交叉參照、編譯、Simulator、故障注入與FAT測試。
8. 對不確定的台達專用指令明確標示「需同版手冊／編譯器確認」，不得捏造。
