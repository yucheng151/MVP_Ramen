# MVP Ramen 本機測試

這個資料夾包含兩類測試，兩者用途不同：

1. `plc_auto_logic_sim.py`：重建全自動流程的Python參考模型，執行單碗、多碗、三麵篩、非FIFO熟成與隨機壓力測試。
2. `virtual_plc_modbus.py`：提供HMI與IPC可連線的本機Modbus TCP虛擬PLC，模擬D、X、Y、心跳、命令與故障。
3. `as200_peripheral_sim.py`：連到真正的AS200 Simulator，模擬IPC／UR與Nachi外部設備回覆。
4. `as200_plc_integration_test.py`：直接測真正AS200 PLC程式的心跳、X映射、EMC與Y輸出快照。

## 1. 流程壓力測試

```powershell
py plc_auto_logic_sim.py --random-tests 200
py plc_auto_logic_sim.py --trace --random-tests 20
```

## 2. 啟動虛擬PLC

```powershell
py virtual_plc_modbus.py
```

若502埠已被占用，可改用1502。HMI可用`--port`指定相同埠號。

若要直接連AS200 Simulator，COMMGR畫面預設使用10002埠。

## 3. 啟動HMI

在另一個終端：

```powershell
cd ..\3.HMI\0.0.3
py main_hmi.py --ip 127.0.0.1 --port 502

# 直接連目前的AS200 Simulator
py main_hmi.py --ip 127.0.0.1 --port 10002
```

這不會修改正式的 `config.py`。

## 3.1 模擬AS200外部設備

AS200 Simulator已啟動並載入PLC程式後：

```powershell
py as200_peripheral_sim.py --host 127.0.0.1 --port 10002
```

它會模擬：

- IPC心跳：`D1200 -> D1300`
- IPC命令：`101/102/103 -> 201/202/203`
- IPC ACK、Busy、ResponseSeq與EMC完成
- Nachi Standby/Home、資料接收完成及動作完成脈波

`as200_plc_integration_test.py`會使用AS200 Simulator的Modbus coil位址
`16#0400`起點強制真正的`X0.1~X0.4`；不會使用D15000冒充X接點。

## 3.2 一鍵測真正AS200 PLC程式

```powershell
py as200_plc_integration_test.py --host 127.0.0.1 --port 10002
```

這支程式會自行啟動IPC／Nachi周邊回覆、維持HMI心跳，並使用AS200標準
Modbus位址`16#0400`強制`X0.1~X0.4`。測試結束會恢復原本X及命令碼／有效位，
但不倒退D1001命令Index，避免和PLC已保存的D1102 ACK碰撞。

## 4. 控制I/O

再開一個終端：

```powershell
py modbus_io_control.py status
py modbus_io_control.py set-x X0.1 on
py modbus_io_control.py set-x X0.2 on
py modbus_io_control.py set-y Y0.7 on
py modbus_io_control.py set-y Y0.7 off
py modbus_io_control.py read-d 1110
py modbus_io_control.py write-d 1109 2
```

## 5. 一鍵Modbus整合測試

虛擬PLC啟動後，在另一個終端執行：

```powershell
py modbus_integration_test.py --host 127.0.0.1 --port 502
```

會自動測試心跳、命令ACK、X0.1~X0.4、Y0.0/Y0.7/Y0.8/Y0.9與全部故障情境。

## 6. 故障情境

```powershell
py modbus_io_control.py scenario normal
py modbus_io_control.py scenario slow
py modbus_io_control.py scenario bowl_sensor_stuck
py modbus_io_control.py scenario station20_stuck
py modbus_io_control.py scenario ipc_timeout
py modbus_io_control.py scenario robot_alarm
py modbus_io_control.py scenario emc
```

情境控制使用測試專用D15010，不得加入正式PLC/HMI位址規格。

## 限制

Python測試器不會解析或執行ISPSoft `.isp`。Python模型、Modbus整合測試與ISPSoft Simulator三者都通過後，才進行實體PLC及機台測試。
