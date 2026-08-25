(* =========================================================
   FB_ActionArbiter 候選版 2026-08-25
   注意：需匯入目標V101、ISPSoft編譯及完整回歸後才可採用。
   ========================================================= *)

(* 每個PLC Scan先清除所有Grant *)
NoodleLoadGrant := FALSE;
NoodleShakeGrant := FALSE;
ConveyorRunGrant := FALSE;
BowlDropGrant := FALSE;
BowlDropGrantUnitID := 0;
UR1VisionGrant := FALSE;
UR1VisionGrantUnitID := 0;
NoodleDropGrant := FALSE;
NoodleDropGrantUnitID := 0;
UR1Grant := FALSE;
UR1GrantUnitID := 0;
UR2Grant := FALSE;
UR2GrantUnitID := 0;
SoupGrant := FALSE;
SoupGrantUnitID := 0;

(* 找出倒麵Request所對應的麵篩狀態 *)
MatchingBasketFound := FALSE;
MatchingBasketState := 0;

IF NoodleDropRequest
   AND (NoodleDropRequestUnitID <> 0) THEN

    IF NoodleBasket_1.UnitID = NoodleDropRequestUnitID THEN
        MatchingBasketFound := TRUE;
        MatchingBasketState := NoodleBasket_1.State;

    ELSIF NoodleBasket_2.UnitID = NoodleDropRequestUnitID THEN
        MatchingBasketFound := TRUE;
        MatchingBasketState := NoodleBasket_2.State;

    ELSIF NoodleBasket_3.UnitID = NoodleDropRequestUnitID THEN
        MatchingBasketFound := TRUE;
        MatchingBasketState := NoodleBasket_3.State;
    END_IF;
END_IF;

(* 輸送帶：CMD103及Nachi可並行，CMD101/CMD102禁止輸送帶 *)
IF ConveyorRunRequest
   AND NOT UR2Active
   AND NOT (UR1Active AND (UR1CommandNo = 101)) THEN
    ConveyorRunGrant := TRUE;
END_IF;

(* 落碗Grant *)
IF BowlDropRequest
   AND NOT ConveyorRunRequest THEN
    BowlDropGrant := TRUE;
    BowlDropGrantUnitID := BowlDropRequestUnitID;
END_IF;

(* UR1 CMD103預先拍照Grant *)
IF UR1VisionRequest
   AND NOT UR1Request
   AND NOT UR2Request
   AND NOT UR1Active
   AND NOT UR2Active THEN
    UR1VisionGrant := TRUE;
    UR1VisionGrantUnitID := UR1VisionRequestUnitID;
END_IF;

(* 注湯Grant *)
IF SoupRequest
   AND (RightmostStation = 40) THEN
    SoupGrant := TRUE;
    SoupGrantUnitID := SoupRequestUnitID;
END_IF;

(* 依最右端站別仲裁主要動作 *)
CASE RightmostStation OF

    0:
        (* 輸送途中：拿生麵優先，其次甩麵 *)
        IF RobotIdle
           AND NOT NoodleZoneLocked
           AND NOT UR2Active
           AND NOT (UR1Active AND (UR1CommandNo = 101)) THEN

            IF (NoodleBasket_1.State = 20)
               OR (NoodleBasket_2.State = 20)
               OR (NoodleBasket_3.State = 20) THEN
                NoodleLoadGrant := TRUE;

            ELSIF (NoodleBasket_1.State = 50)
               OR (NoodleBasket_2.State = 50)
               OR (NoodleBasket_3.State = 50) THEN
                NoodleShakeGrant := TRUE;
            END_IF;
        END_IF;

    20:
        (* 放麵及UR1站 *)
        IF NoodleDropRequest
           AND MatchingBasketFound THEN

            IF MatchingBasketState = 20 THEN
                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT (UR1Active AND (UR1CommandNo = 101)) THEN
                    NoodleLoadGrant := TRUE;
                END_IF;

            ELSIF (MatchingBasketState = 30)
               OR (MatchingBasketState = 40) THEN
                (* 對應麵篩執行放生麵或煮麵時，裝填其他State 20麵篩。 *)
                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT (UR1Active AND (UR1CommandNo = 101))
                   AND ((NoodleBasket_1.State = 20)
                        OR (NoodleBasket_2.State = 20)
                        OR (NoodleBasket_3.State = 20)) THEN
                    NoodleLoadGrant := TRUE;
                END_IF;

            ELSIF MatchingBasketState = 50 THEN
                IF RobotIdle
                   AND NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT (UR1Active AND (UR1CommandNo = 101)) THEN
                    NoodleShakeGrant := TRUE;
                END_IF;

            ELSIF MatchingBasketState = 70 THEN
                IF NOT NoodleZoneLocked
                   AND NOT UR2Active
                   AND NOT (UR1Active AND (UR1CommandNo = 101)) THEN
                    NoodleDropGrant := TRUE;
                    NoodleDropGrantUnitID := NoodleDropRequestUnitID;
                END_IF;
            END_IF;

        ELSIF UR1Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN
            UR1Grant := TRUE;
            UR1GrantUnitID := UR1RequestUnitID;
        END_IF;

    30:
        (* UR2站：UR1/UR2互斥，Nachi麵區鎖定時禁止 *)
        IF UR2Request
           AND NOT UR1Active
           AND NOT UR2Active
           AND NOT NoodleZoneLocked THEN
            UR2Grant := TRUE;
            UR2GrantUnitID := UR2RequestUnitID;
        END_IF;

END_CASE;

