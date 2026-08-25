# 自建點餐系統與PLC全自動控制——核心記憶

記憶優先級：最高  
建立日期：2026-08-24  
資料來源：本聊天串、`7.Ordering/0.0.1`、`3.HMI/0.0.3`、`1.PLC/MVP_V2_101`候選專案及`8.TEST_Code`整合測試。

## 1. 原始目標

建立不依賴LINE或第三方點餐平台的自建手機點餐系統。顧客用手機開啟HTTPS網站，選擇餐點、麵條熟度、數量及取餐名稱；HMI後台接單後，把多碗訂單拆成可由PLC獨立追蹤的單碗製作任務。PLC負責實際排程、麵篩選擇、四站流動、Robot授權、安全互鎖及完成回報。

重要邊界：手機前端不選擇實體麵櫃，也不直接操作PLC。麵櫃分配、庫存保留及單碗Unit建立由HMI後台處理；機械排程與動作授權由PLC處理。

## 2. 點餐前端

目前前端位於`7.Ordering/0.0.1`，第一版餐點是經典豚骨拉麵，單價NT$180。使用者可以：

- 選擇麵條熟度。
- 選擇1~99碗。
- 輸入取餐名稱。
- 確認總價並送出訂單。
- 接收取餐號與等待製作狀態。

若存在`window.ORDER_API_URL`，前端POST JSON到HMI後台；否則以瀏覽器`localStorage`建立A001形式的本機測試取餐號。

目前前端送出資料：

```json
{
  "productId": "classic-tonkotsu",
  "productName": "經典豚骨拉麵",
  "noodleFirmness": "正常",
  "quantity": 2,
  "pickupName": "顧客名稱",
  "total": 360
}
```

這是一張商業訂單，不是PLC工件命令。HMI後台必須將`quantity=2`拆成兩個不同UnitID。

## 3. HMI訂單與庫存模型

HMI本機模型由`AutoHMIStore`保存：

- `next_unit_id`：下一個唯一單碗編號，初始示範值1001。
- 10個麵櫃：每格保存quantity與capacity。
- 2個空盒櫃：每格保存quantity與capacity。
- `orders`：所有單碗Unit。
- 3個麵篩：Idle／Cooking及目前UnitID。
- 4個站：落碗、放麵&UR1、UR2、注湯&完成。

新增訂單前，HMI計算：

```text
可用量 = 麵櫃目前數量 - 尚未Complete/Cancelled訂單的保留量
```

可用量小於等於0時禁止接單。新增成功後分配唯一UnitID並保存cabinet、firmness、Queued及created_at。完成後才扣除實際麵櫃數量；取消只允許Queued狀態。

本機資料以暫存檔寫完後replace，降低寫入中斷造成JSON損壞的風險。PLC正式同步完成後，PLC回報才是流程狀態真值，本機模型只作UI快取或離線用途。

## 4. 商業訂單與PLC Unit的轉換

```text
手機一張訂單（quantity=N）
  -> HMI驗證品項、熟度、名稱與庫存
  -> HMI選擇麵櫃
  -> 拆成N筆單碗Unit
  -> 每筆分配唯一UnitID
  -> 逐筆與PLC進行收單握手
  -> PLC複製進內部FIFO後才算Accepted
```

不能因HMI寫入D暫存器就立刻把訂單標為Accepted。只有PLC回覆同一UnitID與同一Order Index的ACK後，HMI才可更新狀態。

## 5. AUTO收單通訊契約

目前程式與測試使用：

| 位址 | 方向 | 內容 |
|---|---|---|
| D1020~D1021 | HMI→PLC | UnitID，32-bit DINT，low word在前 |
| D1022 | HMI→PLC | Cabinet No，1~10 |
| D1023 | HMI→PLC | Firmness，最新版Scheduler定義為1硬、2正常、3軟 |
| D1024 | HMI→PLC | Order Index |
| D1025 | HMI→PLC | Order Valid |
| D1130~D1131 | PLC→HMI | ACK UnitID |
| D1132 | PLC→HMI | ACK Index |
| D1133 | PLC→HMI | FIFO Count |
| D1134 | PLC→HMI | Order Response |
| D1135~D1136 | PLC→HMI | Completed UnitID |
| D1137~D1138 | PLC→HMI | Completion Index／流水號 |

注意：`auto_plc_contract.py`目前未完整列出D1024、D1132、D1134，但AS200整合測試明確使用它們。正式發布前必須把契約檔、PLC tags、HMI程式與測試常數統一，避免同一協定分散在多處。

## 6. 收單握手

建議且目前測試採用的安全順序：

1. HMI先令D1025 Valid=0。
2. 寫入UnitID、Cabinet、Firmness與新Order Index。
3. 最後令Valid成立。
4. PLC只接受Valid且Index為新值、UnitID合法的訂單。
5. PLC把資料複製到內部FIFO。
6. PLC回覆相同ACK UnitID、ACK Index、Response並更新FIFO Count。
7. HMI核對UnitID與Index後才標示PLC Accepted。
8. HMI清除Valid，下一筆訂單使用新Index。

新Index應同時避開輸入區殘留Index及PLC已ACK Index；16-bit循環後不得使用0作為不明確的新命令值。

## 7. PLC內部流程設計

PLC不是簡單依訂單FIFO一路串行。它需要同時管理：

- 訂單FIFO。
- 三個麵篩的可用狀態與不同熟度時間。
- 落碗區是否可接受下一碗。
- 四個輸送站的UnitID占用。
- Nachi放麵動作。
- UR1 CMD103預先辨識及CMD101執行。
- UR2 CMD102執行。
- Robot碰撞區互斥。
- 注湯與完成回報。

因此「先進FIFO」只代表排隊順序，不保證最後完成順序。任何站、麵篩或Robot資源都必須保存目前UnitID。

## 8. 四站與Robot任務

四站：

1. 落碗。
2. 放麵與UR1。
3. UR2。
4. 注湯與完成。

UR任務：

- CMD103／RESP203：UR1視覺預拍並凍結蛋、筍乾、木耳目標。
- CMD101／RESP201：UR1依凍結目標實際投料。
- CMD102／RESP202：UR2後段配料／湯勺流程。

所有任務必須攜帶Seq；PLC必須核對Ack、Busy、Response及Response Seq。IPC錯誤後維持錯誤狀態等待人工復歸，不自動盲目重送。

## 9. 完成與顧客通知

PLC完成一碗時輸出Completed UnitID及單調遞增Completion Index。HMI不得只監看一個短Done Pulse，也不得以「FIFO第1筆」推測完成者。

HMI收到新的Completion Index後：

1. 讀取Completed UnitID。
2. 找到對應單碗Unit及原始商業訂單。
3. 將Unit標為Complete。
4. 扣除正確麵櫃的實際庫存。
5. 若同張商業訂單全部Unit完成，通知對應取餐號／顧客。
6. 保存已處理Completion Index，避免HMI重啟後重複扣庫存或重複通知。

## 10. 模擬與驗證策略

此規劃的強項是把完整點餐到出餐鏈拆成可驗證層級：

1. HMI本機模型驗證多碗拆單、UnitID、庫存保留及完成扣庫存。
2. Python參考模型驗證FIFO、三麵篩、不同熟度及資源衝突。
3. Virtual Modbus PLC驗證HMI與IPC介面、故障情境。
4. AS200 Simulator執行真正PLC程式，Python只模擬訂單、X感測器、Nachi及UR回覆。
5. 單碗全流程測試確認落碗→放麵/UR1→UR2→注湯完成。
6. 多訂單及流水線壓力測試確認不同Unit同時位於不同站。
7. FIFO復歸測試確認中斷後不遺失或重複訂單。
8. 1000筆耐久測試保存每筆submitted、dropped、completed、latency、FIFO、麵篩狀態與result。
9. 最後才進入實體I/O、低速Robot、碰撞區及完整FAT。

## 11. 禁止事項

- 手機或HMI不得直接寫Robot命令區繞過PLC。
- 不得把一張多碗訂單只用一個UnitID。
- 不得只依完成順序配對訂單。
- 不得只看Response Code而不核對Seq。
- 不得因IPC timeout就自動重送投料任務。
- 不得把Python模型通過等同PLC程式或實機通過。
- 不得用Simulation Mode、強制X或測試D區繞過正式安全條件。
- 不得讓軟體EMC取代實體安全回路。

## 12. 目前缺口

1. HMI正式訂單API尚未完整實作。
2. 顧客查詢訂單狀態與完成推播尚未完成。
3. 商業OrderID、取餐號與多個UnitID的永久關聯需正式資料庫。
4. AUTO契約檔尚未完整列出所有實際使用位址。
5. Unit Status與麵櫃／空盒庫存PLC同步區仍需定案。
6. `MVP_V2_101`仍需與現場PLC正式版核對。
7. 測試程式必須搭配實際log與summary才能形成驗收或研究證據。

## 13. 保存原因

這套設計的價值不只是點餐網頁，而是建立從商業訂單到PLC工件追蹤的完整可驗證控制鏈。UnitID、Order Index、Completion Index、分層模擬及故障注入，使它可以延伸成PLC整合研究、數位分身驗證框架，以及未來AI生成PLC程式的安全測試層。
