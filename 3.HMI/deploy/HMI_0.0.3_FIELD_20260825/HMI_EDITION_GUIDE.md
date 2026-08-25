# HMI版本分離

## SIMULATION 模擬測試版

- 啟動：`start_simulation_live_monitor.cmd`
- PLC：`127.0.0.1:10002`（AS200 Simulator）
- 允許讀取D8000模擬／除錯區。
- 輸送帶、IPC、UR1、UR2、Nachi等外部設備未連線時一律顯示 `SIMULATION PASS`，不產生現場斷線警報。
- 仍保留PLC本身連線判斷；AS200 Simulator沒有開啟時會顯示PLC離線。
- 可使用本機測試訂單、麵櫃資料與流程推進。

## FIELD 現場正式版

- 啟動：`start_field_live_monitor.cmd` 或 `start_hmi.cmd`
- PLC：`192.168.1.5:502`
- 禁止Mock與本機模擬流程；D8000區不得作為正式控制或流程顯示判斷來源。
- 診斷記錄器可在Auto模式唯讀保存D8000-D8031與D8100-D8134，但絕不回寫。
- 保留輸送帶、IPC、UR1、UR2、Nachi的正式連線、異常與安全檢查。
- 自動流程畫面只接受D8100正式監看區。未配置時顯示「PLC映射未完成」，不拿本機資料代替。
- 正式訂單與麵櫃寫入位址尚未完成前，相關本機按鈕會鎖定。
