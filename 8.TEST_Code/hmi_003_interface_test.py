#!/usr/bin/env python3
"""HMI 0.0.3 全頁面、Mock命令與AUTO資料介面測試。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import tkinter.messagebox as messagebox


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "3.HMI" / "0.0.3"
sys.path.insert(0, str(HMI_DIR))

from auto_models import AutoHMIStore  # noqa: E402
from HMI_command import HMICommand  # noqa: E402
from HMI_ui import HMIUI  # noqa: E402


EXPECTED_PAGES = {
    "MainPage",
    "AutoSystemPage",
    "ConveyorControlPage",
    "AlarmPage",
    "CommunicationPage",
    "IPCCommunicationPage",
    "RobotPage",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    # 測試期間不顯示阻塞式對話框。
    originals = (messagebox.showinfo, messagebox.showwarning, messagebox.showerror,
                 messagebox.askyesno, messagebox.askokcancel)
    messagebox.showinfo = lambda *_args, **_kwargs: "ok"
    messagebox.showwarning = lambda *_args, **_kwargs: "ok"
    messagebox.showerror = lambda *_args, **_kwargs: "ok"
    messagebox.askyesno = lambda *_args, **_kwargs: True
    messagebox.askokcancel = lambda *_args, **_kwargs: True

    app = None
    temp = tempfile.TemporaryDirectory()
    try:
        app = HMIUI(mock=True)
        app.root.withdraw()
        app.root.update_idletasks()
        app.auto_store = AutoHMIStore(Path(temp.name) / "auto_hmi_state.json")

        check(set(app.pages) == EXPECTED_PAGES, f"頁面清單不符：{set(app.pages)}")
        for page_name in EXPECTED_PAGES:
            app.show_page(page_name)
            app.root.update_idletasks()
            app.pages[page_name].update_global_status() if hasattr(app.pages[page_name], "update_global_status") else None
            app.pages[page_name].refresh()
        print(f"[PASS] 全部{len(EXPECTED_PAGES)}個主頁面建立、切換與刷新")

        auto_page = app.pages["AutoSystemPage"]
        for tab_id in auto_page.tabs.tabs():
            auto_page.tabs.select(tab_id)
            app.root.update_idletasks()
        check(len(auto_page.tabs.tabs()) == 7, "AUTO SYSTEM分頁不是7個（含運行LOG）")
        check(
            hasattr(auto_page, "plc_debug_log_tree"),
            "AUTO SYSTEM缺少PLC Debug LOG檢視表",
        )
        check(len(auto_page.sim_live_station_labels) == 4, "模擬工作台不是四站顯示")
        check(len(auto_page.sim_station_buttons) == 5, "模擬工作台缺少站點控制")
        check(auto_page._cabinet_source is not None, "麵櫃底圖沒有載入")
        check(len(auto_page._cabinet_hotspots) == 12, "麵櫃熱區不是12格")
        print("[PASS] AUTO流程、訂單FIFO、麵櫃/空盒、PLC規劃、一鍵測試、模擬控制六個分頁")
        print("[PASS] 麵櫃底圖與12個BOX設定熱區")

        # 設定十格生麵各5盒，兩格空盒各1盒。
        for quantity, capacity in auto_page.cabinet_vars:
            quantity.set("5")
            capacity.set("20")
        for quantity, capacity in auto_page.bin_vars:
            quantity.set("1")
            capacity.set("20")
        auto_page._save_inventory()
        inventory = app.auto_store.snapshot()
        check(sum(row["quantity"] for row in inventory["cabinets"]) == 50, "生麵BOX合計錯誤")
        check(sum(row["quantity"] for row in inventory["empty_box_bins"]) == 2, "空盒BOX合計錯誤")

        # PLC即時流程刷新時，不可把操作員正在編輯的BOX數量改回舊值。
        auto_page.selected_quantity_var.set("9")
        auto_page._last_signature = None
        auto_page.refresh()
        check(
            auto_page.selected_quantity_var.get() == "9",
            "PLC畫面刷新覆蓋了正在編輯的BOX數量",
        )

        auto_page.cabinet_var.set("1")
        auto_page.firmness_var.set("正常")
        auto_page._add_order()
        auto_page.cabinet_var.set("2")
        auto_page.firmness_var.set("硬")
        auto_page._add_order()
        state = app.auto_store.snapshot()
        check([row["unit_id"] for row in state["orders"]] == [1001, 1002], "UnitID/FIFO錯誤")
        for _ in range(6):
            app.auto_store.advance_demo()
        state = app.auto_store.snapshot()
        check(state["orders"][0]["status"] == "Complete", "第一碗沒有完成")
        check(state["cabinets"][0]["quantity"] == 4, "完成後沒有扣除BOX")
        print("[PASS] BOX數量、容量、保留量、FIFO、UnitID與完成扣庫存")

        check(app.plc.connect(), "Mock PLC無法連線")
        command_tests = (
            ("Initialize", app.command.send_initialize()),
            ("Alarm Reset", app.command.send_alarm_reset()),
            ("Conveyor Run", app.command.send_conveyor_run(150)),
            ("Conveyor Stop", app.command.send_conveyor_stop()),
            ("Set Speed", app.command.send_set_conveyor_speed(200)),
            ("Bowl Dispense", app.command.send_bowl_dispense()),
            ("Small Material First", app.command.send_small_material_first()),
            ("Small Material Last", app.command.send_small_material_last()),
            ("Semi Auto", app.command.send_semi_auto_test(0x00FF)),
            ("Mode Manual", app.command.send_machine_mode(0)),
            ("Mode Semi", app.command.send_machine_mode(1)),
            ("Mode Auto", app.command.send_machine_mode(2)),
            ("Robot Load", app.command.send_robot_manual(1, 1, 1, 1)),
            ("Robot Shake", app.command.send_robot_manual(2, 0, 1, 0)),
        )
        failed = [name for name, result in command_tests if not result.ok]
        check(not failed, f"Mock命令失敗：{failed}")

        # 模擬 HMI 程式重開：新 HMICommand 物件必須從 PLC 的 D1001 接續，
        # 不能重新使用 Index 1。
        previous_index = app.plc.read_d(1001, 1)[0]
        restarted_command = HMICommand(app.plc)
        restarted_result = restarted_command.send_alarm_reset()
        check(restarted_result.ok, "HMI重開後命令送出失敗")
        check(
            restarted_result.command_index == ((previous_index + 1) & 0xFFFF),
            "HMI重開後沒有從PLC D1001接續命令Index",
        )

        heartbeat = app.heartbeat.tick()
        status = app.status.read_status()
        check(heartbeat.ok, f"Mock HMI心跳失敗：{heartbeat.message}")
        check(status.ok, f"Mock狀態讀取失敗：{status.message}")
        print(f"[PASS] {len(command_tests)}種HMI命令、重開Index接續、心跳與狀態讀取")

        print("RESULT: PASS - HMI 0.0.3介面與Mock功能全部通過。")
    finally:
        if app is not None:
            app._stop_event.set()
            app.plc.close()
            try:
                app.root.destroy()
            except Exception:
                pass
        temp.cleanup()
        (messagebox.showinfo, messagebox.showwarning, messagebox.showerror,
         messagebox.askyesno, messagebox.askokcancel) = originals


def main() -> int:
    _ = argparse.ArgumentParser(description="HMI 0.0.3全介面測試").parse_args()
    try:
        run()
    except Exception as exc:
        print(f"RESULT: FAIL - {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
