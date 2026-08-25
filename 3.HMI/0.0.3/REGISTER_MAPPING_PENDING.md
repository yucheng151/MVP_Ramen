# HMI / PLC Register Mapping Pending

The following signals are required by the Process page but do not have confirmed PLC addresses.
The HMI does not read or write guessed D registers for these items.

| Signal | Direction | Purpose |
|---|---|---|
| Current_Process_Step | PLC → HMI | 0, 10 … 90 current production step |
| Process_Step_Status | PLC → HMI | Idle / Waiting / Running / Complete / Alarm |
| Process_Alarm_Code | PLC → HMI | Latched process alarm code |
| Process_Alarm_Source | PLC → HMI | Device/source identifier |
| Process_Alarm_Message / Detail Index | PLC → HMI | Alarm description lookup |
| Process_Recipe_Name / Order Index | PLC → HMI | Current recipe or order identity |
| Auto_Start_Command | HMI → PLC | Start one automatic recipe via command handshake |
| SemiAuto_Step_Command | HMI → PLC | Execute one selected semi-auto step |
| Recipe parameter block | HMI → PLC | Auto recipe snapshot parameters |
| Semi-auto parameter block | HMI → PLC | Parameters for selected step |
| Parameter_Accept / Reject | PLC → HMI | PLC validation result |
| Parameter_Reject_Reason | PLC → HMI | Rejection reason code |
| Recipe_Index / Version | Bidirectional | Bind command to immutable recipe snapshot |
| Process_Command_ACK_Index | PLC → HMI | Confirm the command instance |

Reserved addresses such as D1140–D1143 are deliberately not used until PLC-side confirmation.
