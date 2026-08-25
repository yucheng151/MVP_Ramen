(* =========================================================
   PRG_AutoHMIMonitor

   用途：只把PLC內部全自動狀態複製到D8100監看區。
   本程式不發出任何動作命令，不修改原本FB流程。

   區域變數：
   MonitorSearchIndex : INT;
   ========================================================= *)

(* HMI監看區識別碼與版本 *)
PLCtoHMI_AutoMonitorMagic := 16#A55A;
PLCtoHMI_AutoMonitorVersion := 1;

(* 每個PLC Scan先清空四站，再由FIFO實際BowlState重新建立 *)
PLCtoHMI_Station10UnitID := 0;
PLCtoHMI_Station10BowlState := 0;
PLCtoHMI_Station20UnitID := 0;
PLCtoHMI_Station20BowlState := 0;
PLCtoHMI_Station30UnitID := 0;
PLCtoHMI_Station30BowlState := 0;
PLCtoHMI_Station40UnitID := 0;
PLCtoHMI_Station40BowlState := 0;

FOR MonitorSearchIndex := 0 TO 15 DO

    IF UnitFIFO.Units[MonitorSearchIndex].UnitID <> 0 THEN

        IF ((UnitFIFO.Units[MonitorSearchIndex].BowlState = 10)
            OR (UnitFIFO.Units[MonitorSearchIndex].BowlState = 15))
           AND (PLCtoHMI_Station10UnitID = 0) THEN

            PLCtoHMI_Station10UnitID :=
                UnitFIFO.Units[MonitorSearchIndex].UnitID;
            PLCtoHMI_Station10BowlState :=
                UnitFIFO.Units[MonitorSearchIndex].BowlState;

        ELSIF ((UnitFIFO.Units[MonitorSearchIndex].BowlState = 20)
               OR (UnitFIFO.Units[MonitorSearchIndex].BowlState = 25))
              AND (PLCtoHMI_Station20UnitID = 0) THEN

            PLCtoHMI_Station20UnitID :=
                UnitFIFO.Units[MonitorSearchIndex].UnitID;
            PLCtoHMI_Station20BowlState :=
                UnitFIFO.Units[MonitorSearchIndex].BowlState;

        ELSIF ((UnitFIFO.Units[MonitorSearchIndex].BowlState = 30)
               OR (UnitFIFO.Units[MonitorSearchIndex].BowlState = 35))
              AND (PLCtoHMI_Station30UnitID = 0) THEN

            PLCtoHMI_Station30UnitID :=
                UnitFIFO.Units[MonitorSearchIndex].UnitID;
            PLCtoHMI_Station30BowlState :=
                UnitFIFO.Units[MonitorSearchIndex].BowlState;

        ELSIF (UnitFIFO.Units[MonitorSearchIndex].BowlState = 40)
              AND (PLCtoHMI_Station40UnitID = 0) THEN

            PLCtoHMI_Station40UnitID :=
                UnitFIFO.Units[MonitorSearchIndex].UnitID;
            PLCtoHMI_Station40BowlState :=
                UnitFIFO.Units[MonitorSearchIndex].BowlState;

        END_IF;

    END_IF;

END_FOR;

(* 三個麵篩直接複製UnitID、State與麵櫃編號 *)
PLCtoHMI_Basket1UnitID := NoodleBasket_1.UnitID;
PLCtoHMI_Basket1State := NoodleBasket_1.State;
PLCtoHMI_Basket1CabinetNo := NoodleBasket_1.NoodleCabinetNo;

PLCtoHMI_Basket2UnitID := NoodleBasket_2.UnitID;
PLCtoHMI_Basket2State := NoodleBasket_2.State;
PLCtoHMI_Basket2CabinetNo := NoodleBasket_2.NoodleCabinetNo;

PLCtoHMI_Basket3UnitID := NoodleBasket_3.UnitID;
PLCtoHMI_Basket3State := NoodleBasket_3.State;
PLCtoHMI_Basket3CabinetNo := NoodleBasket_3.NoodleCabinetNo;

(* 全自動動作狀態Bit *)
PLCtoHMI_AutoActiveFlags := 0;

IF Robot_Idle THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 1;
END_IF;

IF Auto_NoodleLoadGrant THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 2;
END_IF;

IF Auto_NoodleActionBusy THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 4;
END_IF;

IF Auto_NoodleZoneLocked THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 8;
END_IF;

IF Auto_NoodleShakeGrant THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 16;
END_IF;

IF Auto_NoodleDropGrant THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 32;
END_IF;

IF Auto_UR1Active THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 64;
END_IF;

IF Auto_UR2Active THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 128;
END_IF;

IF Auto_ConveyorRunRequest THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 256;
END_IF;

IF Auto_SoupRequest THEN
    PLCtoHMI_AutoActiveFlags := PLCtoHMI_AutoActiveFlags + 512;
END_IF;

(* 若你的ActionStep目前是MainAuto區域變數，這兩項先保持0即可。 *)
PLCtoHMI_AutoNoodleActionStep := 0;
PLCtoHMI_AutoIPCActionStep := 0;

PLCtoHMI_AutoRightmostStation := Auto_RightmostStation;
PLCtoHMI_AutoFIFOCount := UnitFIFO.Count;
PLCtoHMI_AutoCompleteUnitID := Auto_SoupDoneUnitID;
PLCtoHMI_AutoCompleteIndex := OrderCompleteIndex;
