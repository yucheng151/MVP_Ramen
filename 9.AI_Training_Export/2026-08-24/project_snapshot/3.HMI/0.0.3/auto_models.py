"""全自動HMI的本機資料模型；PLC通訊完成後可替換資料來源。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import threading


DEFAULT_STATE = {
    "next_unit_id": 1001,
    "cabinets": [
        {"no": number, "quantity": 0, "capacity": 20}
        for number in range(1, 11)
    ],
    "empty_box_bins": [
        {"no": number, "quantity": 0, "capacity": 20}
        for number in range(1, 3)
    ],
    "orders": [],
    "baskets": [
        {"no": number, "state": "Idle", "unit_id": None, "cabinet_no": None}
        for number in range(1, 4)
    ],
    "stations": [
        {"no": 1, "name": "落碗", "state": "Idle", "unit_id": None},
        {"no": 2, "name": "放麵 & UR1", "state": "Idle", "unit_id": None},
        {"no": 3, "name": "UR2", "state": "Idle", "unit_id": None},
        {"no": 4, "name": "注湯 & 完成", "state": "Idle", "unit_id": None},
    ],
}


class AutoHMIStore:
    """保存訂單、麵櫃、空盒櫃、麵篩與四站的HMI端狀態。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.state = deepcopy(DEFAULT_STATE)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in DEFAULT_STATE:
                    if key in loaded:
                        self.state[key] = loaded[key]
        except (OSError, ValueError, TypeError):
            # 壞檔不阻止HMI啟動；下一次儲存會建立有效資料。
            self.state = deepcopy(DEFAULT_STATE)

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self.state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(self.path)

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self.state)

    def update_inventory(self, cabinets: list[tuple[int, int]], bins: list[tuple[int, int]]) -> None:
        with self.lock:
            for row, (quantity, capacity) in zip(self.state["cabinets"], cabinets):
                row["quantity"] = max(0, int(quantity))
                row["capacity"] = max(1, int(capacity))
            for row, (quantity, capacity) in zip(self.state["empty_box_bins"], bins):
                row["quantity"] = max(0, int(quantity))
                row["capacity"] = max(1, int(capacity))
            self.save()

    def reserved(self, cabinet_no: int) -> int:
        with self.lock:
            return sum(
                1 for order in self.state["orders"]
                if order["cabinet_no"] == cabinet_no
                and order["status"] not in ("Complete", "Cancelled")
            )

    def add_order(self, cabinet_no: int, firmness: str) -> int:
        with self.lock:
            cabinet = self.state["cabinets"][cabinet_no - 1]
            if cabinet["quantity"] - self.reserved(cabinet_no) <= 0:
                raise ValueError(f"麵櫃 {cabinet_no} 沒有可用麵盒")
            unit_id = int(self.state["next_unit_id"])
            self.state["next_unit_id"] = unit_id + 1
            self.state["orders"].append({
                "unit_id": unit_id,
                "cabinet_no": cabinet_no,
                "firmness": firmness,
                "status": "Queued",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            })
            self.save()
            return unit_id

    def cancel_order(self, unit_id: int) -> bool:
        with self.lock:
            for order in self.state["orders"]:
                if order["unit_id"] == unit_id and order["status"] == "Queued":
                    order["status"] = "Cancelled"
                    self.save()
                    return True
        return False

    def advance_demo(self) -> str:
        """無PLC時推進一個示範步驟；不會送出任何實機命令。"""
        with self.lock:
            active = next(
                (order for order in self.state["orders"]
                 if order["status"] not in ("Complete", "Cancelled")),
                None,
            )
            if active is None:
                return "沒有等待中的訂單"

            unit_id = active["unit_id"]
            status = active["status"]
            baskets = self.state["baskets"]
            stations = self.state["stations"]

            if status == "Queued":
                basket = next((item for item in baskets if item["state"] == "Idle"), None)
                if basket is None:
                    return "三個麵篩都在使用中"
                basket.update(state="Cooking", unit_id=unit_id, cabinet_no=active["cabinet_no"])
                active["basket_no"] = basket["no"]
                active["status"] = "Cooking"
                message = f"Unit {unit_id} 使用麵篩 {basket['no']} 開始煮麵"
            elif status == "Cooking":
                stations[0].update(state="Working", unit_id=unit_id)
                active["status"] = "Bowl Drop"
                message = f"Unit {unit_id} 執行落碗"
            elif status == "Bowl Drop":
                stations[0].update(state="Complete", unit_id=unit_id)
                stations[1].update(state="Working", unit_id=unit_id)
                active["status"] = "Noodle + UR1"
                message = f"Unit {unit_id} 執行放麵與UR1"
            elif status == "Noodle + UR1":
                stations[1].update(state="Complete", unit_id=unit_id)
                stations[2].update(state="Working", unit_id=unit_id)
                active["status"] = "UR2"
                message = f"Unit {unit_id} 執行UR2"
            elif status == "UR2":
                stations[2].update(state="Complete", unit_id=unit_id)
                stations[3].update(state="Working", unit_id=unit_id)
                active["status"] = "Soup"
                message = f"Unit {unit_id} 執行注湯"
            else:
                stations[3].update(state="Complete", unit_id=unit_id)
                active["status"] = "Complete"
                basket_no = active.get("basket_no")
                if basket_no:
                    baskets[basket_no - 1].update(state="Idle", unit_id=None, cabinet_no=None)
                cabinet = self.state["cabinets"][active["cabinet_no"] - 1]
                cabinet["quantity"] = max(0, cabinet["quantity"] - 1)
                message = f"Unit {unit_id} 模擬完成"
            self.save()
            return message
