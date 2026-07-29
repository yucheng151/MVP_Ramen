"""PLC D 暫存器集中定義。"""

CONVEYOR_FAULT_WORD = 100
CONVEYOR_ACTUAL_SPEED = 101
CONVEYOR_ACTUAL_BUS_CURRENT = 102
CONVEYOR_SET_SPEED_READ = 103
CONVEYOR_ACCEL_READ = 104
CONVEYOR_DECEL_READ = 105
CONVEYOR_BUS_CURRENT_READ = 106
CONVEYOR_PHASE_CURRENT_READ = 107
CONVEYOR_SET_SPEED_WRITE = 108
CONVEYOR_ACCEL_WRITE = 109
CONVEYOR_DECEL_WRITE = 110
CONVEYOR_BUS_CURRENT_WRITE = 111
CONVEYOR_PHASE_CURRENT_WRITE = 112
HMI_CMD_CODE = 1000
HMI_CMD_INDEX = 1001
HMI_CMD_VALID = 1002
HMI_CONVEYOR_SPEED = 1003
HMI_ROBOT_ACTION_NO = 1010
HMI_ROBOT_NOODLE_CABINET_NO = 1011
HMI_ROBOT_CUT_NO = 1012
HMI_ROBOT_OUTPUT_CABINET_NO = 1013
HMI_HEARTBEAT_RETURN_INDEX = 1005
PLC_HEARTBEAT_INDEX = 1100
PLC_CMD_ACK_INDEX = 1102
PLC_CMD_RESPONSE_CODE = 1103
PLC_CONVEYOR_STATUS = 1104
HMI_COMM_STATUS = 1105
PLC_STATUS_CODE = 1106
CONVEYOR_TIMEOUT_WORD = 1107
PLC_TO_HMI_SENSOR_STATUS = 1110
PLC_ROBOT_MANUAL_STATUS = 1120
PLC_ROBOT_MANUAL_ACK_INDEX = 1121
PLC_ROBOT_MANUAL_RESULT_CODE = 1122
PLC_ROBOT_MANUAL_ALARM_CODE = 1123

# PLC-internal Robot manual flow. HMI must not write D3080~D3093.
ROBOT_MANUAL_INTERNAL_START = 3080
ROBOT_MANUAL_INTERNAL_END = 3093

# Nachi Robot handshake monitor.
# PLC reads D12100~D12104 from Robot and writes D12150~D12156 to Robot.
# All Robot registers below are read-only from HMI side.
# HMI must not write to D12100~D12156.
ROBOT_READ_ONLY_START = 12100
ROBOT_READ_ONLY_END = 12156
ROBOT_STATUS_WORD = 12100
ROBOT_READ_COMPLETE = 12101
ROBOT_ERROR_CODE = 12102
ROBOT_ACTION_COMPLETE = 12103
ROBOT_INDEX = 12104

ROBOT_COMMAND_WORD = 12150
ROBOT_COMMAND_INDEX = 12151
ROBOT_ACTION_NO = 12152
ROBOT_NOODLE_CABINET_NO = 12153
ROBOT_CUT_NO = 12154
ROBOT_OUTPUT_CABINET_NO = 12155
ROBOT_NOODLE_TYPE_NO = 12156

ROBOT_STATUS_BITS = {
    "busy": 0,
    "status_output": 1,
    "home_signal": 2,
    "error_signal": 3,
    "alarm_signal": 4,
    "estop_active": 5,
    "program_running": 6,
    "sub_start": 7,
    "external_control_start": 9,
    "remote_control_available": 12,
}

ROBOT_COMMAND_BITS = {
    "external_stop": 0,
    "external_start": 1,
    "servo_power_on": 2,
    "external_reset": 3,
    "program_select_bit1": 4,
    "program_select_pulse": 5,
    "program_start_enable": 6,
    "intermittent": 7,
    "plc_data_ready": 8,
    "interval_motion_enable": 9,
    "shutdown": 13,
}

CONVEYOR_COMM_TIMEOUT_BIT = 0
CONVEYOR_INITIALIZE_TIMEOUT_BIT = 1

SENSOR_BITS = {
    "bowl_drop_confirm": 0,
    "pause_point_1": 1,
    "pause_point_2": 2,
    "right_stop_point": 3,
    "bowl_dispenser_busy": 4,
}

FAULT_NAMES = (
    "Over Current", "Stall Protection", "Motor Hall Fault", "Motor Fault",
    "Under Voltage", "Over Voltage", "Motor Over Temperature",
    "Controller Over Temperature", "Controller Fault",
)

PARAMETER_LIMITS = {
    "Speed RPM": (100, 1000),
    "Acceleration": (5, 50),
    "Deceleration": (5, 50),
    "Bus Current Setting": (0, 65535),
    "Phase Current Setting": (0, 65535),
}
