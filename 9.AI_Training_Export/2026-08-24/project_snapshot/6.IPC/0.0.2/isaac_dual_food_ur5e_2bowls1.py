#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雙 UR5e 餐點流程：左臂處理蛋／筍乾／木耳，右臂處理芝麻／蔥。"""

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False})

import os
import sys
import time
import glob
import json
import math
import copy
from collections import deque
from threading import Event, Lock, Thread

import numpy as np
import rclpy
import omni.appwindow
import omni.usd
import carb.input as carb_input
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from geometry_msgs.msg import PoseStamped, Vector3Stamped
from std_msgs.msg import Bool, Float32, String

from isaacsim.core.utils import stage as stage_utils
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.robot.manipulators.manipulators import SingleManipulator
from isaacsim.robot_motion.motion_generation import RmpFlow, ArticulationMotionPolicy
from pxr import UsdGeom, UsdPhysics, Gf

from enum import Enum, auto
from dataclasses import dataclass
from pathlib import Path

os.environ["UR_RBC_IMPORT_MOVE_TO_EGG_MANUAL"] = "1"

from .utils.geometry.geometry_kit import (
    apply_spin_about_tool_axis,
    fmt_vec,
    get_world_pos,
    look_at_quat,
    quat_from_matrix,
    set_world_pos_flat_z,
)
from .isaac_dual_food_ur5e_2bowls1_config import *

def _env_flag(name, default="0"):
    return str(os.environ.get(name, default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class PLCMaterialInputs:
    heartbeat_index: int = 0
    request_code: int = 0
    request_seq: int = 0
    request_valid: bool = False
    recipe_no: int = 0
    emc_request: bool = False

class PLCMaterialBridge:
    """以背景執行緒將 PLC 任務送入現有流程。"""

    def __init__(
        self,
        config,
        left_arm,
        right_ladle_runner,
        keyboard_runtime,
        emergency_stop_fn=None,
        emergency_stopped_fn=None,
        emc_released_fn=None,
    ):
        self.enabled = bool(PLC_MATERIAL_ENABLE)
        self.config = config
        self.left_arm = left_arm
        self.right_ladle_runner = right_ladle_runner
        self.keyboard_runtime = keyboard_runtime
        self.emergency_stop_fn = emergency_stop_fn
        self.emergency_stopped_fn = emergency_stopped_fn
        self.emc_released_fn = emc_released_fn
        self._stop_event = Event()
        self._thread = None
        self._lock = Lock()
        self._inputs = PLCMaterialInputs()
        self._connected = False
        self._heartbeat_ok_once = False
        self._outgoing = deque()
        self._last_handled_seq = None
        self._active_seq = None
        self._active_code = None
        self._emc_logged = False
        self._emc_stop_commanded = False
        self._emc_done_written = False
        self._emc_release_restart_due = None

    def start(self):
        if not self.enabled:
            print("[PLC] bridge disabled (set UR_RBC_PLC_ENABLE=1 to enable)", flush=True)
            return
        if not (0 <= PLC_MATERIAL_SLAVE_ID <= 255):
            raise ValueError("UR_RBC_PLC_SLAVE_ID must be in 0..255")
        self._thread = Thread(target=self._worker, name="plc-material-bridge", daemon=True)
        self._thread.start()
        print(
            f"[PLC] bridge enabled: {PLC_MATERIAL_IP}:{PLC_MATERIAL_PORT} "
            f"slave={PLC_MATERIAL_SLAVE_ID}",
            flush=True,
        )

    def close(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(PLC_MATERIAL_TIMEOUT_SEC + 1.0, 2.0))
            self._thread = None

    def _queue_write(self, address, value):
        with self._lock:
            self._outgoing.append((int(address), int(value) & 0xFFFF))

    def _drain_writes(self):
        with self._lock:
            pending = list(self._outgoing)
            self._outgoing.clear()
        return pending

    def _snapshot(self):
        with self._lock:
            return self._inputs

    def _set_inputs(self, inputs):
        with self._lock:
            self._inputs = inputs

    def _worker(self):
        from pymodbus.client import ModbusTcpClient

        client = ModbusTcpClient(
            host=PLC_MATERIAL_IP,
            port=PLC_MATERIAL_PORT,
            timeout=PLC_MATERIAL_TIMEOUT_SEC,
        )
        try:
            while not self._stop_event.is_set():
                if not self._connected:
                    try:
                        self._connected = bool(client.connect())
                    except OSError:
                        self._connected = False
                    if not self._connected:
                        print(f"[PLC][WARN] cannot connect {PLC_MATERIAL_IP}:{PLC_MATERIAL_PORT}", flush=True)
                        self._stop_event.wait(PLC_MATERIAL_RECONNECT_SEC)
                        continue
                    self._heartbeat_ok_once = False
                    print("[PLC] TCP connected; verifying Modbus heartbeat...", flush=True)

                try:
                    result = client.read_holding_registers(
                        address=PLC_D_INPUT_START,
                        count=8,
                        device_id=PLC_MATERIAL_SLAVE_ID,
                    )
                    if result.isError():
                        raise ConnectionError(str(result))
                    data = result.registers
                    inputs = PLCMaterialInputs(
                        heartbeat_index=int(data[0]) & 0xFFFF,
                        request_code=int(data[1]) & 0xFFFF,
                        request_seq=int(data[2]) & 0xFFFF,
                        request_valid=bool(int(data[3]) & 0x0001),
                        recipe_no=int(data[4]) & 0xFFFF,
                        emc_request=bool(int(data[7]) & 0x0001),
                    )
                    self._set_inputs(inputs)
                    heartbeat_result = client.write_register(
                        address=PLC_D_HB_RETURN,
                        value=(inputs.heartbeat_index + 1) & 0xFFFF,
                        device_id=PLC_MATERIAL_SLAVE_ID,
                    )
                    if heartbeat_result.isError():
                        raise ConnectionError(str(heartbeat_result))
                    if not self._heartbeat_ok_once:
                        self._heartbeat_ok_once = True
                        print(
                            "[PLC][READY] Modbus heartbeat confirmed: "
                            f"D1200={inputs.heartbeat_index} -> "
                            f"D1300={(inputs.heartbeat_index + 1) & 0xFFFF}",
                            flush=True,
                        )
                    for address, value in self._drain_writes():
                        write_result = client.write_register(
                            address=address,
                            value=value,
                            device_id=PLC_MATERIAL_SLAVE_ID,
                        )
                        if write_result.isError():
                            raise ConnectionError(str(write_result))
                    self._stop_event.wait(PLC_MATERIAL_INTERVAL_SEC)
                except (OSError, ConnectionError) as exc:
                    print(f"[PLC][WARN] communication lost: {exc}", flush=True)
                    self._connected = False
                    self._heartbeat_ok_once = False
                    try:
                        client.close()
                    except OSError:
                        pass
                    self._stop_event.wait(PLC_MATERIAL_RECONNECT_SEC)
        finally:
            try:
                client.close()
            except OSError:
                pass

    def _left_busy(self):
        controller = self.left_arm.controller
        return bool(controller.sequence_active() or controller.pending_sequence_queue or controller.queued_sequence_active)

    def _right_busy(self):
        runner = self.right_ladle_runner
        return bool(runner is not None and (runner.active or runner.ru_sequence_active))

    def _all_workflows_idle(self):
        return not self._left_busy() and not self._right_busy()

    def _left_as_capture_ready(self):
        """判斷 A 流程是否可執行 S／PLC 101。"""
        controller = self.left_arm.controller
        return bool(
            getattr(controller, "as_capture_ready", False)
            and getattr(controller, "as_capture_egg_ready", False)
        )

    def _left_fungus_release_sent(self):
        """判斷 PLC 101 是否已完成木耳開爪。"""
        return bool(
            getattr(self.left_arm.controller, "plc_grid_food_release_sent_source", None)
            == "fungus"
        )

    def _right_scallion_p9_5_complete(self):
        """判斷 PLC 102 是否已完成蔥 P9.5。"""
        return bool(
            self.right_ladle_runner is not None
            and getattr(self.right_ladle_runner, "plc_p9_5_completed_food", None)
            == "scallion"
        )

    def _can_start_task(self, code):
        if self._all_workflows_idle():
            return True
        return bool(
            code == PLC_CMD_FIRST_MATERIAL
            and self._left_as_capture_ready()
            and not self._right_busy()
        )

    def _respond_error(self, seq, error_code):
        self._queue_write(PLC_D_ACK_SEQ, seq)
        self._queue_write(PLC_D_BUSY, 0)
        self._queue_write(PLC_D_RESPONSE_CODE, PLC_RESP_ERROR)
        self._queue_write(PLC_D_RESPONSE_SEQ, seq)
        self._queue_write(PLC_D_ERROR_CODE, error_code)
        self._queue_write(PLC_D_CURRENT_TASK, 0)
        self._last_handled_seq = seq
        print(f"[PLC] rejected seq={seq} error={error_code}", flush=True)

    def _start_task(self, inputs):
        code = inputs.request_code
        seq = inputs.request_seq
        if code == PLC_CMD_FIRST_MATERIAL:
            if not self.keyboard_runtime.start_as_execute_sequence(source="PLC 101"):
                self._respond_error(seq, PLC_ERR_WORKFLOW_UNAVAILABLE)
                return
        elif code == PLC_CMD_LAST_MATERIAL:
            if not self.keyboard_runtime.start_ru_sequence(source="PLC 102"):
                self._respond_error(seq, PLC_ERR_WORKFLOW_UNAVAILABLE)
                return
        elif code == PLC_CMD_CAPTURE_MATERIAL:
            if not self.keyboard_runtime.start_as_capture_sequence(source="PLC 103"):
                self._respond_error(seq, PLC_ERR_WORKFLOW_UNAVAILABLE)
                return
        else:
            self._respond_error(seq, PLC_ERR_UNSUPPORTED_COMMAND)
            return

        self._queue_write(PLC_D_ACK_SEQ, seq)
        self._queue_write(PLC_D_CURRENT_TASK, code)
        self._queue_write(PLC_D_BUSY, 1)
        self._active_seq = seq
        self._active_code = code
        self._last_handled_seq = seq
        print(f"[PLC] started code={code} seq={seq} recipe={inputs.recipe_no}", flush=True)

    def _complete_task(self):
        response = {
            PLC_CMD_FIRST_MATERIAL: PLC_RESP_FIRST_MATERIAL_DONE,
            PLC_CMD_LAST_MATERIAL: PLC_RESP_LAST_MATERIAL_DONE,
            PLC_CMD_CAPTURE_MATERIAL: PLC_RESP_CAPTURE_MATERIAL_DONE,
        }[self._active_code]
        self._queue_write(PLC_D_BUSY, 0)
        self._queue_write(PLC_D_RESPONSE_CODE, response)
        self._queue_write(PLC_D_RESPONSE_SEQ, self._active_seq)
        self._queue_write(PLC_D_ERROR_CODE, 0)
        self._queue_write(PLC_D_CURRENT_TASK, 0)
        print(f"[PLC] completed code={self._active_code} seq={self._active_seq}", flush=True)
        self._active_seq = None
        self._active_code = None

    def _abort_active_task_for_emc(self):
        if self._active_seq is None:
            return
        self._queue_write(PLC_D_BUSY, 0)
        self._queue_write(PLC_D_RESPONSE_CODE, PLC_RESP_ERROR)
        self._queue_write(PLC_D_RESPONSE_SEQ, self._active_seq)
        self._queue_write(PLC_D_ERROR_CODE, PLC_ERR_EMC_ABORT)
        self._queue_write(PLC_D_CURRENT_TASK, 0)
        print(f"[PLC][EMC] aborted active seq={self._active_seq}", flush=True)
        self._active_seq = None
        self._active_code = None

    def tick(self):
        """在 Isaac 執行緒處理快照，不執行 socket I/O。"""
        if not self.enabled:
            return
        inputs = self._snapshot()
        if inputs.emc_request:
            self._emc_release_restart_due = None
            if not self._emc_logged:
                self._emc_logged = True
                self._abort_active_task_for_emc()
                self._emc_stop_commanded = True
                print("[PLC][EMC][WARN] D1207=1 received; stopping both arms", flush=True)
                if self.emergency_stop_fn is None or not self.emergency_stop_fn():
                    print("[PLC][EMC][ERROR] stop command failed; D1308 remains 0", flush=True)
            if (
                self._emc_stop_commanded
                and not self._emc_done_written
                and self.emergency_stopped_fn is not None
                and self.emergency_stopped_fn()
            ):
                self._queue_write(PLC_D_EMC_DONE, 1)
                self._emc_done_written = True
                print("[PLC][EMC] both arms stopped; D1308=1", flush=True)
            return
        was_emc_active = self._emc_logged
        was_emc_done = self._emc_done_written
        if was_emc_active:
            print("[PLC][EMC] D1207 cleared", flush=True)
        self._emc_logged = False
        self._emc_stop_commanded = False
        if was_emc_done:
            self._queue_write(PLC_D_EMC_DONE, 0)
            self._emc_done_written = False
            self._emc_release_restart_due = time.perf_counter() + PLC_EMC_RELEASE_FLUSH_SEC
            print(
                "[PLC][EMC] D1308=0 queued; watchdog home/restart will begin after flush",
                flush=True,
            )
        if self._emc_release_restart_due is not None and time.perf_counter() >= self._emc_release_restart_due:
            self._emc_release_restart_due = None
            if self.emc_released_fn is not None:
                print("[PLC][EMC] requesting watchdog home/restart cycle", flush=True)
                self.emc_released_fn()

        if self._active_seq is not None:
            if self._active_code == PLC_CMD_FIRST_MATERIAL:
                done = self._left_fungus_release_sent()
            elif self._active_code == PLC_CMD_CAPTURE_MATERIAL:
                done = self._left_as_capture_ready()
            else:
                done = self._right_scallion_p9_5_complete()
            if done:
                self._complete_task()
            return

        if (
            inputs.request_valid
            and inputs.request_seq != self._last_handled_seq
            and self._can_start_task(inputs.request_code)
        ):
            self._start_task(inputs)

if ENABLE_REAL_ARM_IO:
    from .utils.rtde_control.rtde_connect import _rtde_r
    from .utils.rtde_control.rtde_main import streamer, ur_gripper_close, ur_gripper_open
else:
    _rtde_r = None

    class _SimulationOnlyStreamer:
        dt = 1.0 / 500.0

        def send(self, *_args, **_kwargs):
            return None

    streamer = _SimulationOnlyStreamer()

    def ur_gripper_open():
        print("[UR][SIM_ONLY] gripper open skipped; real arm IO disabled")
        return None

    def ur_gripper_close(*_args, **_kwargs):
        print("[UR][SIM_ONLY] gripper close skipped; real arm IO disabled")
        return None

class ManualScenePrims:
    def __init__(
        self,
        ur5e=UR5E_PRIM,
        ee=EE_PRIM,
        egg_plate=EGG_PLATE_PRIM_PATH,
        egg=EGG_PRIM_PATH,
        ramen_bowl=RAMEN_BOWL_PRIM_PATH,
        menma_bowl=MENMA_BOWL_PRIM_PATH,
        menma=MENMA_PRIM_PATH,
    ):
        self.ur5e = ur5e
        self.ee = ee
        self.egg_plate = egg_plate
        self.egg = egg
        self.ramen_bowl = ramen_bowl
        self.menma_bowl = menma_bowl
        self.menma = menma

class LeftRosTopics:
    def __init__(self):
        self.egg_plate_pose = EGG_PLATE_TOPIC
        self.egg_plate_normal = EGG_PLATE_NORMAL_TOPIC
        self.egg_rough_pose = EGG_ROUGH_TOPIC
        self.egg_accurate_pose = EGG_ACCURATE_TOPIC
        self.egg_normal = EGG_NORMAL_TOPIC
        self.egg_yaw = EGG_YAW_TOPIC
        self.egg_yaw_axis_width_mm = EGG_YAW_AXIS_WIDTH_MM_TOPIC
        self.egg_yaw_other_axis_width_mm = EGG_YAW_OTHER_AXIS_WIDTH_MM_TOPIC
        self.egg_yaw_axis_name = EGG_YAW_AXIS_NAME_TOPIC
        self.egg_yaw_axis_center_to_endpoint_max_mm = EGG_YAW_AXIS_CENTER_TO_ENDPOINT_MAX_MM_TOPIC
        self.egg_yaw_axis_base_x_err_deg = EGG_YAW_AXIS_BASE_X_ERR_DEG_TOPIC
        self.egg_back_has_egg = EGG_BACK_HAS_EGG_TOPIC
        self.egg_bowl_status = EGG_BOWL_STATUS_TOPIC
        self.egg_h_tip = EGG_H_TIP_TOPIC
        self.grid_food_cells = {
            food: profile["occupied_cells_topic"]
            for food, profile in GRID_FOOD_PROFILES.items()
        }
        self.enable_yaw = "/egg_face_up/enable_yaw"
        self.enable_accurate_pose = "/egg_face_up/enable_accurate_pose"

class StageSyncTarget:
    def __init__(self, topic, prim_path):
        self.topic = topic
        self.prim_path = prim_path

LEFT_SCENE_PRIMS = ManualScenePrims()
LEFT_ROS_TOPICS = LeftRosTopics()
LEFT_STAGE_SYNC_TARGETS = {
    name: StageSyncTarget(topic, prim_path)
    for name, (topic, prim_path) in STAGE_SYNC_TOPICS.items()
}

class EggManualProfile:
    def __init__(
        self,
        enabled=True,
        target_pos=None,
        normal_down=None,
        no_back_target_pos=None,
        no_back_normal_down=None,
        target_is_rtde_tcp=True,
    ):
        self.enabled = bool(enabled)
        self.target_pos = np.asarray(
            [0.1595, 0.3258, 0.3928] if target_pos is None else target_pos,
            dtype=np.float32,
        ).reshape(3)
        self.normal_down = np.asarray(
            [0.442065,-0.006482,-0.896960] if normal_down is None else normal_down,
            dtype=np.float32,
        ).reshape(3)
        self.no_back_target_pos = np.asarray(
            [0.3489,0.3516,0.3535]
            if no_back_target_pos is None
            else no_back_target_pos,
            dtype=np.float32,
        ).reshape(3)
        self.no_back_normal_down = np.asarray(
            [-0.0435, -0.0051, -0.9990] if no_back_normal_down is None else no_back_normal_down,
            dtype=np.float32,
        ).reshape(3)
        self.target_is_rtde_tcp = bool(target_is_rtde_tcp)

EGG_MANUAL_PROFILE = EggManualProfile()
USE_MANUAL_ARM_TARGET = EGG_MANUAL_PROFILE.enabled
MANUAL_ARM_TARGET_POS = EGG_MANUAL_PROFILE.target_pos
MANUAL_ARM_NORMAL_DOWN = EGG_MANUAL_PROFILE.normal_down
NO_BACK_EGG_TARGET_POS = EGG_MANUAL_PROFILE.no_back_target_pos
NO_BACK_EGG_NORMAL_DOWN = EGG_MANUAL_PROFILE.no_back_normal_down
MANUAL_ARM_TARGET_IS_RTDE_TCP = EGG_MANUAL_PROFILE.target_is_rtde_tcp

class RuntimeFrameTransform:
    def __init__(
        self,
        rtde_tcp_to_isaac_z_offset=RTDE_TCP_TO_ISAAC_Z_OFFSET,
        rtde_tcp_to_isaac_world_offset=None,
        single_to_dual_world_offset=None,
    ):
        self.rtde_tcp_to_isaac_z_offset = float(rtde_tcp_to_isaac_z_offset)
        self.rtde_tcp_to_isaac_world_offset = self._vec3(
            rtde_tcp_to_isaac_world_offset,
            [0.0, 0.0, self.rtde_tcp_to_isaac_z_offset],
        )
        self.single_to_dual_world_offset = self._vec3(single_to_dual_world_offset, [0.0, 0.0, 0.0])

    @staticmethod
    def _vec3(value, default):
        if value is None:
            value = default
        return np.asarray(value, dtype=np.float32).reshape(3)

    def configure(
        self,
        rtde_tcp_to_isaac_z_offset=None,
        rtde_tcp_to_isaac_world_offset=None,
        single_to_dual_world_offset=None,
    ):
        if rtde_tcp_to_isaac_z_offset is not None:
            self.rtde_tcp_to_isaac_z_offset = float(rtde_tcp_to_isaac_z_offset)
        if rtde_tcp_to_isaac_world_offset is None:
            rtde_tcp_to_isaac_world_offset = [0.0, 0.0, self.rtde_tcp_to_isaac_z_offset]
        self.rtde_tcp_to_isaac_world_offset = self._vec3(rtde_tcp_to_isaac_world_offset, None)
        if single_to_dual_world_offset is not None:
            self.single_to_dual_world_offset = self._vec3(single_to_dual_world_offset, None)

    def rtde_tcp_to_isaac_offset(self):
        return np.asarray(self.rtde_tcp_to_isaac_world_offset, dtype=np.float32).reshape(3)

    def single_isaac_pos_to_runtime(self, pos):
        return (
            np.asarray(pos, dtype=np.float32).reshape(3)
            + np.asarray(self.single_to_dual_world_offset, dtype=np.float32).reshape(3)
        ).astype(np.float32)

FRAME_TRANSFORM = RuntimeFrameTransform(
    rtde_tcp_to_isaac_z_offset=RTDE_TCP_TO_ISAAC_Z_OFFSET,
    rtde_tcp_to_isaac_world_offset=RTDE_TCP_TO_ISAAC_WORLD_OFFSET,
    single_to_dual_world_offset=SINGLE_TO_DUAL_WORLD_OFFSET,
)


def normalize_vec(v, default=None):
    if v is None:
        return default
    arr = np.asarray(v, dtype=np.float32).reshape(3)
    n = float(np.linalg.norm(arr))
    if (not np.isfinite(n)) or n < 1e-9:
        return default
    return arr / n

def orient_normal_to_negative_z(v):
    normal = normalize_vec(v, default=np.array([0.0, 0.0, -1.0], dtype=np.float32))
    if normal[2] > 0.0:
        normal = -normal
    return normal.astype(np.float32)

def runtime_rtde_tcp_to_isaac_offset():
    frame_transform = globals().get("FRAME_TRANSFORM", None)
    if frame_transform is not None:
        return frame_transform.rtde_tcp_to_isaac_offset()
    offset = globals().get("RTDE_TCP_TO_ISAAC_WORLD_OFFSET", None)
    if offset is not None:
        return np.asarray(offset, dtype=np.float32).reshape(3)
    return np.array([0.0, 0.0, float(RTDE_TCP_TO_ISAAC_Z_OFFSET)], dtype=np.float32)

def single_isaac_pos_to_runtime(pos):
    frame_transform = globals().get("FRAME_TRANSFORM", None)
    if frame_transform is not None:
        return frame_transform.single_isaac_pos_to_runtime(pos)
    return (
        np.asarray(pos, dtype=np.float32).reshape(3)
        + np.asarray(SINGLE_TO_DUAL_WORLD_OFFSET, dtype=np.float32).reshape(3)
    ).astype(np.float32)

def pre_home_release_config_path_for_source(source=None):
    source_key = str(source or "").strip().lower()
    return PRE_HOME_RELEASE_CONFIG_PATH_BY_SOURCE.get(source_key, PRE_HOME_RELEASE_CONFIG_PATH)

def pre_home_release_cfg(source=None):
    path = Path(pre_home_release_config_path_for_source(source))
    cfg = {
        "enabled": bool(PRE_HOME_RELEASE_ENABLE),
        "target_pos": np.asarray(PRE_HOME_RELEASE_TARGET_POS, dtype=np.float32).reshape(3),
        "normal_down": orient_normal_to_negative_z(PRE_HOME_RELEASE_NORMAL_DOWN),
        "open_wait_sec": float(PRE_HOME_RELEASE_OPEN_WAIT_SEC),
        "source": str(path),
        "release_source": str(source or "default"),
    }
    if not path.exists() and path != Path(PRE_HOME_RELEASE_CONFIG_PATH):
        fallback = Path(PRE_HOME_RELEASE_CONFIG_PATH)
        cfg["source"] = str(fallback)
        cfg["fallback_from"] = str(path)
        path = fallback
    if not path.exists():
        return cfg
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if "enabled" in payload:
            cfg["enabled"] = bool(payload["enabled"])
        if "target_pos_isaac_m" in payload:
            cfg["target_pos"] = single_isaac_pos_to_runtime(
                np.asarray(payload["target_pos_isaac_m"], dtype=np.float32).reshape(3)
            )
        if "normal_down" in payload:
            cfg["normal_down"] = orient_normal_to_negative_z(payload["normal_down"])
        if "open_wait_sec" in payload:
            cfg["open_wait_sec"] = float(payload["open_wait_sec"])
    except Exception as exc:
        print(f"[TEST][PRE_HOME_RELEASE][WARN] failed to load {path}: {exc}; using defaults.")
    return cfg

def manual_home_cfg():
    default_home_pos = np.array(
        [HOME_XY[0], HOME_XY[1], HOME_Z + APPROACH_OFFSET],
        dtype=np.float32,
    )
    default_home_look = np.array(
        [HOME_XY[0], HOME_XY[1], HOME_Z - HOME_LOOK_DZ],
        dtype=np.float32,
    )
    cfg = {
        "enabled": False,
        "target_pos": default_home_pos,
        "look_pos": default_home_look,
        "normal_down": normalize_vec(default_home_look - default_home_pos, default=np.array([0.0, 0.0, -1.0], dtype=np.float32)),
        "quat_xyzw": None,
        "source": str(MANUAL_HOME_CONFIG_PATH),
    }
    path = Path(MANUAL_HOME_CONFIG_PATH)
    if not path.exists():
        return cfg
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        cfg["enabled"] = bool(payload.get("enabled", True))
        if "target_pos_isaac_m" in payload:
            cfg["target_pos"] = single_isaac_pos_to_runtime(
                np.asarray(payload["target_pos_isaac_m"], dtype=np.float32).reshape(3)
            )
        elif "tcp_position_base_m" in payload:
            cfg["target_pos"] = rtde_tcp_pos_to_isaac(np.asarray(payload["tcp_position_base_m"], dtype=np.float32).reshape(3))
        if "target_quat_xyzw" in payload:
            cfg["quat_xyzw"] = np.asarray(payload["target_quat_xyzw"], dtype=np.float64).reshape(4)
        elif "tcp_rotvec_base_rad" in payload:
            cfg["quat_xyzw"] = quat_from_matrix(rotvec_to_matrix(payload["tcp_rotvec_base_rad"])).astype(np.float64)
        if "look_pos_isaac_m" in payload:
            cfg["look_pos"] = single_isaac_pos_to_runtime(
                np.asarray(payload["look_pos_isaac_m"], dtype=np.float32).reshape(3)
            )
        else:
            cfg["look_pos"] = cfg["target_pos"] + np.array([0.0, 0.0, -HOME_LOOK_DZ], dtype=np.float32)
        cfg["normal_down"] = normalize_vec(
            cfg["look_pos"] - cfg["target_pos"],
            default=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
    except Exception as exc:
        print(f"[TEST][HOME][WARN] failed to load {path}: {exc}; using defaults.")
        cfg["enabled"] = False
    return cfg

def optional_axis(v):
    if v is None:
        return None
    return normalize_vec(v, default=None)

def fixed_quat_from_tool_axes(z_axis, x_axis=None, y_axis=None):
    z_axis = orient_normal_to_negative_z(z_axis)
    x_axis = optional_axis(x_axis)
    y_axis = optional_axis(y_axis)

    if x_axis is not None:
        x_axis = x_axis - z_axis * float(np.dot(x_axis, z_axis))
        x_axis = normalize_vec(x_axis, default=None)
    elif y_axis is not None:
        y_axis = y_axis - z_axis * float(np.dot(y_axis, z_axis))
        y_axis = normalize_vec(y_axis, default=None)
        if y_axis is not None:
            x_axis = normalize_vec(np.cross(y_axis, z_axis), default=None)

    if x_axis is None:
        return None

    y_axis = normalize_vec(np.cross(z_axis, x_axis), default=np.array([0.0, 1.0, 0.0], dtype=np.float32))
    x_axis = normalize_vec(np.cross(y_axis, z_axis), default=x_axis)
    R = np.stack([x_axis, y_axis, z_axis], axis=1).astype(np.float64)
    quat = quat_from_matrix(R)
    quat = np.asarray(quat, dtype=np.float64).reshape(4)
    quat /= max(float(np.linalg.norm(quat)), 1e-12)
    return quat

def fixed_downward_base_x_quat():
    """回傳 tool +Z 朝下且 tool +X 對齊 base +X 的固定姿態。"""
    return fixed_quat_from_tool_axes(
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
        x_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )

class SpinRampMixin:
    """共用的 tool 軸旋轉漸進與穩定判斷。"""

    def _update_spin_ramp(self, dt):
        target_spin = float(self._spin_offset_target())
        max_step = self.spin_ramp_speed * max(float(dt), 1e-4)
        diff = target_spin - self.current_spin_offset
        if abs(diff) <= max_step:
            self.current_spin_offset = target_spin
        else:
            self.current_spin_offset += np.sign(diff) * max_step
        return self.current_spin_offset

    def _spin_is_settled(self):
        target_spin = float(self._spin_offset_target())
        return abs(target_spin - self.current_spin_offset) <= self.spin_settle_tol

def normalize_yaw_deg(yaw_deg):
    if yaw_deg is None or not np.isfinite(yaw_deg):
        return None
    yaw = (float(yaw_deg) + 180.0) % 360.0 - 180.0
    if yaw > 90.0:
        yaw -= 180.0
    elif yaw < -90.0:
        yaw += 180.0
    return float(yaw)

def apply_egg_yaw_offset(yaw_deg):
    if yaw_deg is None or not np.isfinite(yaw_deg):
        return None
    return normalize_yaw_deg(float(yaw_deg) + float(EGG_YAW_OFFSET_DEG))

def egg_tool_pose_yaw_deg(selected_axis_yaw_deg, selected_axis_name):
    """兩種蛋軸共用 D405 發布的 TCP yaw。"""
    _ = selected_axis_name
    return apply_egg_yaw_offset(selected_axis_yaw_deg)

def egg_manual_enabled():
    return bool(EGG_MANUAL_PROFILE.enabled)

def egg_manual_normal_down():
    return orient_normal_to_negative_z(EGG_MANUAL_PROFILE.normal_down)

def egg_non_sweepable_ungraspable_normal_down():
    """取得兩側不可撥蛋的固定下降法向量。"""
    return orient_normal_to_negative_z(NON_SWEEPABLE_UNGRASPABLE_NORMAL_DOWN)

def egg_no_back_normal_down():
    return orient_normal_to_negative_z(EGG_MANUAL_PROFILE.no_back_normal_down)

def egg_no_back_rtde_target():
    return np.asarray(EGG_MANUAL_PROFILE.no_back_target_pos, dtype=np.float32).copy()

def egg_manual_target_mode_text():
    return "manual RTDE TCP -> Isaac target" if EGG_MANUAL_PROFILE.target_is_rtde_tcp else "manual Isaac target"

def grid_food_cfg(food: str):
    food = str(food).strip().lower()
    if food not in GRID_FOOD_PROFILES:
        raise ValueError(f"unknown grid food: {food}")
    profile = GRID_FOOD_PROFILES[food]
    return {
        "cell_order": list(profile["cell_order"]),
        "manual_target_pos": np.asarray(profile["manual_target_pos"], dtype=np.float32).copy(),
        "observe_normal_down": orient_normal_to_negative_z(profile["observe_normal_down"]),
        "observe_x_axis": optional_axis(profile.get("observe_x_axis")),
        "observe_y_axis": optional_axis(profile.get("observe_y_axis")),
        "manual_normal_down": orient_normal_to_negative_z(profile["manual_normal_down"]),
        "manual_x_axis": optional_axis(profile.get("manual_x_axis")),
        "manual_y_axis": optional_axis(profile.get("manual_y_axis")),
        "approach_offset_m": float(profile["approach_offset_m"]),
        "descend_dz_m": float(profile["descend_dz_m"]),
        "base_y_shift_m": float(profile["base_y_shift_m"]),
        "target_normal_offset_m": float(profile["target_normal_offset_m"]),
        "approach_settle_sec": float(profile["approach_settle_sec"]),
        "lift_offset_m": float(profile["lift_offset_m"]),
        "gripper_approach_hold_width_mm": float(profile["gripper_approach_hold_width_mm"]),
        "gripper_close_width_mm": float(profile["gripper_close_width_mm"]),
        "post_lift_base_x_retract_m": float(profile.get("post_lift_base_x_retract_m", 0.0)),
        "post_lift_last_row_base_x_retract_m": float(
            profile.get("post_lift_last_row_base_x_retract_m", profile.get("post_lift_base_x_retract_m", 0.0))
        ),
        "post_lift_tool_z_raise_m": float(profile.get("post_lift_tool_z_raise_m", 0.0)),
        "post_lift_tool_z_raise_cycles": int(profile.get("post_lift_tool_z_raise_cycles", 0)),
        "post_lift_tool_y_sequence_deg": tuple(
            float(v) for v in profile.get(
                "post_lift_tool_y_sequence_deg", (GRID_FOOD_POST_LIFT_TOOL_Y_DEG,)
            )
        ),
    }

def grid_food_manual_target_for_isaac(food: str):
    pos = np.asarray(grid_food_cfg(food)["manual_target_pos"], dtype=np.float32).copy()
    if EGG_MANUAL_PROFILE.target_is_rtde_tcp:
        pos += runtime_rtde_tcp_to_isaac_offset()
    return pos

def signed_angle_about_axis(a, b, axis):
    a_n = normalize_vec(a, default=None)
    b_n = normalize_vec(b, default=None)
    axis_n = normalize_vec(axis, default=None)
    if a_n is None or b_n is None or axis_n is None:
        return 0.0
    a_n = normalize_vec(a_n - axis_n * float(np.dot(a_n, axis_n)), default=None)
    b_n = normalize_vec(b_n - axis_n * float(np.dot(b_n, axis_n)), default=None)
    if a_n is None or b_n is None:
        return 0.0
    sin_v = float(np.dot(axis_n, np.cross(a_n, b_n)))
    cos_v = float(np.dot(a_n, b_n))
    return float(np.arctan2(sin_v, cos_v))

def signed_angle_to_parallel_axis(a, target_axis, spin_axis):
    angle = signed_angle_about_axis(a, target_axis, spin_axis)
    angle_flipped = signed_angle_about_axis(a, -np.asarray(target_axis, dtype=np.float32), spin_axis)
    if abs(angle_flipped) < abs(angle):
        return angle_flipped
    return angle

def manual_arm_target_for_isaac():
    pos = np.asarray(EGG_MANUAL_PROFILE.target_pos, dtype=np.float32).copy()
    if EGG_MANUAL_PROFILE.target_is_rtde_tcp:
        pos += runtime_rtde_tcp_to_isaac_offset()
    return pos

def no_back_arm_target_for_isaac():
    """取得無後方蛋的專用觀測目標。"""
    pos = egg_no_back_rtde_target()
    if EGG_MANUAL_PROFILE.target_is_rtde_tcp:
        pos += runtime_rtde_tcp_to_isaac_offset()
    return pos

def egg_approach_narrow_width_add_m(width_mm):
    if width_mm is None or not np.isfinite(width_mm):
        return 0.0
    points = sorted(EGG_APPROACH_NARROW_WIDTH_ADD_TABLE, key=lambda p: p[0])
    width = float(width_mm)
    if width >= points[-1][0]:
        return 0.0
    if width <= points[0][0]:
        return float(points[0][1])
    for (w0, add0), (w1, add1) in zip(points, points[1:]):
        if w0 <= width <= w1:
            ratio = (width - w0) / (w1 - w0)
            return float(add0 + ratio * (add1 - add0))
    return 0.0

def isaac_pos_to_rtde_tcp_est(pos):
    if pos is None:
        return None
    arr = np.asarray(pos, dtype=np.float32).copy()
    if EGG_MANUAL_PROFILE.target_is_rtde_tcp:
        arr -= runtime_rtde_tcp_to_isaac_offset()
    return arr

def rtde_tcp_pos_to_isaac(pos):
    arr = np.asarray(pos, dtype=np.float32).copy()
    if EGG_MANUAL_PROFILE.target_is_rtde_tcp:
        arr += runtime_rtde_tcp_to_isaac_offset()
    return arr

def egg_pose_sanity_error(pos):
    if (
        not EGG_MANUAL_PROFILE.enabled
        or not ENABLE_EGG_SANITY_CHECK_NEAR_MANUAL_TARGET
        or pos is None
    ):
        return None
    egg = np.asarray(pos, dtype=np.float32).reshape(3)
    ref = manual_arm_target_for_isaac()
    dxy = float(np.linalg.norm(egg[:2] - ref[:2]))
    if dxy > float(EGG_MAX_XY_DIST_FROM_MANUAL_TARGET):
        return (
            f"xy_dist={dxy:.3f} m > {EGG_MAX_XY_DIST_FROM_MANUAL_TARGET:.3f} m "
            f"(egg={fmt_vec(egg)}, manual_isaac={fmt_vec(ref)})"
        )
    if OVERRIDE_EGG_Z_FROM_MANUAL_TARGET:
        return None
    dz_below = float(ref[2] - egg[2])
    if dz_below > float(EGG_MAX_Z_BELOW_MANUAL_TARGET):
        return (
            f"z_below={dz_below:.3f} m > {EGG_MAX_Z_BELOW_MANUAL_TARGET:.3f} m "
            f"(egg={fmt_vec(egg)}, manual_isaac={fmt_vec(ref)}, "
            f"egg_rtde_est={fmt_vec(isaac_pos_to_rtde_tcp_est(egg))})"
        )
    return None

def corrected_egg_pose_for_manual_target(pos):
    if not EGG_MANUAL_PROFILE.enabled or not OVERRIDE_EGG_Z_FROM_MANUAL_TARGET or pos is None:
        return pos
    egg = np.asarray(pos, dtype=np.float32).reshape(3).copy()
    ref = manual_arm_target_for_isaac()
    normal_down = orient_normal_to_negative_z(EGG_MANUAL_PROFILE.normal_down)
    corrected = ref + normal_down * float(EGG_SURFACE_BELOW_MANUAL_TARGET)
    egg[2] = corrected[2]
    return egg.astype(np.float32)


def normal_angle_deg(a, b):
    a_n = normalize_vec(a, default=None)
    b_n = normalize_vec(b, default=None)
    if a_n is None or b_n is None:
        return float("inf")
    dot = float(np.clip(np.dot(a_n, b_n), -1.0, 1.0))
    return float(np.rad2deg(np.arccos(dot)))

def fmt_arr(a, digits=4):
    if a is None:
        return "None"
    arr = np.asarray(a, dtype=np.float64)
    return "[" + ", ".join(f"{v:.{digits}f}" for v in arr.tolist()) + "]"


def quat_xyzw_to_matrix(q):
    q = np.asarray(q, dtype=np.float64).reshape(4)
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        return np.eye(3, dtype=np.float64)
    x, y, z, w = q / n
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )

def quat_xyzw_to_wxyz(q):
    q = np.asarray(q, dtype=np.float64).reshape(4)
    return np.array([q[3], q[0], q[1], q[2]], dtype=np.float64)

def quat_mul_xyzw(q1, q2):
    x1, y1, z1, w1 = np.asarray(q1, dtype=np.float64).reshape(4)
    x2, y2, z2, w2 = np.asarray(q2, dtype=np.float64).reshape(4)
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ],
        dtype=np.float64,
    )

def local_axis_from_rotation(R, axis_name):
    idx = {"X": 0, "Y": 1, "Z": 2}[axis_name[-1].upper()]
    sign = -1.0 if axis_name.startswith("-") else 1.0
    return normalize_vec(sign * R[:, idx], default=None)

def prefer_camera_forward_quat(quat_xyzw):
    quat_xyzw = np.asarray(quat_xyzw, dtype=np.float64).reshape(4)
    R = quat_xyzw_to_matrix(quat_xyzw)
    camera_forward = local_axis_from_rotation(R, CAMERA_FORWARD_AXIS_LOCAL)
    ref_forward = normalize_vec(CAMERA_FORWARD_REF_BASE, default=None)
    if camera_forward is None or ref_forward is None:
        return quat_xyzw, False
    if float(np.dot(camera_forward, ref_forward)) >= 0.0:
        return quat_xyzw, False

    spin_z_180 = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float64)
    q_fixed = quat_mul_xyzw(quat_xyzw, spin_z_180)
    q_fixed /= max(float(np.linalg.norm(q_fixed)), 1e-12)
    return q_fixed, True

def gf_matrix_to_rotation_axes(M):
    R = np.array(
        [
            [float(M[0][0]), float(M[0][1]), float(M[0][2])],
            [float(M[1][0]), float(M[1][1]), float(M[1][2])],
            [float(M[2][0]), float(M[2][1]), float(M[2][2])],
        ],
        dtype=np.float64,
    )
    axes_col = [normalize_vec(R[:, i], default=None) for i in range(3)]
    axes_row = [normalize_vec(R[i, :], default=None) for i in range(3)]
    return axes_col, axes_row

def set_prim_visibility(stage_ref, prim_path, visible=True):
    prim = stage_ref.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return False

    imageable = UsdGeom.Imageable(prim)
    if not imageable:
        return False

    imageable.GetVisibilityAttr().Set("inherited" if visible else "invisible")
    return True


class EggPlateBridge:
    # 【共用功能／辨識通訊】接收蛋盤、蛋與十八宮格資料，提供兩類食材共同使用。
    def __init__(self, node: Node, world_offset=None, auto_world_offset=False):
        self.node = node
        self.joint_state_provider = None
        self.world_offset = np.zeros(3, dtype=np.float32) if world_offset is None else np.asarray(world_offset, dtype=np.float32).reshape(3)
        self.auto_world_offset = bool(auto_world_offset)
        self._world_offset_source_by_label = {}
        self.scene_prims = LEFT_SCENE_PRIMS
        self.topics = LEFT_ROS_TOPICS
        self.stage_sync_targets = LEFT_STAGE_SYNC_TARGETS
        self.latest_pos = None
        self.last_update = None
        self.normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.normal_last_update = None
        self.egg_rough_pos = None
        self.egg_rough_last_update = None
        self.egg_accurate_pos = None
        self.egg_accurate_last_update = None
        self.egg_accurate_samples = deque(maxlen=30)
        self.egg_normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.egg_normal_last_update = None
        self.egg_yaw_deg = None
        self.egg_yaw_last_update = None
        self.egg_yaw_axis_width_mm = None
        self.egg_yaw_axis_width_last_update = None
        self.egg_yaw_other_axis_width_mm = None
        self.egg_yaw_other_axis_width_last_update = None
        self.egg_yaw_axis_name = None
        self.egg_yaw_axis_name_last_update = None
        self.egg_yaw_axis_center_to_endpoint_max_mm = None
        self.egg_yaw_axis_center_to_endpoint_max_last_update = None
        self.egg_yaw_axis_base_x_err_deg = None
        self.egg_yaw_axis_base_x_err_last_update = None
        self.egg_back_has_egg = None
        self.egg_back_has_egg_last_update = None
        self.egg_bowl_status = None
        self.egg_bowl_status_last_update = None
        self.egg_h_tip_latest = None
        self.egg_h_tip_last_update = None
        self.stage_sync_pose = {name: None for name in self.stage_sync_targets.keys()}
        self.stage_sync_last_update = {name: None for name in self.stage_sync_targets.keys()}
        self.egg_gate_on = False
        self.egg_gate_on_wall = None
        self.waiting_accurate_since = None
        self.grid_food_cells = {food: [] for food in GRID_FOOD_NAMES}
        self.grid_food_last_update = {food: None for food in GRID_FOOD_NAMES}
        self.grid_food_samples = {food: deque(maxlen=30) for food in GRID_FOOD_NAMES}
        self.grid_food_cell_first_center_m = {food: {} for food in GRID_FOOD_NAMES}
        self.grid_food_cell_center_distance_logged = {food: set() for food in GRID_FOOD_NAMES}
        self.grid_food_permanent_empty_ids = {food: set() for food in GRID_FOOD_NAMES}
        self.grid_food_empty_confirmation_pending = {food: set() for food in GRID_FOOD_NAMES}
        self.grid_food_all_cells_rejected = {food: False for food in GRID_FOOD_NAMES}
        self.grid_food_height_sampling_enabled = {food: False for food in GRID_FOOD_NAMES}

        self.pose_sub = self.node.create_subscription(
            PoseStamped, self.topics.egg_plate_pose, self._pose_cb, 10
        )
        self.normal_sub = self.node.create_subscription(
            Vector3Stamped, self.topics.egg_plate_normal, self._normal_cb, 10
        )
        self.egg_rough_sub = self.node.create_subscription(
            PoseStamped, self.topics.egg_rough_pose, self._egg_rough_cb, 10
        )
        self.egg_accurate_sub = self.node.create_subscription(
            PoseStamped, self.topics.egg_accurate_pose, self._egg_accurate_cb, 10
        )
        self.egg_normal_sub = self.node.create_subscription(
            Vector3Stamped, self.topics.egg_normal, self._egg_normal_cb, 10
        )
        self.egg_yaw_sub = self.node.create_subscription(
            Float32, self.topics.egg_yaw, self._egg_yaw_cb, 10
        )
        self.egg_yaw_axis_width_sub = self.node.create_subscription(
            Float32, self.topics.egg_yaw_axis_width_mm, self._egg_yaw_axis_width_cb, 10
        )
        self.egg_yaw_other_axis_width_sub = self.node.create_subscription(
            Float32, self.topics.egg_yaw_other_axis_width_mm, self._egg_yaw_other_axis_width_cb, 10
        )
        self.egg_yaw_axis_name_sub = self.node.create_subscription(
            String, self.topics.egg_yaw_axis_name, self._egg_yaw_axis_name_cb, 10
        )
        self.egg_yaw_axis_center_to_endpoint_max_sub = self.node.create_subscription(
            Float32,
            self.topics.egg_yaw_axis_center_to_endpoint_max_mm,
            self._egg_yaw_axis_center_to_endpoint_max_cb,
            10,
        )
        self.egg_yaw_axis_base_x_err_sub = self.node.create_subscription(
            Float32, self.topics.egg_yaw_axis_base_x_err_deg, self._egg_yaw_axis_base_x_err_cb, 10
        )
        self.egg_back_has_egg_sub = self.node.create_subscription(
            Bool, self.topics.egg_back_has_egg, self._egg_back_has_egg_cb, 10
        )
        self.egg_bowl_status_sub = self.node.create_subscription(
            String, self.topics.egg_bowl_status, self._egg_bowl_status_cb, 10
        )
        self.egg_h_tip_sub = self.node.create_subscription(
            Float32, self.topics.egg_h_tip, self._egg_h_tip_cb, 10
        )
        self.grid_food_subs = {
            food: self.node.create_subscription(
                String,
                self.topics.grid_food_cells[food],
                lambda msg, selected_food=food: self._grid_food_cells_cb(msg, selected_food),
                10,
            )
            for food in GRID_FOOD_NAMES
        }
        self.stage_sync_subs = []
        for name, target in self.stage_sync_targets.items():
            self.stage_sync_subs.append(
                self.node.create_subscription(
                    PoseStamped, target.topic, lambda msg, n=name: self._stage_sync_pose_cb(msg, n), 10
                )
            )
        self.pub_enable_yaw = self.node.create_publisher(Bool, self.topics.enable_yaw, 10)
        self.pub_enable_accurate = self.node.create_publisher(Bool, self.topics.enable_accurate_pose, 10)

    def set_joint_state_provider(self, provider):
        self.joint_state_provider = provider

    def _to_world(self, pos, reference_pos=None, label=None):
        raw = np.asarray(pos, dtype=np.float32).reshape(3)
        shifted = (raw + self.world_offset).astype(np.float32)
        if (
            not self.auto_world_offset
            or reference_pos is None
            or float(np.linalg.norm(self.world_offset)) < 1e-6
        ):
            return shifted

        ref = np.asarray(reference_pos, dtype=np.float32).reshape(3)
        raw_err = float(np.linalg.norm(raw - ref))
        shifted_err = float(np.linalg.norm(shifted - ref))
        use_raw = raw_err <= shifted_err
        source = "raw_dual_world" if use_raw else "single_world_plus_offset"

        if label is not None and self._world_offset_source_by_label.get(label) != source:
            self._world_offset_source_by_label[label] = source
            chosen = raw if use_raw else shifted
            print(
                f"[TEST][FRAME][{label}] {source}: "
                f"raw_err={raw_err * 1000.0:.1f}mm "
                f"shifted_err={shifted_err * 1000.0:.1f}mm "
                f"chosen={fmt_vec(chosen)}"
            )
        return raw.astype(np.float32) if use_raw else shifted

    def _pose_cb(self, msg: PoseStamped):
        p = msg.pose.position
        self.latest_pos = self._to_world(
            [p.x, p.y, p.z],
            reference_pos=manual_arm_target_for_isaac(),
            label="egg_plate",
        )
        self.last_update = time.perf_counter()

    def _normal_cb(self, msg: Vector3Stamped):
        v = msg.vector
        new_normal_down = orient_normal_to_negative_z([v.x, v.y, v.z])
        if normal_angle_deg(new_normal_down, self.normal_down) >= NORMAL_KEEP_ANGLE_DEG:
            self.normal_down = new_normal_down
        self.normal_last_update = time.perf_counter()

    def _egg_rough_cb(self, msg: PoseStamped):
        p = msg.pose.position
        pos = self._to_world(
            [p.x, p.y, p.z],
            reference_pos=manual_arm_target_for_isaac(),
            label="egg_rough",
        )
        sanity_error = egg_pose_sanity_error(pos)
        if sanity_error is not None:
            print(f"[TEST][EGG_ROUGH][REJECT] {sanity_error}")
            self.egg_rough_pos = None
            self.egg_rough_last_update = None
            return
        corrected = corrected_egg_pose_for_manual_target(pos)
        if corrected is not pos and not np.allclose(corrected, pos):
            print(f"[TEST][EGG_ROUGH][Z_OVERRIDE] raw={fmt_vec(pos)} corrected={fmt_vec(corrected)}")
        self.egg_rough_pos = corrected
        self.egg_rough_last_update = time.perf_counter()

    def _egg_accurate_cb(self, msg: PoseStamped):
        p = msg.pose.position
        pos = self._to_world(
            [p.x, p.y, p.z],
            reference_pos=manual_arm_target_for_isaac(),
            label="egg_accurate",
        )
        sanity_error = egg_pose_sanity_error(pos)
        if sanity_error is not None:
            print(f"[TEST][EGG_ACCURATE][REJECT] {sanity_error}")
            self.egg_accurate_pos = None
            self.egg_accurate_last_update = None
            return
        corrected = corrected_egg_pose_for_manual_target(pos)
        if corrected is not pos and not np.allclose(corrected, pos):
            print(f"[TEST][EGG_ACCURATE][Z_OVERRIDE] raw={fmt_vec(pos)} corrected={fmt_vec(corrected)}")
        self.egg_accurate_pos = corrected
        self.egg_accurate_last_update = time.perf_counter()
        self.egg_accurate_samples.append(
            {
                "t": self.egg_accurate_last_update,
                "pos": corrected.copy(),
                "yaw_deg": self.egg_yaw_deg,
                "yaw_axis_width_mm": self.egg_yaw_axis_width_mm,
                "yaw_other_axis_width_mm": self.egg_yaw_other_axis_width_mm,
                "yaw_axis_name": self.egg_yaw_axis_name,
                "yaw_axis_center_to_endpoint_max_mm": self.egg_yaw_axis_center_to_endpoint_max_mm,
                "yaw_axis_base_x_err_deg": self.egg_yaw_axis_base_x_err_deg,
                "back_has_egg": self.egg_back_has_egg,
                "h_tip": self.egg_h_tip_latest,
                "normal_down": self.egg_normal_down.copy(),
            }
        )
        if self.waiting_accurate_since is not None:
            dt_wait = self.egg_accurate_last_update - self.waiting_accurate_since
            dt_gate = (
                self.egg_accurate_last_update - self.egg_gate_on_wall
                if self.egg_gate_on_wall is not None
                else None
            )
            gate_text = f", gate_dt={dt_gate:.3f}s" if dt_gate is not None else ""
            print(
                f"[TEST][EGG_ACCURATE] received after wait_dt={dt_wait:.3f}s{gate_text}: "
                f"{fmt_vec(self.egg_accurate_pos)}"
            )
            self.waiting_accurate_since = None

    def _egg_normal_cb(self, msg: Vector3Stamped):
        v = msg.vector
        new_normal_down = orient_normal_to_negative_z([v.x, v.y, v.z])
        if normal_angle_deg(new_normal_down, self.egg_normal_down) >= NORMAL_KEEP_ANGLE_DEG:
            self.egg_normal_down = new_normal_down
        self.egg_normal_last_update = time.perf_counter()

    def _egg_yaw_cb(self, msg: Float32):
        self.egg_yaw_deg = float(msg.data)
        self.egg_yaw_last_update = time.perf_counter()

    def _egg_yaw_axis_width_cb(self, msg: Float32):
        val = float(msg.data)
        self.egg_yaw_axis_width_mm = val if np.isfinite(val) and val > 0.0 else None
        self.egg_yaw_axis_width_last_update = time.perf_counter()

    def _egg_yaw_other_axis_width_cb(self, msg: Float32):
        val = float(msg.data)
        self.egg_yaw_other_axis_width_mm = val if np.isfinite(val) and val > 0.0 else None
        self.egg_yaw_other_axis_width_last_update = time.perf_counter()

    def _egg_yaw_axis_name_cb(self, msg: String):
        val = str(msg.data).strip().lower()
        self.egg_yaw_axis_name = val if val in ("major", "minor") else None
        self.egg_yaw_axis_name_last_update = time.perf_counter()

    def _egg_yaw_axis_center_to_endpoint_max_cb(self, msg: Float32):
        val = float(msg.data)
        self.egg_yaw_axis_center_to_endpoint_max_mm = val if np.isfinite(val) and val > 0.0 else None
        self.egg_yaw_axis_center_to_endpoint_max_last_update = time.perf_counter()

    def _egg_yaw_axis_base_x_err_cb(self, msg: Float32):
        val = float(msg.data)
        self.egg_yaw_axis_base_x_err_deg = val if np.isfinite(val) else None
        self.egg_yaw_axis_base_x_err_last_update = time.perf_counter()

    def _egg_back_has_egg_cb(self, msg: Bool):
        self.egg_back_has_egg = bool(msg.data)
        self.egg_back_has_egg_last_update = time.perf_counter()

    def _egg_bowl_status_cb(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except Exception as exc:
            print(f"[TEST][EGG_BOWL_STATUS][JSON_ERROR] {exc}")
            return
        state = payload.get("state")
        if state not in {
            "empty", "graspable_available", "only_ungraspable",
            "only_non_sweepable_ungraspable", "unknown_no_graspable",
        }:
            print(f"[TEST][EGG_BOWL_STATUS][INVALID] {payload}")
            return
        self.egg_bowl_status = payload
        self.egg_bowl_status_last_update = time.perf_counter()

    def _egg_h_tip_cb(self, msg: Float32):
        self.egg_h_tip_latest = float(msg.data)
        self.egg_h_tip_last_update = time.perf_counter()

    def _grid_food_cells_cb(self, msg: String, food: str):
        try:
            payload = json.loads(msg.data)
        except Exception as exc:
            print(f"[TEST][GRID_FOOD][{food}][JSON_ERROR] {exc}")
            return

        cells = payload.get("occupied_cells", [])
        if not isinstance(cells, list):
            cells = []
        occupied = []
        for cell in cells:
            if not isinstance(cell, dict) or not bool(cell.get("occupied", True)):
                continue
            center = cell.get("center_base_m")
            if center is None:
                center = cell.get("center_base")
            try:
                center = self._to_world(
                    center,
                    reference_pos=grid_food_manual_target_for_isaac(food),
                    label=f"grid_food_{food}",
                )
            except Exception:
                continue
            if not np.all(np.isfinite(center)):
                continue
            copied = dict(cell)
            copied["center_base_m"] = center
            occupied.append(copied)

        now = time.perf_counter()
        self.grid_food_cells[food] = occupied
        self.grid_food_last_update[food] = now

        all_cells = payload.get("all_cells", [])
        observed_cell_ids = set()
        if (
            bool(payload.get("ok", False))
            and isinstance(all_cells, list)
            and self.grid_food_height_sampling_enabled.get(food, False)
        ):
            newly_empty_ids = []
            permanent_empty_ids = self.grid_food_permanent_empty_ids.setdefault(food, set())
            pending_empty_ids = self.grid_food_empty_confirmation_pending.setdefault(food, set())
            for raw_cell in all_cells:
                if not isinstance(raw_cell, dict):
                    continue
                try:
                    cell_id = int(raw_cell.get("cell_id"))
                except Exception:
                    continue
                observed_cell_ids.add(cell_id)
                if (
                    cell_id in pending_empty_ids
                    and not bool(raw_cell.get("occupied", False))
                    and cell_id not in permanent_empty_ids
                ):
                    permanent_empty_ids.add(cell_id)
                    pending_empty_ids.discard(cell_id)
                    newly_empty_ids.append(cell_id)
            if newly_empty_ids:
                newly_empty_ids.sort()
                print(
                    f"[TEST][GRID_FOOD][{food}] permanently mark empty cells from one valid D405 result: "
                    f"{newly_empty_ids}"
                )

        if not self.grid_food_height_sampling_enabled.get(food, False):
            return

        selected = self.select_grid_food_cell(food)
        occupied_ids = {
            int(cell.get("cell_id"))
            for cell in occupied
            if cell.get("cell_id") is not None
        }
        rejected_ids = self.grid_food_cell_center_distance_logged.setdefault(food, set())
        permanently_empty_ids = self.grid_food_permanent_empty_ids.setdefault(food, set())
        rejected_or_empty_ids = rejected_ids | permanently_empty_ids
        if observed_cell_ids:
            self.grid_food_all_cells_rejected[food] = observed_cell_ids.issubset(rejected_or_empty_ids)
        else:
            self.grid_food_all_cells_rejected[food] = bool(occupied_ids) and occupied_ids.issubset(rejected_or_empty_ids)
        if selected is not None:
            self.grid_food_samples[food].append(
                {
                    "t": now,
                    "cell": selected,
                    "center": np.asarray(selected["center_base_m"], dtype=np.float32).copy(),
                }
            )

    def reset_grid_food_height_state(self, food: str, reset_center_baseline=False):
        """重設本次取樣，但保留目前料盤的中心基準。"""
        self.grid_food_samples.setdefault(food, deque(maxlen=30)).clear()
        if bool(reset_center_baseline):
            self.grid_food_cell_first_center_m[food] = {}
            self.grid_food_cell_center_distance_logged[food] = set()
        self.grid_food_all_cells_rejected[food] = False
        self.grid_food_height_sampling_enabled[food] = False

    def reset_grid_food_tray_state(self, food: str):
        """補料後重設全部十八宮格狀態。"""
        food = str(food).strip().lower()
        if food not in GRID_FOOD_PROFILES:
            raise ValueError(f"unsupported grid food: {food}")
        self.grid_food_cells[food] = []
        self.grid_food_last_update[food] = None
        self.grid_food_samples.setdefault(food, deque(maxlen=30)).clear()
        self.grid_food_cell_first_center_m[food] = {}
        self.grid_food_cell_center_distance_logged[food] = set()
        self.grid_food_permanent_empty_ids[food] = set()
        self.grid_food_empty_confirmation_pending[food] = set()
        self.grid_food_all_cells_rejected[food] = False
        self.grid_food_height_sampling_enabled[food] = False
        print(
            f"[TEST][GRID_FOOD][{food}] D reset: cleared all 18-cell height/empty state.",
            flush=True,
        )

    def set_grid_food_height_sampling(self, food: str, enabled: bool):
        self.grid_food_height_sampling_enabled[food] = bool(enabled)

    def request_grid_food_empty_confirmation_after_grasp(self, food: str, cell_id):
        """等待後續照片確認已夾格為空。"""
        try:
            cid = int(cell_id)
        except Exception:
            return
        if cid < 0:
            return
        pending = self.grid_food_empty_confirmation_pending.setdefault(food, set())
        if cid in self.grid_food_permanent_empty_ids.setdefault(food, set()):
            return
        pending.add(cid)

    def _stage_sync_pose_cb(self, msg: PoseStamped, name: str):
        p = msg.pose.position
        self.stage_sync_pose[name] = self._to_world([p.x, p.y, p.z])
        self.stage_sync_last_update[name] = time.perf_counter()

    def set_egg_detection_gate(self, on: bool):
        if bool(on) == self.egg_gate_on:
            return
        self.egg_gate_on = bool(on)
        self.egg_gate_on_wall = time.perf_counter() if self.egg_gate_on else None
        msg = Bool()
        msg.data = bool(on)
        self.pub_enable_yaw.publish(msg)
        self.pub_enable_accurate.publish(msg)
        print(f"[TEST][EGG_GATE] enable_yaw / enable_accurate_pose -> {on}")

    def mark_waiting_for_accurate(self):
        if self.waiting_accurate_since is None:
            self.waiting_accurate_since = time.perf_counter()
            print("[TEST][EGG_ACCURATE] waiting for /egg_face_up/accurate_pose ...")

    def clear_egg_measurements_for_new_lock(self):
        self.egg_rough_pos = None
        self.egg_rough_last_update = None
        self.egg_accurate_pos = None
        self.egg_accurate_last_update = None
        self.egg_accurate_samples.clear()
        self.egg_yaw_deg = None
        self.egg_yaw_last_update = None
        self.egg_yaw_axis_width_mm = None
        self.egg_yaw_axis_width_last_update = None
        self.egg_yaw_axis_name = None
        self.egg_yaw_axis_name_last_update = None
        self.egg_yaw_axis_center_to_endpoint_max_mm = None
        self.egg_yaw_axis_center_to_endpoint_max_last_update = None
        self.egg_yaw_axis_base_x_err_deg = None
        self.egg_yaw_axis_base_x_err_last_update = None
        self.egg_back_has_egg = None
        self.egg_back_has_egg_last_update = None
        self.egg_bowl_status = None
        self.egg_bowl_status_last_update = None
        self.egg_h_tip_latest = None
        self.egg_h_tip_last_update = None
        self.waiting_accurate_since = None

    def stable_accurate_egg_candidate(
        self,
        min_samples=EGG_STABLE_LOCK_MIN_SAMPLES,
        max_xy_spread=EGG_STABLE_LOCK_MAX_XY_SPREAD,
        max_z_spread=EGG_STABLE_LOCK_MAX_Z_SPREAD,
        max_age_sec=EGG_STABLE_LOCK_MAX_AGE_SEC,
        require_h_tip=EGG_STABLE_LOCK_REQUIRE_H_TIP,
    ):
        now = time.perf_counter()
        if max_age_sec is None or float(max_age_sec) <= 0.0:
            samples = list(self.egg_accurate_samples)
        else:
            samples = [s for s in self.egg_accurate_samples if (now - s["t"]) <= float(max_age_sec)]
        if len(samples) < int(min_samples):
            return None, "accurate", {
                "reason": "need_more_samples",
                "samples": len(samples),
                "min_samples": int(min_samples),
            }

        if require_h_tip and (self.egg_h_tip_latest is None or not np.isfinite(self.egg_h_tip_latest)):
            return None, "accurate", {
                "reason": "wait_h_tip",
                "samples": len(samples),
                "min_samples": int(min_samples),
            }

        clusters = []
        for sample in samples:
            sample_pos = np.asarray(sample["pos"], dtype=np.float32).reshape(3)
            best_cluster = None
            best_dist = float("inf")
            for cluster in clusters:
                center = np.median(
                    np.asarray([entry["pos"] for entry in cluster["samples"]], dtype=np.float32),
                    axis=0,
                )
                dist = float(np.linalg.norm(sample_pos - center))
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = cluster
            if best_cluster is not None and best_dist <= float(EGG_STABLE_LOCK_IDENTITY_CLUSTER_M):
                best_cluster["samples"].append(sample)
            else:
                clusters.append({"samples": [sample]})

        dominant_cluster = max(
            clusters,
            key=lambda cluster: (len(cluster["samples"]), float(cluster["samples"][-1]["t"])),
        )
        recent = list(dominant_cluster["samples"])
        if len(recent) < int(min_samples):
            dominant_center = np.median(
                np.asarray([entry["pos"] for entry in recent], dtype=np.float32), axis=0
            )
            return None, "accurate", {
                "reason": "dominant_egg_need_more_samples",
                "samples": len(samples),
                "used_samples": len(recent),
                "min_samples": int(min_samples),
                "cluster_count": len(clusters),
                "dominant_ratio": float(len(recent)) / max(float(len(samples)), 1.0),
                "dominant_median_pos": dominant_center,
                "identity_cluster_radius_m": float(EGG_STABLE_LOCK_IDENTITY_CLUSTER_M),
            }

        pts = np.asarray([s["pos"] for s in recent], dtype=np.float32)
        pos_med = np.median(pts, axis=0).astype(np.float32)
        xy_dists = np.linalg.norm(pts[:, :2] - pos_med[:2].reshape(1, 2), axis=1)
        max_xy = float(np.max(xy_dists)) if xy_dists.size else float("inf")
        z_dists = np.abs(pts[:, 2] - float(pos_med[2]))
        max_z = float(np.max(z_dists)) if z_dists.size else float("inf")
        if max_xy > float(max_xy_spread):
            return None, "accurate", {
                "reason": "xy_spread_too_large",
                "samples": len(samples),
                "used_samples": len(recent),
                "cluster_count": len(clusters),
                "dominant_ratio": float(len(recent)) / max(float(len(samples)), 1.0),
                "identity_cluster_radius_m": float(EGG_STABLE_LOCK_IDENTITY_CLUSTER_M),
                "max_xy_spread": max_xy,
                "limit": float(max_xy_spread),
                "median_pos": pos_med,
                "latest_pos": recent[-1]["pos"],
            }
        if max_z > float(max_z_spread):
            return None, "accurate", {
                "reason": "z_spread_too_large",
                "samples": len(samples),
                "used_samples": len(recent),
                "cluster_count": len(clusters),
                "dominant_ratio": float(len(recent)) / max(float(len(samples)), 1.0),
                "identity_cluster_radius_m": float(EGG_STABLE_LOCK_IDENTITY_CLUSTER_M),
                "max_xy_spread": max_xy,
                "max_z_spread": max_z,
                "limit": float(max_z_spread),
                "median_pos": pos_med,
                "latest_pos": recent[-1]["pos"],
            }

        yaw_vals = [s["yaw_deg"] for s in recent if s["yaw_deg"] is not None and np.isfinite(s["yaw_deg"])]
        yaw_med = float(np.median(yaw_vals)) if len(yaw_vals) > 0 else self.egg_yaw_deg
        width_vals = [
            s["yaw_axis_width_mm"]
            for s in recent
            if s.get("yaw_axis_width_mm") is not None and np.isfinite(s["yaw_axis_width_mm"])
        ]
        width_med = float(np.median(width_vals)) if len(width_vals) > 0 else self.egg_yaw_axis_width_mm
        other_width_vals = [
            s["yaw_other_axis_width_mm"]
            for s in recent
            if (
                s.get("yaw_other_axis_width_mm") is not None
                and np.isfinite(s["yaw_other_axis_width_mm"])
            )
        ]
        other_width_med = (
            float(np.median(other_width_vals))
            if len(other_width_vals) > 0
            else self.egg_yaw_other_axis_width_mm
        )
        axis_name_vals = [
            s.get("yaw_axis_name")
            for s in recent
            if s.get("yaw_axis_name") in ("major", "minor")
        ]
        if len(axis_name_vals) > 0:
            axis_name_med = "minor" if sum(1 for v in axis_name_vals if v == "minor") >= (len(axis_name_vals) / 2.0) else "major"
        else:
            axis_name_med = self.egg_yaw_axis_name
        center_to_endpoint_vals = [
            s["yaw_axis_center_to_endpoint_max_mm"]
            for s in recent
            if (
                s.get("yaw_axis_center_to_endpoint_max_mm") is not None
                and np.isfinite(s["yaw_axis_center_to_endpoint_max_mm"])
            )
        ]
        center_to_endpoint_med = (
            float(np.median(center_to_endpoint_vals))
            if len(center_to_endpoint_vals) > 0
            else self.egg_yaw_axis_center_to_endpoint_max_mm
        )
        axis_err_vals = [
            s["yaw_axis_base_x_err_deg"]
            for s in recent
            if s.get("yaw_axis_base_x_err_deg") is not None and np.isfinite(s["yaw_axis_base_x_err_deg"])
        ]
        axis_err_med = (
            float(np.median(axis_err_vals))
            if len(axis_err_vals) > 0
            else self.egg_yaw_axis_base_x_err_deg
        )
        back_vals = [s.get("back_has_egg") for s in recent if s.get("back_has_egg") is not None]
        back_has_egg = (
            bool(sum(1 for v in back_vals if bool(v)) >= (len(back_vals) / 2.0))
            if len(back_vals) > 0
            else self.egg_back_has_egg
        )
        stats = {
            "reason": "stable",
            "samples": len(samples),
            "used_samples": len(recent),
            "cluster_count": len(clusters),
            "dominant_ratio": float(len(recent)) / max(float(len(samples)), 1.0),
            "identity_cluster_radius_m": float(EGG_STABLE_LOCK_IDENTITY_CLUSTER_M),
            "max_xy_spread": max_xy,
            "max_z_spread": max_z,
            "median_pos": pos_med,
            "latest_pos": recent[-1]["pos"],
            "yaw_deg": yaw_med,
            "yaw_axis_width_mm": width_med,
            "yaw_other_axis_width_mm": other_width_med,
            "yaw_axis_name": axis_name_med,
            "yaw_axis_center_to_endpoint_max_mm": center_to_endpoint_med,
            "yaw_axis_base_x_err_deg": axis_err_med,
            "back_has_egg": back_has_egg,
            "h_tip": self.egg_h_tip_latest,
            "normal_down": self.egg_normal_down,
        }
        return pos_med, "accurate_stable", stats

    def timeout_tick(self):
        now = time.perf_counter()
        if self.last_update is not None and (now - self.last_update) > DETECTION_TIMEOUT:
            self.latest_pos = None
            self.last_update = None
        if (
            self.normal_last_update is not None
            and (now - self.normal_last_update) > DETECTION_TIMEOUT
        ):
            self.normal_last_update = None
        if self.egg_rough_last_update is not None and (now - self.egg_rough_last_update) > DETECTION_TIMEOUT:
            self.egg_rough_pos = None
            self.egg_rough_last_update = None
        if self.egg_accurate_last_update is not None and (now - self.egg_accurate_last_update) > DETECTION_TIMEOUT:
            self.egg_accurate_pos = None
            self.egg_accurate_last_update = None
        if self.egg_normal_last_update is not None and (now - self.egg_normal_last_update) > DETECTION_TIMEOUT:
            self.egg_normal_last_update = None
        if self.egg_yaw_last_update is not None and (now - self.egg_yaw_last_update) > DETECTION_TIMEOUT:
            self.egg_yaw_deg = None
            self.egg_yaw_last_update = None
        if (
            self.egg_yaw_axis_width_last_update is not None
            and (now - self.egg_yaw_axis_width_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_yaw_axis_width_mm = None
            self.egg_yaw_axis_width_last_update = None
        if (
            self.egg_yaw_other_axis_width_last_update is not None
            and (now - self.egg_yaw_other_axis_width_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_yaw_other_axis_width_mm = None
            self.egg_yaw_other_axis_width_last_update = None
        if (
            self.egg_yaw_axis_name_last_update is not None
            and (now - self.egg_yaw_axis_name_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_yaw_axis_name = None
            self.egg_yaw_axis_name_last_update = None
        if (
            self.egg_yaw_axis_center_to_endpoint_max_last_update is not None
            and (now - self.egg_yaw_axis_center_to_endpoint_max_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_yaw_axis_center_to_endpoint_max_mm = None
            self.egg_yaw_axis_center_to_endpoint_max_last_update = None
        if (
            self.egg_yaw_axis_base_x_err_last_update is not None
            and (now - self.egg_yaw_axis_base_x_err_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_yaw_axis_base_x_err_deg = None
            self.egg_yaw_axis_base_x_err_last_update = None
        if (
            self.egg_back_has_egg_last_update is not None
            and (now - self.egg_back_has_egg_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_back_has_egg = None
            self.egg_back_has_egg_last_update = None
        if (
            self.egg_bowl_status_last_update is not None
            and (now - self.egg_bowl_status_last_update) > DETECTION_TIMEOUT
        ):
            self.egg_bowl_status = None
            self.egg_bowl_status_last_update = None
        if self.egg_h_tip_last_update is not None and (now - self.egg_h_tip_last_update) > DETECTION_TIMEOUT:
            self.egg_h_tip_latest = None
            self.egg_h_tip_last_update = None
        for food in GRID_FOOD_NAMES:
            tlast = self.grid_food_last_update.get(food)
            if tlast is not None and (now - tlast) > DETECTION_TIMEOUT:
                self.grid_food_cells[food] = []
                self.grid_food_last_update[food] = None
                self.grid_food_samples[food].clear()
        for name in self.stage_sync_targets.keys():
            tlast = self.stage_sync_last_update.get(name)
            if tlast is not None and (now - tlast) > DETECTION_TIMEOUT:
                self.stage_sync_pose[name] = None
                self.stage_sync_last_update[name] = None

    def sync_stage(self, stage_ref, pose_locked=False):
        if pose_locked:
            return

        if self.latest_pos is not None:
            set_world_pos_flat_z(stage_ref, self.scene_prims.egg_plate, self.latest_pos, z_fixed=Z_FIXED)
        egg_pos, _ = self.best_egg_pos()
        if egg_pos is not None:
            set_world_pos_flat_z(stage_ref, self.scene_prims.egg, egg_pos, z_fixed=EGG_STAGE_Z)
        for name, target in self.stage_sync_targets.items():
            pos = self.stage_sync_pose.get(name)
            if pos is not None:
                set_world_pos_flat_z(stage_ref, target.prim_path, pos, z_fixed=Z_FIXED)

    def have_pose(self):
        if egg_manual_enabled():
            return True
        return self.latest_pos is not None

    def best_egg_pos(self):
        if self.egg_accurate_pos is not None:
            return self.egg_accurate_pos.copy(), "accurate"
        if self.egg_rough_pos is not None:
            return self.egg_rough_pos.copy(), "rough"
        return None, "none"

    def select_grid_food_cell(self, food: str):
        cells = self.grid_food_cells.get(food) or []
        cfg = grid_food_cfg(food)
        height_axis = normalize_vec(
            -cfg["manual_normal_down"], default=np.array([0.0, 0.0, 1.0], dtype=np.float32)
        )
        order_rank = {
            int(cid): i
            for i, cid in enumerate(cfg["cell_order"])
        }
        candidates = []
        for cell in cells:
            try:
                cid = int(cell.get("cell_id"))
            except Exception:
                continue
            try:
                ratio = float(cell.get("ratio", 0.0))
            except Exception:
                ratio = 0.0
            rejected_by_center_distance = self.grid_food_cell_center_distance_logged.setdefault(food, set())
            permanently_empty_ids = self.grid_food_permanent_empty_ids.setdefault(food, set())
            if cid in rejected_by_center_distance or cid in permanently_empty_ids:
                continue
            try:
                center = np.asarray(cell.get("center_base_m"), dtype=np.float32).reshape(3)
            except Exception:
                center = None
            if center is not None and np.all(np.isfinite(center)):
                first_center_by_cell = self.grid_food_cell_first_center_m.setdefault(food, {})
                if cid not in first_center_by_cell:
                    first_center_by_cell[cid] = center.copy()
                else:
                    first_center = np.asarray(first_center_by_cell[cid], dtype=np.float32).reshape(3)
                    center_distance_m = float(np.linalg.norm(center - first_center))
                    if center_distance_m > float(GRID_FOOD_EMPTY_BY_CELL_CENTER_DISTANCE_M):
                        rejected_by_center_distance.add(cid)
                        delta_mm = (center - first_center) * 1000.0
                        print(
                            f"[TEST][GRID_FOOD][{food}] cell {cid} permanently skipped as empty by center displacement: "
                            f"distance={center_distance_m * 1000.0:.1f}mm "
                            f"threshold={GRID_FOOD_EMPTY_BY_CELL_CENTER_DISTANCE_M * 1000.0:.1f}mm "
                            f"delta_xyz_mm={fmt_vec(delta_mm)}"
                        )
                        continue
            selection_height = (
                float(np.dot(center, height_axis))
                if center is not None and np.all(np.isfinite(center))
                else float("-inf")
            )
            candidates.append((ratio, selection_height, -order_rank.get(cid, 999), cell))
        if not candidates:
            return None
        max_ratio = max(item[0] for item in candidates)
        close_candidates = [
            item for item in candidates
            if (max_ratio - item[0]) <= float(GRID_FOOD_RATIO_HEIGHT_TIE_EPS)
        ]
        close_candidates.sort(key=lambda item: (item[1], item[0], item[2]), reverse=True)
        return close_candidates[0][3]

    def stable_grid_food_candidate(
        self,
        food: str,
        min_samples=GRID_FOOD_STABLE_MIN_SAMPLES,
        max_xy_spread=GRID_FOOD_STABLE_MAX_XY_SPREAD_M,
        max_age_sec=GRID_FOOD_STABLE_MAX_AGE_SEC,
    ):
        now = time.perf_counter()
        samples = [
            s for s in self.grid_food_samples.get(food, [])
            if (now - s["t"]) <= float(max_age_sec)
        ]
        if len(samples) < int(min_samples):
            return None, {
                "reason": "need_more_samples",
                "samples": len(samples),
                "min_samples": int(min_samples),
            }
        recent = samples[-int(min_samples):]
        cell_ids = [int(s["cell"].get("cell_id", -1)) for s in recent]
        if len(set(cell_ids)) != 1:
            return None, {
                "reason": "cell_id_not_stable",
                "samples": len(samples),
                "recent_cell_ids": cell_ids,
            }
        pts = np.asarray([s["center"] for s in recent], dtype=np.float32)
        center_med = np.median(pts, axis=0).astype(np.float32)
        xy_dists = np.linalg.norm(pts[:, :2] - center_med[:2].reshape(1, 2), axis=1)
        max_xy = float(np.max(xy_dists)) if xy_dists.size else float("inf")
        if max_xy > float(max_xy_spread):
            return None, {
                "reason": "xy_spread_too_large",
                "samples": len(samples),
                "cell_id": cell_ids[-1],
                "max_xy_spread": max_xy,
                "limit": float(max_xy_spread),
            }

        locked = dict(recent[-1]["cell"])
        locked["center_base_m"] = center_med
        return locked, {
            "reason": "stable",
            "samples": len(samples),
            "used_samples": int(min_samples),
            "cell_id": cell_ids[-1],
            "max_xy_spread": max_xy,
            "center_base_m": center_med,
        }

class MoveToEggPlateController(SpinRampMixin):
    # 左臂函數分類：
    # 1. 共用功能：流程控制、夾爪、放料、RMPflow、每幀更新與恢復狀態。
    # 2. 蛋專用：蛋姿態鎖定、下降、夾取、抬升及放入拉麵碗。
    # 3. 筍乾／木耳專用：十八宮格選格、接近、夾取、分段抬升及退回。

    # 【共用功能／初始化】建立左右流程共用的狀態、到位判斷與命令快取。
    def __init__(
        self,
        world: World,
        perception: EggPlateBridge,
        prim_path: str = UR5E_PRIM,
        ee_prim_path: str = EE_PRIM,
        name: str = "ur5e",
        rmpflow_base_dir=None,
        urdf_filename: str = "ur5e_gripper_root_joint_revise.urdf",
        robot_description_filename: str = "ur5e_collision_gripper.yaml",
        rmpflow_config_filename: str = "ur5e_collision_gripper_rmpflow.yaml",
        gripper_close_fn=None,
        gripper_open_fn=None,
        idle_home_enabled=True,
        safe_idle_home_enabled=False,
        idle_home_clearance_z=None,
    ):
        self.perception = perception
        self.name = str(name)
        self.prim_path = str(prim_path)
        self.ee_prim_path = str(ee_prim_path)
        self.gripper_close_fn = gripper_close_fn if gripper_close_fn is not None else ur_gripper_close
        self.gripper_open_fn = gripper_open_fn if gripper_open_fn is not None else ur_gripper_open
        self.idle_home_enabled = bool(idle_home_enabled)
        self.robot = SingleManipulator(
            prim_path=self.prim_path,
            name=self.name,
            end_effector_prim_path=self.ee_prim_path,
        )
        world.scene.add(self.robot)
        self.robot.initialize()
        self.robot.post_reset()

        if rmpflow_base_dir is None:
            rmpflow_base_dir = ROOT_PATH / "rmpflow_file" / "ur5e_gripper"
        rmpflow_base_dir = Path(rmpflow_base_dir)
        self.rmpflow = RmpFlow(
            robot_description_path=str(rmpflow_base_dir / robot_description_filename),
            urdf_path=str(rmpflow_base_dir / urdf_filename),
            rmpflow_config_path=str(rmpflow_base_dir / rmpflow_config_filename),
            end_effector_frame_name="wrist_3_link",
            maximum_substep_size=0.003,
        )
        self.policy = ArticulationMotionPolicy(self.robot, self.rmpflow)
        self.rmpflow.update_world()
        self.latest_joint_positions = None
        self.latest_arm6_cmd = None
        try:
            self._record_joint_positions(self.robot.get_joint_positions())
        except Exception:
            pass
        self.perception.set_joint_state_provider(self.joint_state_snapshot)

        self.requested = False
        self.auto_run = False
        self.mode = None
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        self.as_capture_active = False
        self.as_capture_queue = []
        self.as_capture_egg_ready = False
        self.as_capture_ready = False
        self.as_execute_active = False
        self.as_grid_snapshots = {}
        self.grid_food_capture_only = False
        self.as_egg_pre_shrink_width_mm = None
        self.as_egg_pre_shrink_sent_at = None
        self.target_locked = None
        self.target_normal_locked = None
        self.target_yaw_locked = None
        self.target_yaw_raw_locked = None
        self.target_yaw_axis_width_mm_locked = None
        self.target_yaw_other_axis_width_mm_locked = None
        self.target_yaw_axis_name_locked = None
        self.target_yaw_axis_center_to_endpoint_max_mm_locked = None
        self.target_yaw_axis_base_x_err_deg_locked = None
        self.target_back_has_egg_locked = None
        self.target_side_edge_fallback_locked = False
        self.target_side_edge_fallback_side_locked = None
        self.egg_wrist_offset = 0.0
        self.current_spin_offset = 0.0
        self.egg_descend_dz_locked = EGG_DESCEND_DZ
        self.egg_descend_source_locked = "fallback_default"
        self.egg_h_tip_locked = None
        self.egg_h_tip_descend_dz_locked = None
        self.egg_wrist_offset = 0.0
        self.current_spin_offset = 0.0
        self.spin_ramp_speed = np.deg2rad(SPIN_RAMP_SPEED_DEG_PER_SEC)
        self.spin_settle_tol = np.deg2rad(SPIN_SETTLE_TOL_DEG)
        self.target_source = "none"
        self.reach = ReachHold()
        self.grid_food_post_lift_tool_z_reach = ReachHold(
            tol=GRID_FOOD_POST_LIFT_TOOL_Z_REACH_TOL_M,
            hold_sec=GRID_FOOD_POST_LIFT_TOOL_Z_REACH_HOLD_SEC,
        )
        self.grid_food_descend_real_tcp_in_tol_since = None
        self.pre_descend_step = None
        self.pre_descend_wait_start = None
        self.egg_pre_descend_y_backoff_m_locked = 0.0
        self.egg_pre_descend_y_backoff_sign_locked = 0.0
        self.post_step = None
        self.post_reach = ReachHold()
        self.home_open_reach = ReachHold()
        self.open_gripper_at_home_pending = False
        self.ungraspable_sweep_open_at_plate_pending = False
        self.ungraspable_sweep_return_phase = None
        self.ungraspable_sweep_return_quat = None
        self.ungraspable_sweep_return_base_z_target = None
        self.ungraspable_sweep_count = 0
        self.ungraspable_sweep_limit_logged = False
        self.pre_home_release_step = None
        self.pre_home_release_wait_start = None
        self.pre_home_release_source = None
        self.plc_grid_food_release_sent_source = None
        self.egg_home_return_active = False
        self.egg_home_return_reach = ReachHold(hold_sec=EGG_HOME_REACH_HOLD_SEC)
        self.plate_mask_stabilize_until = None
        self.no_back_reobserve_done = False
        self.no_back_reobserve_stabilize_until = None
        self.post_wait_start = None
        self.gripper_cmd = GRIPPER_OPEN
        self.last_gripper_state = "open"
        self.last_real_gripper_close_send_wall = None
        self.real_gripper_close_resend_count = 0
        self.done_logged = False
        self.next_joint_event_log_t = 0.0
        self.last_target_pos = None
        self.last_look_pos = None
        self.last_normal_down = None
        self.last_ee_pos = None
        self.last_isaac_axes_col = None
        self.last_isaac_axes_row = None
        self.last_target_quat = None
        self.last_target_quat_rmp_wxyz = None
        self.egg_descend_quat_locked = None
        self.egg_descend_quat_rmp_locked = None
        self.egg_descend_real_tcp_in_tol_since = None
        self.egg_descend_real_tcp_correction_m = np.zeros(3, dtype=np.float32)
        self.egg_descend_real_tcp_y_integral_m = 0.0
        self.egg_descend_real_tcp_last_feedback_wall = None
        self.egg_descend_path_start_pos = None
        self.egg_descend_path_final_pos = None
        self.egg_descend_path_pre_segment_pos = None
        self.egg_descend_path_pre_segment_reach = ReachHold(
            tol=EGG_DESCEND_CARTESIAN_WAYPOINT_REACH_TOL_M,
            hold_sec=EGG_DESCEND_REACH_HOLD_SEC,
        )
        self.egg_descend_path_pre_segment_reached = False
        self.egg_descend_path_waypoints = []
        self.egg_descend_path_index = 0
        self.egg_descend_path_count = 0
        self.egg_descend_path_complete = False
        self.back_egg_axis_target1_locked = None
        self.back_egg_axis_slide_dir_locked = None
        self.back_egg_axis_half_length_m_locked = 0.0
        self.last_target_axes = None
        self.last_camera_spin_180 = False
        self.last_orient_err_deg = float("inf")
        self.grid_food_type_locked = None
        self.grid_food_cell_locked = None
        self.grid_food_cell_size_xy_mm_locked = None
        self.grid_food_post_lift_rotation_index = 0
        self.grid_food_post_lift_tool_z_cycle_index = 0
        self.grid_food_base_y_shift_m_locked = 0.0
        self.grid_food_step = None
        self.grid_food_wait_start = None
        self.ungraspable_sweep_step = None
        self.ungraspable_sweep_side = None
        self.ungraspable_sweep_cfg = None
        self.ungraspable_sweep_reach = ReachHold()
        self.pending_sequence_queue = []
        self.queued_sequence_active = False
        self.queued_transition_wait_until = None


    # 【共用功能／狀態與流程入口】記錄關節、判斷忙碌並管理連續食材任務。
    def _record_joint_positions(self, joint_positions):
        if joint_positions is None:
            return
        arr = np.asarray(joint_positions, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return
        self.latest_joint_positions = [float(x) for x in arr.tolist()]
        if arr.size >= 6:
            self.latest_arm6_cmd = [float(x) for x in arr[:6].tolist()]

    def joint_state_snapshot(self):
        jp = self.latest_joint_positions
        arm6 = self.latest_arm6_cmd
        return {
            "left_joint_positions_rad": jp,
            "left_arm6_rad": arm6,
            "left_gripper_cmd": float(self.gripper_cmd),
        }

    def sequence_active(self):
        return bool(
            self.requested
            or self.auto_run
            or self.mode is not None
            or self.waiting_for_egg_pose
            or self.egg_inspect_only
            or self.pre_descend_step is not None
            or self.post_step is not None
            or self.grid_food_step is not None
            or self.ungraspable_sweep_step is not None
            or self.pre_home_release_step is not None
            or self.open_gripper_at_home_pending
            or self.plate_mask_stabilize_until is not None
            or self.no_back_reobserve_stabilize_until is not None
        )

    def queue_sequence(self, name):
        name = str(name).strip().lower()
        if name not in LEFT_FOOD_NAMES:
            print(f"[TEST][QUEUE] unknown sequence={name}")
            return
        self.pending_sequence_queue.append(name)
        print(f"[TEST][QUEUE] queued {name}; queue={self.pending_sequence_queue}")

    def start_next_queued_sequence(self, reason="done"):
        if not self.pending_sequence_queue:
            self.queued_sequence_active = False
            if self.as_execute_active:
                self.as_execute_active = False
                self.as_grid_snapshots.clear()
                print("[TEST][A/S] S sequence complete; frozen targets cleared.")
            return False
        next_name = self.pending_sequence_queue.pop(0)
        print(
            f"[TEST][QUEUE] start queued {next_name}; skip home. "
            f"reason={reason} remaining_queue={self.pending_sequence_queue}"
        )
        if next_name == "egg":
            self.start_auto_egg_sequence(from_queue=True)
        else:
            self.request_grid_food_sequence(next_name, from_queue=True)
        return True

    def _start_next_as_capture(self):
        """推進 A 拍照：木耳、筍乾、蛋。"""
        if not self.as_capture_queue:
            self.as_capture_active = False
            self.as_capture_ready = bool(
                self.as_capture_egg_ready
                and set(GRID_FOOD_NAMES).issubset(self.as_grid_snapshots)
            )
            print("[TEST][A/S] capture complete; press S to grasp egg -> menma -> fungus.")
            return
        next_food = self.as_capture_queue.pop(0)
        if next_food == "egg":
            self.start_auto_egg_sequence(from_queue=True)
        else:
            self.request_grid_food_sequence(next_food, from_queue=True, capture_only=True)

    def start_as_capture_sequence(self):
        """A：依序辨識並鎖定木耳、筍乾與蛋。"""
        if self.sequence_active():
            print("[TEST][A/S] A ignored: left-arm flow is already active.")
            return False
        self.pending_sequence_queue.clear()
        self.queued_sequence_active = False
        self.as_capture_active = True
        self.as_capture_queue = [*GRID_FOOD_CAPTURE_ORDER, "egg"]
        self.as_capture_egg_ready = False
        self.as_capture_ready = False
        self.as_execute_active = False
        self.as_grid_snapshots.clear()
        self.as_egg_pre_shrink_width_mm = None
        self.as_egg_pre_shrink_sent_at = None
        print("[TEST][A/S] A capture start: fungus -> menma -> egg; no descend or gripper close.")
        self._start_next_as_capture()
        return True

    def start_as_execute_sequence(self):
        """S：夾取 A 流程凍結的目標。"""
        needed = set(GRID_FOOD_NAMES)
        if not self.as_capture_ready or not self.as_capture_egg_ready or not needed.issubset(self.as_grid_snapshots):
            print("[TEST][A/S] S ignored: complete A capture first.")
            return False
        if self.mode != "egg" or self.target_locked is None:
            print("[TEST][A/S] S ignored: frozen egg approach is no longer held; press A again.")
            return False
        self.as_capture_ready = False
        self.as_execute_active = True
        self.queued_sequence_active = True
        self.pending_sequence_queue.clear()
        self.pending_sequence_queue.extend(GRID_FOOD_NAMES)
        self.egg_inspect_only = False
        self.auto_run = True
        self.requested = True
        self.waiting_for_egg_pose = False
        self.done_logged = True
        print("[TEST][A/S] S execute start: frozen egg -> menma -> fungus.")
        self.start_pre_descend_flow()
        return True

    # 【蛋專用／流程入口】啟動蛋盤拍照、選蛋與夾取流程。
    def start_auto_egg_sequence(self, from_queue=False):
        if not from_queue and self.sequence_active():
            self.queue_sequence("egg")
            return
        self.ungraspable_sweep_count = 0
        self.ungraspable_sweep_limit_logged = False
        self.auto_run = True
        self.request_move()
        if self.requested:
            tail = "ramen" if ENABLE_RAMEN_PLACE_FLOW else "egg lift done"
            print(f"[TEST][AUTO] Q sequence started: plate -> accurate egg -> egg approach -> descend -> {tail}.")
        else:
            self.auto_run = False

    # 【筍乾／木耳專用／流程入口】啟動十八宮格拍照、選格與夾取流程。
    def request_grid_food_sequence(self, food: str, from_queue=False, capture_only=False):
        food = str(food).strip().lower()
        if food not in GRID_FOOD_PROFILES:
            print(f"[TEST][GRID_FOOD] unknown food={food}")
            return
        if not from_queue and self.sequence_active():
            self.queue_sequence(food)
            return
        if self.as_execute_active and not capture_only and food in self.as_grid_snapshots:
            self.request_grid_food_from_snapshot(food)
            return
        self.perception.reset_grid_food_height_state(food)
        self.reset_post_flow(open_gripper=True)
        self.perception.set_egg_detection_gate(False)
        self.auto_run = False
        self.mode = "grid_food"
        self.reach = ReachHold()
        self.grid_food_type_locked = food
        self.grid_food_cell_locked = None
        self.grid_food_cell_size_xy_mm_locked = None
        self.grid_food_post_lift_rotation_index = 0
        self.grid_food_post_lift_tool_z_cycle_index = 0
        self.grid_food_post_lift_tool_z_reach.reset()
        self.grid_food_descend_real_tcp_in_tol_since = None
        self.pre_descend_step = None
        self.pre_descend_wait_start = None
        self.egg_pre_descend_y_backoff_m_locked = 0.0
        self.egg_pre_descend_y_backoff_sign_locked = 0.0
        cfg = grid_food_cfg(food)
        self.grid_food_base_y_shift_m_locked = float(cfg["base_y_shift_m"])
        self.grid_food_step = "observe_move"
        self.grid_food_capture_only = bool(capture_only)
        self.grid_food_wait_start = None
        self.target_locked = grid_food_manual_target_for_isaac(food) if egg_manual_enabled() else np.array(
            [HOME_XY[0], HOME_XY[1], HOME_Z],
            dtype=np.float32,
        )
        self.target_normal_locked = cfg["observe_normal_down"]
        self.target_source = f"{food}_observe"
        self.target_yaw_locked = None
        self.target_yaw_raw_locked = None
        self.requested = True
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        self.reach.reset()
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        self.gripper_cmd = GRIPPER_OPEN
        self.last_gripper_state = "open"
        print(
            f"[TEST][GRID_FOOD][{food}] start: move to observe target "
            f"{fmt_vec(self.target_locked)} normal={fmt_vec(self.target_normal_locked)}"
        )

    def request_grid_food_from_snapshot(self, food: str):
        """從 A 流程凍結的格子繼續夾取。"""
        food = str(food).strip().lower()
        cell = copy.deepcopy(self.as_grid_snapshots[food])
        cfg = grid_food_cfg(food)
        self.reset_post_flow(open_gripper=True)
        self.perception.set_egg_detection_gate(False)
        self.auto_run = False
        self.mode = "grid_food"
        self.reach = ReachHold()
        self.grid_food_type_locked = food
        self.grid_food_cell_locked = cell
        self.grid_food_cell_size_xy_mm_locked = None
        self.grid_food_post_lift_rotation_index = 0
        self.grid_food_post_lift_tool_z_cycle_index = 0
        self.grid_food_post_lift_tool_z_reach.reset()
        self.grid_food_descend_real_tcp_in_tol_since = None
        self.grid_food_base_y_shift_m_locked = float(cfg["base_y_shift_m"])
        self.grid_food_step = "approach"
        self.grid_food_capture_only = False
        self.grid_food_wait_start = None
        self.target_locked = np.asarray(cell["center_base_m"], dtype=np.float32).reshape(3).copy()
        self.target_normal_locked = np.asarray(cfg["manual_normal_down"], dtype=np.float32).copy()
        self.target_source = f"A_snapshot_{food}_cell_{int(cell.get('cell_id', -1))}"
        self.requested = True
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        self.reach.reset()
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        self.gripper_cmd = GRIPPER_OPEN
        self.last_gripper_state = "open"
        print(f"[TEST][A/S] resume {food} frozen cell={cell.get('cell_id')} -> approach.")

    # 【共用功能／夾爪控制】統一模擬與真實 Robotiq 的開合及寬度命令。
    def _send_robotiq_direct_cmd(self, state: str):
        if state == "open":
            return self.gripper_open_fn()
        if state == "close":
            width_mm = self.gripper_close_width_mm()
            use_nonselected_axis = bool(
                self.use_back_egg_base_x_axis_slide()
            )
            close_axis = "nonselected" if use_nonselected_axis else "selected"
            measured_width = (
                self.target_yaw_other_axis_width_mm_locked
                if use_nonselected_axis
                else self.target_yaw_axis_width_mm_locked
            )
            print(
                f"[TEST][Gripper] close axis={close_axis} measured_width={measured_width} mm "
                f"cmd_width={width_mm:.1f} mm"
            )
            self.last_real_gripper_close_send_wall = time.perf_counter()
            return self.gripper_close_fn(force=60, speed=100, dis=width_mm)
        return None

    def send_gripper_width_mm(self, width_mm, event_name="gripper_width_cmd"):
        width_mm = float(width_mm)
        self.gripper_cmd = GRIPPER_CLOSE
        self.last_gripper_state = f"width_{width_mm:.1f}"
        print(f"[TEST][Gripper] width cmd={width_mm:.1f} mm")
        if ENABLE_REAL_GRIPPER:
            return self.gripper_close_fn(force=60, speed=100, dis=width_mm)
        return None

    # 【蛋專用／量測鎖定】鎖定蛋的選中軸、另一軸與端點距離。
    def _lock_egg_measurement(self, target_attr, source_attr, value=None):
        value = getattr(self.perception, source_attr) if value is None else value
        locked = float(value) if value is not None and np.isfinite(value) else None
        setattr(self, target_attr, locked)
        return locked

    def lock_yaw_axis_width_mm(self, value=None):
        return self._lock_egg_measurement(
            "target_yaw_axis_width_mm_locked", "egg_yaw_axis_width_mm", value
        )

    def lock_yaw_other_axis_width_mm(self, value=None):
        return self._lock_egg_measurement(
            "target_yaw_other_axis_width_mm_locked", "egg_yaw_other_axis_width_mm", value
        )

    def lock_yaw_axis_center_to_endpoint_max_mm(self, value=None):
        return self._lock_egg_measurement(
            "target_yaw_axis_center_to_endpoint_max_mm_locked",
            "egg_yaw_axis_center_to_endpoint_max_mm",
            value,
        )

    def reset_egg_spin_from_current_pose(self):
        self.egg_wrist_offset = 0.0
        self.current_spin_offset = 0.0

    def gripper_close_width_mm(self):
        if not USE_EGG_YAW_AXIS_WIDTH_FOR_GRIPPER_CLOSE:
            return float(GRIPPER_CLOSE_WIDTH_MM)
        use_nonselected_axis = bool(
            self.use_back_egg_base_x_axis_slide()
        )
        width = (
            self.target_yaw_other_axis_width_mm_locked
            if use_nonselected_axis
            else self.target_yaw_axis_width_mm_locked
        )
        if width is None or not np.isfinite(width):
            return float(GRIPPER_CLOSE_WIDTH_MM)
        shrink_mm = (
            float(EGG_GRIPPER_SMALL_WIDTH_SHRINK_MM)
            if float(width) < float(EGG_GRIPPER_SMALL_WIDTH_THRESHOLD_MM)
            else float(GRIPPER_CLOSE_EXTRA_SHRINK_MM)
        )
        cmd_width = float(max(float(width) - shrink_mm, 0.0))
        return float(cmd_width)

    def resend_real_gripper_close_if_needed(self):
        if not ENABLE_REAL_GRIPPER:
            return
        if self.real_gripper_close_resend_count >= int(GRIPPER_CLOSE_RESEND_MAX):
            return
        now = time.perf_counter()
        if self.last_real_gripper_close_send_wall is not None:
            if (now - self.last_real_gripper_close_send_wall) < float(GRIPPER_CLOSE_RESEND_INTERVAL_SEC):
                return
        self.real_gripper_close_resend_count += 1
        self._send_robotiq_direct_cmd("close")

    def set_gripper(self, state: str, send_real=True):
        if state == self.last_gripper_state:
            return
        if state == "open":
            self.gripper_cmd = GRIPPER_OPEN
        elif state == "close":
            self.gripper_cmd = GRIPPER_CLOSE
        else:
            print(f"[TEST][Gripper] Unknown state: {state}")
            return

        self.last_gripper_state = state
        print(f"[TEST][Gripper] -> {state} (sim cmd={self.gripper_cmd:.2f})")

        if send_real and ENABLE_REAL_GRIPPER:
            return self._send_robotiq_direct_cmd(state)

    # 【共用功能／放料與回 Home】重設夾取後狀態並啟動安全放料流程。
    def reset_post_flow(self, open_gripper=False):
        self.pre_descend_step = None
        self.pre_descend_wait_start = None
        self.egg_pre_descend_y_backoff_m_locked = 0.0
        self.egg_pre_descend_y_backoff_sign_locked = 0.0
        self.post_step = None
        self.post_wait_start = None
        self.post_reach.reset()
        self.egg_descend_quat_locked = None
        self.egg_descend_quat_rmp_locked = None
        self.egg_descend_real_tcp_in_tol_since = None
        self.egg_descend_real_tcp_correction_m = np.zeros(3, dtype=np.float32)
        self.egg_descend_real_tcp_y_integral_m = 0.0
        self.egg_descend_real_tcp_last_feedback_wall = None
        self.egg_descend_path_start_pos = None
        self.egg_descend_path_final_pos = None
        self.egg_descend_path_pre_segment_pos = None
        self.egg_descend_path_pre_segment_reach.reset()
        self.egg_descend_path_pre_segment_reached = False
        self.egg_descend_path_waypoints = []
        self.egg_descend_path_index = 0
        self.egg_descend_path_count = 0
        self.egg_descend_path_complete = False
        self.last_real_gripper_close_send_wall = None
        self.real_gripper_close_resend_count = 0
        self.open_gripper_at_home_pending = False
        self.ungraspable_sweep_open_at_plate_pending = False
        self.pre_home_release_step = None
        self.pre_home_release_wait_start = None
        self.pre_home_release_source = None
        self.plc_grid_food_release_sent_source = None
        self.egg_home_return_active = False
        self.egg_home_return_reach = ReachHold(hold_sec=EGG_HOME_REACH_HOLD_SEC)
        self.plate_mask_stabilize_until = None
        self.home_open_reach.reset()
        if open_gripper:
            self.set_gripper("open")
        else:
            self.gripper_cmd = GRIPPER_OPEN
            self.last_gripper_state = "open"

    # 【共用功能／放料與回 Home】移動至放料點、開夾並安全返回 Home。
    def start_pre_home_release_flow(self, source="unknown"):
        cfg = pre_home_release_cfg(source)
        if str(source) == "egg":
            cfg = dict(cfg)
            cfg["open_wait_sec"] = float(EGG_PRE_HOME_OPEN_WAIT_SEC)
        if not bool(cfg["enabled"]):
            self.open_gripper_at_home_pending = True
            self.home_open_reach.reset()
            print(f"[TEST][PRE_HOME_RELEASE] disabled; opening at home. source={source}")
            return
        self.pre_home_release_step = "move"
        self.pre_home_release_wait_start = None
        self.pre_home_release_source = str(source)
        self.open_gripper_at_home_pending = False
        self.home_open_reach.reset()
        self.reach = ReachHold(
            hold_sec=(
                EGG_PRE_HOME_REACH_HOLD_SEC
                if str(source) == "egg"
                else REACH_HOLD_SEC
            )
        )
        self.reach.reset()
        if str(source).startswith("grid_food_"):
            self.gripper_cmd = GRIPPER_CLOSE
            print(f"[TEST][PRE_HOME_RELEASE] keep grid-food gripper width before release. source={source}")
        else:
            self.set_gripper("close")
        print(
            f"[TEST][PRE_HOME_RELEASE] move to release pose before home: "
            f"target={fmt_vec(cfg['target_pos'])} normal={fmt_vec(cfg['normal_down'])} "
            f"open_wait={cfg['open_wait_sec']:.1f}s source={source} file={cfg['source']}"
        )

    def target_from_pre_home_release(self):
        cfg = pre_home_release_cfg(self.pre_home_release_source)
        if str(self.pre_home_release_source) == "egg":
            cfg = dict(cfg)
            cfg["open_wait_sec"] = float(EGG_PRE_HOME_OPEN_WAIT_SEC)
        target_pos = np.asarray(cfg["target_pos"], dtype=np.float32).reshape(3)
        normal_down = orient_normal_to_negative_z(cfg["normal_down"])
        look_pos = target_pos + normal_down * float(HOME_LOOK_DZ)
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down, cfg

    def pre_home_release_fixed_quat_for_source(self):
        """移向放料位時保持格子食材抬升姿態。"""
        if str(self.pre_home_release_source).startswith("grid_food_"):
            return self.grid_food_post_lift_fixed_quat()
        return fixed_downward_base_x_quat()

    def grid_food_pre_home_to_home_waypoint(self):
        """取得筍乾／木耳共用回 Home 中間點。"""
        target_pos = rtde_tcp_pos_to_isaac(GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_RTDE_POS)
        normal_down = orient_normal_to_negative_z(GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Z_AXIS)
        look_pos = target_pos + normal_down * float(HOME_LOOK_DZ)
        fixed_quat = fixed_quat_from_tool_axes(
            normal_down,
            x_axis=GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_X_AXIS,
            y_axis=GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Y_AXIS,
        )
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down, fixed_quat

    def update_pre_home_release_flow(self, ee_pos, dt):
        if self.pre_home_release_step is None:
            return False

        target_pos, look_pos, normal_down, cfg = self.target_from_pre_home_release()
        fixed_quat = self.pre_home_release_fixed_quat_for_source()

        if self.pre_home_release_step == "move":
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=fixed_quat)
            self.gripper_cmd = GRIPPER_CLOSE
            if self.reach.update(target_pos, ee_pos):
                self.pre_home_release_step = "open_wait"
                self.pre_home_release_wait_start = time.perf_counter()
                self.reach.reset()
                print(
                    f"[TEST][PRE_HOME_RELEASE] release pose reached; "
                    f"opening gripper for {float(cfg['open_wait_sec']):.1f}s."
                )
                self.set_gripper("open")
                if str(self.pre_home_release_source) == "grid_food_fungus":
                    self.plc_grid_food_release_sent_source = "fungus"
            return True

        if self.pre_home_release_step == "open_wait":
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=fixed_quat)
            self.gripper_cmd = GRIPPER_OPEN
            elapsed = (
                0.0
                if self.pre_home_release_wait_start is None
                else time.perf_counter() - self.pre_home_release_wait_start
            )
            if elapsed >= float(cfg["open_wait_sec"]):
                done_source = self.pre_home_release_source
                if str(done_source).startswith("grid_food_"):
                    self.pre_home_release_step = "grid_food_home_waypoint"
                    self.pre_home_release_wait_start = None
                    self.reach.reset()
                    waypoint_pos, _waypoint_look, waypoint_normal, _waypoint_quat = (
                        self.grid_food_pre_home_to_home_waypoint()
                    )
                    print(
                        "[TEST][PRE_HOME_RELEASE] gripper opened; moving through "
                        f"grid-food home waypoint {fmt_vec(waypoint_pos)} before home."
                    )
                    return True

                print("[TEST][PRE_HOME_RELEASE] gripper opened; returning home.")
                # 連續食材流程在筍乾放料後先回 Home，固定時間後切換木耳。
                if (
                    self.queued_sequence_active
                    and done_source == "grid_food_menma"
                    and self.pending_sequence_queue
                    and self.pending_sequence_queue[0] == "fungus"
                ):
                    self.queued_transition_wait_until = (
                        time.perf_counter() + QUEUED_MENMA_TO_FUNGUS_DELAY_SEC
                    )
                    self.pre_home_release_step = "queued_menma_to_fungus_wait"
                    print(
                        "[TEST][QUEUE] T sequence: return home, then switch to fungus after "
                        f"{QUEUED_MENMA_TO_FUNGUS_DELAY_SEC:.3f}s (do not wait for home reach)."
                    )
                    return True
                self.pre_home_release_step = None
                self.pre_home_release_wait_start = None
                self.pre_home_release_source = None
                self.home_open_reach.reset()
                if done_source == "egg":
                    self.egg_home_return_active = True
                    self.egg_home_return_reach.reset()
                if self.start_next_queued_sequence(reason=f"pre_home_release_done:{done_source}"):
                    return True
            return True

        if self.pre_home_release_step == "grid_food_home_waypoint":
            waypoint_pos, waypoint_look, waypoint_normal, waypoint_quat = (
                self.grid_food_pre_home_to_home_waypoint()
            )
            self.set_motion_target(
                waypoint_pos,
                waypoint_look,
                waypoint_normal,
                dt,
                fixed_quat=waypoint_quat,
            )
            self.gripper_cmd = GRIPPER_OPEN
            if self.reach.update(waypoint_pos, ee_pos):
                done_source = self.pre_home_release_source
                # 到達必要的中繼點後，開始筍乾到木耳的計時切換。
                if (
                    self.queued_sequence_active
                    and done_source == "grid_food_menma"
                    and self.pending_sequence_queue
                    and self.pending_sequence_queue[0] == "fungus"
                ):
                    self.queued_transition_wait_until = (
                        time.perf_counter() + QUEUED_MENMA_TO_FUNGUS_DELAY_SEC
                    )
                    self.pre_home_release_step = "queued_menma_to_fungus_wait"
                    return True
                self.pre_home_release_step = None
                self.pre_home_release_wait_start = None
                self.pre_home_release_source = None
                self.home_open_reach.reset()
                if self.start_next_queued_sequence(
                    reason=f"grid_food_pre_home_to_home_waypoint_done:{done_source}"
                ):
                    return True
            return True

        if self.pre_home_release_step == "queued_menma_to_fungus_wait":
            home_cfg = manual_home_cfg()
            home_target = np.asarray(home_cfg["target_pos"], dtype=np.float32).reshape(3)
            home_look = np.asarray(home_cfg["look_pos"], dtype=np.float32).reshape(3)
            home_normal = np.asarray(home_cfg["normal_down"], dtype=np.float32).reshape(3)
            self.set_motion_target(
                home_target,
                home_look,
                home_normal,
                dt,
                fixed_quat=home_cfg.get("quat_xyzw"),
            )
            self.gripper_cmd = GRIPPER_OPEN
            if (
                self.queued_transition_wait_until is not None
                and time.perf_counter() >= self.queued_transition_wait_until
            ):
                done_source = self.pre_home_release_source
                self.pre_home_release_step = None
                self.pre_home_release_wait_start = None
                self.pre_home_release_source = None
                self.queued_transition_wait_until = None
                self.home_open_reach.reset()
                if self.start_next_queued_sequence(
                    reason=f"queued_menma_to_fungus_delay_done:{done_source}"
                ):
                    return True
            return True

        self.pre_home_release_step = None
        self.pre_home_release_wait_start = None
        self.pre_home_release_source = None
        return False

    def pose_locked(self):
        return bool(
            self.requested
            or self.grid_food_step is not None
            or self.pre_descend_step is not None
            or self.post_step is not None
            or self.pre_home_release_step is not None
            or (self.egg_inspect_only and self.target_locked is not None)
        )

    # 【蛋專用／目標鎖定】建立蛋盤、蛋與二次拍照的鎖定目標。

    def plate_normal_down(self):
        if egg_manual_enabled():
            return egg_manual_normal_down()
        if USE_PLATE_NORMAL:
            return orient_normal_to_negative_z(self.perception.normal_down)
        return np.array([0.0, 0.0, -1.0], dtype=np.float32)

    def egg_target_normal_down(self, back_has_egg=None):
        if back_has_egg is None:
            back_has_egg = self.perception.egg_back_has_egg
        if back_has_egg is False:
            return egg_no_back_normal_down()
        return self.plate_normal_down()

    def start_no_back_reobserve(self, selected_egg_pos, source, stable_stats=None):
        """移至無後方蛋拍照位並重新鎖定一次。"""
        self.no_back_reobserve_done = True
        self.no_back_reobserve_stabilize_until = None
        self.perception.set_egg_detection_gate(False)
        self.perception.clear_egg_measurements_for_new_lock()
        self.mode = "no_back_reobserve"
        self.target_locked = no_back_arm_target_for_isaac()
        self.target_normal_locked = egg_no_back_normal_down()
        self.target_source = "no_back_reobserve"
        self.requested = True
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        self.reach.reset()
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        self.set_gripper("open")
        print(
            "[TEST][NO_BACK] selected egg has no back egg; moving to dedicated "
            f"re-observe pose target={fmt_vec(self.target_locked)} "
            f"normal={fmt_vec(self.target_normal_locked)}."
        )

    def request_move(self, force_back_egg_photo_pose=False):
        if not self.perception.have_pose():
            print("[TEST] No /egg_plate/pose yet; keep tracking and press Q again.")
            return
        self.reset_post_flow()
        self.reach = ReachHold(hold_sec=EGG_PLATE_APPROACH_REACH_HOLD_SEC)
        self.no_back_reobserve_done = False
        self.no_back_reobserve_stabilize_until = None
        self.perception.set_egg_detection_gate(False)
        self.mode = "plate"
        self.waiting_for_egg_pose = False
        if egg_manual_enabled():
            if ENABLE_NO_BACK_CAMERA_POSE_FOR_FIRST_EGG_OBSERVATION and not force_back_egg_photo_pose:
                self.target_locked = no_back_arm_target_for_isaac()
                self.target_normal_locked = egg_no_back_normal_down()
                self.no_back_reobserve_done = True
                normal_mode = "no-back camera normal (first observation)"
                target_mode = f"{egg_manual_target_mode_text()} / no-back first observation"
            else:
                self.target_locked = manual_arm_target_for_isaac()
                self.target_normal_locked = self.plate_normal_down()
                normal_mode = (
                    "back-egg standard plate normal (after ungraspable sweep)"
                    if force_back_egg_photo_pose else "manual arm normal"
                )
                target_mode = (
                    f"{egg_manual_target_mode_text()} / back-egg photo pose"
                    if force_back_egg_photo_pose else egg_manual_target_mode_text()
                )
        else:
            self.target_locked = self.perception.latest_pos.copy()
            if USE_PLATE_NORMAL:
                self.target_normal_locked = orient_normal_to_negative_z(self.perception.normal_down)
                normal_mode = "locked plate normal"
            else:
                self.target_normal_locked = np.array([0.0, 0.0, -1.0], dtype=np.float32)
                normal_mode = "fixed vertical normal"
            target_mode = "vision"
        self.target_yaw_locked = None
        self.target_yaw_raw_locked = None
        self.target_yaw_axis_width_mm_locked = None
        self.target_yaw_axis_center_to_endpoint_max_mm_locked = None
        self.target_yaw_axis_base_x_err_deg_locked = None
        self.target_side_edge_fallback_locked = False
        self.target_side_edge_fallback_side_locked = None
        self.egg_wrist_offset = 0.0
        self.current_spin_offset = 0.0
        self.egg_descend_dz_locked = EGG_DESCEND_DZ
        self.egg_descend_source_locked = "fallback_default"
        self.egg_h_tip_locked = None
        self.egg_h_tip_descend_dz_locked = None
        self.target_source = "plate"
        self.reach.reset()
        self.requested = True
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        print(
            f"[TEST] Locked manual arm approach: {fmt_vec(self.target_locked)} "
            f"normal={fmt_vec(self.target_normal_locked)} ({normal_mode}, {target_mode})"
        )

    def request_egg_move(self):
        if self.mode == "egg" and self.egg_inspect_only and self.target_locked is not None:
            self.reset_post_flow()
            self.egg_inspect_only = False
            self.egg_descend_requested = False
            self.requested = True
            self.waiting_for_egg_pose = False
            self.reach = ReachHold(hold_sec=EGG_APPROACH_REACH_HOLD_SEC)
            self.done_logged = False
            self.last_orient_err_deg = float("inf")
            print(
                f"[TEST] Confirmed egg target: {fmt_vec(self.target_locked)} "
                f"normal={fmt_vec(self.target_normal_locked)} yaw={self.target_yaw_locked} "
                f"({self.target_source}); moving arm."
            )
            return

        self.reset_post_flow()
        self.perception.clear_egg_measurements_for_new_lock()
        self.perception.set_egg_detection_gate(True)
        egg_pos, source = self.perception.best_egg_pos()
        if PREFER_ACCURATE_EGG_LOCK and self.perception.egg_accurate_pos is None:
            self.perception.mark_waiting_for_accurate()
            self.waiting_for_egg_pose = True
            self.requested = False
            self.mode = "egg"
            self.egg_inspect_only = True
            self.target_locked = egg_pos.copy() if egg_pos is not None else None
            self.target_normal_locked = None
            self.target_yaw_locked = None
            self.target_yaw_raw_locked = None
            self.target_yaw_axis_width_mm_locked = None
            self.target_yaw_axis_name_locked = None
            self.target_yaw_axis_center_to_endpoint_max_mm_locked = None
            self.target_yaw_axis_base_x_err_deg_locked = None
            self.target_back_has_egg_locked = None
            self.target_side_edge_fallback_locked = False
            self.target_side_edge_fallback_side_locked = None
            self.egg_wrist_offset = 0.0
            self.current_spin_offset = 0.0
            self.egg_descend_dz_locked = EGG_DESCEND_DZ
            self.egg_descend_source_locked = "fallback_default"
            self.egg_h_tip_locked = None
            self.egg_h_tip_descend_dz_locked = None
            self.target_source = source if egg_pos is not None else "none"
            print(
                "[TEST] Waiting for /egg_face_up/accurate_pose before locking egg "
                f"(current={source})."
            )
            return

        if egg_pos is None:
            self.waiting_for_egg_pose = True
            self.requested = False
            self.mode = "egg"
            self.egg_inspect_only = True
            self.target_locked = None
            self.target_normal_locked = None
            self.target_yaw_locked = None
            self.target_yaw_raw_locked = None
            self.target_yaw_axis_width_mm_locked = None
            self.target_yaw_axis_name_locked = None
            self.target_yaw_axis_center_to_endpoint_max_mm_locked = None
            self.target_yaw_axis_base_x_err_deg_locked = None
            self.target_back_has_egg_locked = None
            self.target_side_edge_fallback_locked = False
            self.target_side_edge_fallback_side_locked = None
            self.egg_wrist_offset = 0.0
            self.current_spin_offset = 0.0
            self.egg_descend_dz_locked = EGG_DESCEND_DZ
            self.egg_descend_source_locked = "fallback_default"
            self.egg_h_tip_locked = None
            self.egg_h_tip_descend_dz_locked = None
            self.target_source = "none"
            print("[TEST] No egg pose yet; enabled D405 egg gate, waiting to inspect.")
            return

        self.mode = "egg"
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = True
        self.egg_descend_requested = False
        self.target_locked = egg_pos.copy()
        self.target_back_has_egg_locked = self.perception.egg_back_has_egg
        self.target_side_edge_fallback_locked = self.current_bowl_status_is_side_edge_fallback()
        self.target_side_edge_fallback_side_locked = self.current_bowl_status_selected_side_edge()
        self.target_normal_locked = (
            egg_non_sweepable_ungraspable_normal_down()
            if self.target_side_edge_fallback_locked
            else self.egg_target_normal_down(self.target_back_has_egg_locked)
        )
        self.target_yaw_raw_locked = self.perception.egg_yaw_deg
        self.lock_yaw_axis_width_mm()
        self.lock_yaw_other_axis_width_mm()
        self.target_yaw_axis_name_locked = self.perception.egg_yaw_axis_name
        self.target_yaw_locked = egg_tool_pose_yaw_deg(
            self.target_yaw_raw_locked, self.target_yaw_axis_name_locked
        )
        self.lock_yaw_axis_center_to_endpoint_max_mm()
        self.target_yaw_axis_base_x_err_deg_locked = self.perception.egg_yaw_axis_base_x_err_deg
        self.apply_base_x_parallel_approach_yaw()
        self.reset_egg_spin_from_current_pose()
        self.egg_descend_dz_locked, self.egg_descend_source_locked = self.lock_egg_descend_dz()
        self.target_source = source
        self.requested = False
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        print(
            f"[TEST] Locked egg target: {fmt_vec(self.target_locked)} "
            f"normal={fmt_vec(self.target_normal_locked)} yaw_raw={self.target_yaw_raw_locked} "
            f"yaw={self.target_yaw_locked} "
            f"yaw_axis={self.target_yaw_axis_name_locked} "
            f"back_has_egg={self.perception.egg_back_has_egg} "
            f"gripper_width={self.gripper_close_width_mm():.1f}mm "
            f"descend_source={self.egg_descend_source_locked} "
            f"({source}); arm holds. Press E again to move."
        )

    def initialize_egg_descend_cartesian_path(self, final_pos):
        """只在接觸前的最後下降段使用 waypoint。"""
        start_pos, _start_look, _start_normal = self.target_from_egg(
            self.target_locked,
            normal_down=self.target_normal_locked,
            offset=self.egg_approach_offset(),
            y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
        )
        start_pos = np.asarray(start_pos, dtype=np.float32)
        final_pos = np.asarray(final_pos, dtype=np.float32)
        full_delta = final_pos - start_pos
        full_distance = float(np.linalg.norm(full_delta))
        direction = normalize_vec(full_delta, default=np.array([0.0, 0.0, -1.0], dtype=np.float32))
        segment_distance = min(float(EGG_DESCEND_CARTESIAN_SEGMENT_NEAR_FINAL_M), full_distance)
        # 先到一般接近點，再分段移至原夾取終點。
        segment_start = final_pos - direction * segment_distance
        count = max(1, int(math.ceil(segment_distance / float(EGG_DESCEND_CARTESIAN_WAYPOINT_STEP_M))))
        self.egg_descend_path_start_pos = segment_start.astype(np.float32)
        self.egg_descend_path_final_pos = final_pos
        self.egg_descend_path_pre_segment_pos = segment_start.astype(np.float32)
        self.egg_descend_path_pre_segment_reached = False
        self.egg_descend_path_pre_segment_reach.reset()
        self.egg_descend_path_index = 1
        self.egg_descend_path_count = count
        self.egg_descend_path_complete = False
        print(
            f"[TEST][FLOW] Egg descend: direct to final-{segment_distance * 1000.0:.1f} mm, "
            f"then {count} x {EGG_DESCEND_CARTESIAN_WAYPOINT_STEP_M * 1000.0:.1f} mm waypoints."
        )

    def egg_descend_path_target(self):
        if not self.egg_descend_path_pre_segment_reached:
            return self.egg_descend_path_pre_segment_pos
        return self.egg_descend_cartesian_waypoint()

    def egg_descend_cartesian_waypoint(self):
        if self.egg_descend_path_start_pos is None or self.egg_descend_path_final_pos is None:
            return None
        count = max(1, int(self.egg_descend_path_count))
        fraction = min(float(self.egg_descend_path_index) / float(count), 1.0)
        return (
            self.egg_descend_path_start_pos
            + fraction * (self.egg_descend_path_final_pos - self.egg_descend_path_start_pos)
        ).astype(np.float32)

    def advance_egg_descend_cartesian_path(self, ee_pos):
        """Isaac TCP 接近目前 waypoint 後才前進。"""
        if not self.egg_descend_path_pre_segment_reached:
            pre_segment = self.egg_descend_path_pre_segment_pos
            if pre_segment is None:
                return True
            if not self.egg_descend_path_pre_segment_reach.update(pre_segment, ee_pos):
                return False
            self.egg_descend_path_pre_segment_reached = True
            return False
        waypoint = self.egg_descend_cartesian_waypoint()
        if waypoint is None:
            return True
        err_m = float(np.linalg.norm(np.asarray(ee_pos, dtype=np.float32) - waypoint))
        if err_m > float(EGG_DESCEND_CARTESIAN_WAYPOINT_REACH_TOL_M):
            return False
        if self.egg_descend_path_index >= self.egg_descend_path_count:
            self.egg_descend_path_complete = True
            return True
        self.egg_descend_path_index += 1
        return False

    def request_egg_descend(self):
        if self.mode != "egg" or self.target_locked is None:
            print("[TEST] No locked egg target; press E first to inspect/lock the egg.")
            return
        if self.egg_inspect_only:
            print("[TEST] Egg is inspect-only now; press E again to move to approach before D descend.")
            return

        self.egg_descend_requested = True
        self.requested = True
        self.waiting_for_egg_pose = False
        # 分段起點與終點都需穩定 0.2 秒。
        self.reach = ReachHold(hold_sec=EGG_DESCEND_REACH_HOLD_SEC)
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        # 側邊備援下降須保持固定法向量。
        if self.last_target_quat is not None:
            self.egg_descend_quat_locked = np.asarray(self.last_target_quat, dtype=np.float64).copy()
            self.egg_descend_quat_rmp_locked = quat_xyzw_to_wxyz(self.egg_descend_quat_locked)
        else:
            self.egg_descend_quat_locked = None
            self.egg_descend_quat_rmp_locked = None
        descend_pos, look_pos, normal_down = self.target_from_egg(
            self.target_locked,
            normal_down=self.target_normal_locked,
            offset=self.egg_descend_offset(),
            y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
        )
        self.initialize_egg_descend_cartesian_path(descend_pos)
        print(
            f"[TEST] Egg descend requested: target={fmt_vec(self.target_locked)} "
            f"normal={fmt_vec(self.target_normal_locked)} yaw={self.target_yaw_locked} "
            f"descend_dz={self.egg_descend_dz_locked:.3f} m "
            f"descend_source={self.egg_descend_source_locked} "
            f"h_tip={self.format_locked_h_tip()} "
            f"h_tip_descend_dz={self.format_locked_h_tip_descend_dz()} "
            f"y_backoff={self.egg_pre_descend_y_backoff_m_locked:.3f} m "
            f"remaining_offset={self.egg_descend_offset():.3f} m ({self.target_source})."
        )
        print(
            "[TEST] Egg descend orientation locked: "
            f"{fmt_arr(self.egg_descend_quat_locked)}"
        )
        print(
            f"[TEST] Egg descend target_pos={fmt_vec(descend_pos)} "
            f"look={fmt_vec(look_pos)} dir={fmt_vec(normal_down)}"
        )

    def cancel(self):
        if self.grid_food_type_locked in GRID_FOOD_PROFILES:
            self.perception.set_grid_food_height_sampling(self.grid_food_type_locked, False)
        self.auto_run = False
        self.reset_post_flow(open_gripper=True)
        self.requested = False
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        self.mode = None
        self.target_locked = None
        self.target_normal_locked = None
        self.target_yaw_locked = None
        self.target_yaw_raw_locked = None
        self.target_yaw_axis_width_mm_locked = None
        self.target_yaw_axis_name_locked = None
        self.target_yaw_axis_center_to_endpoint_max_mm_locked = None
        self.target_yaw_axis_base_x_err_deg_locked = None
        self.target_back_has_egg_locked = None
        self.target_side_edge_fallback_locked = False
        self.target_side_edge_fallback_side_locked = None
        self.egg_wrist_offset = 0.0
        self.current_spin_offset = 0.0
        self.egg_descend_dz_locked = EGG_DESCEND_DZ
        self.egg_descend_source_locked = "fallback_default"
        self.egg_h_tip_locked = None
        self.egg_h_tip_descend_dz_locked = None
        self.target_source = "none"
        self.grid_food_type_locked = None
        self.grid_food_cell_locked = None
        self.grid_food_cell_size_xy_mm_locked = None
        self.grid_food_base_y_shift_m_locked = 0.0
        self.grid_food_step = None
        self.grid_food_wait_start = None
        self.pending_sequence_queue.clear()
        self.queued_sequence_active = False
        self.queued_transition_wait_until = None
        self.no_back_reobserve_done = False
        self.no_back_reobserve_stabilize_until = None
        self.pre_home_release_step = None
        self.pre_home_release_wait_start = None
        self.pre_home_release_source = None
        self.reach = ReachHold()
        self.reach.reset()
        self.plate_mask_stabilize_until = None
        self.perception.set_egg_detection_gate(False)
        print("[TEST] Canceled move request; returning home target.")

    # 【筍乾／木耳專用／目標與姿態】計算選中格、接近、下降、抬升與退回姿態。
    def grid_food_gripper_close_width_mm(self):
        return float(grid_food_cfg(self.grid_food_type_locked)["gripper_close_width_mm"])

    def target_from_grid_food(self, cell=None, offset=None):
        if cell is None:
            cell = self.grid_food_cell_locked
        if cell is None:
            base = np.asarray(self.target_locked, dtype=np.float32).reshape(3)
        else:
            base = np.asarray(cell["center_base_m"], dtype=np.float32).reshape(3)
        cfg = grid_food_cfg(self.grid_food_type_locked)
        normal_down = orient_normal_to_negative_z(
            self.target_normal_locked
            if self.target_normal_locked is not None
            else cfg["manual_normal_down"]
        )
        base = base.copy()
        base[1] += float(self.grid_food_base_y_shift_m_locked)
        if offset is None:
            offset = cfg["target_normal_offset_m"]
        target_pos = base - normal_down * float(offset)
        look_pos = base + normal_down * 0.10
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down

    def target_from_grid_food_home_lift(self, offset=None, fraction=1.0):
        base_target, _base_look, _base_normal = self.target_from_grid_food(offset=0.0)
        descend_target, _descend_look, _descend_normal = self.target_from_grid_food(
            offset=self.grid_food_descend_offset_m()
        )
        normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        if offset is None:
            offset = self.grid_food_lift_offset_m()
        target_pos = descend_target.copy()
        final_z = float(base_target[2]) + float(offset)
        target_pos[2] += (final_z - float(target_pos[2])) * float(fraction)
        look_pos = target_pos + normal_down * float(HOME_LOOK_DZ)
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down

    def grid_food_post_lift_tool_y_sequence_deg(self):
        return grid_food_cfg(self.grid_food_type_locked)["post_lift_tool_y_sequence_deg"]

    def grid_food_post_lift_base_x_retract_m(self):
        """取得目前格子抬升後的 base -X 退離量。"""
        cfg = grid_food_cfg(self.grid_food_type_locked)
        cell_id = None
        if isinstance(self.grid_food_cell_locked, dict):
            try:
                cell_id = int(self.grid_food_cell_locked.get("cell_id"))
            except Exception:
                cell_id = None
        # 十八宮格最後一列通常是第 16～18 格。
        last_row_ids = {int(cid) for cid in cfg["cell_order"][-3:]}
        if cell_id in last_row_ids:
            return float(cfg["post_lift_last_row_base_x_retract_m"])
        return float(cfg["post_lift_base_x_retract_m"])

    def grid_food_post_lift_fixed_quat(self, tool_y_deg=None):
        """在抬升姿態套用一次工具 +Y 旋轉。"""
        if tool_y_deg is None:
            tool_y_deg = self.grid_food_post_lift_tool_y_sequence_deg()[-1]
        base_R = quat_xyzw_to_matrix(fixed_downward_base_x_quat())
        local_R = rotation_matrix_axis_angle(
            [0.0, 1.0, 0.0], np.deg2rad(float(tool_y_deg))
        )
        return quat_from_matrix(base_R @ local_R)

    def target_from_grid_food_post_lift(self, tool_y_deg=None):
        # 旋轉時保持抬升後的 base -X 位置。
        target_pos, _look_pos, _normal_down, _fixed_quat = self.target_from_grid_food_post_lift_move()
        quat = self.grid_food_post_lift_fixed_quat(tool_y_deg=tool_y_deg)
        normal_down = quat_xyzw_to_matrix(quat)[:, 2].astype(np.float32)
        look_pos = target_pos + normal_down * 0.10
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down, quat

    def target_from_grid_food_post_lift_move(self):
        """從一般抬升點沿 base -X 移動。"""
        target_pos, _look_pos, _normal_down = self.target_from_grid_food_home_lift(
            offset=self.grid_food_lift_offset_m()
        )
        retract_m = self.grid_food_post_lift_base_x_retract_m()
        target_pos = np.asarray(target_pos, dtype=np.float32).copy()
        target_pos[0] -= retract_m
        quat = fixed_downward_base_x_quat()
        normal_down = quat_xyzw_to_matrix(quat)[:, 2].astype(np.float32)
        look_pos = target_pos + normal_down * 0.10
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down, quat

    def target_from_grid_food_post_lift_tool_z_raise(self):
        """保持姿態並沿工具 -Z 抬升 50 mm。"""
        lift_pos, _lift_look, _lift_normal = self.target_from_grid_food_home_lift(
            offset=self.grid_food_lift_offset_m()
        )
        quat = fixed_downward_base_x_quat()
        tool_z = normalize_vec(quat_xyzw_to_matrix(quat)[:, 2], default=np.array([0.0, 0.0, -1.0]))
        raise_m = float(grid_food_cfg(self.grid_food_type_locked)["post_lift_tool_z_raise_m"])
        # 此流程工具 +Z 為下降方向，因此 -Z 是抬升。
        target_pos = lift_pos - tool_z * raise_m
        normal_down = tool_z.astype(np.float32)
        look_pos = target_pos + normal_down * 0.10
        return target_pos.astype(np.float32), look_pos.astype(np.float32), normal_down, quat, raise_m

    def _command_grid_food_pose(self, pose, ee_pos, dt, reach=None, require_orientation=False):
        target_pos, look_pos, normal_down, fixed_quat = pose[:4]
        self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=fixed_quat)
        self.gripper_cmd = GRIPPER_CLOSE
        reached = (self.reach if reach is None else reach).update(target_pos, ee_pos)
        return reached and (not require_orientation or self.last_orient_err_deg <= ORIENT_REACH_TOL_DEG)

    def grid_food_approach_offset_m(self):
        cfg = grid_food_cfg(self.grid_food_type_locked)
        return float(cfg["target_normal_offset_m"]) + float(cfg["approach_offset_m"])

    def grid_food_descend_offset_m(self):
        cfg = grid_food_cfg(self.grid_food_type_locked)
        approach_offset = float(cfg["target_normal_offset_m"]) + float(cfg["approach_offset_m"])
        return max(0.0, approach_offset - float(cfg["descend_dz_m"]))

    def grid_food_lift_offset_m(self):
        cfg = grid_food_cfg(self.grid_food_type_locked)
        return float(cfg["target_normal_offset_m"]) + float(cfg["lift_offset_m"])

    def grid_food_real_tcp_descend_confirmed(self, target_isaac_pos):
        """確認真實 TCP 穩定抵達格子食材下降點。"""
        rtde_receive = globals().get("_rtde_r")
        now = time.perf_counter()
        target_rtde = isaac_pos_to_rtde_tcp_est(target_isaac_pos)
        status = {
            "target_rtde_tcp_m": target_rtde,
            "tol_m": float(GRID_FOOD_DESCEND_REAL_TCP_TOL_M),
            "stable_sec_required": float(GRID_FOOD_DESCEND_REAL_TCP_STABLE_SEC),
        }
        if rtde_receive is None:
            self.grid_food_descend_real_tcp_in_tol_since = None
            status.update(reason="rtde_tcp_unavailable_sim_fallback", confirmed=True)
            return True, status
        try:
            actual_pose = rtde_receive.getActualTCPPose()
        except Exception as exc:
            self.grid_food_descend_real_tcp_in_tol_since = None
            status.update(reason="rtde_tcp_read_failed", error=str(exc), confirmed=False)
            return False, status
        if actual_pose is None or len(actual_pose) < 3:
            self.grid_food_descend_real_tcp_in_tol_since = None
            status.update(reason="rtde_tcp_invalid", actual_rtde_tcp_m=actual_pose, confirmed=False)
            return False, status

        actual_rtde = np.asarray(actual_pose[:3], dtype=np.float64)
        error = actual_rtde - np.asarray(target_rtde, dtype=np.float64)
        error_norm_m = float(np.linalg.norm(error))
        within = error_norm_m <= float(GRID_FOOD_DESCEND_REAL_TCP_TOL_M)
        if within:
            if self.grid_food_descend_real_tcp_in_tol_since is None:
                self.grid_food_descend_real_tcp_in_tol_since = now
            stable_sec = now - self.grid_food_descend_real_tcp_in_tol_since
        else:
            self.grid_food_descend_real_tcp_in_tol_since = None
            stable_sec = 0.0
        confirmed = bool(within and stable_sec >= float(GRID_FOOD_DESCEND_REAL_TCP_STABLE_SEC))
        status.update(
            reason="confirmed" if confirmed else "stabilizing" if within else "outside_tol",
            confirmed=confirmed,
            actual_rtde_tcp_m=actual_rtde,
            error_rtde_tcp_m=error,
            error_rtde_tcp_mm=error * 1000.0,
            error_norm_mm=error_norm_m * 1000.0,
            stable_sec=stable_sec,
        )
        return confirmed, status

    # 【筍乾／木耳專用／夾取準備】設定固定姿態、夾爪與真實 TCP 到位判斷。
    def grid_food_fixed_quat(self, phase="manual"):
        cfg = grid_food_cfg(self.grid_food_type_locked)
        if phase == "observe":
            return fixed_quat_from_tool_axes(
                cfg["observe_normal_down"],
                x_axis=cfg.get("observe_x_axis"),
                y_axis=cfg.get("observe_y_axis"),
            )
        return fixed_quat_from_tool_axes(
            self.target_normal_locked if self.target_normal_locked is not None else cfg["manual_normal_down"],
            x_axis=cfg.get("manual_x_axis"),
            y_axis=cfg.get("manual_y_axis"),
        )

    def start_grid_food_grip_flow(self):
        self.grid_food_step = "gripper_close"
        self.grid_food_wait_start = time.perf_counter()
        self.post_reach.reset()
        width_mm = self.grid_food_gripper_close_width_mm()
        self.send_gripper_width_mm(width_mm, event_name="grid_food_gripper_width_cmd")
        print(
            f"[TEST][GRID_FOOD][{self.grid_food_type_locked}] target reached; "
            f"close gripper to {width_mm:.1f} mm."
        )

    # 【筍乾／木耳專用／動作 1：拍照選格】移動到拍照姿態並鎖定十八宮格結果。
    def _update_grid_food_observe_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "observe_move":
            target_pos = grid_food_manual_target_for_isaac(food) if egg_manual_enabled() else np.array(
                [HOME_XY[0], HOME_XY[1], HOME_Z],
                dtype=np.float32,
            )
            normal_down = cfg["observe_normal_down"]
            look_pos = target_pos + normal_down * 0.10
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.grid_food_fixed_quat("observe"),
            )
            if self.reach.update(target_pos, ee_pos):
                self.grid_food_step = "observe_wait"
                self.grid_food_wait_start = time.perf_counter()
                self.reach.reset()
                self.perception.set_grid_food_height_sampling(food, True)
                print(f"[TEST][GRID_FOOD][{food}] observe pose reached; waiting stable occupied cell.")
            return True

        if self.grid_food_step == "observe_wait":
            cell, _ = self.perception.stable_grid_food_candidate(food)
            if cell is None:
                if self.perception.grid_food_all_cells_rejected.get(food, False):
                    rejected_ids = sorted(
                        set(self.perception.grid_food_cell_center_distance_logged.get(food, set()))
                        | set(self.perception.grid_food_permanent_empty_ids.get(food, set()))
                    )
                    print(
                        f"[TEST][GRID_FOOD][{food}] all observed cells are excluded or confirmed empty; "
                        f"returning home. excluded_cells={rejected_ids}"
                    )
                    self.grid_food_step = None
                    self.grid_food_wait_start = None
                    self.grid_food_cell_locked = None
                    self.grid_food_cell_size_xy_mm_locked = None
                    self.perception.set_grid_food_height_sampling(food, False)
                    self.requested = False
                    self.mode = None
                    self.reach = ReachHold()
                    self.done_logged = False
                    self.gripper_cmd = GRIPPER_OPEN
                    if self.grid_food_capture_only and self.as_capture_active:
                        self.grid_food_capture_only = False
                        self.as_capture_active = False
                        self.as_capture_queue.clear()
                        self.as_capture_ready = False
                        self.as_capture_egg_ready = False
                        self.as_grid_snapshots.clear()
                        print(f"[TEST][A/S] A capture canceled: no usable {food} cell.")
                        return True
                    if self.start_next_queued_sequence(reason=f"grid_food_all_cells_rejected:{food}"):
                        return True
                    return True
                target_pos = grid_food_manual_target_for_isaac(food) if egg_manual_enabled() else np.array(
                    [HOME_XY[0], HOME_XY[1], HOME_Z],
                    dtype=np.float32,
                )
                normal_down = cfg["observe_normal_down"]
                self.set_motion_target(
                    target_pos,
                    target_pos + normal_down * 0.10,
                    normal_down,
                    dt,
                    fixed_quat=self.grid_food_fixed_quat("observe"),
                )
                return True
            size_xy_mm = cell.get("size_xy_mm")
            if size_xy_mm is not None:
                self.grid_food_cell_size_xy_mm_locked = [float(x) for x in size_xy_mm]
            else:
                self.grid_food_cell_size_xy_mm_locked = None
            cell = dict(cell)
            target_center = np.asarray(cell["center_base_m"], dtype=np.float32).reshape(3).copy()
            self.grid_food_cell_locked = cell
            self.target_locked = target_center
            self.target_normal_locked = cfg["manual_normal_down"]
            self.target_source = f"{food}_cell_{int(cell.get('cell_id', -1))}"
            self.grid_food_step = "approach"
            self.perception.set_grid_food_height_sampling(food, False)
            self.reach.reset()
            self.done_logged = False
            print(
                f"[TEST][GRID_FOOD][{food}] locked cell id={cell.get('cell_id')} "
                f"name={cell.get('cell_name')} center={fmt_vec(self.target_locked)} "
                f"size_xy_mm={self.grid_food_cell_size_xy_mm_locked}"
            )
            if self.grid_food_capture_only and self.as_capture_active:
                # A 只鎖定格子，S 才移至格子上方。
                self.as_grid_snapshots[food] = copy.deepcopy(self.grid_food_cell_locked)
                print(
                    f"[TEST][A/S] A locked {food} cell="
                    f"{self.grid_food_cell_locked.get('cell_id')} at photo pose; "
                    "S will move to approach."
                )
                self.grid_food_step = None
                self.grid_food_capture_only = False
                self.grid_food_wait_start = None
                self.requested = False
                self.mode = None
                self.reach.reset()
                self._start_next_as_capture()
            return True

        return False

    # 【筍乾／木耳專用／動作 2：接近】移動到食材上方並等待穩定。
    def _update_grid_food_approach_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "approach":
            target_pos, look_pos, normal_down = self.target_from_grid_food(
                offset=self.grid_food_approach_offset_m()
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=self.grid_food_fixed_quat())
            if self.reach.update(target_pos, ee_pos):
                self.grid_food_step = "approach_hold"
                self.grid_food_wait_start = time.perf_counter()
                self.reach.reset()
                settle_sec = grid_food_cfg(food)["approach_settle_sec"]
                print(
                    f"[TEST][GRID_FOOD][{food}] approach reached; hold "
                    f"{settle_sec:.1f}s."
                )
            return True

        if self.grid_food_step == "approach_hold":
            target_pos, look_pos, normal_down = self.target_from_grid_food(
                offset=self.grid_food_approach_offset_m()
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=self.grid_food_fixed_quat())
            approach_hold_width_mm = grid_food_cfg(food).get("gripper_approach_hold_width_mm")
            if approach_hold_width_mm is not None:
                self.send_gripper_width_mm(
                    float(approach_hold_width_mm),
                    event_name="grid_food_approach_hold_gripper_width_cmd",
                )
            elapsed = self.elapsed_since(self.grid_food_wait_start)
            if elapsed >= float(grid_food_cfg(food)["approach_settle_sec"]):
                self.grid_food_step = "descend"
                self.grid_food_wait_start = None
                self.reach.reset()
            return True

        return False

    # 【筍乾／木耳專用／動作 3：下降】下降並確認真實手臂 TCP 抵達目標。
    def _update_grid_food_descend_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "descend":
            target_pos, look_pos, normal_down = self.target_from_grid_food(
                offset=self.grid_food_descend_offset_m()
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=self.grid_food_fixed_quat())
            if self.reach.update(target_pos, ee_pos):
                real_tcp_confirmed, _ = self.grid_food_real_tcp_descend_confirmed(target_pos)
                if real_tcp_confirmed:
                    self.start_grid_food_grip_flow()
            return True

        return False

    # 【筍乾／木耳專用／動作 4：夾取】閉合夾爪並啟動格子清空確認。
    def _update_grid_food_grasp_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "gripper_close":
            target_pos, look_pos, normal_down = self.target_from_grid_food(
                offset=self.grid_food_descend_offset_m()
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=self.grid_food_fixed_quat())
            elapsed = self.elapsed_since(self.grid_food_wait_start)
            if elapsed >= float(GRIPPER_WAIT_CLOSE_SEC):
                # 關爪等待完成後，才允許下次照片確認此格永久為空。
                cell_id = None
                if self.grid_food_cell_locked is not None:
                    cell_id = self.grid_food_cell_locked.get("cell_id")
                self.perception.request_grid_food_empty_confirmation_after_grasp(food, cell_id)
                self.grid_food_step = "lift_keep_pose"
                self.grid_food_wait_start = None
                self.reach.reset()
                print(f"[TEST][GRID_FOOD][{food}] gripper closed; lift 1/3 along base +Z with grasp pose.")
            return True

        return False

    # 【筍乾／木耳專用／動作 5：抬升】保持夾取姿態分段抬升並對正工具。
    def _update_grid_food_lift_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "lift_keep_pose":
            target_pos, look_pos, normal_down = self.target_from_grid_food_home_lift(
                offset=self.grid_food_lift_offset_m(),
                fraction=1.0 / 3.0,
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=self.grid_food_fixed_quat())
            self.gripper_cmd = GRIPPER_CLOSE
            if self.reach.update(target_pos, ee_pos):
                self.grid_food_step = "lift"
                self.grid_food_wait_start = None
                self.reach.reset()
                print(
                    f"[TEST][GRID_FOOD][{food}] lift 1/3 reached; "
                    "align tool Z to base -Z, tool X to base +X, then lift remaining distance."
                )
            return True

        if self.grid_food_step == "lift":
            target_pos, look_pos, normal_down = self.target_from_grid_food_home_lift(
                offset=self.grid_food_lift_offset_m()
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt, fixed_quat=fixed_downward_base_x_quat())
            self.gripper_cmd = GRIPPER_CLOSE
            if self.reach.update(target_pos, ee_pos):
                self.reach.reset()
                if (
                    float(cfg["post_lift_tool_z_raise_m"]) > 0.0
                    and int(cfg["post_lift_tool_z_raise_cycles"]) > 0
                ):
                    self.grid_food_post_lift_tool_z_cycle_index = 0
                    self.grid_food_step = "lift_tool_z_raise"
                    print(
                        f"[TEST][GRID_FOOD][{food}] lifted; raise {float(cfg['post_lift_tool_z_raise_m']) * 1000.0:.0f} mm "
                        f"along tool -Z, return to lift, repeat {int(cfg['post_lift_tool_z_raise_cycles'])} cycles."
                    )
                else:
                    self.grid_food_step = "lift_post_move"
                    self.reach.reset()
                    print(
                        f"[TEST][GRID_FOOD][{food}] lifted; retreat "
                        f"{self.grid_food_post_lift_base_x_retract_m() * 1000.0:.0f} mm along base -X."
                    )
            return True

        return False

    # 【筍乾／木耳專用／動作 6：退回】執行後退、工具旋轉並交接放料流程。
    def _update_grid_food_post_lift_action(self, food, cfg, ee_pos, dt):
        if self.grid_food_step == "lift_post_move":
            pose = self.target_from_grid_food_post_lift_move()
            if self._command_grid_food_pose(pose, ee_pos, dt):
                self.reach.reset()
                self.grid_food_step = "lift_post_transform"
                self.grid_food_post_lift_rotation_index = 0
                sequence = self.grid_food_post_lift_tool_y_sequence_deg()
                print(
                    f"[TEST][GRID_FOOD][{food}] post-lift target reached; "
                    f"run tool +Y rotation sequence {[float(v) for v in sequence]} deg."
                )
            return True

        if self.grid_food_step == "lift_tool_z_raise":
            pose = self.target_from_grid_food_post_lift_tool_z_raise()
            if self._command_grid_food_pose(
                pose, ee_pos, GRID_FOOD_LIFT_TOOL_Z_POLICY_DT,
                reach=self.grid_food_post_lift_tool_z_reach,
            ):
                self.grid_food_step = "lift_tool_z_return"
                self.grid_food_post_lift_tool_z_reach.reset()
            return True

        if self.grid_food_step == "lift_tool_z_return":
            target_pos, look_pos, normal_down = self.target_from_grid_food_home_lift(
                offset=self.grid_food_lift_offset_m()
            )
            fixed_quat = fixed_downward_base_x_quat()
            if self._command_grid_food_pose(
                (target_pos, look_pos, normal_down, fixed_quat),
                ee_pos,
                GRID_FOOD_LIFT_TOOL_Z_POLICY_DT,
                reach=self.grid_food_post_lift_tool_z_reach,
            ):
                self.grid_food_post_lift_tool_z_reach.reset()
                self.grid_food_post_lift_tool_z_cycle_index += 1
                if self.grid_food_post_lift_tool_z_cycle_index < int(cfg["post_lift_tool_z_raise_cycles"]):
                    self.grid_food_step = "lift_tool_z_raise"
                    print(
                        f"[TEST][GRID_FOOD][{food}] lift-point return reached; start tool -Z raise "
                        f"cycle {int(self.grid_food_post_lift_tool_z_cycle_index) + 1}/"
                        f"{int(cfg['post_lift_tool_z_raise_cycles'])}."
                    )
                else:
                    self.grid_food_step = "lift_post_move"
                    self.reach.reset()
                    print(
                        f"[TEST][GRID_FOOD][{food}] returned to lift point after "
                        f"{int(self.grid_food_post_lift_tool_z_cycle_index)} cycles; retreat "
                        f"{self.grid_food_post_lift_base_x_retract_m() * 1000.0:.0f} mm along base -X."
                    )
            return True

        if self.grid_food_step == "lift_post_transform":
            sequence = self.grid_food_post_lift_tool_y_sequence_deg()
            step_index = int(np.clip(
                self.grid_food_post_lift_rotation_index, 0, len(sequence) - 1
            ))
            tool_y_deg = float(sequence[step_index])
            pose = self.target_from_grid_food_post_lift(tool_y_deg=tool_y_deg)
            if self._command_grid_food_pose(pose, ee_pos, dt, require_orientation=True):
                if step_index + 1 < len(sequence):
                    self.grid_food_post_lift_rotation_index = step_index + 1
                    self.reach.reset()
                    print(
                        f"[TEST][GRID_FOOD][{food}] tool +Y {tool_y_deg:.0f}deg reached; "
                        f"next {float(sequence[step_index + 1]):.0f}deg."
                    )
                    return True
                print(f"[TEST][GRID_FOOD][{food}] lift-after +Y reached; move to release pose before home.")
                self.grid_food_step = None
                self.grid_food_wait_start = None
                self.perception.set_grid_food_height_sampling(food, False)
                self.start_pre_home_release_flow(source=f"grid_food_{food}")
                self.requested = False
                self.mode = None
                self.reach = ReachHold()
                self.done_logged = False
            return True

        return False

    # 【筍乾／木耳專用／流程分派】依目前步驟呼叫對應動作處理函式。
    def update_grid_food_flow(self, ee_pos, dt):
        if self.grid_food_step is None:
            return False

        food = self.grid_food_type_locked
        cfg = grid_food_cfg(food)
        handlers = {
            "approach": self._update_grid_food_approach_action,
            "approach_hold": self._update_grid_food_approach_action,
            "descend": self._update_grid_food_descend_action,
            "gripper_close": self._update_grid_food_grasp_action,
            "lift": self._update_grid_food_lift_action,
            "lift_keep_pose": self._update_grid_food_lift_action,
            "lift_post_move": self._update_grid_food_post_lift_action,
            "lift_post_transform": self._update_grid_food_post_lift_action,
            "lift_tool_z_raise": self._update_grid_food_post_lift_action,
            "lift_tool_z_return": self._update_grid_food_post_lift_action,
            "observe_move": self._update_grid_food_observe_action,
            "observe_wait": self._update_grid_food_observe_action,
        }
        handler = handlers.get(self.grid_food_step)
        if handler is None:
            return False
        return handler(food, cfg, ee_pos, dt)

    # 【蛋專用／目標與姿態】計算蛋盤、蛋接近、下降深度及工具方向。

    def target_from_plate(self, plate_pos):
        if egg_manual_enabled():
            approach = np.asarray(plate_pos, dtype=np.float32).copy()
            normal_down = orient_normal_to_negative_z(
                self.target_normal_locked
                if self.target_normal_locked is not None
                else EGG_MANUAL_PROFILE.normal_down
            )
            # `look_pos` 只決定姿態，命令位置仍是接近點。
            look_pos = approach + normal_down * PLATE_APPROACH_OFFSET
            return approach.astype(np.float32), look_pos.astype(np.float32), normal_down
        else:
            base_point = plate_pos + np.array([EGG_CONTAINER_OFFSET_X, 0.0, 0.0], dtype=np.float32)
            if USE_PLATE_NORMAL:
                normal_down = orient_normal_to_negative_z(
                    self.target_normal_locked
                    if self.target_normal_locked is not None
                    else self.perception.normal_down
                )
            else:
                normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)

        approach = base_point - normal_down * PLATE_APPROACH_OFFSET
        return approach.astype(np.float32), base_point.astype(np.float32), normal_down

    def lock_egg_descend_dz(self):
        # 側邊不可撥蛋使用較淺下降，其餘蛋維持共用距離。
        if bool(self.target_side_edge_fallback_locked):
            descend_dz = float(NON_SWEEPABLE_UNGRASPABLE_DESCEND_DZ)
            descend_source = "non_sweepable_ungraspable_descend_dz"
        elif self.target_back_has_egg_locked is False:
            descend_dz = float(NO_BACK_EGG_DESCEND_DZ)
            descend_source = "no_back_egg_descend_dz"
        else:
            descend_dz = float(EGG_DESCEND_DZ)
            descend_source = "fixed_egg_descend_dz"
        h_tip = self.perception.egg_h_tip_latest
        self.egg_h_tip_locked = None if h_tip is None or not np.isfinite(h_tip) else float(h_tip)
        if self.egg_h_tip_locked is not None and self.egg_h_tip_locked > 0.0:
            self.egg_h_tip_descend_dz_locked = float(np.clip(self.egg_h_tip_locked, 0.0, descend_dz))
        else:
            self.egg_h_tip_descend_dz_locked = None
        print(
            f"[TEST][EGG] {descend_source}={descend_dz * 1000.0:.1f} mm "
            f"(h_tip_observed={self.format_locked_h_tip()}, "
            f"h_tip_descend_dz={self.format_locked_h_tip_descend_dz()})"
        )
        return descend_dz, descend_source

    def egg_descend_offset(self):
        return max(float(self.egg_approach_offset()) - float(self.egg_descend_dz_locked), 0.0)

    def egg_approach_offset(self):
        if self.target_back_has_egg_locked is False:
            offset = float(NO_BACK_EGG_APPROACH_OFFSET)
        else:
            offset = float(EGG_APPROACH_OFFSET)
        width = self.target_yaw_axis_width_mm_locked
        offset += egg_approach_narrow_width_add_m(width)
        return float(offset)

    def format_locked_h_tip(self):
        if self.egg_h_tip_locked is None:
            return "None"
        return f"{self.egg_h_tip_locked:.4f} m ({self.egg_h_tip_locked * 1000.0:.1f} mm)"

    def format_locked_h_tip_descend_dz(self):
        if self.egg_h_tip_descend_dz_locked is None:
            return "None"
        dz = self.egg_h_tip_descend_dz_locked
        return f"{dz:.4f} m ({dz * 1000.0:.1f} mm)"

    def egg_y_backoff_direction(self, normal_down):
        normal_down = orient_normal_to_negative_z(normal_down)
        _, y_axis, _ = self.egg_pose_axes_from_normal_yaw(normal_down, self.target_yaw_locked)
        y_axis = normalize_vec(y_axis, default=np.array([0.0, 1.0, 0.0], dtype=np.float32))
        base_x = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        base_x_proj = base_x - normal_down * float(np.dot(base_x, normal_down))
        y_axis_proj = y_axis - normal_down * float(np.dot(y_axis, normal_down))
        base_x_proj = normalize_vec(base_x_proj, default=None)
        y_axis_proj = normalize_vec(y_axis_proj, default=None)
        if base_x_proj is None or y_axis_proj is None:
            sign = 1.0 if float(y_axis[0]) >= 0.0 else -1.0
        else:
            plus_err = normal_angle_deg(y_axis_proj, base_x_proj)
            minus_err = normal_angle_deg(-y_axis_proj, base_x_proj)
            sign = 1.0 if plus_err <= minus_err else -1.0
        return (y_axis * sign).astype(np.float32), sign, y_axis

    def target_from_egg(self, egg_pos, normal_down=None, offset=None, y_backoff_m=0.0):
        if offset is None:
            offset = self.egg_approach_offset()
        if normal_down is not None:
            normal_down = orient_normal_to_negative_z(normal_down)
        elif USE_EGG_NORMAL:
            normal_down = orient_normal_to_negative_z(self.perception.egg_normal_down)
        elif egg_manual_enabled():
            normal_down = self.plate_normal_down()
        elif USE_PLATE_NORMAL:
            normal_down = orient_normal_to_negative_z(self.perception.normal_down)
        else:
            normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        egg_pos = np.asarray(egg_pos, dtype=np.float32).reshape(3)
        shift = np.zeros(3, dtype=np.float32)
        if y_backoff_m is not None and float(y_backoff_m) > 1e-6:
            y_dir, _sign, y_axis = self.egg_y_backoff_direction(normal_down)
            if abs(float(self.egg_pre_descend_y_backoff_sign_locked)) > 1e-6:
                y_dir = normalize_vec(
                    y_axis * float(self.egg_pre_descend_y_backoff_sign_locked),
                    default=y_dir,
                )
            shift = y_dir * float(y_backoff_m)
        look_pos = egg_pos + shift
        approach = look_pos - normal_down * float(offset)
        return approach.astype(np.float32), look_pos.astype(np.float32), normal_down

    def egg_pose_axes_from_normal_yaw(self, normal_down, yaw_deg):
        z_axis = orient_normal_to_negative_z(normal_down).astype(np.float32)
        yaw_rad = 0.0 if yaw_deg is None else float(np.deg2rad(yaw_deg))
        x0 = np.array([np.cos(yaw_rad), np.sin(yaw_rad), 0.0], dtype=np.float32)
        x_axis = x0 - z_axis * float(np.dot(x0, z_axis))
        x_axis = normalize_vec(x_axis, default=np.array([1.0, 0.0, 0.0], dtype=np.float32))
        y_axis = normalize_vec(np.cross(z_axis, x_axis), default=np.array([0.0, 1.0, 0.0], dtype=np.float32))
        x_axis = normalize_vec(np.cross(y_axis, z_axis), default=x_axis)
        return x_axis, y_axis, z_axis

    # 【蛋專用／方向對正】沿工具 Z 軸對正蛋的選中軸方向。

    def _spin_offset_target(self):
        if self.mode == "egg" and self.post_step in (
            None,
            "gripper_close",
            "egg_lift",
        ):
            return self.egg_wrist_offset
        return 0.0

    def _minimal_spin_to_locked_yaw_axis(self, quat):
        if self.mode != "egg" or self.target_yaw_locked is None:
            return self._spin_offset_target()
        normal_down = (
            self.last_normal_down
            if self.last_normal_down is not None
            else self.target_normal_locked
        )
        desired_x, _, spin_axis = self.egg_pose_axes_from_normal_yaw(
            normal_down,
            self.target_yaw_locked,
        )
        R = quat_xyzw_to_matrix(quat)
        current_x = normalize_vec(R[:, 0], default=np.array([1.0, 0.0, 0.0], dtype=np.float32))
        if (
            bool(self.target_side_edge_fallback_locked)
            and self.target_side_edge_fallback_side_locked in ("p1p4", "p2p3")
        ):
            return float(signed_angle_about_axis(current_x, desired_x, spin_axis))
        spin = signed_angle_to_parallel_axis(current_x, desired_x, spin_axis)
        return float(spin)

    def _apply_orientation_modifiers(self, quat_in, dt):
        q = np.asarray(quat_in, dtype=np.float64).reshape(4)
        if self.mode == "egg" and self.post_step in (None, "gripper_close", "egg_lift"):
            self.egg_wrist_offset = self._minimal_spin_to_locked_yaw_axis(q)
        spin_offset = self._update_spin_ramp(dt)
        if abs(spin_offset) > 1e-6:
            half = 0.5 * spin_offset
            spin_local_z = np.array([0.0, 0.0, np.sin(half), np.cos(half)], dtype=np.float64)
            q = quat_mul_xyzw(q, spin_local_z)
            q /= max(float(np.linalg.norm(q)), 1e-12)
        return q

    # 【共用功能／RMPflow】設定末端位置與姿態目標。
    def set_motion_target(self, target_pos, look_pos, normal_down, dt, apply_modifiers=True, fixed_quat=None):
        self.last_target_pos = np.asarray(target_pos, dtype=np.float32).copy()
        self.last_look_pos = np.asarray(look_pos, dtype=np.float32).copy()
        self.last_normal_down = orient_normal_to_negative_z(normal_down)

        if fixed_quat is not None:
            quat = np.asarray(fixed_quat, dtype=np.float64).reshape(4)
            self.last_camera_spin_180 = False
        else:
            quat = look_at_quat(
                self.last_target_pos,
                self.last_look_pos,
                world_up=WORLD_UP,
                tool_axis_local=TOOL_AXIS,
            )
            quat, self.last_camera_spin_180 = prefer_camera_forward_quat(quat)
            if apply_modifiers:
                quat = self._apply_orientation_modifiers(quat, dt)

        R_target = quat_xyzw_to_matrix(quat)
        self.last_target_quat = np.asarray(quat, dtype=np.float64).copy()
        self.last_target_quat_rmp_wxyz = quat_xyzw_to_wxyz(quat)
        self.last_target_axes = [R_target[:, i] for i in range(3)]

        self.rmpflow.set_end_effector_target(
            target_position=self.last_target_pos,
            target_orientation=self.last_target_quat_rmp_wxyz,
        )
        self.rmpflow.update_world()
        isaac_tool_z = self.last_isaac_axes_row[2] if self.last_isaac_axes_row is not None else None
        self.last_orient_err_deg = normal_angle_deg(isaac_tool_z, self.last_normal_down)
        return self.last_target_pos, self.last_look_pos, self.last_normal_down

    # 【共用功能／計時】計算目前狀態的經過時間。
    @staticmethod
    def elapsed_since(start_time):
        return 0.0 if start_time is None else max(0.0, time.perf_counter() - start_time)

    # 【蛋專用／下降準備】處理夾爪預縮、滑入路徑、姿態與拉麵碗目標。

    def target_from_ramen(self, stage_ref, xcache, offset=APPROACH_OFFSET):
        ramen_pos = get_world_pos(stage_ref, RAMEN_BOWL_PRIM_PATH, xcache)
        place_pos = ramen_pos + np.array(
            [EGG_RAMEN_OFFSET_X, EGG_RAMEN_OFFSET_Y, 0.0],
            dtype=np.float32,
        )
        normal_down = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        target_pos = place_pos - normal_down * float(offset)
        return target_pos.astype(np.float32), place_pos.astype(np.float32), normal_down

    def current_bowl_status_is_side_edge_fallback(self):
        """判斷是否選中側邊備援蛋。"""
        status = self.perception.egg_bowl_status
        if not isinstance(status, dict):
            return False
        return bool(
            status.get("state") == "only_non_sweepable_ungraspable"
            and int(status.get("ranked_count", 0)) == 0
            and int(status.get("side_edge_ungraspable_count", 0)) > 0
        )

    def current_bowl_status_selected_side_edge(self):
        status = self.perception.egg_bowl_status
        if not isinstance(status, dict):
            return None
        side = str(status.get("selected_side_edge") or "").lower()
        return side if side in ("p1p4", "p2p3") else None

    def use_back_egg_base_x_axis_slide(self):
        """判斷是否使用 target1 滑入蛋中心。"""
        if bool(self.target_side_edge_fallback_locked):
            return True
        axis_err_deg = self.target_yaw_axis_base_x_err_deg_locked
        return bool(
            axis_err_deg is not None
            and np.isfinite(axis_err_deg)
            and float(axis_err_deg) <= float(EGG_PRE_DESCEND_BASE_X_PARALLEL_TOL_DEG)
        )

    def nonselected_axis_camera_forward_yaw(self, camera_forward_ref_base=None):
        """取得非選中軸朝指定 base 方向的 yaw。"""
        yaw = egg_tool_pose_yaw_deg(
            self.target_yaw_raw_locked,
            self.target_yaw_axis_name_locked,
        )
        if yaw is None:
            return None
        candidates = (normalize_yaw_deg(float(yaw) + 90.0), normalize_yaw_deg(float(yaw) - 90.0))
        ref = normalize_vec(
            CAMERA_FORWARD_REF_BASE if camera_forward_ref_base is None else camera_forward_ref_base,
            default=np.array([1.0, 0.0, 0.0]),
        )
        scores = []
        for candidate_yaw in candidates:
            x_axis, _y_axis, _z_axis = self.egg_pose_axes_from_normal_yaw(
                self.target_normal_locked, candidate_yaw
            )
            scores.append(float(np.dot(x_axis, ref)))
        return float(candidates[int(np.argmax(scores))])

    def apply_base_x_parallel_approach_yaw(self):
        """離開拍照位前套用非選中軸姿態。"""
        if not self.use_back_egg_base_x_axis_slide():
            return False
        side = self.target_side_edge_fallback_side_locked
        side_camera_ref = {
            "p2p3": np.array([0.0, 1.0, 0.0], dtype=np.float32),
            "p1p4": np.array([0.0, -1.0, 0.0], dtype=np.float32),
        }.get(side)
        yaw = self.nonselected_axis_camera_forward_yaw(side_camera_ref)
        if yaw is None:
            return False
        if side_camera_ref is not None:
            tool_x, _tool_y, _tool_z = self.egg_pose_axes_from_normal_yaw(
                self.target_normal_locked, yaw
            )
            if float(np.dot(tool_x, side_camera_ref)) < 0.0:
                yaw = float(yaw) + 180.0
        self.target_yaw_locked = yaw
        return True

    def start_back_egg_base_x_axis_slide_flow(self):
        """執行 target1 下降與兩段滑入夾取。"""
        if self.target_locked is None:
            return False
        width_mm = self.target_yaw_axis_width_mm_locked
        if (
            width_mm is None
            or not np.isfinite(width_mm)
            or float(width_mm) <= 0.0
        ):
            print("[TEST][FLOW] Back-egg axis-slide unavailable; descend directly without old pre-close/backoff.")
            self.request_egg_descend()
            return False

        if self.last_target_quat is not None:
            self.egg_descend_quat_locked = np.asarray(self.last_target_quat, dtype=np.float64).copy()
        else:
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_approach_offset(),
            )
            self.egg_descend_quat_locked = look_at_quat(
                target_pos, look_pos, world_up=WORLD_UP, tool_axis_local=TOOL_AXIS
            )
            self.egg_descend_quat_locked, _ = prefer_camera_forward_quat(self.egg_descend_quat_locked)
        camera_spin_180 = False
        side_camera_ref = {
            "p2p3": np.array([0.0, 1.0, 0.0], dtype=np.float32),
            "p1p4": np.array([0.0, -1.0, 0.0], dtype=np.float32),
        }.get(self.target_side_edge_fallback_side_locked)
        if side_camera_ref is not None:
            current_tool_x = normalize_vec(
                quat_xyzw_to_matrix(self.egg_descend_quat_locked)[:, 0], default=None
            )
            if current_tool_x is not None and float(np.dot(current_tool_x, side_camera_ref)) < 0.0:
                spin_180 = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float64)
                self.egg_descend_quat_locked = quat_mul_xyzw(self.egg_descend_quat_locked, spin_180)
                self.egg_descend_quat_locked /= max(float(np.linalg.norm(self.egg_descend_quat_locked)), 1e-12)
                self.target_yaw_locked = float(self.target_yaw_locked) + 180.0
                camera_spin_180 = True
        self.egg_descend_quat_rmp_locked = quat_xyzw_to_wxyz(self.egg_descend_quat_locked)
        tool_x_dir = normalize_vec(
            quat_xyzw_to_matrix(self.egg_descend_quat_locked)[:, 0], default=None
        )
        if tool_x_dir is None:
            print("[TEST][FLOW] Back-egg tool +X slide unavailable; descend directly without old pre-close/backoff.")
            self.request_egg_descend()
            return False

        half_length_m = float(width_mm) * 0.0005
        target1 = np.asarray(self.target_locked, dtype=np.float32) + tool_x_dir * half_length_m
        self.back_egg_axis_target1_locked = target1.astype(np.float32)
        self.back_egg_axis_slide_dir_locked = (-tool_x_dir).astype(np.float32)
        self.back_egg_axis_half_length_m_locked = half_length_m
        self.egg_pre_descend_y_backoff_m_locked = 0.0
        self.egg_pre_descend_y_backoff_sign_locked = 0.0
        self.egg_descend_requested = False
        width_cmd_mm = self.pre_descend_other_axis_width_cmd_mm(
            EGG_BASE_X_AXIS_SLIDE_PRE_DESCEND_EXTRA_MM
        )
        pre_shrink_sent_at = self.consume_as_egg_pre_shrink(width_cmd_mm)
        if pre_shrink_sent_at is None:
            self.send_gripper_width_mm(
                width_cmd_mm,
                event_name="egg_back_axis_target1_pre_descend_gripper_width_cmd",
            )
        self.pre_descend_step = "back_axis_target1_pre_descend"
        self.pre_descend_wait_start = pre_shrink_sent_at or time.perf_counter()
        self.post_reach.reset()
        print(
            "[TEST][FLOW] Base-X-parallel target1: keep the locked non-selected-axis "
            "approach orientation, move to target1 pre-descend, "
            f"direct descend, then {BACK_EGG_BASE_X_PARALLEL_SLIDE_STAGES} x tool -X slide "
            f"({half_length_m * 1000.0:.1f}mm) into egg center."
        )
        return True

    def start_pre_descend_flow(self):
        if self.mode != "egg":
            return
        if self.pre_descend_step is not None or self.post_step is not None:
            return
        if self.use_back_egg_base_x_axis_slide():
            self.start_back_egg_base_x_axis_slide_flow()
            return
        self.start_pre_descend_axis_width_only(
            reason="axis_not_parallel_base_x",
            axis_err_deg=self.target_yaw_axis_base_x_err_deg_locked,
        )

    def pre_descend_axis_width_cmd_mm(self, extra_mm):
        width_mm = self.target_yaw_axis_width_mm_locked
        if width_mm is None or not np.isfinite(width_mm):
            return float(EGG_PRE_DESCEND_GRIPPER_WIDTH_MM)
        return float(width_mm) + float(extra_mm)

    def pre_descend_other_axis_width_cmd_mm(self, extra_mm):
        """以非選中軸計算預張開寬度。"""
        width_mm = self.target_yaw_other_axis_width_mm_locked
        if width_mm is None or not np.isfinite(width_mm):
            return float(EGG_PRE_DESCEND_GRIPPER_WIDTH_MM)
        return float(width_mm) + float(extra_mm)

    def prepare_as_egg_pre_shrink(self):
        """A 到達接近點後送出一次蛋預張開命令。"""
        if self.mode != "egg" or self.target_locked is None:
            return False
        if self.use_back_egg_base_x_axis_slide():
            width_cmd_mm = self.pre_descend_other_axis_width_cmd_mm(
                EGG_BASE_X_AXIS_SLIDE_PRE_DESCEND_EXTRA_MM
            )
            event_name = "as_egg_back_axis_target1_pre_shrink_gripper_cmd"
            route = "base_x_target1_slide"
        else:
            width_cmd_mm = self.pre_descend_axis_width_cmd_mm(
                EGG_NON_BASE_X_AXIS_PRE_DESCEND_EXTRA_MM
            )
            event_name = "as_egg_axis_width_pre_shrink_gripper_cmd"
            route = "normal_descend"
        self.send_gripper_width_mm(width_cmd_mm, event_name=event_name)
        self.as_egg_pre_shrink_width_mm = float(width_cmd_mm)
        self.as_egg_pre_shrink_sent_at = time.perf_counter()
        print(
            f"[TEST][A/S] A egg approach reached; pre-shrink sent "
            f"to {width_cmd_mm:.1f} mm. S will not resend it."
        )
        return True

    def consume_as_egg_pre_shrink(self, width_cmd_mm):
        """回傳 A 已送出預張開命令的時間。"""
        sent_width = self.as_egg_pre_shrink_width_mm
        sent_at = self.as_egg_pre_shrink_sent_at
        if (
            self.as_execute_active
            and sent_width is not None
            and sent_at is not None
            and abs(float(sent_width) - float(width_cmd_mm)) <= 0.1
        ):
            return float(sent_at)
        return None

    def start_pre_descend_axis_width_only(self, reason, axis_err_deg=None):
        width_cmd_mm = self.pre_descend_axis_width_cmd_mm(
            EGG_NON_BASE_X_AXIS_PRE_DESCEND_EXTRA_MM
        )
        self.egg_pre_descend_y_backoff_m_locked = 0.0
        self.egg_pre_descend_y_backoff_sign_locked = 0.0
        self.pre_descend_step = "gripper_minor_width_only"
        pre_shrink_sent_at = self.consume_as_egg_pre_shrink(width_cmd_mm)
        self.pre_descend_wait_start = pre_shrink_sent_at or time.perf_counter()
        self.post_reach.reset()
        if pre_shrink_sent_at is None:
            self.send_gripper_width_mm(
                width_cmd_mm,
                event_name="egg_pre_descend_minor_width_gripper_cmd",
            )
        print(
            "[TEST][FLOW] Egg approach reached; selected axis is not parallel to base-X. "
            "Keep the selected-axis approach orientation; "
            f"pre-close gripper to selected_axis_width+{EGG_NON_BASE_X_AXIS_PRE_DESCEND_EXTRA_MM:.1f}mm "
            f"= {width_cmd_mm:.1f}mm before descend "
            f"(reason={reason}, mask_axis_err={axis_err_deg})."
        )

    def update_pre_descend_flow(self, dt, ee_pos):
        if self.pre_descend_step is None or self.target_locked is None:
            return False

        if self.pre_descend_step == "back_axis_target1_pre_descend":
            target1 = self.back_egg_axis_target1_locked
            if target1 is None:
                self.pre_descend_step = None
                self.request_egg_descend()
                return True
            target_pos, look_pos, normal_down = self.target_from_egg(
                target1,
                normal_down=self.target_normal_locked,
                offset=self.egg_approach_offset(),
            )
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.post_reach.update(target_pos, ee_pos):
                self.pre_descend_step = "back_axis_target1_preclose"
                self.post_reach.reset()
            return True

        if self.pre_descend_step == "back_axis_target1_preclose":
            target1 = self.back_egg_axis_target1_locked
            if target1 is None:
                self.pre_descend_step = None
                self.request_egg_descend()
                return True
            target_pos, look_pos, normal_down = self.target_from_egg(
                target1,
                normal_down=self.target_normal_locked,
                offset=self.egg_approach_offset(),
            )
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.elapsed_since(self.pre_descend_wait_start) >= EGG_PRE_DESCEND_GRIPPER_WAIT_SEC:
                self.pre_descend_step = "back_axis_target1_descend"
                self.pre_descend_wait_start = None
                self.post_reach.reset()
            return True

        if self.pre_descend_step == "back_axis_target1_descend":
            target1 = self.back_egg_axis_target1_locked
            if target1 is None:
                self.pre_descend_step = None
                self.request_egg_descend()
                return True
            target_pos, look_pos, normal_down = self.target_from_egg(
                target1,
                normal_down=self.target_normal_locked,
                offset=(
                    self.egg_descend_offset()
                    + float(EGG_BASE_X_AXIS_SLIDE_DESCEND_CLEARANCE_M)
                ),
            )
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.post_reach.update(target_pos, ee_pos):
                self.pre_descend_step = "back_axis_slide_1"
                self.post_reach.reset()
            return True

        if self.pre_descend_step in ("back_axis_slide_1", "back_axis_slide_2"):
            target1 = self.back_egg_axis_target1_locked
            axis_dir = self.back_egg_axis_slide_dir_locked
            if target1 is None or axis_dir is None:
                self.pre_descend_step = None
                self.start_post_egg_flow()
                return True
            stage_index = 1 if self.pre_descend_step == "back_axis_slide_1" else 2
            stage_count = max(1, int(BACK_EGG_BASE_X_PARALLEL_SLIDE_STAGES))
            fraction = min(float(stage_index) / float(stage_count), 1.0)
            slide_egg_target = (
                np.asarray(target1, dtype=np.float32)
                + np.asarray(axis_dir, dtype=np.float32)
                * float(self.back_egg_axis_half_length_m_locked)
                * fraction
            )
            remaining_clearance_m = (
                float(EGG_BASE_X_AXIS_SLIDE_DESCEND_CLEARANCE_M)
                - float(EGG_BASE_X_AXIS_SLIDE_DESCEND_PER_STAGE_M) * stage_index
            )
            target_pos, look_pos, normal_down = self.target_from_egg(
                slide_egg_target,
                normal_down=self.target_normal_locked,
                offset=self.egg_descend_offset() + remaining_clearance_m,
            )
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.post_reach.update(target_pos, ee_pos):
                if stage_index < stage_count:
                    self.pre_descend_step = "back_axis_slide_2"
                    self.post_reach.reset()
                else:
                    self.pre_descend_step = None
                    self.post_reach.reset()
                    self.start_post_egg_flow()
            return True

        if self.pre_descend_step == "gripper_minor_width_only":
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_approach_offset(),
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt)
            if self.elapsed_since(self.pre_descend_wait_start) >= EGG_PRE_DESCEND_GRIPPER_WAIT_SEC:
                self.pre_descend_step = None
                self.pre_descend_wait_start = None
                self.request_egg_descend()
            return True

        return False

    # 【蛋專用／夾取後流程】處理蛋抬升、放入拉麵碗及返回 Home。

    def start_post_egg_flow(self):
        if self.post_step is not None:
            return
        if not ENABLE_EGG_DESCEND_REAL_TCP_CONFIRM:
            self.set_post_step(
                "gripper_close",
                "[TEST][FLOW] Egg descend reached; RTDE descend confirmation disabled; close gripper now.",
            )
            self.last_real_gripper_close_send_wall = None
            self.real_gripper_close_resend_count = 0
            self.perception.set_egg_detection_gate(False)
            self.set_gripper("close")
            return
        self.post_step = "descend_confirm"
        self.post_wait_start = time.perf_counter()
        self.post_reach.reset()
        self.egg_descend_real_tcp_in_tol_since = None
        self.egg_descend_real_tcp_correction_m = np.zeros(3, dtype=np.float32)
        self.egg_descend_real_tcp_y_integral_m = 0.0
        self.egg_descend_real_tcp_last_feedback_wall = None
        self.last_real_gripper_close_send_wall = None
        self.real_gripper_close_resend_count = 0
        self.perception.set_egg_detection_gate(False)
        print(
            f"[TEST][FLOW] Egg descend reached; keep descend pose and confirm it for "
            f"{EGG_DESCEND_CONFIRM_HOLD_SEC:.1f}s before closing gripper."
        )

    def real_tcp_descend_confirmed(self, target_isaac_pos):
        """確認真實 RTDE TCP 穩定抵達下降點。"""
        rtde_receive = globals().get("_rtde_r")
        now = time.perf_counter()
        target_rtde = isaac_pos_to_rtde_tcp_est(target_isaac_pos)
        status = {
            "target_rtde_tcp_m": target_rtde,
            "axis_tol_m": float(EGG_DESCEND_REAL_TCP_AXIS_TOL_M),
            "stable_sec_required": float(EGG_DESCEND_REAL_TCP_STABLE_SEC),
        }
        if rtde_receive is None:
            self.egg_descend_real_tcp_in_tol_since = None
            status["reason"] = "rtde_tcp_unavailable"
            return False, status
        try:
            actual_pose = rtde_receive.getActualTCPPose()
        except Exception as exc:
            self.egg_descend_real_tcp_in_tol_since = None
            status.update(reason="rtde_tcp_read_failed", error=str(exc))
            return False, status
        if actual_pose is None or len(actual_pose) < 3:
            self.egg_descend_real_tcp_in_tol_since = None
            status.update(reason="rtde_tcp_invalid", actual_rtde_tcp_m=actual_pose)
            return False, status

        actual_rtde = np.asarray(actual_pose[:3], dtype=np.float64)
        error = actual_rtde - np.asarray(target_rtde, dtype=np.float64)
        if EGG_DESCEND_REAL_TCP_CLOSED_LOOP_ENABLE:
            limit = float(EGG_DESCEND_REAL_TCP_CLOSED_LOOP_MAX_CORRECTION_M)
            desired_correction = np.clip(
                -float(EGG_DESCEND_REAL_TCP_CLOSED_LOOP_GAIN) * error,
                -limit,
                limit,
            )
            last_feedback = self.egg_descend_real_tcp_last_feedback_wall
            feedback_dt = 0.0 if last_feedback is None else min(max(now - last_feedback, 0.0), 0.1)
            self.egg_descend_real_tcp_last_feedback_wall = now
            if EGG_DESCEND_REAL_TCP_Y_INTEGRAL_ENABLE and feedback_dt > 0.0:
                integral_limit = float(EGG_DESCEND_REAL_TCP_Y_INTEGRAL_MAX_M)
                self.egg_descend_real_tcp_y_integral_m = float(np.clip(
                    self.egg_descend_real_tcp_y_integral_m
                    - float(EGG_DESCEND_REAL_TCP_Y_INTEGRAL_GAIN_PER_SEC) * float(error[1]) * feedback_dt,
                    -integral_limit,
                    integral_limit,
                ))
                desired_correction[1] += self.egg_descend_real_tcp_y_integral_m
            desired_correction = np.clip(desired_correction, -limit, limit)
            alpha = float(EGG_DESCEND_REAL_TCP_CLOSED_LOOP_FILTER_ALPHA)
            previous = np.asarray(self.egg_descend_real_tcp_correction_m, dtype=np.float64)
            self.egg_descend_real_tcp_correction_m = (
                previous + alpha * (desired_correction - previous)
            ).astype(np.float32)
        within = bool(np.all(np.abs(error) <= float(EGG_DESCEND_REAL_TCP_AXIS_TOL_M)))
        if within:
            if self.egg_descend_real_tcp_in_tol_since is None:
                self.egg_descend_real_tcp_in_tol_since = now
            stable_sec = now - self.egg_descend_real_tcp_in_tol_since
        else:
            self.egg_descend_real_tcp_in_tol_since = None
            stable_sec = 0.0
        status.update(
            actual_rtde_tcp_m=actual_rtde,
            error_rtde_tcp_m=error,
            error_rtde_tcp_mm=error * 1000.0,
            error_norm_mm=float(np.linalg.norm(error) * 1000.0),
            within_axis_tol=within,
            stable_sec=stable_sec,
            closed_loop_enabled=bool(EGG_DESCEND_REAL_TCP_CLOSED_LOOP_ENABLE),
            closed_loop_correction_m=self.egg_descend_real_tcp_correction_m,
            closed_loop_correction_mm=self.egg_descend_real_tcp_correction_m * 1000.0,
            y_integral_enabled=bool(EGG_DESCEND_REAL_TCP_Y_INTEGRAL_ENABLE),
            y_integral_m=float(self.egg_descend_real_tcp_y_integral_m),
            y_integral_mm=float(self.egg_descend_real_tcp_y_integral_m * 1000.0),
            feedback_dt_sec=feedback_dt if EGG_DESCEND_REAL_TCP_CLOSED_LOOP_ENABLE else None,
        )
        status["reason"] = "confirmed" if (
            within and stable_sec >= float(EGG_DESCEND_REAL_TCP_STABLE_SEC)
        ) else "outside_axis_tol" if not within else "stabilizing"
        return status["reason"] == "confirmed", status

    def egg_descend_command_target(self, nominal_target_pos):
        """將蛋下降目標套用有限幅 RTDE 修正。"""
        return (
            np.asarray(nominal_target_pos, dtype=np.float32)
            + np.asarray(self.egg_descend_real_tcp_correction_m, dtype=np.float32)
        ).astype(np.float32)

    def set_post_step(self, step, message):
        self.post_step = step
        self.post_wait_start = time.perf_counter() if step in ("gripper_close", "gripper_open") else None
        if step == "egg_lift":
            self.post_reach = ReachHold(hold_sec=EGG_LIFT_REACH_HOLD_SEC)
        else:
            self.post_reach.reset()
        print(message)

    def update_post_egg_flow(self, stage_ref, xcache, ee_pos, dt):
        if self.post_step is None or self.target_locked is None:
            return False

        if self.post_step == "descend_confirm":
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_descend_offset(),
                y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
            )
            command_target_pos = self.egg_descend_command_target(target_pos)
            self.set_motion_target(
                command_target_pos,
                look_pos + (command_target_pos - target_pos),
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            position_confirmed = self.post_reach.update(command_target_pos, ee_pos)
            orientation_confirmed = self.last_orient_err_deg <= ORIENT_REACH_TOL_DEG
            real_tcp_confirmed, _ = self.real_tcp_descend_confirmed(target_pos)
            if (
                self.elapsed_since(self.post_wait_start) >= EGG_DESCEND_CONFIRM_HOLD_SEC
                and position_confirmed
                and orientation_confirmed
                and real_tcp_confirmed
            ):
                self.set_post_step(
                    "gripper_close",
                    f"[TEST][FLOW] Egg descend confirmed; close gripper "
                    f"({GRIPPER_WAIT_CLOSE_SEC:.1f}s), "
                    f"{'then lift egg' if ENABLE_EGG_LIFT_AFTER_GRASP else 'then hold before lift'}.",
                )
                self.set_gripper("close")
            return True

        if self.post_step == "gripper_close":
            self.set_gripper("close")
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_descend_offset(),
                y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
            )
            command_target_pos = self.egg_descend_command_target(target_pos)
            self.set_motion_target(
                command_target_pos,
                look_pos + (command_target_pos - target_pos),
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.elapsed_since(self.post_wait_start) >= GRIPPER_WAIT_CLOSE_SEC:
                if ENABLE_EGG_LIFT_AFTER_GRASP:
                    set_prim_visibility(stage_ref, EGG_PRIM_PATH, visible=False)
                    self.set_post_step(
                        "egg_lift",
                        f"[TEST][FLOW] Gripper closed; lift egg to approach ({self.egg_approach_offset():.3f} m).",
                    )
                else:
                    self.set_post_step(
                        "grasp_hold",
                        "[TEST][FLOW] Gripper closed; holding before lift.",
                    )
            return True

        if self.post_step == "grasp_hold":
            self.set_gripper("close")
            self.resend_real_gripper_close_if_needed()
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_descend_offset(),
                y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
            )
            command_target_pos = self.egg_descend_command_target(target_pos)
            self.set_motion_target(
                command_target_pos,
                look_pos + (command_target_pos - target_pos),
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            return True

        if self.post_step == "egg_lift":
            self.set_gripper("close")
            target_pos, look_pos, normal_down = self.target_from_egg(
                self.target_locked,
                normal_down=self.target_normal_locked,
                offset=self.egg_approach_offset(),
                y_backoff_m=self.egg_pre_descend_y_backoff_m_locked,
            )
            self.set_motion_target(
                target_pos,
                look_pos,
                normal_down,
                dt,
                fixed_quat=self.egg_descend_quat_locked,
            )
            if self.post_reach.update(target_pos, ee_pos):
                if ENABLE_RAMEN_PLACE_FLOW:
                    self.set_post_step(
                        "ramen_approach",
                        "[TEST][FLOW] Egg lifted; moving to ramen bowl approach.",
                    )
                else:
                    print("[TEST][FLOW] Egg lifted; ramen bowl flow disabled. Move to release pose before home.")
                    self.post_step = None
                    self.post_wait_start = None
                    self.post_reach.reset()
                    self.egg_descend_quat_locked = None
                    self.egg_descend_quat_rmp_locked = None
                    self.start_pre_home_release_flow(source="egg")
                    self.set_gripper("close")
                    self.requested = False
                    self.waiting_for_egg_pose = False
                    self.egg_inspect_only = False
                    self.egg_descend_requested = False
                    self.mode = None
                    self.auto_run = False
                    self.done_logged = False
            return True

        if self.post_step == "ramen_approach":
            self.set_gripper("close")
            target_pos, look_pos, normal_down = self.target_from_ramen(
                stage_ref,
                xcache,
                offset=APPROACH_OFFSET,
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt)
            if self.post_reach.update(target_pos, ee_pos):
                self.set_post_step(
                    "ramen_descend",
                    f"[TEST][FLOW] Reached ramen approach; descend {RAMEN_DESCEND_DZ * 1000.0:.1f} mm.",
                )
            return True

        if self.post_step == "ramen_descend":
            self.set_gripper("close")
            target_pos, look_pos, normal_down = self.target_from_ramen(
                stage_ref,
                xcache,
                offset=max(APPROACH_OFFSET - RAMEN_DESCEND_DZ, 0.0),
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt)
            if self.post_reach.update(target_pos, ee_pos):
                self.set_gripper("open")
                self.set_post_step(
                    "gripper_open",
                    f"[TEST][FLOW] Ramen descend reached; open gripper ({GRIPPER_WAIT_OPEN_SEC:.1f}s).",
                )
            return True

        if self.post_step == "gripper_open":
            self.set_gripper("open")
            target_pos, look_pos, normal_down = self.target_from_ramen(
                stage_ref,
                xcache,
                offset=max(APPROACH_OFFSET - RAMEN_DESCEND_DZ, 0.0),
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt)
            if self.elapsed_since(self.post_wait_start) >= GRIPPER_WAIT_OPEN_SEC:
                self.set_post_step(
                    "ramen_lift",
                    "[TEST][FLOW] Gripper opened; lift from ramen bowl.",
                )
            return True

        if self.post_step == "ramen_lift":
            self.set_gripper("open")
            target_pos, look_pos, normal_down = self.target_from_ramen(
                stage_ref,
                xcache,
                offset=APPROACH_OFFSET,
            )
            self.set_motion_target(target_pos, look_pos, normal_down, dt)
            if self.post_reach.update(target_pos, ee_pos):
                print("[TEST][FLOW] Egg-to-ramen sequence finished; returning to home target.")
                self.reset_post_flow()
                self.requested = False
                self.waiting_for_egg_pose = False
                self.egg_inspect_only = False
                self.egg_descend_requested = False
                self.mode = None
                self.auto_run = False
                self.done_logged = False
            return True

        return False

    def maybe_upgrade_rough_lock_to_accurate(self):
        if not PREFER_ACCURATE_EGG_LOCK:
            return
        if self.mode != "egg" or self.target_source != "rough":
            return
        if self.egg_descend_requested:
            return
        accurate = self.perception.egg_accurate_pos
        if accurate is None:
            return

        self.target_locked = accurate.copy()
        self.target_source = "accurate"
        self.target_normal_locked = self.egg_target_normal_down(self.perception.egg_back_has_egg)
        self.target_yaw_raw_locked = self.perception.egg_yaw_deg
        self.lock_yaw_axis_width_mm()
        self.target_yaw_axis_name_locked = self.perception.egg_yaw_axis_name
        self.target_yaw_locked = egg_tool_pose_yaw_deg(
            self.target_yaw_raw_locked, self.target_yaw_axis_name_locked
        )
        self.reset_egg_spin_from_current_pose()
        self.egg_descend_dz_locked, self.egg_descend_source_locked = self.lock_egg_descend_dz()
        self.reach.reset()
        self.done_logged = False
        self.last_orient_err_deg = float("inf")
        print(
            f"[TEST] Upgraded locked egg target from rough to accurate: {fmt_vec(accurate)} "
            f"back_has_egg={self.perception.egg_back_has_egg} "
            f"descend_source={self.egg_descend_source_locked}"
        )

    # 【共用功能／每幀更新】整合辨識、蛋、筍乾木耳與放料狀態機。

    def _hold_current_robot_command(self):
        hold_q = None
        if _rtde_r is not None:
            try:
                q_actual = _rtde_r.getActualQ()
                if q_actual is not None and len(q_actual) >= 6:
                    hold_q = np.asarray(q_actual[:6], dtype=np.float32)
            except Exception:
                hold_q = None

        jp = self.robot.get_joint_positions().copy()
        if hold_q is not None and jp.shape[0] >= 6:
            jp[:6] = hold_q
        jp[GRIPPER_IDX] = self.gripper_cmd
        self.robot.set_joint_positions(jp)
        self._record_joint_positions(jp)

    def start_ungraspable_sweep(self, ungraspable_side):
        """啟動 P3／P4 的反向工具 X 掃動。"""
        side = str(ungraspable_side).lower()
        if side == "p4":
            action = "right"
            descend_pos_base = UNGRASPABLE_SWEEP_RIGHT_DESCEND_POS
            x_axis = UNGRASPABLE_SWEEP_RIGHT_X_AXIS
            y_axis = UNGRASPABLE_SWEEP_RIGHT_Y_AXIS
            z_axis = UNGRASPABLE_SWEEP_RIGHT_Z_AXIS
            tool_x_sign = -1.0
        elif side == "p3":
            action = "left"
            descend_pos_base = UNGRASPABLE_SWEEP_LEFT_DESCEND_POS
            x_axis = UNGRASPABLE_SWEEP_LEFT_X_AXIS
            y_axis = UNGRASPABLE_SWEEP_LEFT_Y_AXIS
            z_axis = UNGRASPABLE_SWEEP_LEFT_Z_AXIS
            tool_x_sign = 1.0
        else:
            return False
        descend_pos = rtde_tcp_pos_to_isaac(descend_pos_base)
        base_quat = fixed_quat_from_tool_axes(z_axis, x_axis=x_axis, y_axis=y_axis)
        x_unit = normalize_vec(x_axis, default=np.array([1.0, 0.0, 0.0], dtype=np.float32))
        y_unit = normalize_vec(y_axis, default=np.array([0.0, 1.0, 0.0], dtype=np.float32))
        z_unit = normalize_vec(z_axis, default=np.array([0.0, 0.0, -1.0], dtype=np.float32))
        pre_descend_pos = np.asarray(descend_pos, dtype=np.float32) - z_unit * float(UNGRASPABLE_SWEEP_PRE_DESCEND_OFFSET_M)
        push_y_pos = np.asarray(descend_pos, dtype=np.float32) - y_unit * float(UNGRASPABLE_SWEEP_TOOL_Y_SHIFT_M)
        push_x_pos = push_y_pos + x_unit * (tool_x_sign * float(UNGRASPABLE_SWEEP_TOOL_X_SHIFT_M))
        self.ungraspable_sweep_side = side
        self.ungraspable_sweep_count += 1
        self.ungraspable_sweep_cfg = {
            "action": action,
            "pre_descend_pos": pre_descend_pos,
            "descend_pos": np.asarray(descend_pos, dtype=np.float32),
            "push_y_pos": push_y_pos,
            "push_x_pos": push_x_pos,
            "base_quat": base_quat,
            "base_z_axis": z_unit,
            "tool_x_sign": tool_x_sign,
        }
        self.ungraspable_sweep_step = "pre_descend"
        self.ungraspable_sweep_reach.reset()
        self.ungraspable_sweep_open_at_plate_pending = False
        self.ungraspable_sweep_return_phase = None
        self.ungraspable_sweep_return_quat = None
        self.ungraspable_sweep_return_base_z_target = None
        self.set_gripper("open")
        self.mode = "ungraspable_sweep"
        self.requested = False
        self.waiting_for_egg_pose = False
        self.egg_inspect_only = False
        self.egg_descend_requested = False
        print(f"[TEST][UNGRASPABLE] {side} egg -> {action} sweep; moving to pre-descend.")
        return True

    def update_ungraspable_sweep(self, ee_pos):
        if self.ungraspable_sweep_step is None or self.ungraspable_sweep_cfg is None:
            return False
        cfg = self.ungraspable_sweep_cfg
        step = self.ungraspable_sweep_step
        if step == "pre_descend":
            target_pos = cfg["pre_descend_pos"]
            quat = cfg["base_quat"]
            normal = cfg["base_z_axis"]
        elif step == "direct_descend":
            target_pos = cfg["descend_pos"]
            quat = cfg["base_quat"]
            normal = cfg["base_z_axis"]
        elif step == "push_tool_minus_y":
            target_pos = cfg["push_y_pos"]
            quat = cfg["base_quat"]
            normal = cfg["base_z_axis"]
        elif step == "push_tool_x":
            target_pos = cfg["push_x_pos"]
            quat = cfg["base_quat"]
            normal = cfg["base_z_axis"]
        else:
            return False
        self.set_motion_target(
            target_pos,
            target_pos + normal,
            normal,
            UNGRASPABLE_SWEEP_POLICY_DT,
            apply_modifiers=False,
            fixed_quat=quat,
        )
        reached = self.ungraspable_sweep_reach.update(target_pos, ee_pos)
        orient_ok = self.last_orient_err_deg <= ORIENT_REACH_TOL_DEG
        if not (reached and orient_ok):
            return True
        self.ungraspable_sweep_reach.reset()
        transitions = {
            "pre_descend": "direct_descend",
            "direct_descend": "push_tool_minus_y",
            "push_tool_minus_y": "push_tool_x",
        }
        next_step = transitions.get(step)
        if next_step is not None:
            if step == "pre_descend":
                self.send_gripper_width_mm(
                    UNGRASPABLE_SWEEP_GRIPPER_WIDTH_MM,
                    event_name="ungraspable_sweep_gripper_width_cmd",
                )
            self.ungraspable_sweep_step = next_step
            return True
        print("[TEST][UNGRASPABLE] sweep complete; restarting plate/camera/egg flow.")
        sweep_return_quat = np.asarray(cfg["base_quat"], dtype=np.float64).copy()
        self.ungraspable_sweep_step = None
        self.ungraspable_sweep_side = None
        self.ungraspable_sweep_cfg = None
        self.perception.clear_egg_measurements_for_new_lock()
        self.request_move(force_back_egg_photo_pose=True)
        self.ungraspable_sweep_open_at_plate_pending = True
        plate_target_pos, _plate_look, _plate_normal = self.target_from_plate(self.target_locked)
        base_z_target = np.asarray(self.last_ee_pos, dtype=np.float32).copy()
        base_z_target[2] = float(plate_target_pos[2])
        self.ungraspable_sweep_return_phase = "base_z"
        self.ungraspable_sweep_return_quat = sweep_return_quat
        self.ungraspable_sweep_return_base_z_target = base_z_target
        print("[TEST][UNGRASPABLE] return to plate: base-Z first with sweep pose held, then XY translation + rotation.")
        return True

    # 【共用功能／命令輸出】套用 RMPflow、夾爪關節與關節命令紀錄。
    def _apply_left_robot_action(self, policy_dt):
        action = self.policy.get_next_articulation_action(policy_dt)
        if getattr(action, "joint_positions", None) is None:
            jp = self.robot.get_joint_positions().copy()
        else:
            jp = np.array(action.joint_positions, dtype=np.float32).copy()
            if jp.shape[0] <= GRIPPER_IDX:
                jp = self.robot.get_joint_positions().copy()
        jp[GRIPPER_IDX] = self.gripper_cmd
        action.joint_positions = jp
        self.robot.get_articulation_controller().apply_action(action)
        self._record_joint_positions(jp)

    # 【蛋專用／辨識等待】處理相機穩定、無法夾取掃動與蛋姿態鎖定。
    def _update_egg_observation_waits(self):
        if self.plate_mask_stabilize_until is not None:
            if time.perf_counter() >= self.plate_mask_stabilize_until:
                self.plate_mask_stabilize_until = None
                if self.auto_run and self.mode == "plate":
                    print("[TEST][AUTO] Plate stabilize done; waiting for fresh egg accurate_pose.")
                    self.request_egg_move()

        if (
            self.no_back_reobserve_stabilize_until is not None
            and time.perf_counter() >= self.no_back_reobserve_stabilize_until
        ):
            self.no_back_reobserve_stabilize_until = None
            self.requested = False
            self.done_logged = False
            print("[TEST][NO_BACK] re-observe pose stabilized; requesting fresh accurate egg pose.")
            self.request_egg_move()

        if self.waiting_for_egg_pose and not self.requested:
            bowl_status = self.perception.egg_bowl_status
            if self.auto_run and isinstance(bowl_status, dict) and bowl_status.get("state") == "only_ungraspable":
                sides = [str(side).lower() for side in bowl_status.get("p3p4_sides", []) if str(side).lower() in ("p3", "p4")]
                sweep_side = "p3" if "p3" in sides else ("p4" if "p4" in sides else None)
                if sweep_side is not None:
                    if self.ungraspable_sweep_count < UNGRASPABLE_SWEEP_MAX_REPEATS:
                        if self.start_ungraspable_sweep(sweep_side):
                            return True
                    elif not self.ungraspable_sweep_limit_logged:
                        self.ungraspable_sweep_limit_logged = True
                        self.auto_run = False
                        print(
                            f"[TEST][UNGRASPABLE] repeat limit reached "
                            f"({UNGRASPABLE_SWEEP_MAX_REPEATS}); waiting at plate."
                        )
            if PREFER_ACCURATE_EGG_LOCK and self.perception.egg_accurate_pos is not None:
                egg_pos, source, stable_stats = self.perception.stable_accurate_egg_candidate()
                if egg_pos is None:
                    return True
            else:
                egg_pos, source = self.perception.best_egg_pos()
                stable_stats = None
            if egg_pos is not None:
                if PREFER_ACCURATE_EGG_LOCK and source not in ("accurate", "accurate_stable"):
                    return True
                self.mode = "egg"
                self.target_locked = egg_pos.copy()
                back_has_egg_locked = (
                    stable_stats.get("back_has_egg")
                    if isinstance(stable_stats, dict)
                    else self.perception.egg_back_has_egg
                )
                if back_has_egg_locked is False and not self.no_back_reobserve_done:
                    if ENABLE_NO_BACK_EGG_REOBSERVE:
                        self.start_no_back_reobserve(egg_pos, source, stable_stats=stable_stats)
                        return True
                    self.no_back_reobserve_done = True
                    print("[TEST][NO_BACK] second camera observation disabled; use first locked egg pose.")
                self.target_back_has_egg_locked = back_has_egg_locked
                self.target_side_edge_fallback_locked = self.current_bowl_status_is_side_edge_fallback()
                self.target_side_edge_fallback_side_locked = self.current_bowl_status_selected_side_edge()
                self.target_normal_locked = (
                    egg_non_sweepable_ungraspable_normal_down()
                    if self.target_side_edge_fallback_locked
                    else self.egg_target_normal_down(back_has_egg_locked)
                )
                self.target_yaw_raw_locked = (
                    stable_stats.get("yaw_deg")
                    if isinstance(stable_stats, dict) and stable_stats.get("yaw_deg") is not None
                    else self.perception.egg_yaw_deg
                )
                self.lock_yaw_axis_width_mm(
                    stable_stats.get("yaw_axis_width_mm")
                    if isinstance(stable_stats, dict)
                    else None
                )
                self.lock_yaw_other_axis_width_mm(
                    stable_stats.get("yaw_other_axis_width_mm")
                    if isinstance(stable_stats, dict)
                    else None
                )
                self.target_yaw_axis_name_locked = (
                    stable_stats.get("yaw_axis_name")
                    if isinstance(stable_stats, dict) and stable_stats.get("yaw_axis_name") in ("major", "minor")
                    else self.perception.egg_yaw_axis_name
                )
                self.target_yaw_locked = egg_tool_pose_yaw_deg(
                    self.target_yaw_raw_locked, self.target_yaw_axis_name_locked
                )
                self.lock_yaw_axis_center_to_endpoint_max_mm(
                    stable_stats.get("yaw_axis_center_to_endpoint_max_mm")
                    if isinstance(stable_stats, dict)
                    else None
                )
                self.target_yaw_axis_base_x_err_deg_locked = (
                    stable_stats.get("yaw_axis_base_x_err_deg")
                    if isinstance(stable_stats, dict) and stable_stats.get("yaw_axis_base_x_err_deg") is not None
                    else self.perception.egg_yaw_axis_base_x_err_deg
                )
                self.apply_base_x_parallel_approach_yaw()
                self.reset_egg_spin_from_current_pose()
                self.egg_descend_dz_locked, self.egg_descend_source_locked = self.lock_egg_descend_dz()
                self.target_source = source
                self.requested = False
                self.waiting_for_egg_pose = False
                self.egg_inspect_only = True
                self.egg_descend_requested = False
                self.done_logged = False
                self.last_orient_err_deg = float("inf")
                print(
                    f"[TEST] Egg pose arrived; locked target {fmt_vec(self.target_locked)} "
                    f"normal={fmt_vec(self.target_normal_locked)} yaw_raw={self.target_yaw_raw_locked} "
                    f"yaw={self.target_yaw_locked} "
                    f"back_has_egg={back_has_egg_locked} "
                    f"gripper_width={self.gripper_close_width_mm():.1f}mm "
                    f"descend_source={self.egg_descend_source_locked} "
                    f"({source}); arm holds. Press E again to move."
                )
                if self.auto_run:
                    self.egg_inspect_only = False
                    self.egg_descend_requested = False
                    self.requested = True
                    self.waiting_for_egg_pose = False
                    self.reach = ReachHold(hold_sec=EGG_APPROACH_REACH_HOLD_SEC)
                    self.done_logged = False
                    self.last_orient_err_deg = float("inf")
                    print("[TEST][AUTO] Accurate egg locked; moving to egg approach.")

        return False

    def update(self, stage_ref, xcache, dt):
        ee_prim = stage_ref.GetPrimAtPath(self.ee_prim_path)
        ee_tf = xcache.GetLocalToWorldTransform(ee_prim)
        ee_pos = np.array(ee_tf.ExtractTranslation(), dtype=np.float32)
        self.last_ee_pos = ee_pos.copy()
        self.last_isaac_axes_col, self.last_isaac_axes_row = gf_matrix_to_rotation_axes(ee_tf)
        self.maybe_upgrade_rough_lock_to_accurate()

        if self.ungraspable_sweep_step is not None:
            self.update_ungraspable_sweep(ee_pos)
            self._apply_left_robot_action(UNGRASPABLE_SWEEP_POLICY_DT)
            return

        if self._update_egg_observation_waits():
            return

        if self.egg_inspect_only and self.mode == "egg":
            if self.target_locked is not None:
                target_pos, look_pos, normal_down = self.target_from_egg(
                    self.target_locked,
                    normal_down=self.target_normal_locked,
                )
                self.last_target_pos = target_pos.copy()
                self.last_look_pos = look_pos.copy()
                self.last_normal_down = normal_down.copy()
                quat = look_at_quat(target_pos, look_pos, world_up=WORLD_UP, tool_axis_local=TOOL_AXIS)
                quat, self.last_camera_spin_180 = prefer_camera_forward_quat(quat)
                quat = self._apply_orientation_modifiers(quat, dt)
                self.last_target_quat = np.asarray(quat, dtype=np.float64).copy()
                self.last_target_quat_rmp_wxyz = quat_xyzw_to_wxyz(quat)
                R_target = quat_xyzw_to_matrix(self.last_target_quat)
                self.last_target_axes = [R_target[:, i] for i in range(3)]
            self._hold_current_robot_command()
            return

        pre_descend_active = self.update_pre_descend_flow(dt, ee_pos)

        post_flow_active = (
            self.update_post_egg_flow(stage_ref, xcache, ee_pos, dt)
            if self.post_step is not None and not pre_descend_active
            else False
        )
        grid_food_active = (
            self.update_grid_food_flow(ee_pos, dt)
            if self.grid_food_step is not None and not pre_descend_active and not post_flow_active
            else False
        )
        pre_home_release_active = (
            self.update_pre_home_release_flow(ee_pos, dt)
            if (
                self.pre_home_release_step is not None
                and not pre_descend_active
                and not post_flow_active
                and not grid_food_active
            )
            else False
        )

        if pre_descend_active or post_flow_active or grid_food_active or pre_home_release_active:
            pass
        elif self.requested and self.target_locked is not None:
            if self.mode == "egg":
                target = self.target_locked
                source = self.target_source if self.target_source != "none" else "locked"
                self.target_source = source
                offset = self.egg_descend_offset() if self.egg_descend_requested else self.egg_approach_offset()
                target_pos, look_pos, normal_down = self.target_from_egg(
                    target,
                    normal_down=self.target_normal_locked,
                    offset=offset,
                    y_backoff_m=self.egg_pre_descend_y_backoff_m_locked if self.egg_descend_requested else 0.0,
                )
                if self.egg_descend_requested:
                    final_target_pos = target_pos.copy()
                    waypoint = self.egg_descend_path_target()
                    if waypoint is not None and not self.egg_descend_path_complete:
                        target_pos = waypoint
                        look_pos = look_pos + (target_pos - final_target_pos)
            elif self.mode == "plate":
                target = self.target_locked
                self.target_source = "plate_locked"
                target_pos, look_pos, normal_down = self.target_from_plate(target)
            elif self.mode == "no_back_reobserve":
                target = self.target_locked
                self.target_source = "no_back_reobserve"
                target_pos, look_pos, normal_down = self.target_from_plate(target)
            else:
                self._hold_current_robot_command()
                return

            self.last_target_pos = target_pos.copy()
            self.last_look_pos = look_pos.copy()
            self.last_normal_down = normal_down.copy()
            if self.mode == "egg" and self.egg_descend_requested and self.egg_descend_quat_locked is not None:
                quat = self.egg_descend_quat_locked.copy()
                self.last_camera_spin_180 = False
            else:
                quat = look_at_quat(target_pos, look_pos, world_up=WORLD_UP, tool_axis_local=TOOL_AXIS)
                quat, self.last_camera_spin_180 = prefer_camera_forward_quat(quat)
                quat = self._apply_orientation_modifiers(quat, dt)

            sweep_return_base_z = bool(
                self.mode == "plate"
                and self.ungraspable_sweep_return_phase == "base_z"
                and self.ungraspable_sweep_return_quat is not None
                and self.ungraspable_sweep_return_base_z_target is not None
            )
            if sweep_return_base_z:
                target_pos = np.asarray(self.ungraspable_sweep_return_base_z_target, dtype=np.float32).copy()
                look_pos = target_pos + np.asarray(self.target_normal_locked, dtype=np.float32) * PLATE_APPROACH_OFFSET
                quat = np.asarray(self.ungraspable_sweep_return_quat, dtype=np.float64).copy()
                self.last_camera_spin_180 = False
            R_target = quat_xyzw_to_matrix(quat)

            if self.mode == "plate" and not egg_manual_enabled():
                tcp_x_shift = normalize_vec(R_target[:, 0], default=np.array([1.0, 0.0, 0.0], dtype=np.float32))
                tcp_x_shift = tcp_x_shift.astype(np.float32) * float(PLATE_TCP_X_OFFSET)
                target_pos = (target_pos + tcp_x_shift).astype(np.float32)
                look_pos = (look_pos + tcp_x_shift).astype(np.float32)
                self.last_target_pos = target_pos.copy()
                self.last_look_pos = look_pos.copy()
                quat = look_at_quat(target_pos, look_pos, world_up=WORLD_UP, tool_axis_local=TOOL_AXIS)
                quat, self.last_camera_spin_180 = prefer_camera_forward_quat(quat)
                quat = self._apply_orientation_modifiers(quat, dt)
                R_target = quat_xyzw_to_matrix(quat)

            self.last_target_quat = np.asarray(quat, dtype=np.float64).copy()
            self.last_target_quat_rmp_wxyz = quat_xyzw_to_wxyz(quat)
            self.last_target_axes = [R_target[:, i] for i in range(3)]

            self.rmpflow.set_end_effector_target(
                target_position=target_pos,
                target_orientation=quat_xyzw_to_wxyz(quat),
            )
            self.rmpflow.update_world()

            if self.mode == "egg" and self.egg_descend_requested:
                descend_path_complete = self.advance_egg_descend_cartesian_path(ee_pos)
                if not descend_path_complete:
                    self.reach.reset()
                    pos_reached = False
                else:
                    pos_reached = self.reach.update(target_pos, ee_pos)
            else:
                pos_reached = self.reach.update(target_pos, ee_pos)
            if sweep_return_base_z and pos_reached:
                self.ungraspable_sweep_return_phase = "final"
                self.ungraspable_sweep_return_quat = None
                self.ungraspable_sweep_return_base_z_target = None
                self.reach.reset()
                pos_reached = False
                print("[TEST][UNGRASPABLE] base-Z return reached; moving remaining XY and rotating to camera pose.")
            isaac_tool_z = self.last_isaac_axes_row[2] if self.last_isaac_axes_row is not None else None
            self.last_orient_err_deg = normal_angle_deg(isaac_tool_z, normal_down)
            orient_reached = self.last_orient_err_deg <= ORIENT_REACH_TOL_DEG
            target_axis_err_deg = {}
            if self.last_target_axes is not None and self.last_isaac_axes_row is not None:
                for axis_name, target_axis, actual_axis in zip(
                    ("x", "y", "z"),
                    self.last_target_axes,
                    self.last_isaac_axes_row,
                ):
                    target_axis_err_deg[axis_name] = normal_angle_deg(actual_axis, target_axis)
            yaw_axis_err_deg = target_axis_err_deg.get("x")
            yaw_reached = True
            spin_settled = True
            if self.mode == "egg" and self.target_yaw_locked is not None:
                spin_settled = self._spin_is_settled()
                yaw_reached = bool(
                    yaw_axis_err_deg is not None
                    and yaw_axis_err_deg <= SPIN_SETTLE_TOL_DEG
                    and spin_settled
                )

            if pos_reached and orient_reached and yaw_reached and not self.done_logged:
                self.done_logged = True
                if self.mode == "egg" and self.egg_descend_requested:
                    self.start_post_egg_flow()
                elif self.mode == "egg" and self.as_capture_active:
                    self.prepare_as_egg_pre_shrink()
                    self.auto_run = False
                    self.requested = False
                    self.egg_inspect_only = True
                    self.as_capture_egg_ready = True
                    self._start_next_as_capture()
                elif self.auto_run and self.mode == "egg":
                    if ENABLE_AUTO_EGG_DESCEND:
                        print("[TEST][AUTO] Egg approach reached; starting pre-descend gripper/backoff.")
                        self.start_pre_descend_flow()
                    else:
                        print("[TEST][AUTO] Egg approach reached; holding here. Press D to descend.")
                        self.auto_run = False
                elif self.auto_run and self.mode == "plate":
                    if egg_manual_enabled() and not ENABLE_AUTO_EGG_AFTER_MANUAL_APPROACH:
                        print("[TEST][AUTO] Manual approach reached; holding here. Press Esc to cancel.")
                        self.auto_run = False
                    else:
                        if self.ungraspable_sweep_open_at_plate_pending:
                            print("[TEST][UNGRASPABLE] Plate/camera pose reached; opening gripper.")
                            self.set_gripper("open")
                            self.ungraspable_sweep_open_at_plate_pending = False
                            self.ungraspable_sweep_return_phase = None
                            self.ungraspable_sweep_return_base_z_target = None
                        self.plate_mask_stabilize_until = time.perf_counter() + float(EGG_MASK_STABILIZE_SEC)
                        print(
                            f"[TEST][AUTO] Plate approach reached; holding {EGG_MASK_STABILIZE_SEC:.1f}s "
                            "for D405/SAM3 mask stabilization."
                        )
                elif self.mode == "no_back_reobserve":
                    self.no_back_reobserve_stabilize_until = (
                        time.perf_counter() + float(EGG_MASK_STABILIZE_SEC)
                    )
                    print(
                        f"[TEST][NO_BACK] re-observe pose reached; holding "
                        f"{EGG_MASK_STABILIZE_SEC:.1f}s before fresh D405 capture."
                    )
        else:
            if not self.idle_home_enabled:
                self._hold_current_robot_command()
                return
            if self.mode is None and not self.waiting_for_egg_pose:
                self.target_source = "none"
            home_cfg = manual_home_cfg()
            home_hover = np.asarray(home_cfg["target_pos"], dtype=np.float32).reshape(3)
            home_look = np.asarray(home_cfg["look_pos"], dtype=np.float32).reshape(3)
            self.last_target_pos = home_hover.copy()
            self.last_look_pos = home_look.copy()
            self.last_normal_down = np.asarray(home_cfg["normal_down"], dtype=np.float32).reshape(3)
            if home_cfg.get("enabled") and home_cfg.get("quat_xyzw") is not None:
                quat = np.asarray(home_cfg["quat_xyzw"], dtype=np.float64).reshape(4)
            else:
                quat = look_at_quat(ee_pos, home_look, world_up=WORLD_UP, tool_axis_local=TOOL_AXIS)
            self.last_target_quat = np.asarray(quat, dtype=np.float64).copy()
            self.last_target_quat_rmp_wxyz = quat_xyzw_to_wxyz(self.last_target_quat)
            R_target = quat_xyzw_to_matrix(self.last_target_quat)
            self.last_target_axes = [R_target[:, i] for i in range(3)]
            self.rmpflow.set_end_effector_target(
                target_position=home_hover,
                target_orientation=self.last_target_quat_rmp_wxyz,
            )
            self.rmpflow.update_world()
            if self.egg_home_return_active:
                if self.egg_home_return_reach.update(home_hover, ee_pos):
                    self.egg_home_return_active = False
                    self.egg_home_return_reach.reset()
                    print(
                        f"[TEST][FLOW] Egg home reached; held "
                        f"{EGG_HOME_REACH_HOLD_SEC:.1f}s."
                    )
            elif self.open_gripper_at_home_pending:
                if self.home_open_reach.update(home_hover, ee_pos):
                    print("[TEST][FLOW] Home reached; opening gripper.")
                    self.set_gripper("open")
                    self.open_gripper_at_home_pending = False
                    self.home_open_reach.reset()
            else:
                self.home_open_reach.reset()

        sweep_return_xy_rotate = bool(
            self.mode == "plate" and self.ungraspable_sweep_return_phase == "final"
        )
        policy_dt = (
            UNGRASPABLE_SWEEP_RETURN_FINAL_POLICY_DT
            if sweep_return_xy_rotate
            else dt
        )
        self._apply_left_robot_action(policy_dt)

from .utils.rtde_control.rtde_main_rtde_main import (
    LEFT_ROBOT_IP,
    disconnect_all,
    make_gripper,
    rtde_left_c,
    rtde_left_r,
    rtde_left_streamer,
    rtde_right_r,
    rtde_right_streamer,
    stop_all,
)

@dataclass
class RuntimeServices:
    left_robot_ip: str
    rtde_left_control: object
    rtde_left_receive: object
    rtde_right_receive: object
    rtde_left_streamer: object
    rtde_right_streamer: object
    make_gripper_fn: object
    stop_all_fn: object
    disconnect_all_fn: object

    def left_rtde_control_connected(self):
        return self.rtde_left_control is not None

def create_default_runtime_services():
    return RuntimeServices(
        left_robot_ip=LEFT_ROBOT_IP,
        rtde_left_control=rtde_left_c,
        rtde_left_receive=rtde_left_r,
        rtde_right_receive=rtde_right_r,
        rtde_left_streamer=rtde_left_streamer,
        rtde_right_streamer=rtde_right_streamer,
        make_gripper_fn=make_gripper,
        stop_all_fn=stop_all,
        disconnect_all_fn=disconnect_all,
    )

def wait_for_stage_loaded(timeout_sec: float = 60.0):
    context = omni.usd.get_context()
    t0 = time.perf_counter()
    last_print_sec = -1
    while True:
        _, _, loading = context.get_stage_loading_status()
        if loading <= 0:
            break
        elapsed = time.perf_counter() - t0
        if elapsed > timeout_sec:
            print(f"[StageLoad][WARN] timeout after {elapsed:.1f}s; loading={loading}")
            break
        sec = int(elapsed)
        if sec != last_print_sec:
            print(f"[StageLoad] waiting... loading={loading}")
            last_print_sec = sec
        stage_utils.update_stage()

    stage_utils.update_stage()
    return omni.usd.get_context().get_stage()

def load_json(path):
    with Path(path).expanduser().open("r", encoding="utf-8") as f:
        return json.load(f)

class RightLadlePathTools:
    def __init__(self, root_path: Path):
        self.root_path = Path(root_path)

    def latest_json(self, pattern: str):
        paths = sorted(glob.glob(str(pattern)))
        return Path(paths[-1]) if paths else None

    def latest_json_from_patterns(self, patterns):
        for pattern in patterns:
            path = self.latest_json(pattern)
            if path is not None:
                return path
        return None

    def food_latest_patterns(self, log_name: str, food: str):
        food = str(food).strip().lower()
        if food in ("", "sesame"):
            return [str(self.root_path / "logs" / f"{log_name}_[0-9]*.json")]
        return [
            str(self.root_path / "logs" / food / f"{log_name}_*.json"),
            str(self.root_path / "logs" / f"{log_name}_{food}_*.json"),
            str(self.root_path / "logs" / f"{food}_{log_name}_*.json"),
        ]

    def load_json(self, path):
        return load_json(path)

def normalize(v, default=None):
    arr = np.asarray(v, dtype=np.float64).reshape(3)
    n = float(np.linalg.norm(arr))
    if (not np.isfinite(n)) or n < 1e-12:
        return default
    return arr / n

def skew(v):
    x, y, z = np.asarray(v, dtype=np.float64).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)

def rotation_between(src, dst):
    a = normalize(src, default=np.array([1.0, 0.0, 0.0], dtype=np.float64))
    b = normalize(dst, default=a)
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if c > 1.0 - 1e-9:
        return np.eye(3, dtype=np.float64)
    if c < -1.0 + 1e-9:
        axis = np.cross(a, np.array([1.0, 0.0, 0.0], dtype=np.float64))
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, np.array([0.0, 1.0, 0.0], dtype=np.float64))
        axis = normalize(axis, default=np.array([0.0, 0.0, 1.0], dtype=np.float64))
        K = skew(axis)
        return np.eye(3, dtype=np.float64) + 2.0 * (K @ K)
    v = np.cross(a, b)
    K = skew(v)
    return np.eye(3, dtype=np.float64) + K + (K @ K) * (1.0 / (1.0 + c))

def rotation_matrix_axis_angle(axis, angle_rad):
    axis = normalize(axis, default=np.array([0.0, 1.0, 0.0], dtype=np.float64))
    x, y, z = axis
    c = float(np.cos(angle_rad))
    s = float(np.sin(angle_rad))
    C = 1.0 - c
    return np.array(
        [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ],
        dtype=np.float64,
    )

def rotvec_to_matrix(rotvec):
    rv = np.asarray(rotvec, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(rv))
    if theta < 1e-12:
        return np.eye(3, dtype=np.float64)
    return rotation_matrix_axis_angle(rv / theta, theta)

def quat_from_matrix_wxyz(R):
    m = np.asarray(R, dtype=np.float64).reshape(3, 3)
    t = float(np.trace(m))
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    else:
        idx = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
        if idx == 0:
            s = np.sqrt(max(1.0 + m[0, 0] - m[1, 1] - m[2, 2], 1e-12)) * 2.0
            w = (m[2, 1] - m[1, 2]) / s
            x = 0.25 * s
            y = (m[0, 1] + m[1, 0]) / s
            z = (m[0, 2] + m[2, 0]) / s
        elif idx == 1:
            s = np.sqrt(max(1.0 - m[0, 0] + m[1, 1] - m[2, 2], 1e-12)) * 2.0
            w = (m[0, 2] - m[2, 0]) / s
            x = (m[0, 1] + m[1, 0]) / s
            y = 0.25 * s
            z = (m[1, 2] + m[2, 1]) / s
        else:
            s = np.sqrt(max(1.0 - m[0, 0] - m[1, 1] + m[2, 2], 1e-12)) * 2.0
            w = (m[1, 0] - m[0, 1]) / s
            x = (m[0, 2] + m[2, 0]) / s
            y = (m[1, 2] + m[2, 1]) / s
            z = 0.25 * s
    q = np.array([w, x, y, z], dtype=np.float64)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    return q

def gf_matrix_to_rotation(M):
    return np.array(
        [
            [float(M[0][0]), float(M[0][1]), float(M[0][2])],
            [float(M[1][0]), float(M[1][1]), float(M[1][2])],
            [float(M[2][0]), float(M[2][1]), float(M[2][2])],
        ],
        dtype=np.float64,
    )

def build_entry_rotation(selected):
    x_axis = normalize(selected["x_axis"], default=np.array([1.0, 0.0, 0.0], dtype=np.float64))
    y_axis = normalize(selected["y_axis"], default=np.array([0.0, 1.0, 0.0], dtype=np.float64))
    z_axis = normalize(selected["z_axis"], default=np.array([0.0, 0.0, 1.0], dtype=np.float64))
    R = np.stack([x_axis, y_axis, z_axis], axis=1)
    u, _, vh = np.linalg.svd(R)
    R = u @ vh
    if np.linalg.det(R) < 0.0:
        R[:, 2] *= -1.0
    return R

def waypoint_to_ladle_target(wp, entry_R, spoon_a_offset_tool, spoon_b_offset_tool, base_to_world_z, safety_lift_z=0.0):
    spoon_a_base = np.asarray(wp["spoon_a_base_m"], dtype=np.float64).reshape(3)
    spoon_b_base = np.asarray(wp["spoon_b_base_m"], dtype=np.float64).reshape(3)
    base_to_world = np.array([0.0, 0.0, float(base_to_world_z)], dtype=np.float64)
    safety_lift = np.array([0.0, 0.0, float(safety_lift_z)], dtype=np.float64)
    spoon_a = spoon_a_base + base_to_world + safety_lift
    spoon_b = spoon_b_base + base_to_world + safety_lift
    tool_vec = np.asarray(spoon_b_offset_tool, dtype=np.float64).reshape(3) - np.asarray(spoon_a_offset_tool, dtype=np.float64).reshape(3)
    entry_vec = entry_R @ tool_vec
    desired_vec = spoon_b - spoon_a
    R_target = rotation_between(entry_vec, desired_vec) @ entry_R
    ee_pos = spoon_a - R_target @ np.asarray(spoon_a_offset_tool, dtype=np.float64).reshape(3)
    return {
        "name": str(wp["name"]),
        "target_position": ee_pos,
        "target_orientation": quat_from_matrix_wxyz(R_target),
        "R_target": R_target,
        "spoon_a": spoon_a,
        "spoon_b": spoon_b,
        "spoon_b_bottom_dist_m": float(wp.get("spoon_b_bottom_dist_m", np.nan)),
    }

def apply_ladle_base_ry_offset(target, ry_deg, spoon_a_offset_tool, spoon_b_offset_tool):
    ry_deg = float(ry_deg)
    if abs(ry_deg) < 1e-9:
        return target
    R_base = np.asarray(target["R_target"], dtype=np.float64).reshape(3, 3)
    R_delta = rotation_matrix_axis_angle([0.0, 1.0, 0.0], np.deg2rad(ry_deg))
    R_target = R_delta @ R_base
    update_ladle_target_geometry(target, R_target, spoon_a_offset_tool, spoon_b_offset_tool)
    target["base_ry_offset_deg"] = ry_deg
    return target

def translate_ladle_target(target, axis, shift_m):
    shift_m = float(shift_m)
    if abs(shift_m) < 1e-9:
        return target
    axis = str(axis).lower()
    delta = np.zeros(3, dtype=np.float64)
    delta[{"x": 0, "y": 1, "z": 2}[axis]] = shift_m
    target["target_position"] = np.asarray(target["target_position"], dtype=np.float64).reshape(3) + delta
    target["spoon_a"] = np.asarray(target["spoon_a"], dtype=np.float64).reshape(3) + delta
    target["spoon_b"] = np.asarray(target["spoon_b"], dtype=np.float64).reshape(3) + delta
    target[f"base_{axis}_shift_m"] = shift_m
    return target

def update_ladle_target_geometry(target, rotation, spoon_a_offset_tool, spoon_b_offset_tool):
    R_target = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    ee_pos = np.asarray(target["target_position"], dtype=np.float64).reshape(3)
    target.update(
        R_target=R_target,
        target_orientation=quat_from_matrix_wxyz(R_target),
        spoon_a=ee_pos + R_target @ np.asarray(spoon_a_offset_tool, dtype=np.float64).reshape(3),
        spoon_b=ee_pos + R_target @ np.asarray(spoon_b_offset_tool, dtype=np.float64).reshape(3),
    )
    return target

def set_last_ladle_target_to_pose_posture(targets, R_pose, spoon_a_offset_tool, spoon_b_offset_tool, suffix):
    if not targets or R_pose is None:
        return
    target = targets[-1]
    target["name"] = str(target["name"]) + str(suffix)
    update_ladle_target_geometry(target, R_pose, spoon_a_offset_tool, spoon_b_offset_tool)

def make_ladle_pose_target(name, position, R_target, spoon_a_offset_tool, spoon_b_offset_tool):
    ee_pos = np.asarray(position, dtype=np.float64).reshape(3)
    target = {
        "name": str(name),
        "target_position": ee_pos,
        "spoon_b_bottom_dist_m": np.nan,
    }
    return update_ladle_target_geometry(target, R_target, spoon_a_offset_tool, spoon_b_offset_tool)

def load_recorded_pose(path, point, base_to_world_z):
    if path is None or not Path(path).exists():
        return None
    payload = load_json(path)
    point = str(point).lower().replace(".", "_")
    pose = payload.get(f"{point}_pose_base_m_rad")
    if pose is None:
        selected = payload.get("selected") or {}
        pose = selected.get("tcp_pose_base_m_rad")
    if pose is None:
        pos = payload.get(f"{point}_position_base_m")
        if pos is None:
            return None
        pose = [*pos, 0.0, 0.0, 0.0]
    arr = np.asarray(pose, dtype=np.float64).reshape(-1)
    if arr.shape[0] < 6 or not np.all(np.isfinite(arr[:6])):
        return None
    return {
        "position": arr[:3] + np.array([0.0, 0.0, float(base_to_world_z)], dtype=np.float64),
        "R": rotvec_to_matrix(arr[3:6]),
        "path": str(path),
    }

class SceneRuntime:
    def __init__(self, config: SceneConfig):
        self.config = config

    def repair_left_bowl_payload(self, stage):
        """修正場景中失效的絕對 payload 路徑。"""
        left_bowl_path = "/World/left_bowl"
        left_bowl_prim = stage.GetPrimAtPath(left_bowl_path)
        if not left_bowl_prim.IsValid():
            print(f"[StageLoad][WARN] missing {left_bowl_path}; cannot load left bowl")
            return

        bowl_asset_path = (
            Path(self.config.root_path)
            / "scene_assets_2arm_new"
            / "assets"
            / "bowl_with_noodle_wo_physics"
            / "bowl_with_noodle.usdc"
        )
        if not bowl_asset_path.is_file():
            print(f"[StageLoad][WARN] left-bowl asset not found: {bowl_asset_path}")
            return

        payloads = left_bowl_prim.GetPayloads()
        payloads.ClearPayloads()
        payloads.AddPayload(str(bowl_asset_path))
        left_bowl_prim.Load()
        print(f"[StageLoad] repaired {left_bowl_path} payload: {bowl_asset_path}")

    def open_stage(self):
        stage_utils.open_stage(self.config.usd_path)
        print(f"[Info] Scene loaded: {self.config.usd_path}")
        stage = omni.usd.get_context().get_stage()
        self.repair_left_bowl_payload(stage)
        stage = wait_for_stage_loaded()
        return stage

    def resolve_target_prim_paths(self, stage):
        matches = {name: [] for name in self.config.ros_target_prim_names}
        for prim in stage.Traverse():
            name = prim.GetName()
            if name in matches:
                matches[name].append(str(prim.GetPath()))

        explicit_paths = {
            "bowl_with_noodle": "/World/right_bowl/bowl_with_noodle",
        }

        resolved = {}
        for name, paths in matches.items():
            explicit_path = explicit_paths.get(name)
            if explicit_path is not None:
                if not stage.GetPrimAtPath(explicit_path).IsValid():
                    raise RuntimeError(
                        f"Configured target prim is missing in two-bowl scene: "
                        f"{name} -> {explicit_path}"
                    )
                resolved[name] = explicit_path
                print(f"[ROS][MAP] explicit two-bowl target '{name}' -> {explicit_path}")
                continue
            if len(paths) == 0:
                print(f"[ROS][MAP][WARN] target prim name not found in stage; skip: {name}")
                continue
            if len(paths) > 1:
                sorted_paths = sorted(paths, key=lambda p: (p.count("/"), len(p)))
                candidate = sorted_paths[0]
                if not all(path == candidate or path.startswith(candidate + "/") for path in sorted_paths[1:]):
                    raise RuntimeError(f"Target prim name is ambiguous in stage: {name}, paths={paths}")
                print(f"[ROS][MAP] resolved nested duplicate prim name '{name}' -> {candidate}")
                resolved[name] = candidate
                continue
            resolved[name] = paths[0]
        return resolved

    def find_left_articulation_root_path(self, stage):
        return self.find_articulation_root_path(stage, self.config.ur5e_left_prim)

    def find_right_articulation_root_path(self, stage):
        return self.find_articulation_root_path(stage, self.config.ur5e_right_prim)

    @staticmethod
    def _is_articulation_root(prim):
        if not prim.IsValid():
            return False
        schemas = [str(s) for s in prim.GetAppliedSchemas()]
        return any("ArticulationRoot" in schema for schema in schemas)

    def find_articulation_root_path(self, stage, preferred_path: str):
        preferred = stage.GetPrimAtPath(preferred_path)
        if self._is_articulation_root(preferred):
            print(f"[ArticulationRoot] {preferred_path} uses preferred root")
            return preferred_path

        found = []
        if preferred.IsValid():
            for prim in stage.Traverse():
                path = str(prim.GetPath())
                if path == preferred_path or path.startswith(preferred_path + "/"):
                    if self._is_articulation_root(prim):
                        found.append(path)

        if found:
            print(f"[ArticulationRoot][WARN] {preferred_path} is not articulation root; use {found[0]}")
            return found[0]

        if preferred.IsValid():
            print(f"[ArticulationRoot][WARN] no articulation root found below {preferred_path}")
            for prim in stage.Traverse():
                path = str(prim.GetPath())
                if path == preferred_path or path.startswith(preferred_path + "/"):
                    depth = path.count("/") - preferred_path.count("/")
                    if depth <= 2:
                        print(f"[ArticulationRoot][DBG] {path} type={prim.GetTypeName()} schemas={prim.GetAppliedSchemas()}")
        else:
            print(f"[ArticulationRoot][WARN] preferred root not found: {preferred_path}")
        return preferred_path

    def set_joint_drive(self, stage, joint_path: str, stiffness=None, damping=None, max_force=None):
        joint_prim = stage.GetPrimAtPath(joint_path)
        if not joint_prim.IsValid():
            return
        drive = UsdPhysics.DriveAPI.Get(joint_prim, "angular")
        if not drive:
            drive = UsdPhysics.DriveAPI.Apply(joint_prim, "angular")
        if stiffness is not None:
            drive.GetStiffnessAttr().Set(float(stiffness))
        if damping is not None:
            drive.GetDampingAttr().Set(float(damping))
        if max_force is not None:
            drive.GetMaxForceAttr().Set(float(max_force))

    def patch_ur5e_drives(self, stage, robot_prim_path: str):
        drive_table = [
            ("shoulder_pan_joint",  30000, 300, 3000),
            ("shoulder_lift_joint", 30000, 300, 3000),
            ("elbow_joint",         30000, 300, 3000),
            ("wrist_1_joint",        8000,  80,  800),
            ("wrist_2_joint",        8000,  80,  800),
            ("wrist_3_joint",        4000,  40,  500),
        ]
        for name, stiffness, damping, max_force in drive_table:
            joint_path = f"{robot_prim_path}/joints/{name}"
            self.set_joint_drive(stage, joint_path, stiffness=stiffness, damping=damping, max_force=max_force)

    def patch_all_ur5e_drives(self, stage):
        for prim_path in [self.config.ur5e_left_prim, self.config.ur5e_right_prim]:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                continue
            self.patch_ur5e_drives(stage, prim_path)
            print(f"[DrivePatch] applied: {prim_path}")

class ObjectPoseReceiver(Node):
    def __init__(self, stage, target_prim_paths, xy_diff_threshold: float):
        super().__init__("isaac_main_ur5e_object_pose_receiver")
        self.stage = stage
        self.target_prim_paths = dict(target_prim_paths)
        self.xy_diff_threshold = float(xy_diff_threshold)
        self.topic_to_prim = self._build_topic_to_prim()
        self.translate_ops = {}
        self.latest_xy = {}
        self.last_printed_xy = {}
        self.dirty_prims = set()
        self._subs = []

        for topic, prim_path in self.topic_to_prim.items():
            prim = self.stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise RuntimeError(f"Target prim not found: {prim_path} (topic={topic})")
            self.translate_ops[prim_path] = self._ensure_translate_op(prim)
            self._subs.append(
                self.create_subscription(PoseStamped, topic, self._make_pose_cb(topic, prim_path), 10)
            )
            print(f"[ROS][MAP] {topic} -> {prim_path}")

    def _build_topic_to_prim(self):
        mapping = {}
        for prim_name, prim_path in self.target_prim_paths.items():
            if prim_name == "egg":
                topic = "/egg/accurate_pose"
            else:
                topic = f"/{prim_name}/rough_pose"
            mapping[topic] = prim_path
        return mapping

    def _ensure_translate_op(self, prim):
        xf = UsdGeom.Xformable(prim)
        ops = list(xf.GetOrderedXformOps())
        for op in ops:
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                return op
        t_op = xf.AddXformOp(UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.PrecisionDouble, "")
        xf.SetXformOpOrder(ops + [t_op])
        return t_op

    def _make_pose_cb(self, topic, prim_path):
        def _cb(msg):
            p = msg.pose.position
            xy = np.array([float(p.x), float(p.y)], dtype=np.float32)
            self.latest_xy[prim_path] = xy
            self.dirty_prims.add(prim_path)

            last_xy = self.last_printed_xy.get(prim_path)
            should_print = (
                last_xy is None
                or float(np.linalg.norm(xy - last_xy)) > self.xy_diff_threshold
            )
            if should_print:
                self.last_printed_xy[prim_path] = xy.copy()
                print(
                    f"[ROS][OBJ] {topic} -> {prim_path}: "
                    f"x={xy[0]:.4f}, y={xy[1]:.4f}"
                )
        return _cb

    def spin_and_apply(self):
        rclpy.spin_once(self, timeout_sec=0.0)
        if len(self.dirty_prims) == 0:
            return
        for prim_path in tuple(self.dirty_prims):
            xy = self.latest_xy[prim_path]
            current = self.translate_ops[prim_path].Get()
            z = float(current[2]) if current is not None else 0.0
            self.translate_ops[prim_path].Set(
                Gf.Vec3d(float(xy[0]), float(xy[1]), z)
            )
        self.dirty_prims.clear()

@dataclass
class SceneStartupResult:
    stage: object
    world: object
    target_prim_paths: dict
    object_pose_receiver: ObjectPoseReceiver

class SceneStartupRuntime:
    def __init__(self, config: DualArmConfig, scene_runtime: SceneRuntime):
        self.config = config
        self.scene_runtime = scene_runtime

    def build(self):
        stage, world = self._open_world()
        target_prim_paths, object_pose_receiver = self._create_ros_object_pose_receiver(stage)
        self._patch_drives_if_enabled(stage)
        return SceneStartupResult(
            stage=stage,
            world=world,
            target_prim_paths=target_prim_paths,
            object_pose_receiver=object_pose_receiver,
        )

    def _open_world(self):
        stage = self.scene_runtime.open_stage()
        world = World.instance() if World.instance() else World()
        world.initialize_physics()
        return stage, world

    def _create_ros_object_pose_receiver(self, stage):
        target_prim_paths = self.scene_runtime.resolve_target_prim_paths(stage)
        print(
            "[ROS] dual-arm DDS "
            f"domain={os.environ.get('ROS_DOMAIN_ID', '0')} "
            f"rmw={os.environ.get('RMW_IMPLEMENTATION', 'default')}",
            flush=True,
        )
        rclpy.init()
        object_pose_receiver = ObjectPoseReceiver(
            stage,
            target_prim_paths,
            xy_diff_threshold=self.config.shared.object_pose_print_xy_diff_threshold,
        )
        return target_prim_paths, object_pose_receiver

    def _patch_drives_if_enabled(self, stage):
        if self.config.shared.enable_drive_patch:
            self.scene_runtime.patch_all_ur5e_drives(stage)

class RightLadleStage(Enum):
    INIT = auto()
    SCOOP = auto()
    POUR = auto()
    RETREAT = auto()

class ReachHold:
    def __init__(self, tol=0.015, hold_sec=0.2):
        self.tol = tol
        self.hold_sec = hold_sec
        self.hold_time = 0.0
        self._last_wall_t = None

    def reset(self):
        self.hold_time = 0.0
        self._last_wall_t = None

    def update(self, target_pos, ee_pos):
        now = time.perf_counter()
        if self._last_wall_t is None:
            self._last_wall_t = now
            return False

        dt = now - self._last_wall_t
        self._last_wall_t = now

        d = float(np.linalg.norm(target_pos - ee_pos))
        if d <= self.tol + 1e-6:
            self.hold_time += max(dt, 1e-3)
        else:
            self.hold_time = 0.0

        return self.hold_time >= self.hold_sec

class RobotController:
    """右湯勺使用的機器人、RMPflow 與關節命令核心。"""

    def __init__(
        self,
        name,
        prim_path,
        world: World,
        rmpflow_base_dir: Path,
        urdf_filename: str,
        robot_desc_yaml: str,
        rmpflow_yaml: str,
        ee_frame_name: str = "wrist_3_link",
        zxpe5_client=None,
    ):
        self.name = name
        self.prim_path = prim_path
        self.zxpe5_client = zxpe5_client
        self.latest_arm6_cmd = None
        self.robot = SingleArticulation(prim_path=prim_path, name=name)
        world.scene.add(self.robot)
        self.robot.initialize()
        self.robot.post_reset()
        base_dir = Path(rmpflow_base_dir)
        self.rmpflow = RmpFlow(
            robot_description_path=str(base_dir / robot_desc_yaml),
            urdf_path=str(base_dir / urdf_filename),
            rmpflow_config_path=str(base_dir / rmpflow_yaml),
            end_effector_frame_name=ee_frame_name,
            maximum_substep_size=0.003,
        )
        self.policy = ArticulationMotionPolicy(self.robot, self.rmpflow)
        self.rmpflow.update_world()

    def _set_rmpflow_target(self, target_position, target_orientation):
        self.rmpflow.set_end_effector_target(
            target_position=target_position,
            target_orientation=target_orientation,
        )
        self.rmpflow.update_world()

    def _safe_release_vacuum(self, reason="", force=False):
        if self.zxpe5_client is None:
            return False
        try:
            self.zxpe5_client.release()
            if reason:
                print(f"[{self.name}][ZXPE5] release ({reason})")
            return True
        except Exception as exc:
            print(f"[{self.name}][ZXPE5] release failed ({reason}): {exc}")
            return False

class RightLadlePlanRunner:
    def __init__(
        self,
        robot_controller: RobotController,
        ee_prim_path: str,
        base_to_world_z: float,
        config: RightArmConfig = None,
        root_path: Path = None,
    ):
        default_config = create_default_dual_arm_config() if config is None or root_path is None else None
        self.ctrl = robot_controller
        self.ee_prim_path = ee_prim_path
        self.base_to_world_z = float(base_to_world_z)
        self.config = config if config is not None else default_config.right
        self.path_tools = RightLadlePathTools(root_path if root_path is not None else default_config.scene.root_path)
        self.profiles = {}
        self.path_indices = {}
        self.targets = []
        self.index = 0
        self.active = False
        self.phase_start = time.perf_counter()
        self.last_print = 0.0
        self.spoon_a_offset_tool = None
        self.spoon_b_offset_tool = None
        self.home_target = None
        self.finish_pose_records = None
        self.post_reach_start = None
        self.reach = ReachHold(tol=self.config.ladle_reach_tol_m, hold_sec=0.2)
        self.current_food = None
        self.stage = RightLadleStage.INIT
        self.last_stage_print = None
        self.move_from_name = "START"
        self.move_target_index = None
        self.ru_sequence_active = False
        self.ru_transition_wait_until = None
        self.plc_p9_5_completed_food = None
        self.shutdown_recovery_mode = None
        self.shutdown_recovery_motion_complete = False
        self.shutdown_recovery_ready_for_restart = False
        self.shutdown_recovery_home_reach = ReachHold(
            tol=float(self.config.ladle_reach_tol_m), hold_sec=0.2
        )

    @staticmethod
    def _canonical_food(food: str):
        name = str(food).strip().lower()
        return "scallion" if name == "onion" else name

    def supported_foods(self):
        foods = []
        for food in list(getattr(self.config, "auto_sequence", None) or []) + ["scallion", "sesame"]:
            name = self._canonical_food(food)
            if name in ("scallion", "sesame") and name not in foods:
                foods.append(name)
        return foods

    @staticmethod
    def _mark_stage(target, stage: RightLadleStage):
        target["stage"] = stage.name
        return target

    def _apply_ladle_timing(self, target, food):
        food = self._canonical_food(food)
        if food not in ("sesame", "scallion"):
            raise ValueError(f"unsupported ladle timing food: {food}")
        timing = lambda phase: getattr(self.config, f"{food}_ladle_{phase}_policy_dt")
        name = str(target.get("name", ""))
        base_name = name.rsplit("/", 1)[-1]
        stage = str(target.get("stage", ""))
        if base_name.startswith(("P0_", "P1_")):
            target["policy_dt"] = timing("entry")
        elif base_name.startswith("P7_") and not base_name.startswith("P7_5_"):
            target["policy_dt"] = timing("lift")
        elif base_name.startswith("P10_") or stage == RightLadleStage.RETREAT.name:
            target["policy_dt"] = timing("return")
        elif stage == RightLadleStage.POUR.name:
            target["policy_dt"] = timing("pour")
        else:
            target["policy_dt"] = timing("scoop")

        if "P7_5_base_ry_plus_" in name:
            target["policy_dt"] = timing("p7_5")
        elif "P7_5_" in name:
            target["policy_dt"] = timing("p7_5")
        elif "P9_5_" in name:
            target["policy_dt"] = timing("shake")
        elif "P8_5_recorded_pose" in name or "P9_recorded_pose" in name or "P9_tool_minus_ry_" in name:
            target["policy_dt"] = timing("p8_5_p9")
        elif "P8_recorded_pose" in name:
            target["policy_dt"] = timing("p8_p9")
        return target

    def load_profiles(self):
        for food in self.supported_foods():
            try:
                self.profiles[food] = self._load_food_paths(food)
                self.path_indices[food] = 0
                print(f"[DualLadle] loaded {food}: paths={len(self.profiles[food])}")
            except Exception as exc:
                self.profiles[food] = []
                print(f"[DualLadle][WARN] {food} plan not loaded: {exc}")

    def _load_finish_pose_records(self):
        if self.finish_pose_records is None:
            specs = {
                "p8": ("ladle_p8_pose_20260723_112411.json", "p8"),
                "p8_5": ("ladle_p8_5_pose_20260723_112511.json", "p8_5"),
                "p9": ("ladle_p9_pose_20260723_112710.json", "p9"),
                "home": ("ladle_home_pose_20260721_141409.json", "home"),
            }
            config_dir = self.path_tools.root_path / "config"
            self.finish_pose_records = {
                key: load_recorded_pose(config_dir / filename, label, self.base_to_world_z)
                for key, (filename, label) in specs.items()
            }
        return self.finish_pose_records

    def _load_food_paths(self, food: str):
        plan_override = str(getattr(self.config, f"{food}_plan_path", "") or "").strip()
        if plan_override:
            plan_path = Path(plan_override).expanduser()
            if not plan_path.exists():
                raise RuntimeError(f"{food} explicit plan not found: {plan_path}")
        else:
            plan_path = self.path_tools.latest_json_from_patterns(
                self.path_tools.food_latest_patterns("ladle_scoop_plan", food)
            )
        if plan_path is None:
            raise RuntimeError(f"no ladle_scoop_plan JSON for {food}")
        plan = self.path_tools.load_json(plan_path)
        entry_path = Path(plan.get("entry_path", "")).expanduser()
        if not entry_path.exists():
            entry_path = self.path_tools.latest_json_from_patterns(
                self.path_tools.food_latest_patterns("ladle_entry_pose", food)
            )
        if entry_path is None or not entry_path.exists():
            raise RuntimeError(f"no ladle_entry_pose JSON for {food}")
        entry = self.path_tools.load_json(entry_path)
        samples = list(entry.get("samples") or [])
        selected = entry.get("selected") or (samples[-1] if samples else None)
        if selected is None:
            raise RuntimeError(f"entry has no selected/sample: {entry_path}")
        entry_by_index = {
            int(sample.get("index", i + 1)): sample
            for i, sample in enumerate(samples)
        }
        spoon_a_offset = np.asarray(entry.get("spoon_a_offset_tool_m", [0.0, 0.0, 0.166]), dtype=np.float64).reshape(3)
        spoon_b_offset = np.asarray(entry["spoon_b_offset_tool_m"], dtype=np.float64).reshape(3)
        if self.spoon_a_offset_tool is None:
            self.spoon_a_offset_tool = spoon_a_offset
            self.spoon_b_offset_tool = spoon_b_offset

        finish_records = self._load_finish_pose_records()
        home_record = finish_records["home"]
        if home_record is not None and self.home_target is None:
            self.home_target = make_ladle_pose_target(
                "HOME_WAIT_recorded_pose",
                home_record["position"],
                home_record["R"],
                spoon_a_offset,
                spoon_b_offset,
            )
            self._mark_stage(self.home_target, RightLadleStage.INIT)
            self.home_target["policy_dt"] = RIGHT_LADLE_IDLE_POLICY_DT
            print(
                f"[DualLadle] idle home target={np.round(self.home_target['target_position'], 4).tolist()}",
                flush=True,
            )

        path_payloads = list(plan.get("paths") or [])
        if not path_payloads:
            path_payloads = [
                {
                    "name": "path_legacy",
                    "entry_sample_index": int(selected.get("index", 1)),
                    "tip_bottom_clearance_mm": float((plan.get("plan_parameters") or {}).get("tip_bottom_clearance_m", 0.002)) * 1000.0,
                    "waypoints": plan.get("waypoints", []),
                }
            ]

        paths = []
        for path_i, path in enumerate(path_payloads):
            sample_index = int(path.get("entry_sample_index", selected.get("index", 1)))
            sample = entry_by_index.get(sample_index, selected)
            entry_R = build_entry_rotation(sample)
            targets = []
            path_name = str(path.get("name", f"path_{path_i + 1}"))
            clearance_mm = float(path.get("tip_bottom_clearance_mm", np.nan))
            p7_base_minus_x_m = path.get("p7_base_minus_x_m")
            p7_5_runtime_base_x_shift_m = float(self.config.ladle_p7_5_base_x_shift_m)
            if p7_base_minus_x_m is not None:
                retreat_mm = float(p7_base_minus_x_m) * 1000.0
                retreat_groups = ((50.0, 0.100), (30.0, 0.070), (0.0, 0.050))
                p7_5_runtime_base_x_shift_m = next(
                    shift for minimum, shift in retreat_groups if retreat_mm >= minimum
                )
            p7_5_runtime_base_x_shift_m += float(LADLE_P7_5_RUNTIME_BASE_X_CORRECTION_M)
            for wp in path.get("waypoints", []):
                if food == "scallion" and str(wp.get("name", "")).startswith("P7_5_"):
                    continue
                target = waypoint_to_ladle_target(
                    wp,
                    entry_R,
                    spoon_a_offset,
                    spoon_b_offset,
                    self.base_to_world_z,
                    safety_lift_z=self.config.ladle_safety_lift_z,
                )
                target["path_name"] = path_name
                target["entry_sample_index"] = sample_index
                target["tip_bottom_clearance_mm"] = clearance_mm
                target["p7_base_minus_x_m"] = p7_base_minus_x_m
                target["p7_5_runtime_base_x_shift_m"] = p7_5_runtime_base_x_shift_m
                if str(target["name"]).startswith("P7_5_") and "return_center" not in str(target["name"]):
                    apply_ladle_base_ry_offset(
                        target,
                        self.config.ladle_p7_5_base_ry_deg,
                        spoon_a_offset,
                        spoon_b_offset,
                    )
                    translate_ladle_target(target, "x", p7_5_runtime_base_x_shift_m)
                    translate_ladle_target(target, "z", LADLE_P7_5_RUNTIME_BASE_Z_CORRECTION_M)
                target["name"] = f"{path_name}/{target['name']}"
                self._mark_stage(target, RightLadleStage.SCOOP)
                self._apply_ladle_timing(target, food)
                targets.append(target)
            if targets:
                self._append_finish_targets(
                    food, targets, finish_records, (spoon_a_offset, spoon_b_offset)
                )
                paths.append(targets)
        print(
            f"[DualLadle] {food} plan={plan_path} entry={entry_path} "
            f"base_to_world_z={self.base_to_world_z:.3f} safety_lift_z={self.config.ladle_safety_lift_z:.3f}"
        )
        return paths

    def _make_finish_pose_target(self, name, position, rotation, stage, food, spoon_offsets):
        target = make_ladle_pose_target(name, position, rotation, *spoon_offsets)
        self._mark_stage(target, stage)
        self._apply_ladle_timing(target, food)
        return target

    def _append_finish_targets(self, food, targets, finish_records, spoon_offsets):
        if not targets:
            return
        p8_record, p8_5_record, p9_record, home_record = (
            finish_records[name] for name in ("p8", "p8_5", "p9", "home")
        )
        spoon_a_offset, spoon_b_offset = spoon_offsets
        if p8_record is None and home_record is None:
            print("[DualLadle][WARN] no P8/home record; use plan scoop waypoints only")
            return

        last = targets[-1]
        path_name = last.get("path_name")
        sample_index = last.get("entry_sample_index")
        clearance_mm = last.get("tip_bottom_clearance_mm")

        posture_record = p8_record if p8_record is not None else home_record
        posture_suffix = "_p8_recorded_posture" if p8_record is not None else "_home_forward_posture"
        set_last_ladle_target_to_pose_posture(
            targets, posture_record["R"], spoon_a_offset, spoon_b_offset, posture_suffix
        )
        p8_position = posture_record["position"]
        R_p8 = (
            posture_record["R"]
            if p8_record is not None
            else np.asarray(last["R_target"], dtype=np.float64).reshape(3, 3)
        )

        p8 = self._make_finish_pose_target(
            "P8_recorded_pose", p8_position, R_p8, RightLadleStage.POUR, food, spoon_offsets
        )
        finish_targets = [p8]

        if p8_5_record is not None:
            finish_targets.append(self._make_finish_pose_target(
                "P8_5_recorded_pose", p8_5_record["position"], p8_5_record["R"],
                RightLadleStage.POUR, food, spoon_offsets,
            ))

        if p9_record is not None:
            p9_name = "P9_recorded_pose"
            p9_position = p9_record["position"]
            R_p9 = p9_record["R"]
        else:
            R_delta = rotation_matrix_axis_angle(
                [0.0, 1.0, 0.0],
                -np.deg2rad(float(self.config.ladle_p9_tool_minus_ry_deg)),
            )
            R_p9 = R_p8 @ R_delta
            p9_position = np.asarray(p8_position, dtype=np.float64).reshape(3) + np.array(
                [float(self.config.ladle_p9_base_x_shift_m), 0.0, 0.0],
                dtype=np.float64,
            )
            p9_name = (
                f"P9_tool_minus_ry_{float(self.config.ladle_p9_tool_minus_ry_deg):.0f}deg_"
                f"base_plus_x_{float(self.config.ladle_p9_base_x_shift_m) * 1000.0:.0f}mm"
            )
        p9 = self._make_finish_pose_target(
            p9_name, p9_position, R_p9, RightLadleStage.POUR, food, spoon_offsets
        )
        finish_targets.append(p9)

        shake_cycles = max(int(self.config.ladle_p9_shake_cycles), 0)
        shake_ry_deg = (
            self.config.ladle_scallion_p9_5_base_ry_deg
            if str(food).strip().lower() == "scallion"
            else self.config.ladle_shake_base_ry_deg
        )
        for cycle in range(1, shake_cycles + 1):
            p9_5 = make_ladle_pose_target(
                f"P9_5_base_ry_plus_{cycle:02d}",
                p9_position,
                R_p9,
                spoon_a_offset,
                spoon_b_offset,
            )
            apply_ladle_base_ry_offset(p9_5, shake_ry_deg, spoon_a_offset, spoon_b_offset)
            translate_ladle_target(p9_5, "x", self.config.ladle_p9_5_base_x_shift_m)
            self._mark_stage(p9_5, RightLadleStage.POUR)
            self._apply_ladle_timing(p9_5, food)
            p9_5["post_reach_hold_sec"] = self.config.ladle_p9_5_hold_sec
            finish_targets.append(p9_5)

        if home_record is not None:
            finish_targets.append(self._make_finish_pose_target(
                "P10_return_home_position_posture", home_record["position"], home_record["R"],
                RightLadleStage.RETREAT, food, spoon_offsets,
            ))

        for target in finish_targets:
            target["path_name"] = path_name
            target["entry_sample_index"] = sample_index
            target["tip_bottom_clearance_mm"] = clearance_mm
            targets.append(target)

    def start(self, food: str):
        food = self._canonical_food(food)
        paths = self.profiles.get(food) or []
        if not paths:
            print(f"[DualLadle][WARN] no loaded paths for {food}")
            return
        idx = self.path_indices.get(food, 0) % len(paths)
        self.path_indices[food] = self.path_indices.get(food, 0) + 1
        self.targets = paths[idx]
        self.index = 0
        self.active = True
        self.phase_start = time.perf_counter()
        self.post_reach_start = None
        self.reach.reset()
        self.last_print = 0.0
        self.current_food = food
        self.plc_p9_5_completed_food = None
        self.stage = RightLadleStage.INIT
        self.last_stage_print = None
        self.move_from_name = "START"
        self.move_target_index = None
        stage_counts = {}
        for target in self.targets:
            stage = str(target.get("stage", "UNKNOWN"))
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        print(
            f"[DualLadle] start {food} path {idx + 1}/{len(paths)} "
            f"waypoints={len(self.targets)} stages={stage_counts}"
        )

    @staticmethod
    def _is_p7_target(target):
        """只判定 P7，不包含 P7.5。"""
        name = str(target.get("name", "")).rsplit("/", 1)[-1]
        return name.startswith("P7_") and not name.startswith("P7_5_")

    def snapshot_shutdown_recovery(self, *, announce=True):
        """PLC 停止前保存右湯勺路徑與 P7 狀態。"""
        if not self.active or not self.targets or self.current_food not in ("sesame", "scallion"):
            return None
        target_count = len(self.targets)
        current_index = int(np.clip(self.index, 0, target_count - 1))
        p7_index = next(
            (idx for idx, target in enumerate(self.targets) if self._is_p7_target(target)),
            None,
        )
        p7_completed = bool(p7_index is not None and current_index > p7_index)
        snapshot = {
            "food": str(self.current_food),
            "targets": copy.deepcopy(self.targets),
            "current_index": current_index,
            "p7_index": p7_index,
            "p7_completed": p7_completed,
            "ru_sequence_active": bool(self.ru_sequence_active),
            "current_target": str(self.targets[current_index].get("name", "")),
        }
        branch = "finish" if p7_completed else "reverse"
        if announce:
            print(
                f"[PLC][SHUTDOWN][RIGHT] checkpoint food={snapshot['food']} "
                f"target={snapshot['current_target']} index={current_index + 1}/{target_count} "
                f"P7_index={None if p7_index is None else p7_index + 1} branch={branch}",
                flush=True,
            )
        return snapshot

    def start_shutdown_recovery(self, snapshot):
        """從保存的右湯勺路徑開始恢復。"""
        if not snapshot or self.home_target is None:
            print("[PLC][SHUTDOWN][RIGHT][ERROR] no right-ladle checkpoint/home target for recovery", flush=True)
            return False
        original_targets = copy.deepcopy(snapshot["targets"])
        current_index = int(np.clip(snapshot["current_index"], 0, len(original_targets) - 1))
        if bool(snapshot.get("p7_completed", False)):
            mode = "finish_after_P7"
            recovery_targets = original_targets[current_index:]
            self.ru_sequence_active = bool(
                snapshot.get("ru_sequence_active", False) and snapshot.get("food") == "sesame"
            )
        else:
            mode = "reverse_before_P7"
            recovery_targets = list(reversed(original_targets[:current_index]))
            home = copy.deepcopy(self.home_target)
            home["name"] = "PLC_shutdown_reverse_to_home"
            home["post_reach_hold_sec"] = 0.0
            recovery_targets.append(home)
            self.ru_sequence_active = False

        if not recovery_targets:
            recovery_targets = [copy.deepcopy(self.home_target)]
        self.targets = recovery_targets
        self.index = 0
        self.active = True
        self.current_food = str(snapshot["food"])
        self.phase_start = time.perf_counter()
        self.post_reach_start = None
        self.reach.reset()
        self.last_print = 0.0
        self.stage = RightLadleStage.INIT
        self.last_stage_print = None
        self.move_from_name = "PLC_SHUTDOWN_RELEASE"
        self.move_target_index = None
        self.shutdown_recovery_mode = mode
        self.shutdown_recovery_motion_complete = False
        self.shutdown_recovery_ready_for_restart = False
        self.shutdown_recovery_home_reach.reset()
        print(
            f"[PLC][SHUTDOWN][RIGHT] recovery start mode={mode} food={self.current_food} "
            f"waypoints={len(self.targets)} dt={RIGHT_LADLE_RECOVERY_POLICY_DT:.3f}s "
            f"first={self.targets[0].get('name', '')}",
            flush=True,
        )
        return True

    def _finish_active_path(self):
        self.active = False
        if self.ru_sequence_active and self.current_food == "scallion":
            self.ru_sequence_active = False
            self.ru_transition_wait_until = None
        completed_food = self.current_food
        self.current_food = None
        self.stage = RightLadleStage.INIT
        print("[DualLadle] done")
        if self.shutdown_recovery_mode is not None:
            self.shutdown_recovery_motion_complete = True
            self.shutdown_recovery_home_reach.reset()
            print(
                f"[PLC][SHUTDOWN][RIGHT] path complete ({self.shutdown_recovery_mode}); "
                "holding Home before watchdog restart",
                flush=True,
            )

    def start_ru_sequence(self):
        """Y：先執行芝麻，再切換蔥。"""
        if self.active:
            print("[DualLadle][RU] ignored Y: right arm is already executing a path", flush=True)
            return
        self.ru_sequence_active = True
        self.ru_transition_wait_until = None
        print("[DualLadle][RU] start R→U sequence: sesame then scallion", flush=True)
        self.start("sesame")

    # 套用右湯勺關節命令並保存提供給真實右臂的六軸命令。
    def _apply_articulation_action(self, policy_dt):
        action = self.ctrl.policy.get_next_articulation_action(policy_dt)
        jp = getattr(action, "joint_positions", None)
        if jp is None:
            jp = self.ctrl.robot.get_joint_positions().copy()
        else:
            jp = np.asarray(jp, dtype=np.float32).copy()
        action.joint_positions = jp
        self.ctrl.robot.get_articulation_controller().apply_action(action)
        self.ctrl.latest_arm6_cmd = np.asarray(jp[:6], dtype=np.float64).copy()

    # 最後一個蔥 P9.5 完成時通知 PLC 後續流程。
    def _mark_scallion_p9_5_complete(self, target):
        if (
            self.current_food == "scallion"
            and target["name"].rsplit("/", 1)[-1].startswith("P9_5_")
            and not any(
                str(candidate.get("name", "")).rsplit("/", 1)[-1].startswith("P9_5_")
                for candidate in self.targets[self.index + 1:]
            )
        ):
            self.plc_p9_5_completed_food = "scallion"
            print("[DualLadle][PLC] scallion P9.5 completed", flush=True)

    # 統一完成目前 waypoint、重設到位狀態並切換下一點。
    def _advance_target(self, target, mark_p9_5=False):
        if mark_p9_5:
            self._mark_scallion_p9_5_complete(target)
        self.move_from_name = str(target["name"])
        self.index += 1
        self.post_reach_start = None
        self.reach.reset()
        if self.index >= len(self.targets):
            self._finish_active_path()

    def update(self, stage_ref, xcache, dt=RIGHT_LADLE_IDLE_POLICY_DT):
        idle_home = not self.active
        if idle_home:
            if self.home_target is None:
                return
            target = self.home_target
        elif not self.targets:
            return
        else:
            target = self.targets[min(self.index, len(self.targets) - 1)]
        target_stage_name = str(target.get("stage", RightLadleStage.INIT.name))
        target_stage = RightLadleStage.__members__.get(target_stage_name, RightLadleStage.INIT)
        if target_stage != self.stage or self.last_stage_print != target_stage:
            self.stage = target_stage
            self.last_stage_print = target_stage
            print(
                f"[DualLadle][Stage] {self.current_food or 'idle'} -> {self.stage.name} "
                f"target={target.get('name', '')}",
                flush=True,
            )
        ee_prim = stage_ref.GetPrimAtPath(self.ee_prim_path)
        M_ee = xcache.GetLocalToWorldTransform(ee_prim)
        ee_pos = np.array(M_ee.ExtractTranslation(), dtype=np.float64)
        ee_R = gf_matrix_to_rotation(M_ee)
        self.ctrl._set_rmpflow_target(target["target_position"], target["target_orientation"])

        ee_err = float(np.linalg.norm(np.asarray(target["target_position"], dtype=np.float64) - ee_pos))
        now = time.perf_counter()
        if (
            self.ru_sequence_active
            and self.current_food == "sesame"
            and str(target.get("name", "")).endswith("P10_return_home_position_posture")
        ):
            if self.ru_transition_wait_until is None:
                self.ru_transition_wait_until = now + RIGHT_RU_SESAME_TO_SCALLION_DELAY_SEC
                print(
                    "[DualLadle][RU] sesame return-home started; switch to scallion after "
                    f"{RIGHT_RU_SESAME_TO_SCALLION_DELAY_SEC:.3f}s without waiting for home reach",
                    flush=True,
                )
            elif now >= self.ru_transition_wait_until:
                self.ru_transition_wait_until = None
                print("[DualLadle][RU] switch R→U: start scallion", flush=True)
                self.start("scallion")
                return
        if not idle_home and self.move_target_index != self.index:
            self.move_target_index = self.index
            self.phase_start = now
            print(
                f"[DualLadle][MoveTime] {self.move_from_name} -> {target['name']} start",
                flush=True,
            )
        policy_dt = (
            float(RIGHT_LADLE_RECOVERY_POLICY_DT)
            if self.shutdown_recovery_mode is not None
            else float(target.get("policy_dt", dt))
        )
        if now - self.last_print >= self.config.ladle_status_print_sec:
            self.last_print = now
            spoon_msg = ""
            if self.spoon_a_offset_tool is not None and self.spoon_b_offset_tool is not None:
                spoon_a = ee_pos + ee_R @ self.spoon_a_offset_tool
                spoon_b = ee_pos + ee_R @ self.spoon_b_offset_tool
                spoon_msg = (
                    f" Aerr={np.linalg.norm(target['spoon_a'] - spoon_a) * 1000.0:.1f}mm"
                    f" Berr={np.linalg.norm(target['spoon_b'] - spoon_b) * 1000.0:.1f}mm"
                )
            print(
                f"[DualLadle] {'home' if idle_home else f'wp {self.index + 1}/{len(self.targets)}'} {target['name']} "
                f"stage={self.stage.name} "
                f"ee_err={ee_err * 1000.0:.1f}mm "
                f"target={np.round(target['target_position'], 4).tolist()} "
                f"actual={np.round(ee_pos, 4).tolist()}{spoon_msg}",
                flush=True,
            )

        if idle_home:
            self._apply_articulation_action(policy_dt)
            if self.shutdown_recovery_motion_complete:
                if self.shutdown_recovery_home_reach.update(
                    np.asarray(target["target_position"], dtype=np.float64), ee_pos
                ):
                    if not self.shutdown_recovery_ready_for_restart:
                        self.shutdown_recovery_ready_for_restart = True
                        print("[PLC][SHUTDOWN][RIGHT] Home reached; recovery ready for watchdog restart", flush=True)
            return

        elapsed = now - self.phase_start
        hold_sec = float(target.get("post_reach_hold_sec", 0.0) or 0.0)
        reached = self.reach.update(np.asarray(target["target_position"], dtype=np.float64), ee_pos)
        if self.post_reach_start is not None:
            hold_elapsed = now - self.post_reach_start
            if hold_elapsed >= hold_sec:
                print(f"[DualLadle] hold done {target['name']}")
                self._advance_target(target, mark_p9_5=True)
        elif reached or elapsed >= self.config.ladle_phase_timeout_sec:
            timed_out = elapsed >= self.config.ladle_phase_timeout_sec and ee_err > self.config.ladle_reach_tol_m
            if timed_out:
                print(
                    f"[DualLadle][MoveTime] {self.move_from_name} -> {target['name']} "
                    f"timeout move={elapsed:.3f}s ee_err={ee_err * 1000.0:.1f}mm; continue"
                )
                self._advance_target(target)
            else:
                print(
                    f"[DualLadle][MoveTime] {self.move_from_name} -> {target['name']} "
                    f"reached move={elapsed:.3f}s",
                    flush=True,
                )
                if hold_sec > 0.0:
                    print(f"[DualLadle] reached {target['name']}; hold {hold_sec:.1f}s")
                    self.post_reach_start = now
                else:
                    print(f"[DualLadle] reached {target['name']}")
                    self._advance_target(target, mark_p9_5=True)

        self._apply_articulation_action(policy_dt)

class RightArmRuntime:
    def __init__(
        self,
        config: RightArmConfig,
        scene_config: SceneConfig,
        shared_config: SharedMotionConfig,
    ):
        self.config = config
        self.scene_config = scene_config
        self.shared_config = shared_config

    def initial_joint_positions_from_rtde(self, rtde_r):
        joints = self.config.fallback_joint_positions.copy()
        if rtde_r is None:
            print("[RTDE][right] no receive interface; using fallback Isaac joint init")
            return joints
        try:
            actual_q = rtde_r.getActualQ()
            if actual_q is not None and len(actual_q) >= 6:
                joints[:6] = np.array(actual_q[:6], dtype=np.float32)
                print("[RTDE][right] Isaac joint init from getActualQ")
        except Exception as exc:
            print(f"[RTDE][right] getActualQ failed; using fallback Isaac joint init: {exc}")
        return joints

    def create_controller(self, world, robot_prim_path: str):
        return RobotController(
            name="ur5e_right",
            prim_path=robot_prim_path,
            world=world,
            rmpflow_base_dir=self.scene_config.rmpflow_gripper_dir,
            zxpe5_client=None,
            urdf_filename="ur5e_right_6dof_root_joint_revise.urdf",
            robot_desc_yaml="ur5e_right_6dof_collision.yaml",
            rmpflow_yaml="ur5e_right_6dof_rmpflow.yaml",
            ee_frame_name="wrist_3_link",
        )

    def create_ladle_runner(self, controller):
        runner = RightLadlePlanRunner(
            controller,
            self.scene_config.ee_right_prim,
            base_to_world_z=self.shared_config.dual_base_to_world_z,
            config=self.config,
            root_path=self.scene_config.root_path,
        )
        runner.load_profiles()
        return runner

class DisabledLeftArm:
    name = "left_disabled"
    robot = None
    controller = None
    perception = None
    latest_arm6_cmd = None

    def pose_locked(self):
        return False

    def start(self, food: str):
        print(f"[LeftArmSystem] ignored {food}: left arm disabled", flush=True)

    def cancel(self):
        return None

    def update(self, *_args, **_kwargs):
        self.latest_arm6_cmd = None

class LeftArmRuntime:
    def __init__(
        self,
        config: LeftArmConfig,
        scene_config: SceneConfig,
        shared_config: SharedMotionConfig,
        manual_module=None,
    ):
        self.config = config
        self.scene_config = scene_config
        self.shared_config = shared_config
        self.manual = sys.modules[__name__] if manual_module is None else manual_module

    def initial_joint_positions_from_rtde(self, rtde_r, label: str = "left"):
        joints = self.config.fallback_joint_positions.copy()
        if rtde_r is None:
            print(f"[RTDE][{label}] no receive interface; using fallback Isaac joint init")
            return joints
        try:
            actual_q = rtde_r.getActualQ()
            if actual_q is not None and len(actual_q) >= 6:
                joints[:6] = np.array(actual_q[:6], dtype=np.float32)
                print(f"[RTDE][{label}] Isaac joint init from getActualQ")
        except Exception as exc:
            print(f"[RTDE][{label}] getActualQ failed; using fallback Isaac joint init: {exc}")
        return joints

    def configure_manual_module(self):
        if self.config.backend != "manual":
            raise ValueError(f"unsupported left arm backend: {self.config.backend}")
        self.manual.HOME_XY = self.config.home_xy
        self.manual.HOME_Z = self.config.home_z
        self.manual.UR5E_PRIM = self.scene_config.ur5e_left_prim
        self.manual.EE_PRIM = self.scene_config.ee_left_prim
        self.manual.RTDE_TCP_TO_ISAAC_Z_OFFSET = float(self.config.dual_left_root_world[2])
        self.manual.RTDE_TCP_TO_ISAAC_WORLD_OFFSET = np.array(
            [
                float(self.config.dual_left_root_world[0]),
                float(self.config.dual_left_root_world[1]),
                float(self.config.dual_left_root_world[2]),
            ],
            dtype=np.float32,
        )
        self.manual.SINGLE_TO_DUAL_WORLD_OFFSET = np.array(
            self.config.dual_left_single_world_offset,
            dtype=np.float32,
        )
        frame_transform = getattr(self.manual, "FRAME_TRANSFORM", None)
        if frame_transform is not None:
            frame_transform.configure(
                rtde_tcp_to_isaac_z_offset=float(self.config.dual_left_root_world[2]),
                rtde_tcp_to_isaac_world_offset=self.manual.RTDE_TCP_TO_ISAAC_WORLD_OFFSET,
                single_to_dual_world_offset=self.manual.SINGLE_TO_DUAL_WORLD_OFFSET,
            )
        scene_prims = getattr(self.manual, "LEFT_SCENE_PRIMS", None)
        if scene_prims is not None:
            scene_prims.ur5e = self.scene_config.ur5e_left_prim
            scene_prims.ee = self.scene_config.ee_left_prim
            scene_prims.egg_plate = self.scene_config.egg_plate_prim_path
            scene_prims.egg = self.scene_config.egg_prim_path
            scene_prims.ramen_bowl = self.scene_config.ramen_bowl_prim_path
            scene_prims.menma_bowl = self.scene_config.menma_bowl_prim_path
            scene_prims.menma = self.scene_config.menma_prim_path
        stage_sync_targets = getattr(self.manual, "LEFT_STAGE_SYNC_TARGETS", None)
        if stage_sync_targets is not None:
            if "ramen_bowl" in stage_sync_targets:
                stage_sync_targets["ramen_bowl"].prim_path = self.scene_config.ramen_bowl_prim_path
            if "menma_bowl" in stage_sync_targets:
                stage_sync_targets["menma_bowl"].prim_path = self.scene_config.menma_bowl_prim_path
            if "menma" in stage_sync_targets:
                stage_sync_targets["menma"].prim_path = self.scene_config.menma_prim_path
        self.manual.ENABLE_REAL_GRIPPER = True
        self.manual.ENABLE_RTDE_STREAM = True
        self.manual.PRE_HOME_RELEASE_TARGET_POS = np.array(
            [
                self.config.home_xy[0],
                self.config.home_xy[1],
                self.config.home_z + self.shared_config.approach_offset,
            ],
            dtype=np.float32,
        )

    def create_perception(self, object_pose_receiver):
        return self.manual.EggPlateBridge(
            object_pose_receiver,
            world_offset=self.config.dual_left_single_world_offset,
            auto_world_offset=self.config.auto_world_offset,
        )

    def create_controller(self, world, perception, robot_prim_path: str, gripper_close_fn, gripper_open_fn):
        return self.manual.MoveToEggPlateController(
            world,
            perception,
            prim_path=robot_prim_path,
            ee_prim_path=self.scene_config.ee_left_prim,
            name="ur5e_left_manual",
            rmpflow_base_dir=self.scene_config.rmpflow_gripper_dir,
            urdf_filename="ur5e_left_gripper_root_joint_revise.urdf",
            robot_description_filename="ur5e_collision_gripper.yaml",
            rmpflow_config_filename="ur5e_collision_gripper_rmpflow.yaml",
            gripper_close_fn=gripper_close_fn,
            gripper_open_fn=gripper_open_fn,
            idle_home_enabled=True,
            safe_idle_home_enabled=self.config.safe_idle_home_enabled,
            idle_home_clearance_z=(
                self.config.home_z
                + self.shared_config.approach_offset
                + self.config.safe_idle_home_clearance_extra
            ),
        )

    def create_gripper_callbacks(self, left_gripper):
        max_open_width_mm = 85.0

        def manual_width_mm_to_rtde_position(width_mm):
            opening_mm = float(np.clip(float(width_mm), 0.0, max_open_width_mm))
            close_fraction = (max_open_width_mm - opening_mm) / max_open_width_mm
            return int(round(close_fraction * 255.0)), opening_mm

        def manual_percent_to_rtde_scale(value):
            return int(round(float(np.clip(float(value), 0.0, 100.0)) * 255.0 / 100.0))

        def gripper_open():
            if left_gripper is None:
                print("[Gripper][left][manual] open skipped: no left gripper")
                return None
            return left_gripper.open()

        def gripper_close(force=60, speed=100, dis=0):
            if left_gripper is None:
                print("[Gripper][left][manual] close skipped: no left gripper")
                return None
            position, opening_mm = manual_width_mm_to_rtde_position(dis)
            rtde_speed = manual_percent_to_rtde_scale(speed)
            rtde_force = manual_percent_to_rtde_scale(force)
            print(
                "[Gripper][left][manual] "
                f"opening={opening_mm:.1f}mm -> rtde_pos={position}/255 "
                f"(close={(position / 255.0) * 100.0:.1f}%), "
                f"speed={speed}% force={force}%",
                flush=True,
            )
            return left_gripper.move(position, speed=rtde_speed, force=rtde_force)

        return gripper_close, gripper_open

    def create_system(self, controller, perception, vision_executor=None):
        return LeftArmSystem(
            controller,
            perception,
            vision_executor=vision_executor,
        )

@dataclass
class ArmStartupResult:
    left_gripper: object
    left_arm: object
    left_controller: object
    left_vision_node: object
    left_vision_executor: object
    right_controller: object
    right_ladle_runner: object

class ArmStartupRuntime:
    def __init__(
        self,
        config: DualArmConfig,
        services: RuntimeServices,
        scene_runtime: SceneRuntime,
        world,
        stage,
        target_prim_paths,
        object_pose_receiver,
    ):
        self.config = config
        self.services = services
        self.scene_runtime = scene_runtime
        self.world = world
        self.stage = stage
        self.target_prim_paths = target_prim_paths
        self.object_pose_receiver = object_pose_receiver

    def build(self):
        left_robot_prim_path = (
            self.scene_runtime.find_left_articulation_root_path(self.stage)
            if self.config.left.enabled
            else self.config.scene.ur5e_left_prim
        )
        right_robot_prim_path = self.scene_runtime.find_right_articulation_root_path(self.stage)
        left_gripper = self._create_left_gripper()

        left_runtime = LeftArmRuntime(self.config.left, self.config.scene, self.config.shared)
        if self.config.left.enabled:
            left_runtime.configure_manual_module()
        right_runtime = RightArmRuntime(
            self.config.right,
            self.config.scene,
            self.config.shared,
        )

        if self.config.left.enabled:
            left_controller, left_arm, left_vision_node, left_vision_executor = self._create_left_arm(
                left_runtime,
                left_robot_prim_path,
                left_gripper,
            )
        else:
            left_controller, left_arm = self._create_disabled_left_arm()
            left_vision_node, left_vision_executor = None, None
        right_controller = self._create_right_controller(right_runtime, right_robot_prim_path)
        print("[Startup] RobotController objects ready", flush=True)

        self._sync_initial_joints(
            left_runtime,
            right_runtime,
            left_controller,
            right_controller,
            left_robot_prim_path,
            right_robot_prim_path,
        )
        right_ladle_runner = right_runtime.create_ladle_runner(right_controller)

        return ArmStartupResult(
            left_gripper=left_gripper,
            left_arm=left_arm,
            left_controller=left_controller,
            left_vision_node=left_vision_node,
            left_vision_executor=left_vision_executor,
            right_controller=right_controller,
            right_ladle_runner=right_ladle_runner,
        )

    def _create_left_gripper(self):
        if not self.config.left.enabled:
            print("[Startup] skip left gripper client (left arm disabled)", flush=True)
            return None
        if self.config.right.right_arm_only:
            print("[Startup] skip left gripper client (RIGHT_ARM_ONLY=True)", flush=True)
            return None
        if not self.services.left_rtde_control_connected():
            print("[Startup] skip left gripper client (no left RTDE control)", flush=True)
            return None

        print("[Startup] create left gripper client ...", flush=True)
        left_gripper = self.services.make_gripper_fn(
            self.services.left_robot_ip,
            "left",
            rtde_c=self.services.rtde_left_control,
        )
        print("[Startup] left gripper client ready/skip", flush=True)
        return left_gripper

    def _create_left_arm(self, left_runtime: LeftArmRuntime, left_robot_prim_path: str, left_gripper):
        left_manual_gripper_close, left_manual_gripper_open = left_runtime.create_gripper_callbacks(left_gripper)
        left_runtime.manual._rtde_r = self.services.rtde_left_receive
        left_vision_node = left_runtime.manual.Node("isaac_test_move_to_egg_plate")
        left_vision_executor = left_runtime.manual.SingleThreadedExecutor()
        left_vision_executor.add_node(left_vision_node)
        print(
            "[ROS][left] D405 bridge uses dedicated isaac_test_move_to_egg_plate "
            "node/executor (same as standalone manual)",
            flush=True,
        )
        print("[Startup] create left MoveToEggPlateController (manual logic) ...", flush=True)
        left_perception = left_runtime.create_perception(left_vision_node)
        left_controller = left_runtime.create_controller(
            self.world,
            left_perception,
            left_robot_prim_path,
            gripper_close_fn=left_manual_gripper_close,
            gripper_open_fn=left_manual_gripper_open,
        )
        left_arm = left_runtime.create_system(
            left_controller,
            left_perception,
            vision_executor=left_vision_executor,
        )
        left_arm.gripper_client = left_gripper
        return left_controller, left_arm, left_vision_node, left_vision_executor

    def _create_disabled_left_arm(self):
        print("[Startup] left arm disabled; skip left perception/controller", flush=True)
        return None, DisabledLeftArm()

    def _create_right_controller(self, right_runtime: RightArmRuntime, right_robot_prim_path: str):
        print("[Startup] create right RobotController (6DOF, no gripper) ...", flush=True)
        return right_runtime.create_controller(
            self.world,
            right_robot_prim_path,
        )

    def _sync_initial_joints(
        self,
        left_runtime: LeftArmRuntime,
        right_runtime: RightArmRuntime,
        left_controller,
        right_controller,
        left_robot_prim_path: str,
        right_robot_prim_path: str,
    ):
        right_init_joint_positions = right_runtime.initial_joint_positions_from_rtde(self.services.rtde_right_receive)
        if self.config.left.enabled and left_controller is not None:
            left_init_joint_positions = left_runtime.initial_joint_positions_from_rtde(self.services.rtde_left_receive)
            left_controller.robot.set_joint_positions(left_init_joint_positions)
            self.services.rtde_left_streamer.seed(left_init_joint_positions[:6])
        right_controller.robot.set_joint_positions(right_init_joint_positions)
        self.services.rtde_right_streamer.seed(right_init_joint_positions[:6])

class KeyboardRuntime:
    def __init__(
        self,
        config: DualArmConfig,
        left_arm,
        right_ladle_runner,
    ):
        self.config = config
        self.left_arm = left_arm
        self.right_ladle_runner = right_ladle_runner
        self.input_interface = None
        self.subscription = None

        keyboard_config = config.keyboard
        self.left_key_food = dict(keyboard_config.left_food_keys)
        self.capture_key = keyboard_config.capture_key
        self.execute_capture_key = keyboard_config.execute_capture_key
        self.reset_height_key = keyboard_config.reset_height_key
        self.right_ru_key = keyboard_config.right_ru_key
        self.right_key_food = dict(keyboard_config.right_food_keys)
        self.right_auto_keys = set(keyboard_config.right_auto_keys)
        self.right_auto_food = keyboard_config.right_auto_food
        self.cancel_key = keyboard_config.cancel_key

    @staticmethod
    def key_label(key):
        return str(key).split(".")[-1]

    def subscribe(self):
        self.input_interface = carb_input.acquire_input_interface()
        app_window = omni.appwindow.get_default_app_window()
        keyboard_device = app_window.get_keyboard() if app_window is not None else None
        if keyboard_device is None:
            print("[KEY][WARN] keyboard device unavailable", flush=True)
            return None
        self.subscription = self.input_interface.subscribe_to_keyboard_events(keyboard_device, self.on_event)
        return self.subscription

    def unsubscribe(self):
        if self.input_interface is None or self.subscription is None:
            return
        self.input_interface.unsubscribe_to_keyboard_events(self.subscription)
        self.subscription = None

    def start_right_food(self, food: str):
        if self.right_ladle_runner is not None:
            self.right_ladle_runner.start(food)

    def start_as_capture_sequence(self, source="keyboard A"):
        if not self.config.left.enabled or self.config.right.right_arm_only:
            print(f"[KEY][left] {source} ignored because left arm is unavailable", flush=True)
            return False
        print(f"[KEY][left] {source} -> capture fungus, menma, egg (no grasp)", flush=True)
        return self.left_arm.controller.start_as_capture_sequence()

    def start_as_execute_sequence(self, source="keyboard S"):
        if not self.config.left.enabled or self.config.right.right_arm_only:
            print(f"[KEY][left] {source} ignored because left arm is unavailable", flush=True)
            return False
        print(f"[KEY][left] {source} -> execute frozen egg, menma, fungus", flush=True)
        return self.left_arm.controller.start_as_execute_sequence()

    def start_ru_sequence(self, source="keyboard Y"):
        """啟動 Y 對應流程並回傳結果。"""
        if self.right_ladle_runner is None:
            print(f"[KEY][right] {source} ignored: right ladle runner unavailable", flush=True)
            return False
        print(f"[KEY][right] {source} -> R/U sequence (sesame -> scallion)", flush=True)
        self.right_ladle_runner.start_ru_sequence()
        return True

    def reset_food_height_state(self, source="keyboard D"):
        """重設食材高度狀態，不移動手臂。"""
        left_controller = self.left_arm.controller if self.config.left.enabled else None
        left_busy = bool(left_controller is not None and left_controller.sequence_active())
        right_busy = bool(
            self.right_ladle_runner is not None
            and (self.right_ladle_runner.active or self.right_ladle_runner.ru_sequence_active)
        )
        if left_busy or right_busy:
            print(
                f"[KEY][RESET] {source} ignored: reset only when both arms are idle "
                f"(left_busy={left_busy}, right_busy={right_busy}).",
                flush=True,
            )
            return False

        if left_controller is not None:
            for food in GRID_FOOD_NAMES:
                left_controller.perception.reset_grid_food_tray_state(food)
        if self.right_ladle_runner is not None:
            for food in ("sesame", "scallion"):
                self.right_ladle_runner.path_indices[food] = 0
            self.right_ladle_runner.plc_p9_5_completed_food = None
            print(
                "[DualLadle][RESET] D reset: sesame/scallion height(clearance) paths return to first path.",
                flush=True,
            )
        print("[KEY][RESET] D completed; no arm motion commanded.", flush=True)
        return True

    def on_event(self, event, *args, **kwargs):
        if event.type != carb_input.KeyboardEventType.KEY_PRESS:
            return
        print(f"[KEY][debug] input={event.input}", flush=True)

        if event.input == self.capture_key:
            self.start_as_capture_sequence(source=f"keyboard {self.key_label(event.input)}")
        elif event.input == self.execute_capture_key:
            self.start_as_execute_sequence(source=f"keyboard {self.key_label(event.input)}")
        elif event.input == self.reset_height_key:
            self.reset_food_height_state(source=f"keyboard {self.key_label(event.input)}")
        elif event.input == self.right_ru_key:
            self.start_ru_sequence(source=f"keyboard {self.key_label(event.input)}")
        elif event.input in self.left_key_food:
            food = self.left_key_food[event.input]
            if not self.config.left.enabled:
                print(f"[KEY][left] ignored {self.key_label(event.input)} because left arm disabled", flush=True)
                return
            if self.config.right.right_arm_only:
                print(f"[KEY][left] ignored {self.key_label(event.input)} because RIGHT_ARM_ONLY=True", flush=True)
                return
            print(f"[KEY][left] {self.key_label(event.input)} -> {food} sequence", flush=True)
            self.left_arm.start(food)
        elif event.input in self.right_key_food:
            food = self.right_key_food[event.input]
            print(f"[KEY][right] {self.key_label(event.input)} -> {food} ladle sequence", flush=True)
            self.start_right_food(food)
        elif event.input in self.right_auto_keys:
            if self.right_ladle_runner is not None:
                self.right_ladle_runner.start(self.right_auto_food)
        elif event.input == self.cancel_key:
            if self.config.left.enabled and not self.config.right.right_arm_only:
                self.left_arm.cancel()
            if self.right_ladle_runner is not None:
                self.right_ladle_runner.active = False

class DualRtdeRuntime:
    def __init__(
        self,
        config: DualArmConfig,
        left_arm,
        right_controller,
        left_streamer,
        right_streamer,
        right_ladle_runner=None,
        rate_hz: float = 500.0,
    ):
        self.config = config
        self.left_arm = left_arm
        self.right_controller = right_controller
        self.left_streamer = left_streamer
        self.right_streamer = right_streamer
        self.right_ladle_runner = right_ladle_runner
        self._validate_streamer_connections()
        self.period = 1.0 / float(rate_hz)
        self.next_t = time.perf_counter()
        self.tick_count_left = 0
        self.tick_count_right = 0
        self.stat_last_t = time.perf_counter()

    def _validate_streamer_connections(self):
        left_control = getattr(self.left_streamer, "rtde_c", None)
        right_control = getattr(self.right_streamer, "rtde_c", None)
        left_required = self.config.left.enabled and not self.config.right.right_arm_only

        if left_control is not None and left_control is right_control:
            raise RuntimeError(
                "[RTDE][SAFETY] left/right streamers share one RTDE control; "
                "servoJ is blocked to prevent commands reaching the wrong robot."
            )
        if left_required and ((left_control is None) != (right_control is None)):
            raise RuntimeError(
                "[RTDE][SAFETY] only one robot RTDE control is connected; "
                "dual-arm servoJ is blocked. Connect both robots or disable RTDE for simulation."
            )

    def close(self):
        pass

    def tick_streamers(self, enable_left=True, enable_right=True):
        now_t = time.perf_counter()
        while now_t >= self.next_t:
            if enable_left and self.config.left.enabled and not self.config.right.right_arm_only:
                left_cmd6 = self.left_arm.latest_arm6_cmd
                if left_cmd6 is not None:
                    self.left_streamer.send(left_cmd6)
                    self.tick_count_left += 1

            if enable_right:
                right_cmd6 = self.right_controller.latest_arm6_cmd
                if right_cmd6 is not None:
                    self.right_streamer.send(right_cmd6)
                    self.tick_count_right += 1

            self.next_t += self.period

        if self.next_t < (now_t - 0.5):
            self.next_t = now_t + self.period

        if now_t - self.stat_last_t >= 1.0:
            self.print_stats(now_t)

    def print_stats(self, now_t):
        elapsed = now_t - self.stat_last_t
        hz_left = self.tick_count_left / elapsed if elapsed > 0 else 0.0
        hz_right = self.tick_count_right / elapsed if elapsed > 0 else 0.0
        left_rtde_connected = getattr(self.left_streamer, "rtde_c", None) is not None
        right_rtde_connected = getattr(self.right_streamer, "rtde_c", None) is not None

        if not self.config.left.enabled:
            print("[RTDE-servoJ][left ] disabled (left arm disabled)")
        elif self.config.right.right_arm_only:
            print("[RTDE-servoJ][left ] disabled (RIGHT_ARM_ONLY=True)")
        elif not left_rtde_connected:
            print("[RTDE-servoJ][left ] simulation-only (no RTDE control)")
        else:
            print(f"[RTDE-servoJ][left ] ~ {hz_left:.1f} Hz (target=500, mode=zoh)")

        if not right_rtde_connected:
            print("[RTDE-servoJ][right] simulation-only (no RTDE control)")
        else:
            print(f"[RTDE-servoJ][right] ~ {hz_right:.1f} Hz (target=500, mode=zoh)")

        self.tick_count_left = 0
        self.tick_count_right = 0
        self.stat_last_t = now_t

class SimulationLoopRuntime:
    def __init__(
        self,
        config: DualArmConfig,
        world,
        object_pose_receiver,
        left_arm,
        right_controller,
        right_ladle_runner,
        rtde_runtime: DualRtdeRuntime,
        plc_bridge=None,
        rtde_left_receive=None,
        rtde_right_receive=None,
    ):
        self.config = config
        self.world = world
        self.object_pose_receiver = object_pose_receiver
        self.left_arm = left_arm
        self.right_controller = right_controller
        self.right_ladle_runner = right_ladle_runner
        self.rtde_runtime = rtde_runtime
        self.plc_bridge = plc_bridge
        self.rtde_left_receive = rtde_left_receive
        self.rtde_right_receive = rtde_right_receive
        self.plc_emergency_stop_active = False
        self.plc_emergency_stop_started = None
        self.plc_watchdog_restart_requested = False
        self.plc_right_shutdown_checkpoint = None
        self.plc_right_recovery_waiting = False
        self.plc_right_recovery_active = False
        self.pendant_right_shutdown_waiting = False
        self.pendant_right_receive_refreshed = False
        self._right_recovery_control_retry_at = 0.0
        self._right_recovery_wait_log_at = 0.0
        self.right_shutdown_checkpoint_path = (
            Path(self.config.scene.root_path) / "logs" / "right_ladle_shutdown_checkpoint.json"
        )
        self._right_shutdown_checkpoint_signature = None
        self._right_shutdown_checkpoint_armed = False
        self._load_pendant_right_shutdown_checkpoint()

    @staticmethod
    def _checkpoint_json_value(value):
        """將 numpy 資料轉成可寫入 JSON 的值。"""
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {str(key): SimulationLoopRuntime._checkpoint_json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [SimulationLoopRuntime._checkpoint_json_value(item) for item in value]
        return value

    @staticmethod
    def _checkpoint_numpy_value(value):
        """還原右湯勺流程使用的陣列。"""
        if not isinstance(value, dict):
            return value
        restored = copy.deepcopy(value)
        for target in restored.get("targets", []):
            for key in ("target_position", "target_orientation"):
                if key in target:
                    target[key] = np.asarray(target[key], dtype=np.float64)
        return restored

    def _write_right_shutdown_checkpoint(self, checkpoint, *, reason):
        if checkpoint is None:
            return
        payload = {
            "version": 1,
            "reason": str(reason),
            "saved_unix_sec": time.time(),
            "checkpoint": self._checkpoint_json_value(checkpoint),
        }
        try:
            self.right_shutdown_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.right_shutdown_checkpoint_path.with_suffix(".json.tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            temp_path.replace(self.right_shutdown_checkpoint_path)
            self._right_shutdown_checkpoint_armed = True
        except Exception as exc:
            print(f"[RIGHT][RECOVERY][WARN] checkpoint write failed: {exc}", flush=True)

    def _clear_right_shutdown_checkpoint(self, *, reason):
        self._right_shutdown_checkpoint_signature = None
        self._right_shutdown_checkpoint_armed = False
        try:
            if self.right_shutdown_checkpoint_path.exists():
                self.right_shutdown_checkpoint_path.unlink()
                print(f"[RIGHT][RECOVERY] checkpoint cleared ({reason})", flush=True)
        except Exception as exc:
            print(f"[RIGHT][RECOVERY][WARN] checkpoint clear failed: {exc}", flush=True)

    def _load_pendant_right_shutdown_checkpoint(self):
        """在 watchdog 子程序載入示教器停止 checkpoint。"""
        if not _env_flag("UR_RBC_WATCHDOG_CHILD", "0"):
            return
        try:
            if not self.right_shutdown_checkpoint_path.is_file():
                return
            with self.right_shutdown_checkpoint_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            checkpoint = self._checkpoint_numpy_value(payload.get("checkpoint"))
            if not checkpoint or checkpoint.get("food") not in ("sesame", "scallion"):
                raise ValueError("invalid right-ladle checkpoint")
        except Exception as exc:
            print(f"[RIGHT][RECOVERY][WARN] ignored persisted checkpoint: {exc}", flush=True)
            return

        if not bool(checkpoint.get("p7_completed", False)):
            print(
                "[RIGHT][RECOVERY] pendant shutdown before P7: watchdog Home already completed the reverse/Home safety route",
                flush=True,
            )
            self._clear_right_shutdown_checkpoint(reason="before_P7_home_complete")
            return

        self.plc_right_shutdown_checkpoint = checkpoint
        self.plc_right_recovery_waiting = True
        self._right_shutdown_checkpoint_armed = True
        print(
            f"[RIGHT][RECOVERY] restored pendant checkpoint food={checkpoint['food']} "
            f"target={checkpoint.get('current_target', '')}; will finish P7-after path",
            flush=True,
        )

    def _checkpoint_active_right_ladle_progress(self):
        """只在右臂 waypoint 改變時保存。"""
        runner = self.right_ladle_runner
        if runner is None or not runner.active or runner.shutdown_recovery_mode is not None:
            if self._right_shutdown_checkpoint_armed and not self.plc_right_recovery_active:
                self._clear_right_shutdown_checkpoint(reason="normal_path_complete")
            return
        checkpoint = runner.snapshot_shutdown_recovery(announce=False)
        if checkpoint is None:
            return
        signature = (
            checkpoint.get("food"), checkpoint.get("current_index"),
            checkpoint.get("current_target"), checkpoint.get("p7_completed"),
        )
        if signature != self._right_shutdown_checkpoint_signature:
            self._write_right_shutdown_checkpoint(checkpoint, reason="active_right_waypoint")
            self._right_shutdown_checkpoint_signature = signature

    def close(self):
        close_left_trace = getattr(self.left_arm, "close", None)
        if callable(close_left_trace):
            close_left_trace()

    def request_plc_emergency_stop(self):
        """停止雙臂 servoJ，並禁止本程序再送命令。"""
        if self.plc_emergency_stop_active:
            return True
        self.plc_emergency_stop_active = True
        self.plc_emergency_stop_started = time.perf_counter()
        try:
            self.left_arm.capture_plc_shutdown_status()
        except Exception as exc:
            print(f"[PLC][EMC][WARN] left shutdown status capture failed: {exc}", flush=True)
        try:
            if self.right_ladle_runner is not None:
                self.plc_right_shutdown_checkpoint = self.right_ladle_runner.snapshot_shutdown_recovery()
                self._write_right_shutdown_checkpoint(
                    self.plc_right_shutdown_checkpoint,
                    reason="plc_shutdown",
                )
        except Exception as exc:
            self.plc_right_shutdown_checkpoint = None
            print(f"[PLC][SHUTDOWN][RIGHT][WARN] checkpoint failed: {exc}", flush=True)
        try:
            self.left_arm.cancel()
        except Exception as exc:
            print(f"[PLC][EMC][WARN] left flow cancel failed: {exc}", flush=True)
        try:
            if self.right_ladle_runner is not None:
                self.right_ladle_runner.active = False
                self.right_ladle_runner.ru_sequence_active = False
        except Exception as exc:
            print(f"[PLC][EMC][WARN] right flow cancel failed: {exc}", flush=True)
        try:
            self.rtde_runtime.left_streamer.stop()
            self.rtde_runtime.right_streamer.stop()
        except Exception as exc:
            print(f"[PLC][EMC][ERROR] servoStop failed: {exc}", flush=True)
            return False
        print("[PLC][EMC] servoStop sent to left and right arms", flush=True)
        return True

    def _right_recovery_safety_ready(self):
        """確認右臂已可從 NORMAL／IDLE／RUNNING 恢復。"""
        receiver = self.rtde_right_receive
        if receiver is None:
            return getattr(self.rtde_runtime.right_streamer, "rtde_c", None) is None
        try:
            safety_mode = int(receiver.getSafetyMode())
            robot_mode = int(receiver.getRobotMode())
            emergency = bool(receiver.isEmergencyStopped())
            protective = bool(receiver.isProtectiveStopped())
            ready = (
                safety_mode in (1, 2)
                and robot_mode in (5, 7)
                and not emergency
                and not protective
            )
            if not ready:
                now = time.monotonic()
                if now - self._right_recovery_wait_log_at >= 1.0:
                    self._right_recovery_wait_log_at = now
                    print(
                        "[RIGHT][RECOVERY] waiting for local RTDE safety: "
                        f"safety={safety_mode} robot={robot_mode} "
                        f"emergency={emergency} protective={protective}",
                        flush=True,
                    )
            return ready
        except Exception as exc:
            now = time.monotonic()
            if now - self._right_recovery_wait_log_at >= 1.0:
                self._right_recovery_wait_log_at = now
                print(
                    f"[RIGHT][RECOVERY][WARN] local RTDE safety read failed: {exc}",
                    flush=True,
                )
            return False

    def _reconnect_right_servoj_after_pendant_shutdown(self):
        """示教器停止後重建右臂 servoJ control。"""
        streamer = self.rtde_runtime.right_streamer
        now = time.monotonic()
        if now < self._right_recovery_control_retry_at:
            return False
        try:
            from .utils.rtde_control.rtde_main_rtde_main import _connect_control, RIGHT_ROBOT_IP
            old_control = streamer.rtde_c
            if old_control is not None:
                try:
                    old_control.disconnect()
                    print("[RIGHT][RECOVERY] disconnected stale RTDE servoJ control", flush=True)
                except Exception as exc:
                    print(f"[RIGHT][RECOVERY][WARN] stale RTDE control disconnect failed: {exc}", flush=True)
                streamer.rtde_c = None
            new_control = _connect_control("right-recovery", RIGHT_ROBOT_IP)
            if new_control is None:
                self._right_recovery_control_retry_at = now + 1.0
                return False
            streamer.rtde_c = new_control
            streamer.consecutive_servoj_failures = 0
            streamer.last_servoj_ok = True
            self._right_recovery_control_retry_at = 0.0
            print("[RIGHT][RECOVERY] rebuilt RTDE servoJ control after pendant shutdown", flush=True)
            return True
        except Exception as exc:
            self._right_recovery_control_retry_at = now + 1.0
            print(f"[RIGHT][RECOVERY][WARN] RTDE servoJ reconnect failed: {exc}", flush=True)
            return False

    def _refresh_right_receive_after_pendant_shutdown(self):
        """示教器急停後重建 RTDE receive。"""
        if self.pendant_right_receive_refreshed:
            return True
        try:
            from .utils.rtde_control.rtde_main_rtde_main import _connect_receive, RIGHT_ROBOT_IP
            receiver = _connect_receive("right-recovery", RIGHT_ROBOT_IP)
            if receiver is None:
                return False
            self.rtde_right_receive = receiver
            self.pendant_right_receive_refreshed = True
            print("[RIGHT][RECOVERY] rebuilt RTDE receive after pendant shutdown", flush=True)
            return True
        except Exception as exc:
            print(f"[RIGHT][RECOVERY][WARN] RTDE receive reconnect failed: {exc}", flush=True)
            return False

    def _detect_pendant_right_shutdown(self):
        """偵測失效的右臂 servoJ 並啟動反向恢復。"""
        if self.pendant_right_shutdown_waiting or self.plc_right_recovery_active:
            return False
        runner = self.right_ladle_runner
        streamer = self.rtde_runtime.right_streamer
        failures = int(getattr(streamer, "consecutive_servoj_failures", 0) or 0)
        if runner is None or not runner.active:
            return False
        script_running = None
        script_checker = getattr(streamer, "control_script_running", None)
        if callable(script_checker):
            script_running = script_checker()
        path_age_sec = time.perf_counter() - float(getattr(runner, "phase_start", time.perf_counter()))
        script_dead = script_running is False and path_age_sec >= 0.5
        if failures < 10 and not script_dead:
            return False
        reason = "control_script_not_running" if script_dead else f"servoJ_failures={failures}"
        checkpoint = runner.snapshot_shutdown_recovery(announce=True)
        if checkpoint is None:
            return False
        self.plc_right_shutdown_checkpoint = checkpoint
        self._write_right_shutdown_checkpoint(checkpoint, reason="pendant_shutdown")
        runner.active = False
        runner.ru_sequence_active = False
        self.pendant_right_shutdown_waiting = True
        self.pendant_right_receive_refreshed = False
        self.plc_right_recovery_waiting = False
        print(
            f"[RIGHT][RECOVERY] pendant shutdown detected ({reason}): wait for safe NORMAL state, "
            "then reverse/finish path before Isaac exits",
            flush=True,
        )
        return True

    def _start_plc_right_shutdown_recovery(self):
        """同步已停止的右臂，再恢復路徑。"""
        checkpoint = self.plc_right_shutdown_checkpoint
        runner = self.right_ladle_runner
        if checkpoint is None or runner is None:
            return False
        if self.pendant_right_shutdown_waiting and not self._refresh_right_receive_after_pendant_shutdown():
            return False
        if not self._right_recovery_safety_ready():
            return False
        if self.pendant_right_shutdown_waiting and not self._reconnect_right_servoj_after_pendant_shutdown():
            return False
        try:
            if self.rtde_right_receive is not None:
                actual_q = np.asarray(self.rtde_right_receive.getActualQ(), dtype=np.float32).reshape(-1)
                if actual_q.size < 6 or not np.all(np.isfinite(actual_q[:6])):
                    raise RuntimeError("invalid getActualQ")
                self.right_controller.robot.set_joint_positions(actual_q[:6])
                self.right_controller.rmpflow.update_world()
                self.rtde_runtime.right_streamer.seed(actual_q[:6])
                print(
                    f"[PLC][SHUTDOWN][RIGHT] Isaac/servoJ resynchronised at q={np.round(actual_q[:6], 4).tolist()}",
                    flush=True,
                )
            if not runner.start_shutdown_recovery(checkpoint):
                return False
        except Exception as exc:
            print(f"[PLC][SHUTDOWN][RIGHT][ERROR] recovery start failed: {exc}", flush=True)
            return False
        self.plc_right_recovery_waiting = False
        self.pendant_right_shutdown_waiting = False
        self.plc_right_recovery_active = True
        self.plc_emergency_stop_active = False
        self.plc_emergency_stop_started = None
        print("[PLC][SHUTDOWN][RIGHT] D1207 clear accepted; right-arm recovery is active", flush=True)
        return True

    @staticmethod
    def _rtde_joint_speed_stopped(receiver):
        if receiver is None:
            return True
        try:
            qd = np.asarray(receiver.getActualQd(), dtype=float).reshape(-1)
            return qd.size >= 6 and bool(np.all(np.isfinite(qd[:6]))) and float(np.max(np.abs(qd[:6]))) <= PLC_EMC_MAX_JOINT_SPEED_RAD_S
        except Exception:
            return False

    def plc_emergency_stop_confirmed(self):
        if not self.plc_emergency_stop_active or self.plc_emergency_stop_started is None:
            return False
        if (time.perf_counter() - self.plc_emergency_stop_started) < PLC_EMC_STOP_CONFIRM_SEC:
            return False
        return (
            self._rtde_joint_speed_stopped(self.rtde_left_receive)
            and self._rtde_joint_speed_stopped(self.rtde_right_receive)
        )

    def request_plc_watchdog_restart(self):
        """優先恢復右湯勺，否則由 watchdog 回 Home。"""
        if not self.plc_emergency_stop_active:
            return
        if self.plc_right_shutdown_checkpoint is not None:
            self.plc_right_recovery_waiting = True
            self.plc_emergency_stop_active = False
            print("[PLC][SHUTDOWN][RIGHT] D1207 cleared; waiting for right NORMAL/RUNNING before recovery", flush=True)
            return
        self.plc_watchdog_restart_requested = True
        print("[PLC][EMC] Isaac child will exit for watchdog home/restart", flush=True)

    def tick(self):
        if (
            self.config.left.enabled
            and not self.config.right.right_arm_only
        ):
            self.left_arm.spin_vision()
        self.world.step(render=True)
        if not self.world.is_playing():
            return
        if self.world.current_time_step_index == 0:
            self.world.reset()

        if self.plc_emergency_stop_active:
            if self.plc_bridge is not None:
                self.plc_bridge.tick()
            return

        if self.plc_right_recovery_waiting:
            if not self._start_plc_right_shutdown_recovery():
                if self.plc_bridge is not None:
                    self.plc_bridge.tick()
                return

        if self.pendant_right_shutdown_waiting:
            if not self._start_plc_right_shutdown_recovery():
                if self.plc_bridge is not None:
                    self.plc_bridge.tick()
                return

        stage_ref = omni.usd.get_context().get_stage()
        if self.config.shared.enable_ros_object_pose_update:
            self.object_pose_receiver.spin_and_apply()
        xcache = UsdGeom.XformCache()

        if (
            not self.plc_right_recovery_active
            and self.config.left.enabled
            and not self.config.right.right_arm_only
        ):
            left_food = str(getattr(self.left_arm, "active_food", "") or "").lower()
            left_controller = self.left_arm.controller
            grid_pre_home = str(
                getattr(left_controller, "pre_home_release_source", "") or ""
            ).startswith("grid_food_")
            grid_step = getattr(left_controller, "grid_food_step", None)
            if grid_pre_home:
                policy_dt = (
                    GRID_FOOD_HOME_POLICY_DT
                    if grid_step == "grid_food_home_waypoint"
                    else GRID_FOOD_PRE_HOME_POLICY_DT
                )
            elif grid_step is not None or left_food in GRID_FOOD_PROFILES:
                # A/S 與 controller 內部排隊會直接切換 grid_food_step，未必同步
                # LeftArmSystem.active_food；以實際動作步驟優先選擇專用 dt。
                if grid_step in ("observe_move", "observe_wait"):
                    policy_dt = GRID_FOOD_OBSERVE_POLICY_DT
                elif grid_step in ("approach", "approach_hold"):
                    policy_dt = GRID_FOOD_APPROACH_POLICY_DT
                elif grid_step == "descend":
                    policy_dt = GRID_FOOD_DESCEND_POLICY_DT
                elif grid_step == "gripper_close":
                    policy_dt = GRID_FOOD_GRIPPER_CLOSE_POLICY_DT
                elif grid_step in ("lift_tool_z_raise", "lift_tool_z_return"):
                    policy_dt = GRID_FOOD_LIFT_TOOL_Z_POLICY_DT
                elif grid_step in (
                    "lift_keep_pose", "lift", "lift_post_move", "lift_post_transform",
                ):
                    policy_dt = GRID_FOOD_LIFT_POLICY_DT
                else:
                    policy_dt = GRID_FOOD_HOME_POLICY_DT
            elif bool(getattr(left_controller, "egg_home_return_active", False)):
                policy_dt = EGG_HOME_POLICY_DT
            elif getattr(left_controller, "pre_home_release_source", None) == "egg":
                policy_dt = EGG_PRE_HOME_POLICY_DT
            elif getattr(left_controller, "post_step", None) == "egg_lift":
                policy_dt = EGG_LIFT_POLICY_DT
            elif getattr(left_controller, "post_step", None) in (
                "descend_confirm", "gripper_close", "grasp_hold",
            ):
                policy_dt = EGG_DESCEND_POLICY_DT
            elif getattr(left_controller, "pre_descend_step", None) is not None:
                policy_dt = EGG_APPROACH_POLICY_DT
            elif getattr(left_controller, "mode", None) == "plate":
                policy_dt = EGG_PLATE_APPROACH_POLICY_DT
            elif (
                getattr(left_controller, "mode", None) == "egg"
                and bool(getattr(left_controller, "requested", False))
                and not bool(getattr(left_controller, "egg_descend_requested", False))
            ):
                policy_dt = EGG_APPROACH_POLICY_DT
            elif (
                getattr(left_controller, "mode", None) == "egg"
                and bool(getattr(left_controller, "egg_descend_requested", False))
            ):
                policy_dt = EGG_DESCEND_POLICY_DT
            else:
                policy_dt = IDLE_POLICY_DT
            self.left_arm.update(stage_ref, xcache, dt=policy_dt)
        if self.right_ladle_runner is not None:
            self.right_ladle_runner.update(stage_ref, xcache, dt=RIGHT_LADLE_IDLE_POLICY_DT)
            self._checkpoint_active_right_ladle_progress()

        self.rtde_runtime.tick_streamers(enable_left=not self.plc_right_recovery_active)
        if self._detect_pendant_right_shutdown():
            if self.plc_bridge is not None:
                self.plc_bridge.tick()
            return
        if (
            self.plc_right_recovery_active
            and self.right_ladle_runner is not None
            and bool(getattr(self.right_ladle_runner, "shutdown_recovery_ready_for_restart", False))
        ):
            self.plc_right_recovery_active = False
            self.plc_right_shutdown_checkpoint = None
            self._clear_right_shutdown_checkpoint(reason="recovery_complete")
            self.plc_watchdog_restart_requested = True
            print("[PLC][SHUTDOWN][RIGHT] recovery complete; watchdog will move both arms to configured Home then restart Isaac", flush=True)
        if self.plc_bridge is not None:
            self.plc_bridge.tick()

class ShutdownRuntime:
    def __init__(
        self,
        services: RuntimeServices,
        rtde_runtime=None,
        left_controller=None,
        right_controller=None,
        object_pose_receiver=None,
        left_vision_node=None,
        left_vision_executor=None,
        keyboard_runtime=None,
        left_gripper=None,
        simulation_app_ref=None,
    ):
        self.services = services
        self.rtde_runtime = rtde_runtime
        self.left_controller = left_controller
        self.right_controller = right_controller
        self.object_pose_receiver = object_pose_receiver
        self.left_vision_node = left_vision_node
        self.left_vision_executor = left_vision_executor
        self.keyboard_runtime = keyboard_runtime
        self.left_gripper = left_gripper
        self.simulation_app_ref = simulation_app_ref

    @staticmethod
    def _try(label, call):
        try:
            call()
        except Exception:
            return

    def close(self):
        self._try("rtde_runtime.close", lambda: self.rtde_runtime.close() if self.rtde_runtime is not None else None)
        self._try("release_tools", self._release_tools)
        self._try(
            "left_vision_executor.remove_node",
            lambda: self.left_vision_executor.remove_node(self.left_vision_node)
            if self.left_vision_executor is not None and self.left_vision_node is not None
            else None
        )
        self._try("left_vision_node.destroy_node", lambda: self.left_vision_node.destroy_node() if self.left_vision_node is not None else None)
        self._try("object_pose_receiver.destroy_node", lambda: self.object_pose_receiver.destroy_node() if self.object_pose_receiver is not None else None)
        self._try("rclpy.shutdown", rclpy.shutdown)
        self._try("keyboard_runtime.unsubscribe", lambda: self.keyboard_runtime.unsubscribe() if self.keyboard_runtime is not None else None)
        self._try("services.stop_all_fn", self.services.stop_all_fn)
        self._try("left_gripper.disconnect", lambda: self.left_gripper.disconnect() if self.left_gripper is not None else None)
        self._try("services.disconnect_all_fn", self.services.disconnect_all_fn)
        if self.simulation_app_ref is not None:
            self._try("simulation_app.close", self.simulation_app_ref.close)

    def _release_tools(self):
        if self.left_controller is not None and hasattr(self.left_controller, "_safe_release_vacuum"):
            self.left_controller._safe_release_vacuum("shutdown", force=True)
        if self.right_controller is not None:
            self.right_controller._safe_release_vacuum("shutdown", force=True)

@dataclass
class OperationalRuntimeBundle:
    keyboard: KeyboardRuntime
    rtde: DualRtdeRuntime
    shutdown: ShutdownRuntime
    loop: SimulationLoopRuntime
    plc_bridge: object = None

    def close(self):
        if self.plc_bridge is not None:
            self.plc_bridge.close()
        self.loop.close()
        self.shutdown.close()

def create_operational_runtime_bundle(
    config: DualArmConfig,
    services: RuntimeServices,
    world,
    object_pose_receiver,
    arms: ArmStartupResult,
    simulation_app_ref,
):
    keyboard_runtime = KeyboardRuntime(
        config,
        arms.left_arm,
        arms.right_ladle_runner,
    )
    keyboard_runtime.subscribe()

    rtde_runtime = DualRtdeRuntime(
        config,
        arms.left_arm,
        arms.right_controller,
        services.rtde_left_streamer,
        services.rtde_right_streamer,
        right_ladle_runner=arms.right_ladle_runner,
    )
    shutdown_runtime = ShutdownRuntime(
        services,
        rtde_runtime=rtde_runtime,
        left_controller=arms.left_controller,
        right_controller=arms.right_controller,
        object_pose_receiver=object_pose_receiver,
        left_vision_node=arms.left_vision_node,
        left_vision_executor=arms.left_vision_executor,
        keyboard_runtime=keyboard_runtime,
        left_gripper=arms.left_gripper,
        simulation_app_ref=simulation_app_ref,
    )
    loop_runtime = SimulationLoopRuntime(
        config,
        world,
        object_pose_receiver,
        arms.left_arm,
        arms.right_controller,
        arms.right_ladle_runner,
        rtde_runtime,
        rtde_left_receive=services.rtde_left_receive,
        rtde_right_receive=services.rtde_right_receive,
    )
    plc_bridge = PLCMaterialBridge(
        config,
        arms.left_arm,
        arms.right_ladle_runner,
        keyboard_runtime,
        emergency_stop_fn=loop_runtime.request_plc_emergency_stop,
        emergency_stopped_fn=loop_runtime.plc_emergency_stop_confirmed,
        emc_released_fn=loop_runtime.request_plc_watchdog_restart,
    )
    loop_runtime.plc_bridge = plc_bridge
    plc_bridge.start()

    return OperationalRuntimeBundle(
        keyboard=keyboard_runtime,
        rtde=rtde_runtime,
        shutdown=shutdown_runtime,
        loop=loop_runtime,
        plc_bridge=plc_bridge,
    )

class LeftArmSystem:
    def __init__(self, controller, perception, vision_executor=None):
        self.vision_executor = vision_executor
        self._controller = controller
        self._perception = perception
        self.active_food = None
        self.shutdown_status_signature = None
        self.shutdown_status_frozen = False

    def spin_vision(self):
        if self.vision_executor is not None:
            self.vision_executor.spin_once(timeout_sec=0.0)

    @property
    def controller(self):
        return self._controller

    @property
    def perception(self):
        return self._perception

    @property
    def name(self):
        return self.controller.name

    @property
    def robot(self):
        return self.controller.robot

    @property
    def latest_arm6_cmd(self):
        return self.controller.latest_arm6_cmd

    def pose_locked(self):
        return self.controller.pose_locked()

    def start(self, food: str):
        food = str(food).strip().lower()
        if food not in LEFT_FOOD_NAMES:
            print(f"[LeftArmSystem][WARN] unknown food={food}", flush=True)
            return
        self.shutdown_status_frozen = False
        self.active_food = food
        if food == "egg":
            self.controller.start_auto_egg_sequence()
        else:
            self.controller.request_grid_food_sequence(food)

    def cancel(self):
        self.controller.cancel()
        self.active_food = None
        self._write_shutdown_status()

    def capture_plc_shutdown_status(self):
        """PLC 取消前凍結退離狀態。"""
        self._write_shutdown_status(force=True, plc_shutdown=True)
        self.shutdown_status_frozen = True

    def _write_shutdown_status(self, *, force=False, plc_shutdown=False):
        """只保存 watchdog 重啟所需狀態。"""
        if self.shutdown_status_frozen and not force:
            return
        food = str(self.active_food or "").lower()
        substep = self._substep()
        source = str(getattr(self.controller, "pre_home_release_source", "") or "")
        at_pre_home = bool(source) and source in (
            "egg", "grid_food_menma", "grid_food_fungus",
        )
        lift_completed = at_pre_home
        shutdown_origin = "plc" if plc_shutdown else "pendant"
        retreat_reason = "plc_shutdown" if plc_shutdown else "pre_lift"
        if at_pre_home:
            retreat_mode = "base_minus_x"
            retreat_distance_m = 0.15
            if not plc_shutdown:
                retreat_reason = "pre_home"
        elif food == "egg":
            retreat_mode = "tool_minus_z"
            retreat_distance_m = 0.30
        elif food in GRID_FOOD_PROFILES:
            retreat_mode = "base_plus_z"
            retreat_distance_m = 0.30
        else:
            retreat_mode = None
            retreat_distance_m = 0.0
            retreat_reason = "pre_lift"
            shutdown_origin = None
        payload = {
            "version": 1,
            "updated_unix_sec": time.time(),
            "food": food or None,
            "substep": substep,
            "lift_completed": lift_completed,
            "retreat_required": bool(food and retreat_mode),
            "retreat_reason": retreat_reason,
            "shutdown_origin": shutdown_origin,
            "retreat_mode": retreat_mode,
            "retreat_distance_m": retreat_distance_m,
        }
        signature = (
            payload["food"], payload["substep"], payload["lift_completed"], payload["retreat_mode"],
            payload["shutdown_origin"],
        )
        if not force and signature == self.shutdown_status_signature:
            return
        self.shutdown_status_signature = signature
        try:
            LEFT_SHUTDOWN_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = LEFT_SHUTDOWN_STATUS_PATH.with_suffix(".json.tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            temp_path.replace(LEFT_SHUTDOWN_STATUS_PATH)
        except Exception as exc:
            print(f"[LEFT][SHUTDOWN][WARN] status write failed: {exc}", flush=True)

    def _substep(self):
        c = self.controller
        if getattr(c, "pre_home_release_step", None) is not None:
            return f"pre_home_release:{getattr(c, 'pre_home_release_step', None)}"
        if getattr(c, "post_step", None) is not None:
            return f"post:{getattr(c, 'post_step', None)}"
        if getattr(c, "pre_descend_step", None) is not None:
            return f"pre_descend:{getattr(c, 'pre_descend_step', None)}"
        if getattr(c, "grid_food_step", None) is not None:
            return f"grid:{getattr(c, 'grid_food_step', None)}"
        if getattr(c, "mode", None) is not None:
            if getattr(c, "egg_descend_requested", False):
                return f"{getattr(c, 'mode', None)}:descend"
            if getattr(c, "waiting_for_egg_pose", False):
                return f"{getattr(c, 'mode', None)}:wait_egg_pose"
            return str(getattr(c, "mode", None))
        return "idle"

    def _controller_has_flow(self):
        c = self.controller
        return bool(
            c.pose_locked()
            or c.mode is not None
            or c.waiting_for_egg_pose
            or c.egg_descend_requested
            or c.grid_food_step is not None
            or c.pre_descend_step is not None
            or c.post_step is not None
            or c.pre_home_release_step is not None
            or c.open_gripper_at_home_pending
        )

    def update(self, stage_ref, xcache, dt):
        self.perception.timeout_tick()
        self.perception.sync_stage(stage_ref, pose_locked=self.controller.pose_locked())
        self.controller.update(stage_ref, xcache, dt=dt)
        if self.active_food is not None and not self._controller_has_flow():
            self.active_food = None
        self._write_shutdown_status()

class DualArmApplication:
    def __init__(self, config: DualArmConfig, simulation_app_ref, services: RuntimeServices = None):
        self.config = config
        self.services = services if services is not None else create_default_runtime_services()
        self.simulation_app = simulation_app_ref
        self.scene_runtime = SceneRuntime(config.scene)
        self.scene_context = None
        self.arms = None
        self.runtime_bundle = None

    def build(self):
        print(f"ROOT_DIR: {self.config.scene.root_path}")
        print(f"[Mode] RIGHT_ARM_ONLY={self.config.right.right_arm_only}", flush=True)
        print(f"[Mode] LEFT_ARM_ENABLED={self.config.left.enabled}", flush=True)
        print(
            f"[Mode] LEFT_ARM_BACKEND={self.config.left.backend} "
            f"auto_world_offset={self.config.left.auto_world_offset}",
            flush=True,
        )

        scene_startup = SceneStartupRuntime(self.config, self.scene_runtime)
        self.scene_context = scene_startup.build()
        arm_startup = ArmStartupRuntime(
            self.config,
            self.services,
            self.scene_runtime,
            self.scene_context.world,
            self.scene_context.stage,
            self.scene_context.target_prim_paths,
            self.scene_context.object_pose_receiver,
        )
        self.arms = arm_startup.build()
        self.runtime_bundle = create_operational_runtime_bundle(
            self.config,
            self.services,
            self.scene_context.world,
            self.scene_context.object_pose_receiver,
            self.arms,
            simulation_app_ref=self.simulation_app,
        )
        return self

    def run(self):
        try:
            if self.runtime_bundle is None:
                self.build()
            while self.simulation_app.is_running():
                self.runtime_bundle.loop.tick()
                if self.runtime_bundle.loop.plc_watchdog_restart_requested:
                    print("[PLC][EMC] leaving Isaac child; watchdog will move both arms Home", flush=True)
                    break
        finally:
            self.close()

    def close(self):
        if self.runtime_bundle is not None:
            self.runtime_bundle.close()
            self.runtime_bundle = None

def main():
    config = create_default_dual_arm_config()
    DualArmApplication(config, simulation_app).run()

if __name__ == "__main__":
    main()
