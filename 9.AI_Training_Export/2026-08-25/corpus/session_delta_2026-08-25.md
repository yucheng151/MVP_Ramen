# MVP Ramen 最新工作增量（2026-08-23至2026-08-25）

## 1. 本文件目的

本文件只保存舊知識包建立後最後確認的新事實與修正。Claude接手時應先讀本文件，再讀完整專案知識。若本文件與2026-08-24文件矛盾，以本文件及同版本ISPSoft專案為優先。

## 2. 版本邊界

- `MVP_V2_101`：後續實際執行1000筆AS200耐久測試的版本；1000筆PASS證據歸屬此版。
- `MVP_V2_100`：前一版與部分最新重新匯出PDF所在目錄，用於確認`FB_ActionArbiter`、`Noodlebasket`與Scheduler設計；不可假設這些修改已全部同步進V101。
- 不得把V100的FB、V101的變數表和舊PDF拼成一個不存在的版本。
- 使用者在ISPSoft內的程式與最新重新匯出的PDF，優先於先前聊天文字或舊PDF。

## 3. 整機流程與硬體限制

四站定義固定為：

```text
站1 落碗
站2 放麵 & UR1
站3 UR2
站4 注湯 & 完成
```

輸送帶可同時存在多碗；排程以最右端尚未完成的碗優先。Nachi煮麵手臂、UR1、UR2共三支Robot。UR1與UR2主要動作互斥；UR1 CMD103預拍不占用輸送帶區域，可與輸送帶及Nachi部分動作並行，但不可與UR2或UR1 CMD101並行。

## 4. 三麵篩最新版狀態

`NoodleBasket_1..3`各自保存至少：

- `State`
- `UnitID`
- `NoodleCabinetNo`
- `FirmnessNo`
- `CookTimeSet`

已確認的主要狀態：

| State | 意義 |
|---:|---|
| 0 | 空閒，可分配 |
| 10 | 已分配Unit，尚未成為拿生麵請求 |
| 20 | 等待拿生麵 |
| 30 | Nachi拿生麵並放入麵篩中 |
| 40 | 煮麵計時中 |
| 50 | 煮麵完成，等待拿起熟麵及甩麵 |
| 60 | 拿熟麵及甩麵中 |
| 70 | 已甩好，停在安全等待位置 |
| 80 | 倒麵進碗中 |
| 90 | 倒麵完成，等待釋放 |

三個麵篩可同時處於State 40，但Nachi一次只能執行一個拿生麵動作，因此State 20/30按FIFO逐筆啟動。正常重疊序列應可觀察到：

```text
40 / 20 / 10
40 / 40 / 20
40 / 40 / 40
```

## 5. Noodlebasket PRG最新版計時

2026-08-23重新匯出的`MVP_V2_100/Print_Noodlebasket.pdf`有兩頁，已確認該版煮麵計時就在`Noodlebasket PRG`：

| 麵篩 | TIMER變數 | Timer裝置 |
|---|---|---|
| 1 | `NoodleBasket1_CookTimer` | T8 |
| 2 | `NoodleBasket2_CookTimer` | T9 |
| 3 | `NoodleBasket3_CookTimer` | T10 |

每個麵篩的梯圖語意：

```text
NoodleBasket_x.State = 40
  -> TMR(S1=NoodleBasketx_CookTimer,
         S2=NoodleBasket_x.CookTimeSet)
  -> Timer Done
  -> MOV 50 到 NoodleBasket_x.State
```

三個Timer獨立，不能共用。測試觀察顯示目前TMR基準約為100 ms，因此S2=500的實際效果約50秒，不是500 ms。正式時間仍需用ISPSoft說明、PLC設定與實測共同確認。

## 6. 軟硬度與CookTimeSet

使用者提供的最新版`FB_AutoScheduler`已實作：

```text
FirmnessNo = 1 -> CookTime_Hard_Set
FirmnessNo = 2 -> CookTime_Normal_Set
FirmnessNo = 3 -> CookTime_Soft_Set
```

這是本輪最新真值，會覆蓋舊文件曾記載的1=軟、3=硬。

Scheduler把訂單分配到空麵篩時，會複製UnitID、Cabinet、Firmness，並把選出的時間寫入`NoodleBasket_x.CookTimeSet`。因此時間檢查應同時監看：

```text
CookTime_Hard_Set
CookTime_Normal_Set
CookTime_Soft_Set
SelectedCookTime
NoodleBasket_1..3.FirmnessNo
NoodleBasket_1..3.CookTimeSet
T8 / T9 / T10
```

## 7. Scheduler逐筆拿生麵規則

最新版Scheduler允許三個訂單先分配到三個空麵篩，但同一時間只允許一個麵篩處於State 20或30。第一筆進入State 40後，下一筆才由State 10轉成State 20。這不是單麵篩限制，而是單一Nachi拿生麵動作的序列化。

## 8. ActionArbiter發現與修正

原本當`RightmostStation=20`且該碗對應麵篩為State 40時，Arbiter只等待煮熟，不會對其他State 20麵篩產生`NoodleLoadGrant`。結果即使Nachi Idle，仍常看到：

```text
State 10 / State 40 / State 20
```

修正原則：對應麵篩為State 30或40時，如果Nachi Idle、麵區未鎖、UR2未動、UR1未執行CMD101，而且任一其他麵篩為State 20，允許`NoodleLoadGrant=TRUE`。`FB_AutoNoodleAction`會選擇State 20麵篩，所以不會重複選到正在State 30/40的對應麵篩。

ISPSoft ST不允許`THEN`後只有註解。State 60與80若不執行任何指令，不應建立空白`ELSIF`分支；否則會出現錯誤6005，通常標在後續`ELSIF`與`END_IF`。

候選完整碼位於`reference_logic/FB_ActionArbiter_candidate_2026-08-25.st`。

## 9. HMI 0.0.3最後狀態

- Python/Tkinter後台與HMI同一應用。
- SIMULATION與FIELD啟動方式分離。
- SIMULATION允許D8000相容監看與周邊模擬；FIELD不得使用D8000測試輸入繞過現場條件。
- 一鍵自動測試可呼叫既有1000筆耐久程式，並從`hmi_stress_live.json`顯示每個UnitID目前位置。
- D8000相容區只能粗略顯示；完整三麵篩UnitID/Cabinet與多碗精確位置需D8100監看區已匯入且由MainAuto每scan更新。
- 模擬畫面顯示`Unit: --`不代表麵篩沒有Unit，可能只是D8000沒有該欄位。

## 10. 1000筆測試證據

`MVP_V2_101`於2026-08-23 08:41開始的耐久測試自然完成：

```text
Result: PASS
Submitted: 1000
Completed: 1000
Elapsed: 15981.551秒
Last UnitID: 145662000
```

證據檔前綴：`8.TEST_Code/logs/pipeline_1000_20260823_084100`。log目錄未放進一般快照，交接時應從原工作區保存。

較早一次`pipeline_1000_20260823_064444`在304筆後因完成逾時失敗；不能刪除這項歷史。後續PASS證明V101當時版本可完成1000筆，但若V100的Arbiter與計時修改再同步進V101，仍需重新做回歸測試，舊PASS不能自動涵蓋新碼。

## 11. 下一個必做驗證

1. ISPSoft編譯新版`FB_ActionArbiter`。
2. 線上確認Hard/Normal/Soft三個時間設定非0且單位正確。
3. 送至少三筆不同Firmness訂單，觀察三個`CookTimeSet`。
4. 碗停在站2、對應麵篩State 40時，確認其他State 20能進入30再40。
5. 確認三麵篩可同時40，且T8/T9/T10互不重置。
6. 確認先煮好者不會錯配UnitID或倒入錯碗。
7. 再跑單碗、多碗、不同熟度及1000筆回歸。
8. 上機前另做UR/Nachi碰撞區、感測器、EMC及斷線測試。

## 12. Claude回答風格與合作偏好

- 使用繁體中文，先給結論，再給一步一個操作。
- 使用者常直接貼ISPSoft畫面；需根據畫面真值，不要沿用舊PDF。
- 使用者要求「整支」時，要給可直接貼入的完整程式，不只片段。
- 變數表依`Class / Identifiers / Address / Type / Initial Value / Comment`格式；沒有內容的欄位留空。
- 不要擅自修改既有FB；除非使用者明確要求改碼，先診斷與指出精確位置。
- 不得把Python模擬PASS宣稱為實機安全通過。
