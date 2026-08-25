#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雙臂餐點程式的純設定。

此檔只放環境開關、路徑、ROS topic、數值門檻、姿態陣列與資料表，
不得建立 ROS、Isaac、RTDE 控制器或其他執行期物件。
"""

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# 雙臂場景、運動、左右手臂與鍵盤設定資料類別。
@dataclass
class SceneConfig:
    root_path: Path
    usd_path: str
    rmpflow_gripper_dir: Path
    ur5e_left_prim: str
    ur5e_right_prim: str
    ee_left_prim: str
    ee_right_prim: str
    ramen_bowl_prim_path: str
    egg_plate_prim_path: str
    egg_prim_path: str
    menma_bowl_prim_path: str
    menma_prim_path: str
    nori_plate_prim_path: str
    nori_prim_path: str
    green_onion_plate_prim_path: str
    green_onion_prim_path: str
    chashu_plate_prim_path: str
    chashu_prim_path: str
    sesame_plate_prim_path: str
    sesame_prim_path: str
    fungus_plate_prim_path: str
    fungus_prim_path: str
    ros_target_prim_names: list

@dataclass
class SharedMotionConfig:
    stability_sec: float
    stability_eps: float
    approach_offset: float
    vacuum_carry_hover_offset: float
    vacuum_ramen_descend_dz: float
    nori_descend_dz: float
    chashu_descend_dz: float
    nori_ramen_offset_xy: tuple
    chashu_ramen_offset_xy: tuple
    hold_before_grip_sec: float
    hold_before_place_sec: float
    default_obj_hold_tol: float
    world_up: np.ndarray
    tool_axis: str
    phase_timeout: float
    vacuum_adapter_compensation_x_rad: float
    nori_orbit_radius: float
    enable_drive_patch: bool
    enable_ros_object_pose_update: bool
    debug_drives: bool
    dual_base_to_world_z: float
    object_pose_print_xy_diff_threshold: float

@dataclass
class LeftArmConfig:
    enabled: bool
    backend: str
    auto_world_offset: bool
    gripper_idx: int
    gripper_open: float
    gripper_close: float
    default_gripper_close_position: int
    fallback_joint_positions: np.ndarray
    egg_descend_dz: float
    menma_descend_dz: float
    fungus_descend_dz: float
    ramen_descend_dz: float
    egg_gripper_close_position: float
    menma_gripper_close_position: float
    fungus_gripper_close_position: float
    egg_grip_hold_tol: float
    menma_grip_hold_tol: float
    fungus_grip_hold_tol: float
    single_arm_root_world: np.ndarray
    dual_left_root_world: np.ndarray
    dual_left_single_world_offset: np.ndarray
    home_z: float
    home_look_dz: float
    home_xy: tuple
    safe_idle_home_enabled: bool
    safe_idle_home_clearance_extra: float
    park_offset_xy: tuple
    egg_container_offset_x: float
    egg_ramen_offset_xy: tuple
    fungus_ramen_offset_xy: tuple
    spin_ramp_speed_deg_per_sec: float
    spin_settle_tol_deg: float

@dataclass
class RightArmConfig:
    home_xy: tuple
    fallback_joint_positions: np.ndarray
    right_arm_only: bool
    sesame_plan_path: str
    scallion_plan_path: str
    ladle_reach_tol_m: float
    ladle_phase_timeout_sec: float
    ladle_status_print_sec: float
    ladle_quat_order: str
    sesame_ladle_entry_policy_dt: float
    sesame_ladle_scoop_policy_dt: float
    sesame_ladle_lift_policy_dt: float
    sesame_ladle_pour_policy_dt: float
    sesame_ladle_return_policy_dt: float
    sesame_ladle_p8_p9_policy_dt: float
    sesame_ladle_p8_5_p9_policy_dt: float
    sesame_ladle_p7_5_policy_dt: float
    sesame_ladle_shake_policy_dt: float
    scallion_ladle_entry_policy_dt: float
    scallion_ladle_scoop_policy_dt: float
    scallion_ladle_lift_policy_dt: float
    scallion_ladle_pour_policy_dt: float
    scallion_ladle_return_policy_dt: float
    scallion_ladle_p8_p9_policy_dt: float
    scallion_ladle_p8_5_p9_policy_dt: float
    scallion_ladle_p7_5_policy_dt: float
    scallion_ladle_shake_policy_dt: float
    ladle_shake_base_ry_deg: float
    ladle_scallion_p9_5_base_ry_deg: float
    ladle_p7_5_base_ry_deg: float
    ladle_p7_5_base_x_shift_m: float
    ladle_p9_tool_minus_ry_deg: float
    ladle_p9_base_x_shift_m: float
    ladle_p9_shake_cycles: int
    ladle_p9_5_base_x_shift_m: float
    ladle_p9_5_hold_sec: float
    ladle_safety_lift_z: float

@dataclass
class KeyboardConfig:
    left_food_keys: dict
    capture_key: object
    execute_capture_key: object
    reset_height_key: object
    right_food_keys: dict
    right_ru_key: object
    right_auto_keys: set
    right_auto_food: str
    cancel_key: object

@dataclass
class DualArmConfig:
    scene: SceneConfig
    shared: SharedMotionConfig
    left: LeftArmConfig
    right: RightArmConfig
    keyboard: KeyboardConfig

def create_default_scene_config(root_path: Path):
    return SceneConfig(
        root_path=root_path,
        usd_path=str(root_path / "scene_assets_2arm_new" / "dual_ur5e_ramen_scene_gripper_demo.usd"),
        rmpflow_gripper_dir=root_path / "rmpflow_file_2arm" / "ur5e_gripper",
        ur5e_left_prim="/World/ur5e_left",
        ur5e_right_prim="/World/ur5e_right",
        ee_left_prim="/World/ur5e_left/wrist_3_link",
        ee_right_prim="/World/ur5e_right/wrist_3_link",
        ramen_bowl_prim_path="/World/left_bowl/bowl_with_noodle",
        egg_plate_prim_path="/World/egg_plate",
        egg_prim_path="/World/egg",
        menma_bowl_prim_path="/World/menma_bowl",
        menma_prim_path="/World/menma_group",
        nori_plate_prim_path="/World/nori_plate",
        nori_prim_path="/World/nori",
        green_onion_plate_prim_path="/World/green_onion_plate",
        green_onion_prim_path="/World/green_onion_pile",
        chashu_plate_prim_path="/World/chashu_plate",
        chashu_prim_path="/World/chashu",
        sesame_plate_prim_path="/World/sesame_plate",
        sesame_prim_path="/World/sesame_pile",
        fungus_plate_prim_path="/World/fungus_plate",
        fungus_prim_path="/World/fungus",
        ros_target_prim_names=[
            "bowl_with_noodle",
            "egg",
            "menma_group",
            "menma_bowl",
            "nori",
            "egg_plate",
            "chashu",
            "chashu_plate",
            "shuter_table",
            "green_onion_pile",
            "green_onion_plate",
            "nori_plate",
            "sesame_plate",
            "sesame_pile",
            "fungus",
            "fungus_plate",
            "Environment",
        ],
    )

def create_default_shared_motion_config():
    return SharedMotionConfig(
        stability_sec=1.0,
        stability_eps=0.005,
        approach_offset=0.3,
        vacuum_carry_hover_offset=0.4,
        vacuum_ramen_descend_dz=0.048,
        nori_descend_dz=0.07,
        chashu_descend_dz=0.07,
        nori_ramen_offset_xy=(-0.03, 0.03),
        chashu_ramen_offset_xy=(0.03, 0.03),
        hold_before_grip_sec=1.0,
        hold_before_place_sec=1.0,
        default_obj_hold_tol=0.025,
        world_up=np.array([0, 1, 0], dtype=np.float32),
        tool_axis="+Z",
        phase_timeout=1.5,
        vacuum_adapter_compensation_x_rad=np.deg2rad(-45.0),
        nori_orbit_radius=0.14,
        enable_drive_patch=True,
        enable_ros_object_pose_update=False,
        debug_drives=False,
        dual_base_to_world_z=0.8,
        object_pose_print_xy_diff_threshold=0.01,
    )

def create_default_left_arm_config():
    single_arm_root_world = np.array([0.0, 0.0, 0.91], dtype=np.float32)
    dual_left_root_world = np.array([0.0, 0.645, 0.8], dtype=np.float32)
    dual_left_single_world_offset = dual_left_root_world - single_arm_root_world
    return LeftArmConfig(
        enabled=True,
        backend="manual",
        auto_world_offset=True,
        gripper_idx=6,
        gripper_open=0.0,
        gripper_close=0.5,
        default_gripper_close_position=130,
        fallback_joint_positions=np.array(
            [0.0, -np.pi/2, 0.0, -np.pi/2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            dtype=np.float32,
        ),
        egg_descend_dz=0.12,
        menma_descend_dz=0.077,
        fungus_descend_dz=0.12,
        ramen_descend_dz=0.048,
        egg_gripper_close_position=255,
        menma_gripper_close_position=150,
        fungus_gripper_close_position=140,
        egg_grip_hold_tol=0.020,
        menma_grip_hold_tol=0.030,
        fungus_grip_hold_tol=0.018,
        single_arm_root_world=single_arm_root_world,
        dual_left_root_world=dual_left_root_world,
        dual_left_single_world_offset=dual_left_single_world_offset,
        home_z=float(dual_left_root_world[2]),
        home_look_dz=1.0,
        home_xy=(0.4 + float(dual_left_root_world[0]), 0.0 + float(dual_left_root_world[1])),
        safe_idle_home_enabled=True,
        safe_idle_home_clearance_extra=0.30,
        park_offset_xy=(0.0, -0.2),
        egg_container_offset_x=-0.10,
        egg_ramen_offset_xy=(-0.03, -0.03),
        fungus_ramen_offset_xy=(0.03, 0.03),
        spin_ramp_speed_deg_per_sec=60.0,
        spin_settle_tol_deg=3.0,
    )

def create_default_right_arm_config(root_path: Path):
    return RightArmConfig(
        home_xy=(0.2, 0.0),
        fallback_joint_positions=np.array(
            [0.0, -np.pi/2, 0.0, -np.pi/2, 0.0, 0.0],
            dtype=np.float32,
        ),
        right_arm_only=False,
        sesame_plan_path="config/ladle_scoop_plan_20260723_165437_clearance9to1.json",
        scallion_plan_path="config/ladle_scoop_plan_scallion_20260723_165935_clearance9to4.json",
        ladle_reach_tol_m=0.005,
        ladle_phase_timeout_sec=3.0,
        ladle_status_print_sec=0.5,
        ladle_quat_order="wxyz",
        sesame_ladle_entry_policy_dt=1.0 / 50.0,
        sesame_ladle_scoop_policy_dt=1.0 / 50.0,
        sesame_ladle_lift_policy_dt=1.0 / 50.0,
        sesame_ladle_pour_policy_dt=1.0 / 120.0,
        sesame_ladle_return_policy_dt=1.0 / 120.0,
        sesame_ladle_p8_p9_policy_dt=1.0 / 120.0,
        sesame_ladle_p8_5_p9_policy_dt=1.0 / 80.0,
        sesame_ladle_p7_5_policy_dt=1.0 / 60.0,
        sesame_ladle_shake_policy_dt=1.0 / 50.0,
        scallion_ladle_entry_policy_dt=1.0 / 50.0,
        scallion_ladle_scoop_policy_dt=1.0 / 50.0,
        scallion_ladle_lift_policy_dt=1.0 / 50.0,
        scallion_ladle_pour_policy_dt=1.0 / 120.0,
        scallion_ladle_return_policy_dt=1.0 / 120.0,
        scallion_ladle_p8_p9_policy_dt=1.0 / 120.0,
        scallion_ladle_p8_5_p9_policy_dt=1.0 / 80.0,
        scallion_ladle_p7_5_policy_dt=1.0 / 60.0,
        scallion_ladle_shake_policy_dt=1.0 / 50.0,
        ladle_shake_base_ry_deg=12.0,
        ladle_scallion_p9_5_base_ry_deg=12.0,
        ladle_p7_5_base_ry_deg=30.0,
        ladle_p7_5_base_x_shift_m=0.10,
        ladle_p9_tool_minus_ry_deg=50.0,
        ladle_p9_base_x_shift_m=0.07,
        ladle_p9_shake_cycles=1,
        ladle_p9_5_base_x_shift_m=0.01,
        ladle_p9_5_hold_sec=1.0,
        ladle_safety_lift_z=0.0,
    )

def create_default_keyboard_config():
    import carb.input as carb_input

    return KeyboardConfig(
        left_food_keys={
            carb_input.KeyboardInput.Q: "egg",
            carb_input.KeyboardInput.Z: "egg",
            carb_input.KeyboardInput.W: "menma",
            carb_input.KeyboardInput.M: "menma",
            carb_input.KeyboardInput.E: "fungus",
            carb_input.KeyboardInput.F: "fungus",
        },
        capture_key=carb_input.KeyboardInput.A,
        execute_capture_key=carb_input.KeyboardInput.S,
        reset_height_key=carb_input.KeyboardInput.D,
        right_food_keys={
            carb_input.KeyboardInput.R: "sesame",
            carb_input.KeyboardInput.U: "scallion",
        },
        right_ru_key=carb_input.KeyboardInput.Y,
        right_auto_keys={carb_input.KeyboardInput.X},
        right_auto_food="scallion",
        cancel_key=carb_input.KeyboardInput.ESCAPE,
    )

def create_default_dual_arm_config(root_path: Path = None):
    root_path = Path(root_path) if root_path is not None else Path(__file__).resolve().parents[1]
    return DualArmConfig(
        scene=create_default_scene_config(root_path),
        shared=create_default_shared_motion_config(),
        left=create_default_left_arm_config(),
        right=create_default_right_arm_config(root_path),
        keyboard=create_default_keyboard_config(),
    )

def _env_flag(name, default="0"):
    return str(os.environ.get(name, default)).strip().lower() in ("1", "true", "yes", "on")

PLC_MATERIAL_ENABLE = _env_flag("UR_RBC_PLC_ENABLE", "0")

PLC_MATERIAL_IP = os.environ.get("UR_RBC_PLC_IP", "192.168.1.5")

PLC_MATERIAL_PORT = int(os.environ.get("UR_RBC_PLC_PORT", "502"))

PLC_MATERIAL_SLAVE_ID = int(os.environ.get("UR_RBC_PLC_SLAVE_ID", "1"))

PLC_MATERIAL_INTERVAL_SEC = float(os.environ.get("UR_RBC_PLC_INTERVAL_SEC", "0.10"))

PLC_MATERIAL_TIMEOUT_SEC = float(os.environ.get("UR_RBC_PLC_TIMEOUT_SEC", "1.0"))

PLC_MATERIAL_RECONNECT_SEC = float(os.environ.get("UR_RBC_PLC_RECONNECT_SEC", "2.0"))

PLC_D_INPUT_START = 1200

PLC_D_HB_RETURN = 1300

PLC_D_ACK_SEQ = 1301

PLC_D_BUSY = 1302

PLC_D_RESPONSE_CODE = 1303

PLC_D_RESPONSE_SEQ = 1304

PLC_D_ERROR_CODE = 1305

PLC_D_CURRENT_TASK = 1307

PLC_D_EMC_DONE = 1308

PLC_CMD_FIRST_MATERIAL = 101

PLC_CMD_LAST_MATERIAL = 102

PLC_CMD_CAPTURE_MATERIAL = 103

PLC_RESP_FIRST_MATERIAL_DONE = 201

PLC_RESP_LAST_MATERIAL_DONE = 202

PLC_RESP_CAPTURE_MATERIAL_DONE = 203

PLC_RESP_ERROR = 901

PLC_ERR_UNSUPPORTED_COMMAND = 1001

PLC_ERR_WORKFLOW_UNAVAILABLE = 1002

PLC_ERR_EMC_ABORT = 1004

PLC_EMC_STOP_CONFIRM_SEC = float(os.environ.get("UR_RBC_PLC_EMC_STOP_CONFIRM_SEC", "0.25"))

PLC_EMC_MAX_JOINT_SPEED_RAD_S = float(os.environ.get("UR_RBC_PLC_EMC_MAX_JOINT_SPEED_RAD_S", "0.01"))

PLC_EMC_RELEASE_FLUSH_SEC = float(os.environ.get("UR_RBC_PLC_EMC_RELEASE_FLUSH_SEC", "0.30"))

ENABLE_REAL_ARM_IO = False  # DualArmRuntime injects its real-arm interfaces.

UR5E_PRIM = "/World/ur5e"

EE_PRIM = "/World/ur5e/wrist_3_link"

EGG_PLATE_PRIM_PATH = "/World/egg_plate"

EGG_PRIM_PATH = "/World/egg"

RAMEN_BOWL_PRIM_PATH = "/World/bowl_with_noodle"

MENMA_BOWL_PRIM_PATH = "/World/menma_bowl"

MENMA_PRIM_PATH = "/World/menma_group"

GRIPPER_IDX = 6

GRIPPER_OPEN = 0.0

GRIPPER_CLOSE = 0.5

EGG_PLATE_TOPIC = "/egg_plate/pose"

EGG_PLATE_NORMAL_TOPIC = "/egg_plate/normal"

EGG_ROUGH_TOPIC = "/egg_face_up/rough_pose"

EGG_ACCURATE_TOPIC = "/egg_face_up/accurate_pose"

EGG_NORMAL_TOPIC = "/egg_face_up/normal"

EGG_YAW_TOPIC = "/egg_face_up/yaw_deg"

EGG_YAW_AXIS_WIDTH_MM_TOPIC = "/egg_face_up/yaw_axis_width_mm"

EGG_YAW_OTHER_AXIS_WIDTH_MM_TOPIC = "/egg_face_up/yaw_other_axis_width_mm"

EGG_YAW_AXIS_NAME_TOPIC = "/egg_face_up/yaw_axis_name"

EGG_YAW_AXIS_CENTER_TO_ENDPOINT_MAX_MM_TOPIC = "/egg_face_up/yaw_axis_center_to_endpoint_max_mm"

EGG_YAW_AXIS_BASE_X_ERR_DEG_TOPIC = "/egg_face_up/yaw_axis_base_x_err_deg"

EGG_BACK_HAS_EGG_TOPIC = "/egg_face_up/back_has_egg"

EGG_BOWL_STATUS_TOPIC = "/egg_face_up/bowl_status"

EGG_H_TIP_TOPIC = "/egg_face_up/h_tip"

GRID_FOOD_MENMA_CELLS_TOPIC = "/grid_food/menma/occupied_cells"

GRID_FOOD_FUNGUS_CELLS_TOPIC = "/grid_food/fungus/occupied_cells"

DETECTION_TIMEOUT = 0.7

STAGE_SYNC_TOPICS = {
    "ramen_bowl": ("/ramen_bowl/pose", RAMEN_BOWL_PRIM_PATH),
    "menma_bowl": ("/menma_bowl/pose", MENMA_BOWL_PRIM_PATH),
    "menma": ("/menma/pose", MENMA_PRIM_PATH),
}

ROOT_PATH = Path(__file__).resolve().parents[1]

USD_PATH = str(ROOT_PATH / "scene_assets" / "ur5e_ramen_nangang_demo.usd")

MANUAL_HOME_CONFIG_PATH = ROOT_PATH / "config" / "manual_home_pose.json"

LEFT_SHUTDOWN_STATUS_PATH = ROOT_PATH / "logs" / "left_arm_shutdown_status.json"

PRE_HOME_RELEASE_CONFIG_PATH = ROOT_PATH / "config" / "pre_home_release_pose.json"

PRE_HOME_RELEASE_CONFIG_PATH_BY_SOURCE = {
    "egg": ROOT_PATH / "config" / "pre_home_release_pose_egg.json",
    "grid_food_menma": ROOT_PATH / "config" / "pre_home_release_pose_menma.json",
    "grid_food_fungus": ROOT_PATH / "config" / "pre_home_release_pose_fungus.json",
}

Z_FIXED = 0.8

EGG_STAGE_Z = 0.85

HOME_Z = 0.91

HOME_XY = (0.4, 0.0)

HOME_LOOK_DZ = 1.0

APPROACH_OFFSET = 0.30

PLATE_APPROACH_OFFSET = 0.30

EGG_APPROACH_OFFSET = 0.457

NO_BACK_EGG_APPROACH_OFFSET = 0.45

PRE_HOME_RELEASE_ENABLE = True

PRE_HOME_RELEASE_TARGET_POS = np.array([0.4, 0.0, HOME_Z + APPROACH_OFFSET], dtype=np.float32)

PRE_HOME_RELEASE_NORMAL_DOWN = np.array([0.0, 0.0, -1.0], dtype=np.float32)

PRE_HOME_RELEASE_OPEN_WAIT_SEC = 1.0

GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_RTDE_POS = np.array(
    [0.4578, -0.0627, 0.3828], dtype=np.float32
)

GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_X_AXIS = np.array(
    [+0.8121, +0.0581, +0.5806], dtype=np.float32
)

GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Y_AXIS = np.array(
    [+0.0747, -0.9972, -0.0048], dtype=np.float32
)

GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Z_AXIS = np.array(
    [+0.5787, +0.0473, -0.8142], dtype=np.float32
)

QUEUED_MENMA_TO_FUNGUS_DELAY_SEC = 0.85

RIGHT_RU_SESAME_TO_SCALLION_DELAY_SEC = 0.1

EGG_APPROACH_NARROW_WIDTH_ADD_TABLE = (
    (45.0, 0.00430),
    (35.0, 0.00645),
    (25.0, 0.00870),
)

EGG_DESCEND_DZ = 0.215 #EGG_APPROACH_OFFSET - EGG_DESCEND_DZ = 蛋面距離不裝夾爪末端距離184

NO_BACK_EGG_DESCEND_DZ = 0.205

NON_SWEEPABLE_UNGRASPABLE_DESCEND_DZ = 0.205

BACK_EGG_BASE_X_PARALLEL_SLIDE_STAGES = 2

PLATE_TCP_X_OFFSET = -0.08

EGG_CONTAINER_OFFSET_X = 0.0

UNGRASPABLE_SWEEP_PRE_DESCEND_OFFSET_M = 0.247

UNGRASPABLE_SWEEP_POLICY_DT = 1.0 / 100.0

UNGRASPABLE_SWEEP_RETURN_FINAL_POLICY_DT = 1.0 / 100.0

UNGRASPABLE_SWEEP_GRIPPER_WIDTH_MM = 20.0

UNGRASPABLE_SWEEP_TOOL_Y_SHIFT_M = 0.065

UNGRASPABLE_SWEEP_TOOL_X_SHIFT_M = 0.05

UNGRASPABLE_SWEEP_MAX_REPEATS = 2

UNGRASPABLE_SWEEP_LEFT_DESCEND_POS = np.array([0.2615, 0.2806, 0.2476], dtype=np.float32)

UNGRASPABLE_SWEEP_LEFT_X_AXIS = np.array([0.0900, 0.9955, -0.0312], dtype=np.float32)

UNGRASPABLE_SWEEP_LEFT_Y_AXIS = np.array([0.8867, -0.0658, 0.4576], dtype=np.float32)

UNGRASPABLE_SWEEP_LEFT_Z_AXIS = np.array([0.4534, -0.0689, -0.8886], dtype=np.float32)

UNGRASPABLE_SWEEP_RIGHT_DESCEND_POS = np.array([0.2696, 0.4220, 0.2470], dtype=np.float32)

UNGRASPABLE_SWEEP_RIGHT_X_AXIS = np.array([0.0406, 0.9991, -0.0122], dtype=np.float32)

UNGRASPABLE_SWEEP_RIGHT_Y_AXIS = np.array([0.8881, -0.0305, 0.4586], dtype=np.float32)

UNGRASPABLE_SWEEP_RIGHT_Z_AXIS = np.array([0.4578, -0.0294, -0.8886], dtype=np.float32)

RAMEN_DESCEND_DZ = 0.048

EGG_RAMEN_OFFSET_X = -0.02

EGG_RAMEN_OFFSET_Y = -0.02

GRIPPER_WAIT_CLOSE_SEC = 1.0

GRIPPER_WAIT_OPEN_SEC = 1.0

GRIPPER_CLOSE_WIDTH_MM = 28.0

USE_EGG_YAW_AXIS_WIDTH_FOR_GRIPPER_CLOSE = True

GRIPPER_CLOSE_EXTRA_SHRINK_MM = 22.0

EGG_GRIPPER_SMALL_WIDTH_THRESHOLD_MM = 30.0

EGG_GRIPPER_SMALL_WIDTH_SHRINK_MM = 5.0

GRIPPER_CLOSE_RESEND_INTERVAL_SEC = 0.5

GRIPPER_CLOSE_RESEND_MAX = 3

EGG_DESCEND_CONFIRM_HOLD_SEC = 1.0

ENABLE_EGG_DESCEND_REAL_TCP_CONFIRM = False

EGG_DESCEND_REAL_TCP_AXIS_TOL_M = 0.0003  # 0.3 mm per base X/Y/Z axis

EGG_DESCEND_REAL_TCP_STABLE_SEC = 0.25

EGG_DESCEND_REAL_TCP_CLOSED_LOOP_ENABLE = True

EGG_DESCEND_REAL_TCP_CLOSED_LOOP_GAIN = 0.80

EGG_DESCEND_REAL_TCP_CLOSED_LOOP_FILTER_ALPHA = 0.20

EGG_DESCEND_REAL_TCP_CLOSED_LOOP_MAX_CORRECTION_M = 0.005  # 5 mm / axis

EGG_DESCEND_REAL_TCP_Y_INTEGRAL_ENABLE = True

EGG_DESCEND_REAL_TCP_Y_INTEGRAL_GAIN_PER_SEC = 1.0

EGG_DESCEND_REAL_TCP_Y_INTEGRAL_MAX_M = 0.005

EGG_DESCEND_CARTESIAN_SEGMENT_NEAR_FINAL_M = 0.030  # 30 mm

EGG_DESCEND_CARTESIAN_WAYPOINT_STEP_M = 0.010  # 10 mm

EGG_DESCEND_CARTESIAN_WAYPOINT_REACH_TOL_M = 0.001  # 1 mm in Isaac TCP

EGG_PLATE_APPROACH_POLICY_DT = 1.0 / 50.0

EGG_PLATE_APPROACH_REACH_HOLD_SEC = 0.2

EGG_APPROACH_POLICY_DT = 1.0 / 50.0

EGG_APPROACH_REACH_HOLD_SEC = 0.2

EGG_DESCEND_POLICY_DT = 1.0 / 50.0

EGG_DESCEND_REACH_HOLD_SEC = 0.2

EGG_LIFT_POLICY_DT = 1.0 / 60.0

EGG_LIFT_REACH_HOLD_SEC = 0.2

EGG_PRE_HOME_POLICY_DT = 1.0 / 50.0

EGG_PRE_HOME_REACH_HOLD_SEC = 0.2

EGG_PRE_HOME_OPEN_WAIT_SEC = 0.2

EGG_HOME_POLICY_DT = 1.0 / 50.0

EGG_HOME_REACH_HOLD_SEC = 0.2

IDLE_POLICY_DT = 1.0 / 100.0

GRID_FOOD_OBSERVE_POLICY_DT = 1.0 / 50.0

GRID_FOOD_APPROACH_POLICY_DT = 1.0 / 50.0

GRID_FOOD_DESCEND_POLICY_DT = 1.0 / 50.0

GRID_FOOD_GRIPPER_CLOSE_POLICY_DT = 1.0 / 50.0

GRID_FOOD_LIFT_POLICY_DT = 1.0 / 50.0

GRID_FOOD_PRE_HOME_POLICY_DT = 1.0 / 60.0

GRID_FOOD_HOME_POLICY_DT = 1.0 / 50.0

RIGHT_LADLE_IDLE_POLICY_DT = 1.0 / 120.0

RIGHT_LADLE_RECOVERY_POLICY_DT = 1.0 / 100.0

FOOD_MOTION_TIMING_LOG_ENABLED = False

EGG_PRE_DESCEND_GRIPPER_WIDTH_MM = 80.0

EGG_BASE_X_AXIS_SLIDE_PRE_DESCEND_EXTRA_MM = 15.0

EGG_NON_BASE_X_AXIS_PRE_DESCEND_EXTRA_MM = 15.0

EGG_PRE_DESCEND_GRIPPER_WAIT_SEC = 0.5

EGG_PRE_DESCEND_BASE_X_PARALLEL_TOL_DEG = 40.0

EGG_BASE_X_AXIS_SLIDE_DESCEND_CLEARANCE_M = 0.010

EGG_BASE_X_AXIS_SLIDE_DESCEND_PER_STAGE_M = 0.006

LADLE_P7_5_RUNTIME_BASE_X_CORRECTION_M = -0.021

LADLE_P7_5_RUNTIME_BASE_Z_CORRECTION_M = -0.025

WORLD_UP = np.array([0.0, 1.0, 0.0], dtype=np.float32)

TOOL_AXIS = "+Z"

CAMERA_FORWARD_AXIS_LOCAL = "+X"

CAMERA_FORWARD_REF_BASE = np.array([1.0, 0.0, 0.0], dtype=np.float32)

EGG_YAW_OFFSET_DEG = 0.0

REACH_TOL = 0.008

REACH_HOLD_SEC = 0.5

ORIENT_REACH_TOL_DEG = 3.0

ENABLE_DRIVE_PATCH = True

ENABLE_RTDE_STREAM = True

ENABLE_REAL_GRIPPER = True

USE_PLATE_NORMAL = True

USE_EGG_NORMAL = False  # Egg approach uses egg plate normal for stability.

PREFER_ACCURATE_EGG_LOCK = True

NORMAL_KEEP_ANGLE_DEG = 10.0

DEBUG_RTDE_LOG_SEC = 1.0

REAL_EE_TRAJ_LOG_ENABLED = False

REAL_EE_TRAJ_LOG_PERIOD_SEC = 0.02

SPIN_RAMP_SPEED_DEG_PER_SEC = 60.0

SPIN_SETTLE_TOL_DEG = 0.5

NON_SWEEPABLE_UNGRASPABLE_NORMAL_DOWN = np.array(
    [0.442065, -0.006482, -0.896960], dtype=np.float32
)

RTDE_TCP_TO_ISAAC_Z_OFFSET = 0.9090

RTDE_TCP_TO_ISAAC_WORLD_OFFSET = np.array([0.0, 0.0, RTDE_TCP_TO_ISAAC_Z_OFFSET], dtype=np.float32)

SINGLE_TO_DUAL_WORLD_OFFSET = np.zeros(3, dtype=np.float32)

ENABLE_RAMEN_PLACE_FLOW = False

ENABLE_AUTO_EGG_AFTER_MANUAL_APPROACH = True

ENABLE_AUTO_EGG_DESCEND = True

ENABLE_EGG_LIFT_AFTER_GRASP = True

ENABLE_NO_BACK_EGG_REOBSERVE = False

ENABLE_NO_BACK_CAMERA_POSE_FOR_FIRST_EGG_OBSERVATION = False

EGG_MASK_STABILIZE_SEC = 0.5

EGG_STABLE_LOCK_MIN_SAMPLES = 4

EGG_STABLE_LOCK_MAX_XY_SPREAD = 0.005

EGG_STABLE_LOCK_MAX_Z_SPREAD = 0.005

EGG_STABLE_LOCK_MAX_AGE_SEC = None

EGG_STABLE_LOCK_IDENTITY_CLUSTER_M = 0.015

EGG_STABLE_LOCK_REQUIRE_H_TIP = True

ENABLE_EGG_SANITY_CHECK_NEAR_MANUAL_TARGET = False

EGG_MAX_XY_DIST_FROM_MANUAL_TARGET = 0.20

EGG_MAX_Z_BELOW_MANUAL_TARGET = 0.25

OVERRIDE_EGG_Z_FROM_MANUAL_TARGET = False

EGG_SURFACE_BELOW_MANUAL_TARGET = 0.05

GRID_FOOD_STABLE_MIN_SAMPLES = 3

GRID_FOOD_STABLE_MAX_XY_SPREAD_M = 0.008

GRID_FOOD_STABLE_MAX_AGE_SEC = 1.5

GRID_FOOD_LIFT_ALIGN_SEC = 0.5

GRID_FOOD_RATIO_HEIGHT_TIE_EPS = 1.0

GRID_FOOD_EMPTY_BY_CELL_CENTER_DISTANCE_M = 0.015

GRID_FOOD_DESCEND_REAL_TCP_TOL_M = 0.008

GRID_FOOD_DESCEND_REAL_TCP_STABLE_SEC = 0.5

GRID_FOOD_POST_LIFT_TOOL_Y_DEG = 30.0

GRID_FOOD_LIFT_TOOL_Z_POLICY_DT = 1.0 / 40.0

GRID_FOOD_POST_LIFT_TOOL_Z_REACH_TOL_M = 0.03

GRID_FOOD_POST_LIFT_TOOL_Z_REACH_HOLD_SEC = 0.05

GRID_FOOD_COMMON_PROFILE = {
    "cell_order": list(range(1, 19)),
    "observe_normal_down": np.array([0.3446, -0.0130, -0.9387], dtype=np.float32),
    "observe_x_axis": None,
    "observe_y_axis": None,
    "manual_normal_down": np.array([-0.2262, 0.0147, -0.9740], dtype=np.float32),
    "manual_x_axis": np.array([0.9741, -0.0027, -0.2262], dtype=np.float32),
    "manual_y_axis": np.array([-0.0060, -0.9999, -0.0137], dtype=np.float32),
    "approach_offset_m": 0.447,
    "base_y_shift_m": 0.0,
    "target_normal_offset_m": 0.0,
    "approach_settle_sec": 0.5,
    "lift_offset_m": 0.447,
    "gripper_approach_hold_width_mm": 50.0,
    "post_lift_base_x_retract_m": 0.120,
    "post_lift_last_row_base_x_retract_m": 0.070,
    "post_lift_tool_z_raise_m": 0.0,
    "post_lift_tool_z_raise_cycles": 0,
    "post_lift_tool_y_sequence_deg": (GRID_FOOD_POST_LIFT_TOOL_Y_DEG,),
}

GRID_FOOD_PROFILES = {
    "menma": {
        **GRID_FOOD_COMMON_PROFILE,
        "occupied_cells_topic": GRID_FOOD_MENMA_CELLS_TOPIC,
        "manual_target_pos": np.array([0.2408,0.0802,0.3891], dtype=np.float32),
        "descend_dz_m": 0.205,
        "gripper_close_width_mm": 11.0,
    },
    "fungus": {
        **GRID_FOOD_COMMON_PROFILE,
        "occupied_cells_topic": GRID_FOOD_FUNGUS_CELLS_TOPIC,
        "manual_target_pos": np.array([0.2126, -0.1903, 0.3666], dtype=np.float32),
        "descend_dz_m": 0.2,
        "gripper_close_width_mm": 8.0,
    },
}

GRID_FOOD_NAMES = tuple(GRID_FOOD_PROFILES)
GRID_FOOD_CAPTURE_ORDER = tuple(reversed(GRID_FOOD_NAMES))
LEFT_FOOD_NAMES = ("egg", *GRID_FOOD_NAMES)
