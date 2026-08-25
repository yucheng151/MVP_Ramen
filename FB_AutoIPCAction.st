(* =========================================================
   FB_AutoIPCAction
   全自動 IPC 指令執行器

   CMD103 → 回覆 203 → UR1VisionDonePulse
   CMD101 → 回覆 201 → UR1DonePulse
   CMD102 → 回覆 202 → UR2DonePulse

   Seq、Ack、Timeout 及 ResponseCode 仍由既有
   PLCtoIPC_CMD 負責。
   ========================================================= *)

(* ---------------------------------------------------------
   1. 每個 PLC Scan 先清除單次脈波輸出
   --------------------------------------------------------- *)

IPCCommandTrigger := FALSE;

UR1VisionDonePulse := FALSE;
UR1VisionDoneUnitID := 0;

UR1DonePulse := FALSE;
UR1DoneUnitID := 0;

UR2DonePulse := FALSE;
UR2DoneUnitID := 0;

(* 全自動禁止 103 完成後自動接續 101 *)
IPCPreCaptureThenFirst := FALSE;

(* 目前配方固定為 0 *)
IPCCommandRecipeNo := 0;

(* =========================================================
   2. IPC 動作狀態流程
   ========================================================= *)

CASE ActionStep OF

    0:
        (* -------------------------------------------------
           待機：等待新的 Grant
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        ActiveCommandCode := 0;
        ActiveUnitID := 0;

        AutoIPCError := FALSE;
        AutoIPCErrorCode := 0;

        (* 必須確認既有 IPC 通道完全空閒 *)
        IF (IPCRequestValid = 0)
            AND (IPCBusy = 0)
            AND NOT IPCFirstMaterialPending THEN

            (* -----------------------------------------
               第一優先：UR2 CMD102
               ----------------------------------------- *)
            IF UR2Grant
                AND (UR2GrantUnitID <> 0) THEN

                ActiveCommandCode := 102;
                ActiveUnitID := UR2GrantUnitID;

                UR1Active := FALSE;
                UR1CommandNo := 0;
                UR2Active := TRUE;

                ActionStep := 10;

            (* -----------------------------------------
               第二優先：UR1 CMD101
               ----------------------------------------- *)
            ELSIF UR1Grant
                AND (UR1GrantUnitID <> 0) THEN

                ActiveCommandCode := 101;
                ActiveUnitID := UR1GrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 101;
                UR2Active := FALSE;

                ActionStep := 10;

            (* -----------------------------------------
               第三優先：UR1 CMD103 預先拍照
               ----------------------------------------- *)
            ELSIF UR1VisionGrant
                AND (UR1VisionGrantUnitID <> 0) THEN

                ActiveCommandCode := 103;
                ActiveUnitID := UR1VisionGrantUnitID;

                UR1Active := TRUE;
                UR1CommandNo := 103;
                UR2Active := FALSE;

                ActionStep := 10;

            END_IF;

        END_IF;

    10:
        (* -------------------------------------------------
           再次確認 IPC 通道空閒後，送出 Trigger
           ------------------------------------------------- *)

        IF (IPCRequestValid = 0)
            AND (IPCBusy = 0)
            AND NOT IPCFirstMaterialPending THEN

            (* Trigger 只保持一個 PLC Scan *)
            IPCCommandTrigger := TRUE;
            ActionStep := 15;

        END_IF;

    15:
        (* -------------------------------------------------
           等待既有 PLCtoIPC_CMD 接收任務

           不在此步驟判斷舊的 IPCCommandError，
           避免把上一筆殘留錯誤誤認為本次失敗。
           ------------------------------------------------- *)

        IF (IPCRequestValid <> 0)
            OR (IPCBusy <> 0) THEN

            ActionStep := 20;

        (* 若 IPC 極快完成，尚未觀察到 Busy 也可直接完成 *)
        ELSIF IPCCommandDone THEN

            IF ActiveCommandCode = 103 THEN
                UR1VisionDonePulse := TRUE;
                UR1VisionDoneUnitID := ActiveUnitID;
                UR1Active := FALSE;
                UR1CommandNo := 0;

            ELSIF ActiveCommandCode = 101 THEN
                UR1DonePulse := TRUE;
                UR1DoneUnitID := ActiveUnitID;
                UR1Active := FALSE;
                UR1CommandNo := 0;

            ELSIF ActiveCommandCode = 102 THEN
                UR2DonePulse := TRUE;
                UR2DoneUnitID := ActiveUnitID;
                UR2Active := FALSE;

            END_IF;

            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;

        END_IF;

    20:
        (* -------------------------------------------------
           等待既有 PLCtoIPC_CMD 完成或失敗
           ------------------------------------------------- *)

        IF IPCCommandDone THEN

            IF ActiveCommandCode = 103 THEN
                UR1VisionDonePulse := TRUE;
                UR1VisionDoneUnitID := ActiveUnitID;
                UR1Active := FALSE;
                UR1CommandNo := 0;

            ELSIF ActiveCommandCode = 101 THEN
                UR1DonePulse := TRUE;
                UR1DoneUnitID := ActiveUnitID;
                UR1Active := FALSE;
                UR1CommandNo := 0;

            ELSIF ActiveCommandCode = 102 THEN
                UR2DonePulse := TRUE;
                UR2DoneUnitID := ActiveUnitID;
                UR2Active := FALSE;

            END_IF;

            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;

        ELSIF IPCCommandError THEN

            (* 錯誤時停止自動重送，等待人工復歸 *)
            UR1Active := FALSE;
            UR1CommandNo := 0;
            UR2Active := FALSE;

            AutoIPCError := TRUE;
            AutoIPCErrorCode := IPCCommandErrorCode;

            ActionStep := 90;

        END_IF;

    90:
        (* -------------------------------------------------
           IPC 錯誤保持
           不自動重送，避免重複投料
           ------------------------------------------------- *)

        UR1Active := FALSE;
        UR1CommandNo := 0;
        UR2Active := FALSE;

        AutoIPCError := TRUE;

        IF ErrorReset THEN
            AutoIPCError := FALSE;
            AutoIPCErrorCode := 0;

            ActiveCommandCode := 0;
            ActiveUnitID := 0;

            ActionStep := 0;

        END_IF;

ELSE

    (* 未定義步驟，安全回到待機 *)
    IPCCommandTrigger := FALSE;

    UR1Active := FALSE;
    UR1CommandNo := 0;
    UR2Active := FALSE;

    ActiveCommandCode := 0;
    ActiveUnitID := 0;

    AutoIPCError := FALSE;
    AutoIPCErrorCode := 0;

    ActionStep := 0;

END_CASE;

(* ---------------------------------------------------------
   3. 將目前指令碼輸出給既有 PLCtoIPC_CMD
   --------------------------------------------------------- *)

IPCCommandCode := ActiveCommandCode;
