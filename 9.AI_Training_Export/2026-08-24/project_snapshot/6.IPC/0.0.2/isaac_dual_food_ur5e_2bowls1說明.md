# Isaac Sim 雙臂蛋、筍乾、木耳與右湯勺程式說明

本文說明目前下列程式的結構與行為：

- `isaac_dual_food_ur5e_2bowls1.py`：Isaac Sim 場景、左右 UR5e、蛋／筍乾／木耳流程、右湯勺、ROS、PLC、RTDE 與安全恢復。
- `isaac_dual_food_ur5e_2bowls1_config.py`：場景、左右臂、右湯勺、鍵盤與共用運動參數。
- `bowl_pose_publisher_d405_egg_clean.py`：發布蛋姿態與筍乾／木耳十八宮格結果。

> 本文件依照目前程式碼撰寫。第 3 節的函數、類別及方法順序，嚴格按照 `isaac_dual_food_ur5e_2bowls1.py` 由上到下排列。

## 1. 程式負責範圍

| 系統 | 負責內容 |
|---|---|
| 左臂蛋流程 | 拍攝蛋盤、等待穩定蛋姿態、對正夾取軸、下降、夾取、抬升、放料及回 Home。 |
| 左臂筍乾／木耳流程 | 移動到拍照位、接收十八宮格、選格、下降、夾取、分段抬升、姿態轉換、放料及回 Home。 |
| 右臂湯勺流程 | 載入芝麻／蔥錄製路徑，依 waypoint 執行取料、傾倒、抖動與回 Home。 |
| ROS 2 | 接收 D405 感知結果、同步食材 USD Prim，並控制蛋精確辨識閘門。 |
| RTDE | 將 Isaac 關節目標串流到真實左右 UR5e，並讀取實際關節與 TCP 狀態。 |
| PLC Modbus | 接收任務、回覆完成狀態、處理急停與 watchdog 重啟。 |
| 安全恢復 | 覆寫保存左臂與右湯勺恢復 JSON，供重啟後安全退回 Home。 |

整體資料流：

```text
D405 感知程式
  ├─ 蛋姿態／法向量／yaw／尺寸／碗狀態
  └─ 筍乾、木耳 occupied_cells JSON
                    │ ROS 2
                    ▼
isaac_dual_food_ur5e_2bowls1.py
  ├─ EggPlateBridge 保存與穩定化感知資料
  ├─ MoveToEggPlateController 執行左臂食材流程
  ├─ RightLadlePlanRunner 執行右湯勺流程
  ├─ Isaac RMPflow 產生關節命令
  └─ RTDE streamer 控制真實左右 UR5e
                    │
                    ├─ PLC 任務／完成／急停
                    └─ recovery JSON → watchdog 安全回 Home
```

## 2. 函數大類與小類

### 2.1 共用功能

- 數值與座標：向量正規化、frame 轉換、quaternion、RTDE／Isaac 座標互換。
- 流程控制：連續任務佇列、夾爪控制、放料、回 Home、到位判斷與計時。
- 運動命令：RMPflow 目標、Articulation action、關節命令快取及 RTDE 串流。
- 系統整合：場景建立、ROS、鍵盤、PLC、模擬迴圈、關閉與安全恢復。

### 2.2 蛋專用

- 感知鎖定：精確姿態穩定取樣、yaw、兩軸尺寸、後方蛋、碗狀態與 `h_tip`。
- 拍照與選蛋：蛋盤拍照位、粗略／精確姿態升級、無後方蛋二次拍照。
- 姿態與路徑：工具 Z 軸旋轉、base-X 平行滑入、分段 Cartesian 下降。
- 夾取後：真實 TCP 確認、關夾、抬升、放入拉麵碗及返回 Home。
- 不可抓處理：依碗狀態執行 P3／P4 掃動或側邊備援策略。

### 2.3 筍乾／木耳專用

- 十八宮格：接收各食材 JSON、保存格子高度、排除已確認空格並選格。
- 動作 1：移動到拍照姿態並等待穩定格子。
- 動作 2：移動到選中格上方。
- 動作 3：下降並確認真實 TCP。
- 動作 4：關閉夾爪並登記抓取後空格確認。
- 動作 5：保持夾取姿態分段抬升。
- 動作 6：base-X 退回、工具 Z 循環、工具 Y 旋轉，之後交給共用放料流程。

### 2.4 右湯勺

- 路徑載入：讀取芝麻／蔥 scoop、entry、P8、P8.5、P9 與 Home 記錄。
- 目標建立：將湯勺 A/B 點、末端姿態與 base 位移轉成 RMPflow target。
- 執行：依 waypoint、stage、到位時間與 timeout 前進。
- 恢復：保存目前路徑位置，急停解除後先安全抬升再回 Home。

## 3. 主程式函數與類別順序

### 3.1 環境與 PLC（原始碼最前段）

| 函數／類別 | 功能 |
|---|---|
| `_env_flag` | 將環境變數解析成布林值。 |
| `PLCMaterialInputs` | 保存 PLC 任務序號、任務碼、start、EMC 等輸入快照。 |
| `PLCMaterialBridge.__init__` | 建立 PLC client 狀態、背景執行緒、寫入佇列及目前任務狀態。 |
| `PLCMaterialBridge.start` | 啟動 PLC 背景通訊執行緒。 |
| `PLCMaterialBridge.close` | 停止執行緒並關閉 Modbus client。 |
| `PLCMaterialBridge._queue_write` | 將 PLC register 寫入要求放入佇列。 |
| `PLCMaterialBridge._drain_writes` | 在背景執行緒執行待寫 register。 |
| `PLCMaterialBridge._snapshot` | 取得執行緒安全的 PLC 輸入快照。 |
| `PLCMaterialBridge._set_inputs` | 更新目前 PLC 輸入。 |
| `PLCMaterialBridge._worker` | 執行連線、讀取、heartbeat、重連與寫入。 |
| `PLCMaterialBridge._left_busy` | 判斷左臂是否仍有流程或排隊任務。 |
| `PLCMaterialBridge._right_busy` | 判斷右湯勺是否仍在執行。 |
| `PLCMaterialBridge._all_workflows_idle` | 判斷左右流程是否都閒置。 |
| `PLCMaterialBridge._left_as_capture_ready` | 判斷 A 拍照鎖定資料是否可供 S 執行。 |
| `PLCMaterialBridge._left_fungus_release_sent` | 判斷左臂最後木耳是否已送出放料命令。 |
| `PLCMaterialBridge._right_scallion_p9_5_complete` | 判斷右臂蔥流程是否已完成 P9.5。 |
| `PLCMaterialBridge._can_start_task` | 依任務碼及左右臂狀態判斷能否啟動。 |
| `PLCMaterialBridge._respond_error` | 將指定錯誤碼回覆 PLC。 |
| `PLCMaterialBridge._start_task` | 將 PLC 任務碼轉成左臂、右臂或拍照流程。 |
| `PLCMaterialBridge._complete_task` | 在指定完成條件成立時回覆 PLC。 |
| `PLCMaterialBridge._abort_active_task_for_emc` | 急停時凍結恢復資訊並取消目前任務。 |
| `PLCMaterialBridge.tick` | 每個模擬週期處理 PLC 快照、任務、完成與 EMC。 |

### 3.2 左臂設定資料與共用座標工具

| 函數／類別 | 功能 |
|---|---|
| `ManualScenePrims` | 集中保存左臂場景 Prim 路徑。 |
| `LeftRosTopics` | 集中保存蛋與十八宮格 ROS topic。 |
| `StageSyncTarget` | 描述 ROS topic 對應的 USD Prim。 |
| `EggManualProfile` | 保存蛋手動目標、法向量與 frame 模式。 |
| `RuntimeFrameTransform` | 管理單臂、雙臂、RTDE TCP 與 Isaac world 的位移轉換。 |
| `RuntimeFrameTransform._vec3` | 將設定值安全轉成三維向量。 |
| `RuntimeFrameTransform.configure` | 設定各座標系基準與偏移。 |
| `RuntimeFrameTransform.rtde_tcp_to_isaac_offset` | 回傳 RTDE TCP 到 Isaac 的偏移。 |
| `RuntimeFrameTransform.single_isaac_pos_to_runtime` | 將單臂 Isaac 位置轉成目前 runtime 座標。 |
| `normalize_vec` | 正規化向量並處理無效值。 |
| `orient_normal_to_negative_z` | 將法向量統一朝 base 負 Z。 |
| `runtime_rtde_tcp_to_isaac_offset` | 取得目前 runtime 的 TCP／Isaac 偏移。 |
| `single_isaac_pos_to_runtime` | 使用全域 frame transform 轉換單臂位置。 |
| `pre_home_release_config_path_for_source` | 依蛋、筍乾或木耳選擇放料設定路徑。 |
| `pre_home_release_cfg` | 讀取並轉換放料目標設定。 |
| `manual_home_cfg` | 建立左臂 Home 位置、方向與姿態。 |
| `optional_axis` | 驗證可選姿態軸。 |
| `fixed_quat_from_tool_axes` | 由工具 X/Y/Z 軸建立固定 quaternion。 |
| `fixed_downward_base_x_quat` | 建立工具向下且 X 軸沿 base X 的姿態。 |
| `SpinRampMixin._update_spin_ramp` | 依速度限制逐步更新旋轉角。 |
| `SpinRampMixin._spin_is_settled` | 判斷旋轉是否到達目標。 |

### 3.3 蛋、筍乾／木耳與旋轉輔助函數

下表仍依原始碼順序排列。

| 函數 | 分類 | 功能 |
|---|---|---|
| `normalize_yaw_deg` | 蛋 | 將 yaw 正規化到固定角度範圍。 |
| `apply_egg_yaw_offset` | 蛋 | 套用蛋 yaw 校正量。 |
| `egg_tool_pose_yaw_deg` | 蛋 | 將選中蛋軸換成工具姿態 yaw。 |
| `egg_manual_enabled` | 蛋 | 判斷是否使用蛋手動目標。 |
| `egg_manual_normal_down` | 蛋 | 取得手動蛋流程法向量。 |
| `egg_non_sweepable_ungraspable_normal_down` | 蛋 | 取得側邊不可掃蛋的固定下降方向。 |
| `egg_no_back_normal_down` | 蛋 | 取得無後方蛋二次拍照方向。 |
| `egg_no_back_rtde_target` | 蛋 | 取得無後方蛋二次拍照 RTDE 目標。 |
| `egg_manual_target_mode_text` | 蛋 | 回傳目前蛋手動目標模式文字。 |
| `grid_food_cfg` | 筍乾／木耳 | 依食材讀取 grid-food 設定並轉換向量。 |
| `grid_food_manual_target_for_isaac` | 筍乾／木耳 | 將拍照目標轉成 Isaac 位置。 |
| `signed_angle_about_axis` | 共用 | 計算繞指定軸的有號角度。 |
| `signed_angle_to_parallel_axis` | 共用 | 計算忽略正負軸方向後的最短旋轉。 |
| `manual_arm_target_for_isaac` | 蛋 | 取得蛋手動目標的 Isaac 座標。 |
| `no_back_arm_target_for_isaac` | 蛋 | 取得二次拍照目標的 Isaac 座標。 |
| `egg_approach_narrow_width_add_m` | 蛋 | 依蛋寬度增加接近距離。 |
| `isaac_pos_to_rtde_tcp_est` | 共用 | 將 Isaac 位置估算成 RTDE TCP。 |
| `rtde_tcp_pos_to_isaac` | 共用 | 將 RTDE TCP 位置轉成 Isaac。 |
| `egg_pose_sanity_error` | 蛋 | 檢查蛋位置是否超出合理範圍。 |
| `corrected_egg_pose_for_manual_target` | 蛋 | 依手動基準修正蛋的 Z 高度。 |
| `normal_angle_deg` | 共用 | 計算兩向量夾角。 |
| `fmt_arr` | 共用 | 格式化陣列供必要狀態訊息使用。 |
| `quat_xyzw_to_matrix` | 共用 | 將 xyzw quaternion 轉成旋轉矩陣。 |
| `quat_xyzw_to_wxyz` | 共用 | 將 xyzw 排列轉成 wxyz。 |
| `quat_mul_xyzw` | 共用 | 相乘兩個 xyzw quaternion。 |
| `local_axis_from_rotation` | 共用 | 取得旋轉矩陣指定工具軸。 |
| `prefer_camera_forward_quat` | 蛋 | 選擇較符合相機前向的等價姿態。 |
| `gf_matrix_to_rotation_axes` | 共用 | 從 Isaac matrix 取得旋轉軸。 |
| `set_prim_visibility` | 共用 | 設定食材 USD Prim 顯示狀態。 |

### 3.4 `EggPlateBridge`：蛋與十八宮格 ROS 感知橋接

| 方法 | 分類 | 功能 |
|---|---|---|
| `__init__` | 共用 | 建立所有訂閱、發布器、感知快取與穩定取樣狀態。 |
| `set_joint_state_provider` | 共用 | 設定取得左臂關節快照的 callback。 |
| `_to_world` | 共用 | 將 ROS base 位置轉成 Isaac world。 |
| `_pose_cb` | 蛋 | 接收蛋盤位置。 |
| `_normal_cb` | 蛋 | 接收蛋盤法向量。 |
| `_egg_rough_cb` | 蛋 | 接收粗略蛋位置。 |
| `_egg_accurate_cb` | 蛋 | 接收精確蛋位置，並把同步的 yaw、尺寸與狀態存成樣本。 |
| `_egg_normal_cb` | 蛋 | 接收蛋表面法向量。 |
| `_egg_yaw_cb` | 蛋 | 接收蛋 yaw。 |
| `_egg_yaw_axis_width_cb` | 蛋 | 接收選中軸寬。 |
| `_egg_yaw_other_axis_width_cb` | 蛋 | 接收另一軸寬。 |
| `_egg_yaw_axis_name_cb` | 蛋 | 接收 `major`／`minor` 軸名。 |
| `_egg_yaw_axis_center_to_endpoint_max_cb` | 蛋 | 接收中心到軸端最大距離。 |
| `_egg_yaw_axis_base_x_err_cb` | 蛋 | 接收蛋軸與 base X 平行誤差。 |
| `_egg_back_has_egg_cb` | 蛋 | 接收所選蛋後方是否還有蛋。 |
| `_egg_bowl_status_cb` | 蛋 | 接收蛋碗 JSON 狀態與不可抓區資訊。 |
| `_egg_h_tip_cb` | 蛋 | 接收工具尖端下降修正量。 |
| `_grid_food_cells_cb` | 筍乾／木耳 | 接收各自十八宮格 JSON 並更新格子、空格及高度狀態。 |
| `reset_grid_food_height_state` | 筍乾／木耳 | 清除指定食材的高度取樣狀態。 |
| `reset_grid_food_tray_state` | 筍乾／木耳 | 清除整盤永久空格與取樣狀態。 |
| `set_grid_food_height_sampling` | 筍乾／木耳 | 開關拍照位的格子高度取樣。 |
| `request_grid_food_empty_confirmation_after_grasp` | 筍乾／木耳 | 標記抓過的格子，等待下次拍照確認是否為空。 |
| `_stage_sync_pose_cb` | 共用 | 接收食材位置供 USD Prim 同步。 |
| `set_egg_detection_gate` | 蛋 | 發布 yaw 與 accurate-pose 閘門。 |
| `mark_waiting_for_accurate` | 蛋 | 記錄開始等待精確蛋姿態的時間。 |
| `clear_egg_measurements_for_new_lock` | 蛋 | 清除上一顆蛋的姿態與樣本。 |
| `stable_accurate_egg_candidate` | 蛋 | 以時間窗、位置叢集、擴散量與多數決選出穩定蛋。 |
| `timeout_tick` | 共用 | 清除超時感知資料。 |
| `sync_stage` | 共用 | 將最新感知位置同步到 USD Prim。 |
| `have_pose` | 蛋 | 判斷蛋盤位置是否可用。 |
| `best_egg_pos` | 蛋 | 優先回傳精確蛋位置，否則使用粗略位置。 |
| `select_grid_food_cell` | 筍乾／木耳 | 依占用率、高度及格子順序選擇候選格。 |
| `stable_grid_food_candidate` | 筍乾／木耳 | 以時間窗和中心擴散量鎖定穩定格子。 |

### 3.5 `MoveToEggPlateController`：左臂主控制器

以下小節及方法順序完全依照類別內的原始碼順序。

#### 3.5.1 共用初始化、任務佇列與入口

| 方法 | 分類 | 功能 |
|---|---|---|
| `__init__` | 共用 | 建立 RMPflow、夾爪、蛋、grid-food、掃動、A/S 與放料狀態。 |
| `_record_joint_positions` | 共用 | 保存目前關節與真實手臂六軸命令。 |
| `joint_state_snapshot` | 共用 | 產生左臂關節與夾爪快照。 |
| `sequence_active` | 共用 | 判斷控制器是否仍有動作。 |
| `queue_sequence` | 共用 | 將食材加入連續任務佇列。 |
| `start_next_queued_sequence` | 共用 | 不回 Home，直接啟動下一個排隊食材。 |
| `_start_next_as_capture` | 蛋＋筍乾／木耳 | 推進 A 拍照鎖定順序。 |
| `start_as_capture_sequence` | 蛋＋筍乾／木耳 | A：依序拍木耳、筍乾、蛋但不夾取。 |
| `start_as_execute_sequence` | 蛋＋筍乾／木耳 | S：使用 A 凍結的目標依序夾蛋、筍乾、木耳。 |
| `start_auto_egg_sequence` | 蛋 | 啟動完整蛋流程。 |
| `request_grid_food_sequence` | 筍乾／木耳 | 啟動指定食材的拍照與夾取流程。 |
| `request_grid_food_from_snapshot` | 筍乾／木耳 | 使用 A 階段保存的格子啟動夾取。 |

#### 3.5.2 夾爪、蛋量測與共用放料

| 方法 | 分類 | 功能 |
|---|---|---|
| `_send_robotiq_direct_cmd` | 共用 | 將開／關命令送到真實 Robotiq。 |
| `send_gripper_width_mm` | 共用 | 以毫米設定夾爪寬度。 |
| `_lock_egg_measurement` | 蛋 | 共用驗證並鎖定有限量測值。 |
| `lock_yaw_axis_width_mm` | 蛋 | 鎖定選中軸寬。 |
| `lock_yaw_other_axis_width_mm` | 蛋 | 鎖定另一軸寬。 |
| `lock_yaw_axis_center_to_endpoint_max_mm` | 蛋 | 鎖定中心到端點最大距離。 |
| `reset_egg_spin_from_current_pose` | 蛋 | 從目前姿態重新開始 yaw ramp。 |
| `gripper_close_width_mm` | 蛋 | 依蛋寬與縮量計算關夾寬度。 |
| `resend_real_gripper_close_if_needed` | 共用 | 必要時限次重送真實關夾命令。 |
| `set_gripper` | 共用 | 統一設定模擬與真實夾爪狀態。 |
| `reset_post_flow` | 共用 | 重設夾取後、放料與回 Home 狀態。 |
| `start_pre_home_release_flow` | 共用 | 依蛋／筍乾／木耳啟動放料前流程。 |
| `target_from_pre_home_release` | 共用 | 建立目前食材放料目標。 |
| `pre_home_release_fixed_quat_for_source` | 共用 | 取得目前食材放料固定姿態。 |
| `grid_food_pre_home_to_home_waypoint` | 筍乾／木耳 | 建立格子食材放料後回 Home 中繼點。 |
| `update_pre_home_release_flow` | 共用 | 執行移動、開夾、中繼點與下一任務切換。 |

#### 3.5.3 蛋目標鎖定與下降請求

| 方法 | 功能 |
|---|---|
| `pose_locked` | 判斷目前是否持有有效蛋或食材目標。 |
| `plate_normal_down` | 取得蛋盤拍照姿態法向量。 |
| `egg_target_normal_down` | 依後方蛋狀態選擇蛋接近方向。 |
| `start_no_back_reobserve` | 無後方蛋時啟動第二拍照姿態。 |
| `request_move` | 要求移動到蛋盤或二次拍照位置。 |
| `request_egg_move` | 從穩定感知結果鎖定蛋並移動到接近點。 |
| `initialize_egg_descend_cartesian_path` | 建立蛋分段下降路徑。 |
| `egg_descend_path_target` | 取得目前下降 waypoint。 |
| `egg_descend_cartesian_waypoint` | 計算下降路徑目前位置。 |
| `advance_egg_descend_cartesian_path` | 到位後切換下一個下降 waypoint。 |
| `request_egg_descend` | 鎖定下降姿態並啟動預下降流程。 |
| `cancel` | 取消左臂任務並清除感知閘門與流程狀態。 |

#### 3.5.4 筍乾／木耳目標與六個動作

| 方法 | 功能 |
|---|---|
| `grid_food_gripper_close_width_mm` | 取得目前食材關夾寬度。 |
| `target_from_grid_food` | 由選中格中心、法向量與 offset 建立目標。 |
| `target_from_grid_food_home_lift` | 建立完整或分段 base-Z 抬升目標。 |
| `grid_food_post_lift_tool_y_sequence_deg` | 取得抬升後工具 Y 旋轉序列。 |
| `grid_food_post_lift_base_x_retract_m` | 依格子是否位於最後一列取得 base-X 退回量。 |
| `grid_food_post_lift_fixed_quat` | 建立抬升後工具 Y 旋轉姿態。 |
| `target_from_grid_food_post_lift` | 建立退回位置加指定旋轉的目標。 |
| `target_from_grid_food_post_lift_move` | 建立 base-X 退回目標。 |
| `target_from_grid_food_post_lift_tool_z_raise` | 建立沿工具負 Z 抬升目標。 |
| `_command_grid_food_pose` | 共用送出格子食材姿態並判斷位置／方向到位。 |
| `grid_food_approach_offset_m` | 計算接近 offset。 |
| `grid_food_descend_offset_m` | 計算下降 offset。 |
| `grid_food_lift_offset_m` | 計算抬升 offset。 |
| `grid_food_real_tcp_descend_confirmed` | 以 RTDE 確認真實 TCP 在下降目標穩定。 |
| `grid_food_fixed_quat` | 建立拍照或夾取固定姿態。 |
| `start_grid_food_grip_flow` | 從下降切換到關夾等待。 |
| `_update_grid_food_observe_action` | 動作 1：拍照並鎖定格子。 |
| `_update_grid_food_approach_action` | 動作 2：移動到格子上方。 |
| `_update_grid_food_descend_action` | 動作 3：下降並確認真實 TCP。 |
| `_update_grid_food_grasp_action` | 動作 4：關夾並登記空格確認。 |
| `_update_grid_food_lift_action` | 動作 5：分段抬升並轉成固定姿態。 |
| `_update_grid_food_post_lift_action` | 動作 6：退回、工具循環、旋轉並交接放料。 |
| `update_grid_food_flow` | 依 `grid_food_step` 分派六個動作。 |

#### 3.5.5 蛋目標、方向對正、下降與夾取後流程

| 方法 | 功能 |
|---|---|
| `target_from_plate` | 建立蛋盤或二次拍照目標。 |
| `lock_egg_descend_dz` | 依 `h_tip` 與設定鎖定下降距離。 |
| `egg_descend_offset` | 回傳蛋下降 offset。 |
| `egg_approach_offset` | 回傳依蛋寬修正的接近 offset。 |
| `format_locked_h_tip` | 格式化鎖定的 `h_tip`。 |
| `format_locked_h_tip_descend_dz` | 格式化由 `h_tip` 推導的下降距離。 |
| `egg_y_backoff_direction` | 計算蛋預下降 Y 退讓方向。 |
| `target_from_egg` | 由蛋位置、法向量、offset 與 backoff 建立末端目標。 |
| `egg_pose_axes_from_normal_yaw` | 由法向量與 yaw 建立蛋工具三軸。 |
| `_spin_offset_target` | 取得目前蛋動作允許的旋轉目標。 |
| `_minimal_spin_to_locked_yaw_axis` | 計算目前姿態到鎖定蛋軸的最短工具 Z 旋轉。 |
| `_apply_orientation_modifiers` | 套用 spin ramp 與蛋方向修正。 |
| `set_motion_target` | 共用設定 RMPflow 位置及姿態。 |
| `elapsed_since` | 共用計算狀態經過時間。 |
| `target_from_ramen` | 建立蛋放入拉麵碗的位置。 |
| `current_bowl_status_is_side_edge_fallback` | 判斷是否使用側邊不可掃蛋備援。 |
| `current_bowl_status_selected_side_edge` | 取得備援側邊名稱。 |
| `use_back_egg_base_x_axis_slide` | 一般蛋依選中軸與 Base-X 誤差判斷滑入；側邊備援蛋固定滑入。 |
| `nonselected_axis_camera_forward_yaw` | 計算另一軸朝相機前方的 yaw。 |
| `apply_base_x_parallel_approach_yaw` | 套用 base-X 平行接近方向。 |
| `start_back_egg_base_x_axis_slide_flow` | 啟動後方蛋 base-X 軸向滑入。 |
| `start_pre_descend_flow` | 啟動蛋預下降狀態機。 |
| `pre_descend_axis_width_cmd_mm` | 計算選中軸預下降夾爪寬。 |
| `pre_descend_other_axis_width_cmd_mm` | 計算另一軸預下降夾爪寬。 |
| `prepare_as_egg_pre_shrink` | A 階段預先送出蛋夾爪縮小命令。 |
| `consume_as_egg_pre_shrink` | S 階段使用 A 已完成的縮小命令。 |
| `start_pre_descend_axis_width_only` | 啟動只依選中軸寬的預下降流程。 |
| `update_pre_descend_flow` | 執行預縮、方向調整、滑入及正式下降切換。 |
| `start_post_egg_flow` | 啟動蛋下降後的夾取流程。 |
| `real_tcp_descend_confirmed` | 以 RTDE 確認真實 TCP 已在蛋下降位置穩定。 |
| `egg_descend_command_target` | 取得目前分段下降的實際命令位置。 |
| `set_post_step` | 統一切換蛋夾取後步驟與開始時間。 |
| `update_post_egg_flow` | 執行關夾、抬升、放入拉麵碗及回 Home。 |
| `maybe_upgrade_rough_lock_to_accurate` | 到位前將粗略蛋位置升級成精確位置。 |
| `_hold_current_robot_command` | 無新目標時保持目前關節命令。 |
| `start_ungraspable_sweep` | 依 P3／P4 狀態啟動不可抓蛋掃動。 |
| `update_ungraspable_sweep` | 執行掃動、回拍照高度及重新觀測。 |
| `_apply_left_robot_action` | 套用左臂 RMPflow action、夾爪關節與命令快取。 |
| `_update_egg_observation_waits` | 處理蛋穩定等待、碗狀態、掃動及姿態鎖定。 |
| `update` | 左臂每幀主更新，整合所有食材狀態機並輸出動作。 |

### 3.6 Runtime、右湯勺、場景與系統類別

以下仍按原始碼順序列出；同一列中的方法也依類別內順序排列。

| 類別／函數 | 方法順序與功能 |
|---|---|
| `RuntimeServices` | `left_rtde_control_connected`：集中保存 RTDE、streamer、gripper 及關閉服務並檢查左控制連線。 |
| `create_default_runtime_services` | 由既有 RTDE 模組建立 runtime services。 |
| `wait_for_stage_loaded` | 等待 USD stage 與資產完成載入。 |
| `load_json` | 讀取 JSON。 |
| `RightLadlePathTools` | `__init__` → `latest_json` → `latest_json_from_patterns` → `food_latest_patterns` → `load_json`：尋找並載入右湯勺記錄檔。 |
| 右湯勺數學函數 | `normalize` → `skew` → `rotation_between` → `rotation_matrix_axis_angle` → `rotvec_to_matrix` → `quat_from_matrix_wxyz` → `gf_matrix_to_rotation` → `build_entry_rotation`：建立湯勺旋轉與 quaternion。 |
| 右湯勺目標函數 | `waypoint_to_ladle_target` → `apply_ladle_base_ry_offset` → `translate_ladle_target` → `update_ladle_target_geometry` → `set_last_ladle_target_to_pose_posture` → `make_ladle_pose_target` → `load_recorded_pose`：建立、旋轉、平移及載入 waypoint。 |
| `SceneRuntime` | `__init__` → `repair_left_bowl_payload` → `open_stage` → `resolve_target_prim_paths` → `find_left_articulation_root_path` → `find_right_articulation_root_path` → `_is_articulation_root` → `find_articulation_root_path` → `set_joint_drive` → `patch_ur5e_drives` → `patch_all_ur5e_drives`：載入及修正雙臂場景。 |
| `ObjectPoseReceiver` | `__init__` → `_build_topic_to_prim` → `_ensure_translate_op` → `_make_pose_cb` → `spin_and_apply`：接收一般食材位置並同步 USD Prim。 |
| `SceneStartupResult` | 保存 stage、world、Prim mapping 與 ROS receiver。 |
| `SceneStartupRuntime` | `__init__` → `build` → `_open_world` → `_create_ros_object_pose_receiver` → `_patch_drives_if_enabled`：建立場景 runtime。 |
| `RightLadleStage` | 定義右湯勺 `INIT`、`SCOOP`、`POUR`、`RETREAT`。 |
| `ReachHold` | `__init__` → `reset` → `update`：要求目標在容許距離內維持指定時間。 |
| `RobotController` | `__init__` → `_set_rmpflow_target` → `_safe_release_vacuum`：右臂最小 RMPflow 控制核心。 |
| `RightLadlePlanRunner` | `__init__` → `_canonical_food` → `supported_foods` → `_mark_stage` → `_apply_ladle_timing` → `load_profiles` → `_load_finish_pose_records` → `_load_food_paths` → `_make_finish_pose_target` → `_append_finish_targets` → `start` → `_is_p7_target` → `snapshot_shutdown_recovery` → `start_shutdown_recovery` → `_finish_active_path` → `start_ru_sequence` → `_apply_articulation_action` → `_mark_scallion_p9_5_complete` → `_advance_target` → `update`。 |
| `RightArmRuntime` | `__init__` → `initial_joint_positions_from_rtde` → `create_controller` → `create_ladle_runner`：建立右臂與湯勺 runner。 |
| `DisabledLeftArm` | `pose_locked` → `start` → `cancel` → `update`：左臂停用時提供相容空介面。 |
| `LeftArmRuntime` | `__init__` → `initial_joint_positions_from_rtde` → `configure_manual_module` → `create_perception` → `create_controller` → `create_gripper_callbacks` → `create_system`：建立左臂感知、控制器與真實夾爪。 |
| `ArmStartupResult` | 保存左右臂啟動結果。 |
| `ArmStartupRuntime` | `__init__` → `build` → `_create_left_gripper` → `_create_left_arm` → `_create_disabled_left_arm` → `_create_right_controller` → `_sync_initial_joints`：建立左右臂並用 RTDE 初始關節同步 Isaac。 |
| `KeyboardRuntime` | `__init__` → `key_label` → `subscribe` → `unsubscribe` → `start_right_food` → `start_as_capture_sequence` → `start_as_execute_sequence` → `start_ru_sequence` → `reset_food_height_state` → `on_event`：處理鍵盤任務。 |
| `DualRtdeRuntime` | `__init__` → `_validate_streamer_connections` → `close` → `tick_streamers` → `print_stats`：驗證連線並管理左右 RTDE servoJ streamer。 |
| `SimulationLoopRuntime` | `__init__` → `_checkpoint_json_value` → `_checkpoint_numpy_value` → `_write_right_shutdown_checkpoint` → `_clear_right_shutdown_checkpoint` → `_load_pendant_right_shutdown_checkpoint` → `_checkpoint_active_right_ladle_progress` → `close` → `request_plc_emergency_stop` → `_right_recovery_safety_ready` → `_reconnect_right_servoj_after_pendant_shutdown` → `_refresh_right_receive_after_pendant_shutdown` → `_detect_pendant_right_shutdown` → `_start_plc_right_shutdown_recovery` → `_rtde_joint_speed_stopped` → `plc_emergency_stop_confirmed` → `request_plc_watchdog_restart` → `tick`。 |
| `ShutdownRuntime` | `__init__` → `_try` → `close` → `_release_tools`：依序解除工具、ROS、streamer、RTDE 與 Isaac 資源。 |
| `OperationalRuntimeBundle` | `close`：集中保存並關閉 keyboard、RTDE、shutdown、simulation loop 與 PLC。 |
| `create_operational_runtime_bundle` | 建立鍵盤、RTDE、PLC、關閉與模擬迴圈 runtime。 |
| `LeftArmSystem` | `__init__` → `spin_vision` → `controller` → `perception` → `name` → `robot` → `latest_arm6_cmd` → `pose_locked` → `start` → `cancel` → `capture_plc_shutdown_status` → `_write_shutdown_status` → `_substep` → `_controller_has_flow` → `update`：包裝左臂並保存安全恢復狀態。 |
| `DualArmApplication` | `__init__` → `build` → `run` → `close`：建立並執行完整雙臂應用程式。 |
| `main` | 建立預設 config 並啟動 `DualArmApplication`。 |

## 4. Config 參數說明

### 4.1 `SceneConfig`：場景與 Prim

| 參數群組 | 參數 | 說明 |
|---|---|---|
| 路徑 | `root_path`、`usd_path`、`rmpflow_gripper_dir` | 專案、USD 場景及 RMPflow 設定目錄。 |
| 機器人 | `ur5e_left_prim`、`ur5e_right_prim`、`ee_left_prim`、`ee_right_prim` | 左右 UR5e 與末端 Prim。 |
| 左臂食材 | `ramen_bowl_prim_path`、`egg_plate_prim_path`、`egg_prim_path`、`menma_bowl_prim_path`、`menma_prim_path`、`fungus_plate_prim_path`、`fungus_prim_path` | 蛋、筍乾、木耳及拉麵碗 Prim。 |
| 其他食材 | `nori_plate_prim_path`、`nori_prim_path`、`green_onion_plate_prim_path`、`green_onion_prim_path`、`chashu_plate_prim_path`、`chashu_prim_path`、`sesame_plate_prim_path`、`sesame_prim_path` | 海苔、蔥、叉燒與芝麻場景 Prim。 |
| ROS mapping | `ros_target_prim_names` | 一般食材 ROS 名稱到 USD Prim 的 mapping。 |

### 4.2 `SharedMotionConfig`：共用運動

| 參數群組 | 參數 | 說明 |
|---|---|---|
| 到位與 timeout | `stability_sec`、`stability_eps`、`phase_timeout`、`default_obj_hold_tol` | 穩定時間、位置誤差及流程 timeout。 |
| 接近與放料 | `approach_offset`、`vacuum_carry_hover_offset`、`vacuum_ramen_descend_dz` | 通用接近、搬運及下降距離。 |
| 傳統食材下降 | `nori_descend_dz`、`chashu_descend_dz` | 海苔與叉燒下降距離。 |
| 傳統放料偏移 | `nori_ramen_offset_xy`、`chashu_ramen_offset_xy`、`nori_orbit_radius` | 海苔／叉燒拉麵碗偏移與海苔軌道半徑。 |
| 動作等待 | `hold_before_grip_sec`、`hold_before_place_sec` | 夾取與放料前的保持時間。 |
| 姿態 | `world_up`、`tool_axis`、`vacuum_adapter_compensation_x_rad` | look-at 與工具補償設定。 |
| 場景 | `enable_drive_patch`、`enable_ros_object_pose_update`、`debug_drives` | drive 修正及 ROS Prim 更新開關。 |
| 座標 | `dual_base_to_world_z`、`object_pose_print_xy_diff_threshold` | 雙臂 base/world Z 偏移及位置變化門檻。 |

### 4.3 `LeftArmConfig`：蛋、筍乾與木耳

| 參數群組 | 參數 | 說明 |
|---|---|---|
| 啟用 | `enabled`、`backend`、`auto_world_offset` | 左臂開關、控制 backend 與自動座標補償。 |
| 夾爪 | `gripper_idx`、`gripper_open`、`gripper_close`、`default_gripper_close_position` | 模擬與預設真實夾爪設定。 |
| 初始關節 | `fallback_joint_positions` | RTDE 無法讀取時的 Isaac 初始關節。 |
| 下降 | `egg_descend_dz`、`menma_descend_dz`、`fungus_descend_dz`、`ramen_descend_dz` | 各食材與拉麵碗下降距離；後方沒蛋另使用 `NO_BACK_EGG_DESCEND_DZ`。 |
| 關夾 | `egg_gripper_close_position`、`menma_gripper_close_position`、`fungus_gripper_close_position` | 各食材夾爪命令。 |
| 到位 | `egg_grip_hold_tol`、`menma_grip_hold_tol`、`fungus_grip_hold_tol` | 各食材夾取保持容許值。 |
| frame | `single_arm_root_world`、`dual_left_root_world`、`dual_left_single_world_offset` | 單臂與雙臂座標關係。 |
| Home | `home_z`、`home_look_dz`、`home_xy`、`safe_idle_home_enabled`、`safe_idle_home_clearance_extra` | 左臂 Home 與安全高度。 |
| 食材位置 | `park_offset_xy`、`egg_container_offset_x`、`egg_ramen_offset_xy`、`fungus_ramen_offset_xy` | 停放、蛋盤及放料 offset。 |
| 旋轉 | `spin_ramp_speed_deg_per_sec`、`spin_settle_tol_deg` | 蛋 yaw ramp 速度與完成誤差。 |

### 4.4 `RightArmConfig`：右湯勺

| 參數群組 | 參數 | 說明 |
|---|---|---|
| 基本 | `home_xy`、`fallback_joint_positions`、`right_arm_only` | Home、初始關節與單獨右臂模式。 |
| 路徑 | `sesame_plan_path`、`scallion_plan_path` | 芝麻及蔥湯勺路徑。 |
| 到位 | `ladle_reach_tol_m`、`ladle_phase_timeout_sec`、`ladle_status_print_sec`、`ladle_quat_order` | 到位、timeout、狀態週期與 quaternion 格式。 |
| 芝麻 policy dt | `sesame_ladle_entry_policy_dt`、`sesame_ladle_scoop_policy_dt`、`sesame_ladle_lift_policy_dt`、`sesame_ladle_pour_policy_dt`、`sesame_ladle_return_policy_dt`、`sesame_ladle_p8_p9_policy_dt`、`sesame_ladle_p8_5_p9_policy_dt`、`sesame_ladle_p7_5_policy_dt`、`sesame_ladle_shake_policy_dt` | 芝麻 entry、scoop、lift、pour、return、P8/P9、P8.5/P9、P7.5 與 shake 的控制 dt。 |
| 蔥 policy dt | `scallion_ladle_entry_policy_dt`、`scallion_ladle_scoop_policy_dt`、`scallion_ladle_lift_policy_dt`、`scallion_ladle_pour_policy_dt`、`scallion_ladle_return_policy_dt`、`scallion_ladle_p8_p9_policy_dt`、`scallion_ladle_p8_5_p9_policy_dt`、`scallion_ladle_p7_5_policy_dt`、`scallion_ladle_shake_policy_dt` | 蔥 entry、scoop、lift、pour、return、P8/P9、P8.5/P9、P7.5 與 shake 的控制 dt。 |
| 姿態與位移 | `ladle_shake_base_ry_deg`、`ladle_scallion_p9_5_base_ry_deg`、`ladle_p7_5_base_ry_deg`、`ladle_p7_5_base_x_shift_m` | P7.5 與抖動修正。 |
| P9／P9.5 | `ladle_p9_tool_minus_ry_deg`、`ladle_p9_base_x_shift_m`、`ladle_p9_shake_cycles`、`ladle_p9_5_base_x_shift_m`、`ladle_p9_5_hold_sec` | 傾倒、抖動次數與保持時間。 |
| 安全 | `ladle_safety_lift_z` | 路徑套用的額外安全抬升。 |

### 4.5 `KeyboardConfig`

| 參數 | 功能 |
|---|---|
| `left_food_keys` | 蛋、筍乾、木耳單獨流程按鍵。 |
| `capture_key` | A：只拍照並凍結木耳、筍乾、蛋目標。 |
| `execute_capture_key` | S：執行 A 凍結的目標。 |
| `reset_height_key` | D：雙臂閒置時重設格子高度與湯勺路徑 index。 |
| `right_food_keys` | 芝麻與蔥單獨流程按鍵。 |
| `right_ru_key` | Y：依序執行 R/U 右湯勺流程。 |
| `right_auto_keys`、`right_auto_food` | 右湯勺自動按鍵與預設食材。 |
| `cancel_key` | 取消目前左右流程。 |

`DualArmConfig` 是最上層組合設定：`scene`、`shared`、`left`、`right`、`keyboard` 分別指向上述五組 config。

### 4.6 模組常數完整分類與說明

下表依 config 原始碼的功能分類列出模組層級變數。同一列的變數共用說明；距離以公尺或毫米為單位、時間以秒為單位，除非名稱另有標示。

#### 4.6.1 PLC 通訊、任務與急停

| 變數 | 說明 |
|---|---|
| `PLC_MATERIAL_ENABLE`、`PLC_MATERIAL_IP`、`PLC_MATERIAL_PORT`、`PLC_MATERIAL_SLAVE_ID` | PLC Modbus 啟用開關、IP、port 與 slave ID，可由環境變數覆寫。 |
| `PLC_MATERIAL_INTERVAL_SEC`、`PLC_MATERIAL_TIMEOUT_SEC`、`PLC_MATERIAL_RECONNECT_SEC` | PLC 輪詢週期、請求 timeout 與斷線重連間隔。 |
| `PLC_D_INPUT_START`、`PLC_D_HB_RETURN`、`PLC_D_ACK_SEQ`、`PLC_D_BUSY`、`PLC_D_RESPONSE_CODE`、`PLC_D_RESPONSE_SEQ`、`PLC_D_ERROR_CODE`、`PLC_D_CURRENT_TASK`、`PLC_D_EMC_DONE` | PLC D-register 輸入起點、heartbeat、ACK、busy、回應、錯誤、當前任務與急停完成位址。 |
| `PLC_CMD_FIRST_MATERIAL`、`PLC_CMD_LAST_MATERIAL`、`PLC_CMD_CAPTURE_MATERIAL` | PLC 首批食材、末批食材與 A 拍照鎖定任務碼。 |
| `PLC_RESP_FIRST_MATERIAL_DONE`、`PLC_RESP_LAST_MATERIAL_DONE`、`PLC_RESP_CAPTURE_MATERIAL_DONE`、`PLC_RESP_ERROR` | PLC 三種任務完成與錯誤回應碼。 |
| `PLC_ERR_UNSUPPORTED_COMMAND`、`PLC_ERR_WORKFLOW_UNAVAILABLE`、`PLC_ERR_EMC_ABORT` | 不支援命令、流程不可用與 EMC 中止錯誤碼。 |
| `PLC_EMC_STOP_CONFIRM_SEC`、`PLC_EMC_MAX_JOINT_SPEED_RAD_S`、`PLC_EMC_RELEASE_FLUSH_SEC` | EMC 停止確認時間、可接受關節速度上限與釋放命令 flush 時間。 |

#### 4.6.2 基本 Prim、ROS topic 與路徑

| 變數 | 說明 |
|---|---|
| `ENABLE_REAL_ARM_IO` | 傳統單臂實體 IO 開關；目前由 dual runtime 注入實體介面。 |
| `UR5E_PRIM`、`EE_PRIM`、`EGG_PLATE_PRIM_PATH`、`EGG_PRIM_PATH`、`RAMEN_BOWL_PRIM_PATH`、`MENMA_BOWL_PRIM_PATH`、`MENMA_PRIM_PATH` | 傳統左臂、末端與食材 USD Prim 路徑。 |
| `GRIPPER_IDX`、`GRIPPER_OPEN`、`GRIPPER_CLOSE` | Isaac 夾爪關節索引與開、關目標值。 |
| `EGG_PLATE_TOPIC`、`EGG_PLATE_NORMAL_TOPIC`、`EGG_ROUGH_TOPIC`、`EGG_ACCURATE_TOPIC`、`EGG_NORMAL_TOPIC` | 蛋盤與蛋的位置、法向量 topic。 |
| `EGG_YAW_TOPIC`、`EGG_YAW_AXIS_WIDTH_MM_TOPIC`、`EGG_YAW_OTHER_AXIS_WIDTH_MM_TOPIC`、`EGG_YAW_AXIS_NAME_TOPIC`、`EGG_YAW_AXIS_CENTER_TO_ENDPOINT_MAX_MM_TOPIC`、`EGG_YAW_AXIS_BASE_X_ERR_DEG_TOPIC` | 蛋夾取軸角度、兩軸寬度、軸名、端點距離與 base-X 誤差 topic。 |
| `EGG_BACK_HAS_EGG_TOPIC`、`EGG_BOWL_STATUS_TOPIC`、`EGG_H_TIP_TOPIC` | 後方蛋、蛋碗分類與工具尖端修正 topic。 |
| `GRID_FOOD_MENMA_CELLS_TOPIC`、`GRID_FOOD_FUNGUS_CELLS_TOPIC` | 筍乾與木耳十八宮格 JSON topic。 |
| `DETECTION_TIMEOUT`、`STAGE_SYNC_TOPICS` | 感知資料逾時門檻與 ROS topic 對 USD Prim 的同步 mapping。 |
| `ROOT_PATH`、`USD_PATH`、`MANUAL_HOME_CONFIG_PATH` | 專案根目錄、傳統 USD 路徑與手動 Home JSON。 |
| `LEFT_SHUTDOWN_STATUS_PATH` | 左臂 shutdown 恢復狀態 JSON；以 replace 覆寫同一檔案。 |
| `PRE_HOME_RELEASE_CONFIG_PATH`、`PRE_HOME_RELEASE_CONFIG_PATH_BY_SOURCE` | 共用與依蛋／筍乾／木耳分開的放料姿態 JSON 路徑。 |

#### 4.6.3 Home、接近、放料與連續任務

| 變數 | 說明 |
|---|---|
| `Z_FIXED`、`EGG_STAGE_Z`、`HOME_Z`、`HOME_XY`、`HOME_LOOK_DZ` | 傳統固定高度、蛋 Prim 高度與左臂 Home 位置／視線設定。 |
| `APPROACH_OFFSET`、`PLATE_APPROACH_OFFSET`、`EGG_APPROACH_OFFSET`、`NO_BACK_EGG_APPROACH_OFFSET` | 通用、蛋盤、蛋與無後方蛋的接近距離。 |
| `PRE_HOME_RELEASE_ENABLE`、`PRE_HOME_RELEASE_TARGET_POS`、`PRE_HOME_RELEASE_NORMAL_DOWN`、`PRE_HOME_RELEASE_OPEN_WAIT_SEC` | 回 Home 前放料開關、目標、下壓法向量與開爪等待。 |
| `GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_RTDE_POS`、`GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_X_AXIS`、`GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Y_AXIS`、`GRID_FOOD_PRE_HOME_TO_HOME_WAYPOINT_Z_AXIS` | 筍乾／木耳放料後回 Home 的 RTDE 中間點與工具三軸。 |
| `QUEUED_MENMA_TO_FUNGUS_DELAY_SEC`、`RIGHT_RU_SESAME_TO_SCALLION_DELAY_SEC` | 左臂筍乾切木耳與右臂芝麻切蔥的連續任務間隔。 |

#### 4.6.4 蛋接近、下降與不可夾處理

| 變數 | 說明 |
|---|---|
| `EGG_APPROACH_NARROW_WIDTH_ADD_TABLE` | 依蛋軸寬動態增加接近預留距離的對照表。 |
| `EGG_DESCEND_DZ`、`NO_BACK_EGG_DESCEND_DZ`、`NON_SWEEPABLE_UNGRASPABLE_DESCEND_DZ` | 一般蛋、無後方蛋與不可撥不可夾備援流程的獨立下降距離。 |
| `BACK_EGG_BASE_X_PARALLEL_SLIDE_STAGES` | 選中軸接近 Base-X 時的分段滑入段數。 |
| `PLATE_TCP_X_OFFSET`、`EGG_CONTAINER_OFFSET_X` | 蛋盤 TCP X 修正與蛋盤容器 X 偏移。 |
| `UNGRASPABLE_SWEEP_PRE_DESCEND_OFFSET_M`、`UNGRASPABLE_SWEEP_POLICY_DT`、`UNGRASPABLE_SWEEP_RETURN_FINAL_POLICY_DT` | P3／P4 不可夾蛋掃動前預下降、掃動 dt 與回拍照位最後段 dt。 |
| `UNGRASPABLE_SWEEP_GRIPPER_WIDTH_MM`、`UNGRASPABLE_SWEEP_TOOL_Y_SHIFT_M`、`UNGRASPABLE_SWEEP_TOOL_X_SHIFT_M`、`UNGRASPABLE_SWEEP_MAX_REPEATS` | 掃動夾爪寬度、工具 Y/X 移動量與最多重試次數。 |
| `UNGRASPABLE_SWEEP_LEFT_DESCEND_POS`、`UNGRASPABLE_SWEEP_LEFT_X_AXIS`、`UNGRASPABLE_SWEEP_LEFT_Y_AXIS`、`UNGRASPABLE_SWEEP_LEFT_Z_AXIS` | 左側掃動的下降位置與工具姿態軸。 |
| `UNGRASPABLE_SWEEP_RIGHT_DESCEND_POS`、`UNGRASPABLE_SWEEP_RIGHT_X_AXIS`、`UNGRASPABLE_SWEEP_RIGHT_Y_AXIS`、`UNGRASPABLE_SWEEP_RIGHT_Z_AXIS` | 右側掃動的下降位置與工具姿態軸。 |
| `RAMEN_DESCEND_DZ`、`EGG_RAMEN_OFFSET_X`、`EGG_RAMEN_OFFSET_Y` | 拉麵碗放料下降距離與蛋放料 XY 偏移。 |

#### 4.6.5 蛋夾爪寬度與預張開

| 變數 | 說明 |
|---|---|
| `GRIPPER_WAIT_CLOSE_SEC`、`GRIPPER_WAIT_OPEN_SEC` | 夾爪關閉與打開後的等待時間。 |
| `GRIPPER_CLOSE_WIDTH_MM`、`USE_EGG_YAW_AXIS_WIDTH_FOR_GRIPPER_CLOSE` | 固定關夾寬度與是否改用相機蛋軸寬度動態計算。 |
| `GRIPPER_CLOSE_EXTRA_SHRINK_MM`、`EGG_GRIPPER_SMALL_WIDTH_THRESHOLD_MM`、`EGG_GRIPPER_SMALL_WIDTH_SHRINK_MM` | 一般額外縮量、小蛋寬度分界與小蛋縮量。 |
| `GRIPPER_CLOSE_RESEND_INTERVAL_SEC`、`GRIPPER_CLOSE_RESEND_MAX` | 真實夾爪關閉命令重送間隔與上限。 |
| `EGG_PRE_DESCEND_GRIPPER_WIDTH_MM`、`EGG_BASE_X_AXIS_SLIDE_PRE_DESCEND_EXTRA_MM`、`EGG_NON_BASE_X_AXIS_PRE_DESCEND_EXTRA_MM`、`EGG_PRE_DESCEND_GRIPPER_WAIT_SEC` | 蛋下降前預張開基準、base-X 滑入／非滑入額外寬度與等待時間。 |
| `EGG_PRE_DESCEND_BASE_X_PARALLEL_TOL_DEG`、`EGG_BASE_X_AXIS_SLIDE_DESCEND_CLEARANCE_M`、`EGG_BASE_X_AXIS_SLIDE_DESCEND_PER_STAGE_M` | 啟用 Base-X 滑入的平行誤差門檻（目前 `40°`）、總預留高度與每段下降量。 |

#### 4.6.6 蛋真實 TCP 下降確認

| 變數 | 說明 |
|---|---|
| `EGG_DESCEND_CONFIRM_HOLD_SEC`、`ENABLE_EGG_DESCEND_REAL_TCP_CONFIRM`、`EGG_DESCEND_REAL_TCP_AXIS_TOL_M`、`EGG_DESCEND_REAL_TCP_STABLE_SEC` | 下降到位保持、真實 TCP 確認開關、各軸容許誤差與穩定時間。 |
| `EGG_DESCEND_REAL_TCP_CLOSED_LOOP_ENABLE`、`EGG_DESCEND_REAL_TCP_CLOSED_LOOP_GAIN`、`EGG_DESCEND_REAL_TCP_CLOSED_LOOP_FILTER_ALPHA`、`EGG_DESCEND_REAL_TCP_CLOSED_LOOP_MAX_CORRECTION_M` | 真實 TCP 位置閉迴路開關、增益、濾波係數與最大修正量。 |
| `EGG_DESCEND_REAL_TCP_Y_INTEGRAL_ENABLE`、`EGG_DESCEND_REAL_TCP_Y_INTEGRAL_GAIN_PER_SEC`、`EGG_DESCEND_REAL_TCP_Y_INTEGRAL_MAX_M` | TCP Y 軸積分修正開關、每秒增益與累積上限。 |
| `EGG_DESCEND_CARTESIAN_SEGMENT_NEAR_FINAL_M`、`EGG_DESCEND_CARTESIAN_WAYPOINT_STEP_M`、`EGG_DESCEND_CARTESIAN_WAYPOINT_REACH_TOL_M` | 靠近終點時改用 Cartesian 分段的範圍、waypoint 步長與到位容差。 |

#### 4.6.7 Policy dt 與流程到位保持

| 變數 | 說明 |
|---|---|
| `EGG_PLATE_APPROACH_POLICY_DT`、`EGG_PLATE_APPROACH_REACH_HOLD_SEC` | 蛋盤拍照位接近的 policy dt 與到位保持。 |
| `EGG_APPROACH_POLICY_DT`、`EGG_APPROACH_REACH_HOLD_SEC` | 蛋上方接近的 policy dt 與到位保持。 |
| `EGG_DESCEND_POLICY_DT`、`EGG_DESCEND_REACH_HOLD_SEC` | 蛋下降的 policy dt 與到位保持。 |
| `EGG_LIFT_POLICY_DT`、`EGG_LIFT_REACH_HOLD_SEC` | 蛋夾取後抬升的 policy dt 與到位保持。 |
| `EGG_PRE_HOME_POLICY_DT`、`EGG_PRE_HOME_REACH_HOLD_SEC`、`EGG_PRE_HOME_OPEN_WAIT_SEC` | 蛋放料位的 policy dt、到位保持與開爪等待。 |
| `EGG_HOME_POLICY_DT`、`EGG_HOME_REACH_HOLD_SEC` | 蛋流程回 Home 的 policy dt 與到位保持。 |
| `IDLE_POLICY_DT` | 左臂無動作時的 RMPflow policy dt；不應覆蓋筍乾／木耳各階段 dt。 |
| `GRID_FOOD_OBSERVE_POLICY_DT`、`GRID_FOOD_APPROACH_POLICY_DT`、`GRID_FOOD_DESCEND_POLICY_DT`、`GRID_FOOD_GRIPPER_CLOSE_POLICY_DT`、`GRID_FOOD_LIFT_POLICY_DT`、`GRID_FOOD_PRE_HOME_POLICY_DT`、`GRID_FOOD_HOME_POLICY_DT` | 筍乾／木耳拍照、接近、下降、關爪、抬升、放料與回 Home 的獨立 policy dt。 |
| `RIGHT_LADLE_IDLE_POLICY_DT`、`RIGHT_LADLE_RECOVERY_POLICY_DT` | 右湯勺閒置與 shutdown 恢復運動的 policy dt。 |
| `FOOD_MOTION_TIMING_LOG_ENABLED` | 傳統食材動作計時 log 開關；目前為 `False`，不寫入檔案。 |

#### 4.6.8 姿態、到位與實體控制開關

| 變數 | 說明 |
|---|---|
| `LADLE_P7_5_RUNTIME_BASE_X_CORRECTION_M`、`LADLE_P7_5_RUNTIME_BASE_Z_CORRECTION_M` | 右湯勺 P7.5 runtime 的 base X/Z 位置修正。 |
| `WORLD_UP`、`TOOL_AXIS`、`CAMERA_FORWARD_AXIS_LOCAL`、`CAMERA_FORWARD_REF_BASE` | 世界向上軸、工具主軸與相機前向姿態參考軸。 |
| `EGG_YAW_OFFSET_DEG` | 相機蛋 yaw 轉成工具夾取 yaw 時的角度偏移。 |
| `REACH_TOL`、`REACH_HOLD_SEC`、`ORIENT_REACH_TOL_DEG` | 通用位置到位容差、保持時間與姿態角度容差。 |
| `ENABLE_DRIVE_PATCH`、`ENABLE_RTDE_STREAM`、`ENABLE_REAL_GRIPPER` | Isaac drive 修正、RTDE servoJ 串流與真實 Robotiq 開關。 |
| `USE_PLATE_NORMAL`、`USE_EGG_NORMAL`、`PREFER_ACCURATE_EGG_LOCK`、`NORMAL_KEEP_ANGLE_DEG` | 蛋盤／蛋法向量使用開關、精確姿態優先與法向量保留角。 |
| `DEBUG_RTDE_LOG_SEC` | RTDE 終端狀態輸出的節流週期，不是獨立檔案 log。 |
| `REAL_EE_TRAJ_LOG_ENABLED`、`REAL_EE_TRAJ_LOG_PERIOD_SEC` | 傳統真實末端軌跡紀錄開關與取樣週期；目前關閉。 |
| `SPIN_RAMP_SPEED_DEG_PER_SEC`、`SPIN_SETTLE_TOL_DEG` | 蛋工具軸旋轉速度與旋轉完成角度容差。 |
| `NON_SWEEPABLE_UNGRASPABLE_NORMAL_DOWN` | 不可撥不可夾備援夾取使用的固定向下法向量。 |

#### 4.6.9 座標轉換與蛋流程開關

| 變數 | 說明 |
|---|---|
| `RTDE_TCP_TO_ISAAC_Z_OFFSET`、`RTDE_TCP_TO_ISAAC_WORLD_OFFSET`、`SINGLE_TO_DUAL_WORLD_OFFSET` | RTDE TCP、Isaac world 與單臂／雙臂場景之間的位移補償。 |
| `ENABLE_RAMEN_PLACE_FLOW` | 蛋夾取後是否執行拉麵碗放料流程。 |
| `ENABLE_AUTO_EGG_AFTER_MANUAL_APPROACH`、`ENABLE_AUTO_EGG_DESCEND`、`ENABLE_EGG_LIFT_AFTER_GRASP` | 到手動接近位後自動續行、自動下降與夾取後抬升開關。 |
| `ENABLE_NO_BACK_EGG_REOBSERVE`、`ENABLE_NO_BACK_CAMERA_POSE_FOR_FIRST_EGG_OBSERVATION` | 無後方蛋是否二次拍照，以及第一次觀測是否就使用專用相機姿態。 |
| `EGG_MASK_STABILIZE_SEC` | 開啟蛋感知後等待遮罩穩定的時間。 |

#### 4.6.10 蛋姿態穩定鎖定與合理性檢查

| 變數 | 說明 |
|---|---|
| `EGG_STABLE_LOCK_MIN_SAMPLES`、`EGG_STABLE_LOCK_MAX_XY_SPREAD`、`EGG_STABLE_LOCK_MAX_Z_SPREAD`、`EGG_STABLE_LOCK_MAX_AGE_SEC` | 穩定蛋鎖定的最少樣本、XY/Z 最大擴散與樣本最大年齡。 |
| `EGG_STABLE_LOCK_IDENTITY_CLUSTER_M`、`EGG_STABLE_LOCK_REQUIRE_H_TIP` | 同一顆蛋的位置分群距離與是否必須收到 `h_tip`。 |
| `ENABLE_EGG_SANITY_CHECK_NEAR_MANUAL_TARGET`、`EGG_MAX_XY_DIST_FROM_MANUAL_TARGET`、`EGG_MAX_Z_BELOW_MANUAL_TARGET` | 手動目標附近合理性檢查開關、XY 最大距離與可低於基準的最大 Z。 |
| `OVERRIDE_EGG_Z_FROM_MANUAL_TARGET`、`EGG_SURFACE_BELOW_MANUAL_TARGET` | 是否以手動基準覆寫蛋 Z，以及蛋面相對基準的高度偏移。 |

#### 4.6.11 筍乾與木耳十八宮格

| 變數 | 說明 |
|---|---|
| `GRID_FOOD_STABLE_MIN_SAMPLES`、`GRID_FOOD_STABLE_MAX_XY_SPREAD_M`、`GRID_FOOD_STABLE_MAX_AGE_SEC` | 格子目標穩定鎖定的最少樣本、XY 擴散與樣本有效時間。 |
| `GRID_FOOD_LIFT_ALIGN_SEC`、`GRID_FOOD_RATIO_HEIGHT_TIE_EPS` | 抬升對齊時間與格子占用率近似時啟用高度比較的容差。 |
| `GRID_FOOD_EMPTY_BY_CELL_CENTER_DISTANCE_M` | 抓取後後續候選中心與第一次夾取中心的排除距離門檻。 |
| `GRID_FOOD_DESCEND_REAL_TCP_TOL_M`、`GRID_FOOD_DESCEND_REAL_TCP_STABLE_SEC` | 格子下降的真實 TCP 容差與穩定確認時間。 |
| `GRID_FOOD_POST_LIFT_TOOL_Y_DEG`、`GRID_FOOD_LIFT_TOOL_Z_POLICY_DT`、`GRID_FOOD_POST_LIFT_TOOL_Z_REACH_TOL_M`、`GRID_FOOD_POST_LIFT_TOOL_Z_REACH_HOLD_SEC` | 抬升後工具 Y 旋轉角、工具 Z 旋轉 dt、到位容差與保持時間。 |
| `GRID_FOOD_COMMON_PROFILE` | 筍乾與木耳共用的拍照姿態、夾爪、下降、抬升與放料設定。 |
| `GRID_FOOD_PROFILES` | 在共用 profile 上套用筍乾與木耳差異值的資料驅動設定。 |
| `GRID_FOOD_NAMES`、`GRID_FOOD_CAPTURE_ORDER`、`LEFT_FOOD_NAMES` | 格子食材名稱、A 拍照順序與所有左臂食材名稱集合。 |

`EGG_GRIPPER_WIDTH_LOG_PATH`、`ISAAC_SHUTDOWN_TRACE_PATH` 已移除；啟動腳本也不再產生帶時間戳的 Isaac 終端 log。現在只保留左臂與右湯勺安全恢復所需的 JSON。

## 5. 蛋完整流程

1. `start_auto_egg_sequence` 啟動蛋流程並要求移動到蛋盤拍照位。
2. `set_egg_detection_gate(True)` 要求相機發布 yaw 與精確姿態。
3. `_update_egg_observation_waits` 等待蛋盤、`bowl_status` 及穩定蛋樣本。
4. 若只剩 P3／P4 可掃不可抓蛋，啟動 `start_ungraspable_sweep`。
5. 若有正常候選，`stable_accurate_egg_candidate` 以位置叢集和多數決鎖定同一顆蛋。
6. 鎖定位置、法向量、yaw、選中軸寬、另一軸寬、軸名、後方蛋與 `h_tip`。
7. 無後方蛋時可進入 `start_no_back_reobserve`，從第二相機姿態重新確認。
8. `request_egg_move` 建立蛋接近目標；姿態以工具 Z 對準法向量並沿選中軸旋轉。
9. `start_pre_descend_flow` 判斷下降策略：側邊備援蛋固定滑入；一般蛋只要相機所選軸與 Base-X 誤差 `≤40°` 便滑入，否則垂直下降。相機若偵測到剛好兩個空端點且分屬長、短軸，會先改選較接近 Base-X 的軸；這是改選軸規則，不會取消原本 `≤40°` 的滑入條件。
10. `initialize_egg_descend_cartesian_path` 將下降路徑分段，避免直接跳到最終抓取點。
11. `real_tcp_descend_confirmed` 同時確認 Isaac 到位、工具方向與真實 TCP。
12. `update_post_egg_flow` 關夾、抬升，依設定放入拉麵碗。
13. 共用 `start_pre_home_release_flow` 開夾並安全回 Home。

## 6. 筍乾與木耳完整流程

兩者共用相同程式，只由 `GRID_FOOD_PROFILES[food]` 提供不同拍照位、姿態、offset、夾爪寬度與旋轉序列。

1. `request_grid_food_sequence(food)` 清除舊取樣並移動到指定食材拍照位。
2. 相機透過 `/grid_food/menma/occupied_cells` 或 `/grid_food/fungus/occupied_cells` 發布十八宮格 JSON。
3. `_grid_food_cells_cb` 保存 `occupied_cells` 與 `all_cells`，並確認抓過的格子是否已空。
4. `stable_grid_food_candidate` 要求同一格在時間窗內維持穩定。
5. `_update_grid_food_observe_action` 鎖定格子中心、尺寸、法向量與高度。
6. `_update_grid_food_approach_action` 移動到格子上方。
7. `_update_grid_food_descend_action` 下降並以 RTDE 確認真實 TCP。
8. `_update_grid_food_grasp_action` 關閉夾爪，並登記該格等待下次拍照確認是否為空。
9. `_update_grid_food_lift_action` 先保持抓取姿態抬升一段，再轉成固定向下姿態。
10. `_update_grid_food_post_lift_action` 執行工具 Z 循環、base-X 退回與工具 Y 旋轉。
11. 共用放料流程移動到食材放料點、開夾並經中繼點回 Home。

## 7. A／S 連續流程

### 7.1 A：只辨識並凍結目標

順序為：

```text
木耳拍照鎖格 → 筍乾拍照鎖格 → 蛋拍照並停在接近位置
```

- 不執行筍乾與木耳夾取。
- 蛋不下降，只保存精確蛋姿態。
- 三種食材目標都完整後，`as_capture_ready=True`。

### 7.2 S：使用凍結目標執行

順序為：

```text
蛋夾取 → 筍乾夾取 → 木耳夾取
```

S 不重新選擇 A 已鎖定的目標，避免拍照結果改變造成抓取位置跳動。

## 8. 右湯勺流程

1. `RightLadlePathTools` 找到指定食材最新或設定的 JSON。
2. `_load_food_paths` 載入 entry 與 scoop waypoint。
3. `waypoint_to_ladle_target` 由 spoon A/B 點反算末端位置與姿態。
4. `_append_finish_targets` 加入 P8、P8.5、P9、P9.5 抖動及 P10 Home。
5. `start(food)` 選擇該食材下一條路徑並重設 index。
6. `update` 依 `RightLadleStage`、位置誤差、保持時間和 timeout 推進。
7. 蔥到達最後一個 P9.5 時，`_mark_scallion_p9_5_complete` 提供 PLC 完成條件；P10 仍繼續安全回 Home。

## 9. ROS 2 通訊

### 9.1 dual 發布給相機

| Topic | 型別 | 功能 |
|---|---|---|
| `/egg_face_up/enable_yaw` | `std_msgs/Bool` | 控制蛋 yaw 發布閘門。 |
| `/egg_face_up/enable_accurate_pose` | `std_msgs/Bool` | 控制精確姿態發布；新觀測前會清除舊樣本。 |

### 9.2 相機發布給 dual

| Topic | dual 用途 |
|---|---|
| `/egg_plate/pose`、`/egg_plate/normal` | 蛋盤拍照目標與方向。 |
| `/egg_face_up/rough_pose`、`/egg_face_up/accurate_pose` | 蛋粗略與精確位置。 |
| `/egg_face_up/normal` | 蛋表面向下法向量。 |
| `/egg_face_up/yaw_deg` | 蛋夾取軸方向。 |
| `/egg_face_up/yaw_axis_width_mm` | 選中軸寬及夾爪計算。 |
| `/egg_face_up/yaw_other_axis_width_mm` | 另一軸寬。 |
| `/egg_face_up/yaw_axis_name` | `major` 或 `minor`。 |
| `/egg_face_up/yaw_axis_center_to_endpoint_max_mm` | 中心到軸端最大距離。 |
| `/egg_face_up/yaw_axis_base_x_err_deg` | base-X 滑入策略判斷。 |
| `/egg_face_up/back_has_egg` | 後方蛋策略判斷。 |
| `/egg_face_up/bowl_status` | 空碗、可抓、可掃、側邊備援及選中蛋端點空帶資訊。 |
| `/egg_face_up/h_tip` | 蛋下降距離修正。 |
| `/grid_food/menma/occupied_cells` | 筍乾十八宮格 JSON。 |
| `/grid_food/fungus/occupied_cells` | 木耳十八宮格 JSON。 |

兩端必須使用相同的 `ROS_DOMAIN_ID` 與 `RMW_IMPLEMENTATION`。

## 10. 鍵盤操作

實際按鍵由 `create_keyboard_config()` 建立，目前功能如下：

| 功能 | 行為 |
|---|---|
| 蛋／筍乾／木耳單獨鍵 | 啟動指定左臂食材流程。 |
| A | 拍照並凍結木耳、筍乾、蛋目標。 |
| S | 執行 A 凍結的蛋、筍乾、木耳目標。 |
| D | 左右臂都閒置時重設格子高度與湯勺路徑 index。 |
| 芝麻／蔥單獨鍵 | 啟動指定右湯勺流程。 |
| Y | 依序執行芝麻與蔥。 |
| Escape | 取消左臂流程並停止右湯勺 active 狀態。 |

T 鍵 Q→W→E 舊流程已移除。

## 11. PLC 任務與完成條件

| 任務碼 | 主要動作 | 完成條件 |
|---|---|---|
| `101` | 左臂使用已拍攝目標執行蛋、筍乾與木耳 | 最後木耳開夾放料命令已送出；手臂仍可繼續安全回 Home。 |
| `102` | 右湯勺流程 | 蔥最後 P9.5 完成；P10 繼續回 Home。 |
| `103` | 左臂 A 拍照鎖定 | 木耳、筍乾與蛋目標均已凍結。 |

EMC 發生時，程式先凍結恢復狀態、停止流程與 RTDE 命令，再等待 PLC 和 watchdog 處理重新啟動。

## 12. 急停與異常恢復

只保留兩個具流程用途的 JSON，兩者都以暫存檔寫完後 `replace`，不會不斷新增檔案。

| 檔案 | 用途 |
|---|---|
| `logs/left_arm_shutdown_status.json` | 保存左臂食材、substep、是否需要退讓、退讓方向及距離。 |
| `logs/right_ladle_shutdown_checkpoint.json` | 保存右湯勺目前食材、path、waypoint 與恢復所需資料。 |

左臂恢復方向：

- 蛋夾取前／抬升前：沿工具負 Z 安全退出。
- 筍乾／木耳夾取前／抬升前：沿 base 正 Z 安全抬升。
- 已進入共用放料前流程：沿 base 負 X 退讓。

右湯勺恢復會依 checkpoint 判斷目前是否已越過 P7，再執行安全抬升與回 Home。

## 13. 每幀執行順序

`SimulationLoopRuntime.tick()` 大致順序如下：

1. 偵測示教器或 PLC 急停狀態。
2. 處理 PLC bridge 任務與完成條件。
3. `world.step(render=True)` 更新 Isaac Sim。
4. spin ROS，將一般食材位置同步到 USD Prim。
5. spin 左臂 D405 perception executor。
6. 更新左臂 `LeftArmSystem` 與 `MoveToEggPlateController`。
7. 更新右臂 `RightLadlePlanRunner`。
8. 取得左右 RMPflow 關節目標並送到 RTDE streamer。
9. 更新恢復 checkpoint、急停確認及 watchdog 重啟條件。

## 14. 維護注意事項

- 函數說明順序應持續與 Python 原始碼一致；新增、刪除或移動函數後要同步更新第 3 節。
- `EggPlateBridge` 收到精確蛋位置時，會把當時的 yaw、尺寸、法向量與碗狀態存入同一樣本，不應拆開鎖定。
- 筍乾／木耳格子中心已是 base／Isaac 座標，不可再次套用蛋的 RTDE-to-Isaac Z 補償。
- `grid_food_step`、`post_step` 與 `pre_home_release_step` 同時提供安全恢復 `_substep()` 使用，重新命名時必須同步 watchdog。
- 右湯勺 target 改變姿態或位置後，必須同步更新 `target_position`、`target_orientation`、`R_target`、`spoon_a` 與 `spoon_b`。
- 修改 ROS JSON 欄位時，必須同步修改相機發布端與 dual callback。
- 調整下降、退讓或 Home 參數前，應先在不連接真實手臂的 Isaac 模式驗證路徑。
