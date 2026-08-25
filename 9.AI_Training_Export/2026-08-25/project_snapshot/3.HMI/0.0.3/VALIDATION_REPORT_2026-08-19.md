# HMI 0.0.3與AS200整合驗收報告

驗收日期：2026-08-19；修正重測：2026-08-20  
驗收環境：Windows、Python 3.13、pymodbus 3.14、AS200 Simulator `127.0.0.1:10002`

## 結論

HMI 0.0.3介面、Mock命令、FIFO／UnitID、多碗排程參考模型，以及HMI對真正AS200 Simulator的Modbus連線均已通過。

目前不能判定整台自動機流程完成。重新核對`Print11.pdf`後，修正先前兩項判讀：

1. Python以Modbus寫入X位址後再讀回ON，只能證明通訊位址有回應，不能證明AS200 Simulator的PLC CPU輸入映像已被強制；先前「X0.0強制成功」與「X0.1~X0.4強制成功」的PASS判定作廢。
2. PLC的EMC安全鏈為`X0.0 AND NOT D12100.5 AND NOT HMItoPLC_EMC`。周邊模擬值`D12100=16#1207`使`D12100.5=0`，`D1004=0`，所以目前真正未成立的條件就是PLC CPU所見的`X0.0`。必須在ISPSoft Simulator內手動強制`X0.0 ON`後再送CMD6。

## 1. HMI程式與介面

| 測試 | 結果 |
|---|---|
| Python完整編譯 | PASS |
| 7個主頁建立、切換、刷新 | PASS |
| AUTO SYSTEM 4個分頁 | PASS |
| 實際麵櫃底圖載入 | PASS |
| 12個BOX熱區點選與數量／容量編輯 | PASS |
| FIFO、UnitID、熟度、三麵篩與四站畫面 | PASS |
| 14種HMI命令Mock測試 | PASS |
| HMI重開後從D1001／D1102接續命令Index | PASS（本次已修正） |

7個主頁：Home、Auto System、Alarm、PLC/HMI、IPC、Robot、Conveyor。

## 2. 多碗排程參考模型

| 測試 | 結果 |
|---|---|
| 單碗完整流程 | PASS |
| 三麵篩不同熟成時間 | PASS |
| 非FIFO煮熟順序 | PASS |
| 10筆訂單與麵篩循環 | PASS |
| 500組隨機壓力測試 | PASS |

參考模型沒有發現死鎖、UnitID錯配或既定碰撞條件違反；此結果不取代實際PLC程式與機台安全驗證。

## 3. 真正AS200 Simulator周邊模擬

Python直接連到執行`MVP_V2_100`的AS200 Simulator，不另建假PLC：

| 測試 | 實測結果 |
|---|---|
| HMI實際通訊模組連線 | PASS |
| HMI心跳D1100→D1005、D1105 | PASS，D1105=1 |
| IPC心跳D1200→D1300、D1209 | PASS，D1209=1 |
| IPC命令101／102／103回覆201／202／203模擬 | 已建立 |
| Nachi Standby／Home | PASS，D12100=`16#1207` |
| Robot_Idle | PASS，D1124=1 |
| HMI Alarm Reset CMD6 | PASS；CPU重新RUN後Index=1、ACK=1、Response=201 |
| 切換全自動CMD32 | PASS，Response=302、D1109=2 |
| X0.0 Simulator CPU強制 | PASS；Modbus X讀值仍為OFF，證明兩者不是同一個判據 |
| X0.1~X0.4 Modbus位址寫入／讀回 | INCONCLUSIVE，不代表PLC CPU輸入已被強制 |
| X0.1~X0.4→D1110.0~D1110.3 | PLC列印程式未見D1110鏡像邏輯；若HMI要顯示感測器，仍須補上 |
| EMC解除 | PASS，D1108=0、D1207=0；可進入後續動作測試 |
| Y0.0／Y0.7／Y0.8／Y0.9 | 未執行動作；EMC期間皆保持OFF |

最新重測結果：`FAIL=0、BLOCKED=0`。測試沒有繞過EMC安全互鎖。

上述`FAIL=0、BLOCKED=0`是基礎通訊、安全鏈與自動模式切換結果；真正AS200 PLC的單碗流程尚未啟動，因為全自動訂單資料區仍未配置。

## 4. PLC還需要完成的項目

### 必須先修正

1. 在ISPSoft Simulator的裝置監控／強制功能中將`X0.0`設為ON，再送一次CMD6。成功標準是`D1108=0`且`D1207=0`，不是Modbus讀回X0.0=1。
2. 若HMI要顯示四個站點感測器，請在每個PLC Scan加入並確認感測器鏡像：
   - `X0.1 → D1110.0`（落碗到位）
   - `X0.2 → D1110.1`（放麵／UR1站）
   - `X0.3 → D1110.2`（UR2站）
   - `X0.4 → D1110.3`（注湯／出料站）
3. `CMD6`會讓`ALM_Rst`維持一個PLC Scan，並復歸`ALM_Active`與`EMC_Active`；這段程式本身符合目前設計。X0.0確實ON後若仍無法解除，再檢查Simulator是否已下載最新編譯版本。
4. 本地模擬時，需要提供輸送帶Modbus RTU設備模擬，或新增明確且只允許Simulator使用的`Simulation_Mode`。不得在實機模式繞過輸送帶及EMC安全條件。

### 自動點餐通訊仍未配置

`auto_plc_contract.py`中的13組AUTO位址目前全部為`None`，因此HMI訂單與麵櫃資料仍保存在本機JSON，尚未送入PLC FIFO。PLC需分配並確認：

- 訂單UnitID、麵櫃編號、熟度、Valid／ACK。
- PLC FIFO筆數及每碗`DUT_Unit`狀態。
- 三個`DUT_NoodleBasket`狀態。
- 四站碗狀態。
- 麵櫃10格與左上空盒2格數量。
- 完成脈波與完成UnitID。

2026-08-20實讀`D1020~D1029`與`D1110~D1119`皆為0。現有列印程式的`FB_AutoScheduler`只讀內部`UnitFIFO`，未看到把`D1020~D1023`複製進FIFO的Valid／Index／ACK收單流程，因此不能猜測一個未定義位址直接建立測試訂單。

## 5. EMC修正後的下一輪測試

1. 單碗：落碗→放麵→UR1 CMD103→UR1 CMD101→UR2 CMD102→注湯完成。
2. 三碗連續輸送，驗證第一碗離開落碗區後才能落第二碗。
3. 三麵篩不同軟硬時間，驗證先下鍋不一定先起鍋。
4. 驗證Nachi與UR1 CMD101／UR2 CMD102不會同時進入碰撞區。
5. 驗證每次完成回覆正確UnitID並扣除正確麵櫃數量。

## 6. 重跑方式

AS200 Simulator載入`MVP_V2_100`並RUN，先在ISPSoft手動強制`X0.0 ON`後：

```powershell
cd C:\Users\Administrator\Desktop\ITRI\MVP_Ramen\8.TEST_Code
py as200_plc_integration_test.py --host 127.0.0.1 --port 10002
py hmi_003_interface_test.py
py plc_auto_logic_sim.py --random-tests 500
```
