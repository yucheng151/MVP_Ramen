(* =========================================================
   FB_AutoScheduler 使用者提供版 2026-08-25
   功能：FIFO分配空閒麵篩、依軟硬度設定時間、依FIFO產生拿生麵請求。
   ========================================================= *)

Assigned := FALSE;
StartSelected := FALSE;
SelectedCookTime := 0;

(* 第一部分：將FIFO訂單分配給空閒麵篩 *)
IF UnitFIFO.Count > 0 THEN
    CurrentUnitIndex := UnitFIFO.CookIndex;

    IF UnitFIFO.Units[CurrentUnitIndex].JobState = 10 THEN
        CASE UnitFIFO.Units[CurrentUnitIndex].FirmnessNo OF
            1:
                SelectedCookTime := CookTime_Hard_Set;
            2:
                SelectedCookTime := CookTime_Normal_Set;
            3:
                SelectedCookTime := CookTime_Soft_Set;
        ELSE
            SelectedCookTime := CookTime_Normal_Set;
        END_CASE;

        IF NoodleBasket_1.State = 0 THEN
            NoodleBasket_1.UnitID := UnitFIFO.Units[CurrentUnitIndex].UnitID;
            NoodleBasket_1.NoodleCabinetNo := UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;
            NoodleBasket_1.FirmnessNo := UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;
            NoodleBasket_1.CookTimeSet := SelectedCookTime;
            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 1;
            NoodleBasket_1.State := 10;
            Assigned := TRUE;

        ELSIF NoodleBasket_2.State = 0 THEN
            NoodleBasket_2.UnitID := UnitFIFO.Units[CurrentUnitIndex].UnitID;
            NoodleBasket_2.NoodleCabinetNo := UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;
            NoodleBasket_2.FirmnessNo := UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;
            NoodleBasket_2.CookTimeSet := SelectedCookTime;
            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 2;
            NoodleBasket_2.State := 10;
            Assigned := TRUE;

        ELSIF NoodleBasket_3.State = 0 THEN
            NoodleBasket_3.UnitID := UnitFIFO.Units[CurrentUnitIndex].UnitID;
            NoodleBasket_3.NoodleCabinetNo := UnitFIFO.Units[CurrentUnitIndex].NoodleCabinetNo;
            NoodleBasket_3.FirmnessNo := UnitFIFO.Units[CurrentUnitIndex].FirmnessNo;
            NoodleBasket_3.CookTimeSet := SelectedCookTime;
            UnitFIFO.Units[CurrentUnitIndex].NoodleBasketNo := 3;
            NoodleBasket_3.State := 10;
            Assigned := TRUE;
        END_IF;

        IF Assigned THEN
            UnitFIFO.Units[CurrentUnitIndex].JobState := 20;
            UnitFIFO.CookIndex := UnitFIFO.CookIndex + 1;
            IF UnitFIFO.CookIndex >= UnitFIFO.Capacity THEN
                UnitFIFO.CookIndex := 0;
            END_IF;
        END_IF;
    END_IF;
END_IF;

(* 第二部分：同時只允許一個麵篩處於State 20或30。 *)
IF (NoodleBasket_1.State <> 20)
   AND (NoodleBasket_1.State <> 30)
   AND (NoodleBasket_2.State <> 20)
   AND (NoodleBasket_2.State <> 30)
   AND (NoodleBasket_3.State <> 20)
   AND (NoodleBasket_3.State <> 30) THEN

    StartSearchIndex := UnitFIFO.Head;
    StartSearchCount := 0;

    WHILE (StartSearchCount < UnitFIFO.Count)
          AND (NOT StartSelected) DO

        IF UnitFIFO.Units[StartSearchIndex].JobState = 20 THEN
            CASE UnitFIFO.Units[StartSearchIndex].NoodleBasketNo OF
                1:
                    IF (NoodleBasket_1.State = 10)
                       AND (NoodleBasket_1.UnitID = UnitFIFO.Units[StartSearchIndex].UnitID) THEN
                        NoodleBasket_1.State := 20;
                        StartSelected := TRUE;
                    END_IF;

                2:
                    IF (NoodleBasket_2.State = 10)
                       AND (NoodleBasket_2.UnitID = UnitFIFO.Units[StartSearchIndex].UnitID) THEN
                        NoodleBasket_2.State := 20;
                        StartSelected := TRUE;
                    END_IF;

                3:
                    IF (NoodleBasket_3.State = 10)
                       AND (NoodleBasket_3.UnitID = UnitFIFO.Units[StartSearchIndex].UnitID) THEN
                        NoodleBasket_3.State := 20;
                        StartSelected := TRUE;
                    END_IF;
            END_CASE;
        END_IF;

        StartSearchIndex := StartSearchIndex + 1;
        IF StartSearchIndex >= UnitFIFO.Capacity THEN
            StartSearchIndex := 0;
        END_IF;
        StartSearchCount := StartSearchCount + 1;
    END_WHILE;
END_IF;

