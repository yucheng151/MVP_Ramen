"""HMI 與 PLC 的 Modbus TCP 雙向握手心跳模組。

模組用途
========
本檔案負責一件事：持續確認 HMI 與 PLC 之間不只是 TCP Socket 已連線，
而是雙方程式都仍在正常執行。它可以：

1. 被其他 HMI 主程式 ``import``，由主程式定期呼叫 :meth:`HMIHeartbeat.tick`。
2. 直接執行本檔案，作為獨立的命令列心跳測試工具。

本模組使用同步（blocking）Modbus TCP client。每次 ``tick()`` 都會先讀取 PLC，
再寫回一個 WORD，因此不要在 GUI 主執行緒內直接做長時間阻塞呼叫；正式整合到
Tkinter、Qt 等 GUI 時，建議由排程器或背景執行緒定期呼叫。

PLC 暫存器配置
===============

================  =============================  ==========
方向              PLC 變數名稱                    PLC 裝置
================  =============================  ==========
HMI -> PLC         HMItoPLC_HB_ReturnIndex        D1005
PLC -> HMI         PLCtoHMI_HB_Index              D1100
PLC -> HMI         HMI_CommStatus                 D1105
================  =============================  ==========

重要：本專案已用實機確認，PyModbus 位址直接對應 PLC D 編號：

* ``address=1005`` 就是 D1005。
* ``address=1100`` 就是 D1100。
* ``address=1105`` 就是 D1105。

握手協定
========

1. PLC 將目前 Index 寫入 D1100。
2. HMI 讀取 D1100，計算 ``ReturnIndex = PLC_Index + 1``。
3. HMI 將 ReturnIndex 寫入 D1005。
4. PLC 驗證 D1005 正確後，再把下一個 Index 寫入 D1100。
5. PLC 用 D1105 回報 HMI 是否在線：``1`` 表示在線，``0`` 表示尚未確認或逾時。

正常交換範例（PLC 初始 Index 為 1）：

``PLC D1100=1 -> HMI D1005=2 -> PLC D1100=3 -> HMI D1005=4``

若 PLC 初始 Index 為 0，則會看到 ``0 -> 1 -> 2 -> 3``；兩者使用的是同一套協定，
差別只在 PLC 的初始值。Index 使用 16-bit 無號值，範圍是 0~65535，超過上限時：

``PLC D1100=65535 -> HMI D1005=0 -> PLC D1100=1``

長時間或隔夜測試經過多次 ``65535 -> 0`` 是正常現象，不是資料溢位錯誤。

連線與錯誤處理
================

* 已用 ``pymodbus 3.14.0`` 驗證；新版 Unit ID 參數名稱為 ``device_id``。
* Modbus 或網路例外會轉成狀態結果，不會讓命令列噴出 traceback 後退出。
* 獨立執行時，斷線後每 2 秒重試；重連成功會自動恢復心跳。
* ``tick().ok`` 只有在本輪讀寫成功且 PLC 回傳 D1105=1 時才為 ``True``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


# =====================================================
# PLC D 暫存器位址
#
# 這些數字會直接傳給 PyModbus 的 address 參數。
# 本專案的映射是 address N = PLC DN，不可自行做 -1 位移。
# =====================================================

D_HMI_TO_PLC_HB_RETURN_INDEX = 1005   # HMI 寫入：PLC Index + 1
D_PLC_TO_HMI_HB_INDEX = 1100          # HMI 讀取：PLC 目前發出的 Index
D_HMI_COMM_STATUS = 1105              # HMI 讀取：1=在線，0=未確認/逾時


@dataclass
class HMIHeartbeatResult:
    """單次 :meth:`HMIHeartbeat.tick` 的結果快照。

    Attributes:
        ok:
            本輪 Modbus 讀寫成功，而且 PLC 的 D1105 等於 1 時為 ``True``。
            注意：TCP 連線成功不等於 ``ok=True``；PLC 還必須確認握手正確。
        plc_index:
            本輪從 D1100 讀到的 PLC Index。未連線或讀取失敗時為 ``None``。
        return_index:
            本輪計算並準備寫入 D1005 的 HMI Return Index。無法計算時為 ``None``。
        hmi_comm_status:
            本輪從 D1105 讀到的狀態，通常 ``1=在線``、``0=未確認/逾時``；
            未讀到資料時為 ``None``。
        message:
            供畫面或 Log 顯示的人類可讀訊息。呼叫端應優先判斷 ``ok``，
            不要用比對訊息文字的方式判斷程式流程。
    """

    ok: bool                              # 本輪完整握手是否正常
    plc_index: Optional[int]              # D1100
    return_index: Optional[int]           # 寫入 D1005 的值
    hmi_comm_status: Optional[int]        # D1105
    message: str                          # 狀態/錯誤說明


class HMIHeartbeat:
    """HMI <-> PLC 雙向握手心跳控制器。

    最小使用流程::

        hb = HMIHeartbeat(ip="192.168.1.5")
        if hb.connect():
            result = hb.tick()
            print(result.ok, result.message)
        hb.close()

    Args:
        ip:
            PLC Ethernet IP。
        port:
            Modbus TCP 服務埠，標準值通常為 502。
        slave_id:
            Modbus Unit/Device ID。PyModbus 3.14 呼叫時會傳入 ``device_id``。
            變數名稱保留 ``slave_id`` 是為了符合既有專案用語。
        timeout:
            單次 Socket/Modbus 操作的逾時秒數。這不是 PLC 的心跳逾時時間；
            PLC 心跳逾時由 PLC ST 程式的 Timer 決定。

    Notes:
        * 這個類別包裝的是同步 client，不保證 thread-safe；同一實例不要被多個執行緒
          同時呼叫 ``tick()``。
        * ``connect()`` 只建立 TCP/Modbus 連線；是否真正完成心跳要看 ``tick().ok``。
        * ``timeout`` 套用在單次 Modbus 操作。一次 ``tick()`` 包含一次讀與一次寫，
          異常時的總阻塞時間可能高於單一 ``timeout``，GUI 整合時要納入考量。
        * 本類別本身不在背景自動重連；檔案最下方的自動重連只屬於單檔測試程式。
          被其他程式 import 時，呼叫端必須自行排程 ``connect()``/``tick()``。
        * 每次成功的 ``tick()`` 都會寫入 D1005，因此測試時不要同時啟動兩個 HMI
          心跳程序，否則兩個程序可能互相覆寫 Return Index。
    """

    def __init__(
        self,
        ip: str = "192.168.1.5",
        port: int = 502,
        slave_id: int = 1,
        timeout: float = 1.0,
    ):
        # 保存連線參數，方便主程式顯示、重連或後續擴充成可設定介面。
        self.ip = ip
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout

        # 使用同步 Modbus TCP client。client 建立時尚未連線，實際 Socket 由
        # connect() 開啟。斷線後可在同一個 client 上再次呼叫 connect()。
        self.client = ModbusTcpClient(
            host=self.ip,
            port=self.port,
            timeout=self.timeout,
        )

        # 本類別自己的連線旗標。任何讀寫例外都會透過 _mark_disconnected()
        # 將它清為 False，讓外層主迴圈進入自動重連流程。
        self.connected = False

        # 最近一次連線/讀寫錯誤。None 代表目前沒有尚未處理的錯誤。
        # 可提供給 GUI 狀態列或 Log 顯示。
        self.last_error: Optional[str] = None

        # 最近一次成功完成 Modbus 讀寫後的值。這些欄位主要供 GUI 或診斷使用；
        # 心跳運算本身每輪仍以 PLC 當下回傳值為準，不依賴快取值。
        self.last_plc_index: Optional[int] = None
        self.last_return_index: Optional[int] = None
        self.last_hmi_comm_status: Optional[int] = None

    # =====================================================
    # Connection
    # =====================================================

    def connect(self) -> bool:
        """嘗試建立 PLC Modbus TCP 連線。

        Returns:
            連線成功回傳 ``True``；失敗回傳 ``False``。預期中的 Modbus 或網路
            例外不會向外拋出，而是寫入 :attr:`last_error`。

        Notes:
            此方法只確認 TCP/Modbus client 能連上 ``ip:port``，尚未驗證 D 暫存器
            或雙向心跳。連線後仍須呼叫 :meth:`tick`。
        """
        try:
            self.connected = bool(self.client.connect())
        except (ModbusException, OSError) as exc:
            # 將現場常見的拔線、PLC 關機、Socket timeout 等狀況轉成狀態值，
            # 避免獨立測試程式因 traceback 直接退出。
            self.connected = False
            self.last_error = str(exc)
            return False

        if self.connected:
            self.last_error = None
        else:
            self.last_error = f"無法連線 {self.ip}:{self.port}"

        return self.connected

    def close(self) -> None:
        """關閉 Modbus TCP 連線並清除連線旗標。

        此方法可重複呼叫；即使 Socket 已失效，預期中的關閉例外也會被忽略。
        它不會清除最近一次成功的心跳資料，方便斷線畫面保留最後讀值。
        """
        try:
            self.client.close()
        except (ModbusException, OSError):
            pass
        finally:
            self.connected = False

    def _mark_disconnected(self, message: str) -> None:
        """統一處理執行中的讀寫斷線。

        Args:
            message: 要保留在 :attr:`last_error` 的診斷訊息。

        先保存錯誤，再關閉失效 Socket 並把 ``connected`` 清為 ``False``；外層
        主迴圈下一輪看到斷線狀態後，就會依設定的間隔重新呼叫 ``connect()``。
        """
        self.last_error = message
        self.close()

    # =====================================================
    # 底層 Modbus D 暫存器存取
    #
    # 將 PyModbus response/exception 轉成簡單的 Optional 或 bool，讓上層
    # tick() 不需要直接依賴 PyModbus 的 response 類別。
    # =====================================================

    def read_d(self, address: int, count: int = 1) -> Optional[List[int]]:
        """連續讀取 PLC Holding Registers（本專案即 D 暫存器）。

        Args:
            address:
                起始 D 位址。本專案直接使用 D 編號，例如 ``1100`` 代表 D1100，
                不可減 1。
            count:
                要連續讀取的 WORD 數量，預設為 1。必須是 PLC 支援的合法範圍。

        Returns:
            成功時回傳由 0~65535 整數組成的 list；通訊失敗或 PLC 回傳 Modbus
            error response 時回傳 ``None``，並把實例標記為斷線。

        Example:
            ``read_d(1100, 6)`` 會依序取得 D1100、D1101、...、D1105。

        Notes:
            ``device_id`` 是 PyModbus 3.14 的 Unit ID 參數名稱。若未來更換套件
            大版本，應先核對官方 API，不要直接改回舊版的 ``unit``/``slave``。
        """

        try:
            # Function Code 03：Read Holding Registers。
            result = self.client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.slave_id,
            )
        except (ModbusException, OSError) as exc:
            # 包含連線被重置、PLC 關機、Socket timeout 等傳輸層錯誤。
            self._mark_disconnected(f"讀取 D{address} 失敗：{exc}")
            return None

        if result.isError():
            # PyModbus 有些錯誤會以 response 回傳而不是 raise，例如 Modbus
            # exception response。統一視為本輪通訊失敗並交給外層重連。
            self._mark_disconnected(f"讀取 D{address} 失敗：{result}")
            return None

        # registers 的第 0 筆對應 address；第 n 筆對應 address+n。
        return result.registers

    def write_d(self, address: int, value: int) -> bool:
        """寫入一個 PLC Holding Register（本專案即一個 D 暫存器）。

        Args:
            address:
                目標 D 位址，例如 ``1005`` 代表 D1005，不可減 1。
            value:
                要寫入的數值。寫入前會限制成 16-bit WORD（0~65535）。

        Returns:
            PLC 正常接受寫入時回傳 ``True``；例外或 Modbus error response 時
            回傳 ``False``，並把實例標記為斷線。

        Notes:
            ``value & 0xFFFF`` 會保留最低 16 bit。例如 65536 會變成 0，
            正好符合本心跳協定的 UINT/WORD 循環需求。一般業務資料若不允許截斷，
            應在呼叫本方法前另外做範圍驗證。
        """

        # Modbus register 是 16-bit。此遮罩同時處理 65535 後回 0 的情況。
        value = int(value) & 0xFFFF

        try:
            # Function Code 06：Write Single Register。
            result = self.client.write_register(
                address=address,
                value=value,
                device_id=self.slave_id,
            )
        except (ModbusException, OSError) as exc:
            # 發生傳輸層例外時關閉舊 Socket，避免後續一直使用失效連線。
            self._mark_disconnected(f"寫入 D{address} 失敗：{exc}")
            return False

        if result.isError():
            # 將 PLC/Modbus 錯誤回覆轉成 False，並保留原始 response 文字供診斷。
            self._mark_disconnected(f"寫入 D{address} 失敗：{result}")
            return False

        return True

    # =====================================================
    # 雙向握手心跳
    # =====================================================

    @staticmethod
    def calc_return_index(plc_index: int) -> int:
        """計算 HMI 應回覆給 PLC 的下一個 16-bit Index。

        Args:
            plc_index: 從 PLC D1100 讀到的值。

        Returns:
            ``(plc_index + 1)`` 的 16-bit 無號結果。

        Examples:
            * ``calc_return_index(1) == 2``
            * ``calc_return_index(65534) == 65535``
            * ``calc_return_index(65535) == 0``

        ``& 0xFFFF`` 等同只保留最低 16 bit，因此不需要另外撰寫 if/else
        判斷 65535；也可確保回傳值永遠落在 Modbus WORD 合法範圍。
        """
        return (int(plc_index) + 1) & 0xFFFF

    def tick(self) -> HMIHeartbeatResult:
        """執行一次完整的 HMI 心跳讀寫。

        執行順序：
            1. 一次讀取 D1100~D1105，共 6 個 WORD。
            2. 取第 0 筆（D1100）作為 ``PLCtoHMI_HB_Index``。
            3. 取第 5 筆（D1105）作為 ``HMI_CommStatus``。
            4. 計算 ``ReturnIndex = PLC_Index + 1``，並套用 16-bit 循環。
            5. 將 ReturnIndex 寫入 D1005。
            6. 保存本輪快照並回傳 :class:`HMIHeartbeatResult`。

        Returns:
            不論成功或失敗都回傳 :class:`HMIHeartbeatResult`。預期中的通訊錯誤
            不會從此方法向外拋出；呼叫端可檢查 ``result.ok``、``connected`` 與
            ``result.message`` 決定畫面顯示或重連策略。

        Timing:
            D1105 是「本輪讀取當下」的 PLC 狀態，而 D1005 在讀取之後才寫入，
            所以剛啟動的第一輪可能仍讀到 D1105=0。PLC 完成下一次掃描後，後續
            tick 通常才會讀到 D1105=1；這是正常的一個週期延遲。
        """

        if not self.connected:
            # 未連線時不進行任何 Modbus 存取，避免產生沒有意義的 Socket 例外。
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message="尚未連線 PLC",
            )

        # 使用一次連續讀取取得 D1100~D1105，可減少 Modbus 封包數量，並確保
        # PLC Index 與 CommStatus 來自同一筆 response。
        data = self.read_d(D_PLC_TO_HMI_HB_INDEX, 6)

        if data is None:
            # read_d() 已保存詳細錯誤並把 connected 清為 False；這裡只負責將
            # 狀態整理成統一的 HMIHeartbeatResult 交給上層。
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message=self.last_error or "讀取 PLC 心跳失敗",
            )

        if len(data) < 6:
            # 正常 Function Code 03 response 應回傳指定的 6 筆資料。防禦性檢查
            # 可避免未來替換 client/mock 時因短資料直接發生 IndexError。
            return HMIHeartbeatResult(
                ok=False,
                plc_index=None,
                return_index=None,
                hmi_comm_status=None,
                message=f"PLC 回傳資料不足：預期 6 筆，收到 {len(data)} 筆",
            )

        # read_d(1100, 6) 的索引與 PLC 位址對照：
        # data[0] = D1100；data[1] = D1101；...；data[5] = D1105。
        plc_index = data[0]          # D1100：PLCtoHMI_HB_Index
        hmi_comm_status = data[5]    # D1105：HMI_CommStatus

        # HMI 永遠只根據 PLC 本輪給的 Index 計算回覆，不使用本機累加器。
        # 這可避免 HMI 重啟後與 PLC 的 Index 不同步。
        return_index = self.calc_return_index(plc_index)

        # 將計算結果回寫至唯一的 HMI -> PLC 心跳暫存器 D1005。
        write_ok = self.write_d(
            D_HMI_TO_PLC_HB_RETURN_INDEX,
            return_index,
        )

        if not write_ok:
            # write_d() 已負責記錄詳細 Modbus 錯誤及切換斷線狀態。
            return HMIHeartbeatResult(
                ok=False,
                plc_index=plc_index,
                return_index=return_index,
                hmi_comm_status=hmi_comm_status,
                message="寫入 HMItoPLC_HB_ReturnIndex 失敗",
            )

        # 只有「讀取與寫入都成功」才更新最近成功快照，避免斷線時用失敗的
        # 半套資料覆蓋 GUI 上最後一筆可信值。
        self.last_plc_index = plc_index
        self.last_return_index = return_index
        self.last_hmi_comm_status = hmi_comm_status

        # D1105 由 PLC 判定，不是 Python 自己推測。TCP 與本輪讀寫即使成功，
        # PLC 尚未完成握手時仍可能回傳 0，因此 ok 必須同時納入此欄位。
        ok = hmi_comm_status == 1

        return HMIHeartbeatResult(
            ok=ok,
            plc_index=plc_index,
            return_index=return_index,
            hmi_comm_status=hmi_comm_status,
            message="OK" if ok else "PLC 尚未判定 HMI 在線或已 Timeout",
        )


# =====================================================
# 單檔連續測試程式
#
# 只有直接執行 ``python HMI_heartbeat.py`` 時才會進入這段程式。
# 被其他 HMI 主程式 import 時不會自動建立連線、背景執行或自動重連；
# 整合端必須自行安排 connect()/tick()/close() 的生命週期。
# =====================================================

if __name__ == "__main__":
    import time

    # ------------------------- 現場連線設定 -------------------------
    # 正式整合時可改由設定檔、環境變數或 GUI 輸入取得，避免把不同機台 IP
    # 分散硬編碼在多支程式中。
    heartbeat = HMIHeartbeat(ip="192.168.1.5", port=502, slave_id=1)

    # 連線失敗或運行中斷線後的重試間隔（秒）。重試太密集會製造大量 Log
    # 與無效 TCP 封包；太長則會延後復原時間。
    reconnect_delay = 2.0

    # retry_count 用來節流連線失敗訊息：第一次會顯示，之後每 5 次再顯示一次，
    # 避免 PLC 長時間關機時終端被相同訊息洗版。
    retry_count = 0

    # 用來區分「第一次連線成功」與「斷線後重新連線成功」的顯示文字。
    has_connected = False

    # flush=True 強制立即輸出；若 IDE/服務以 pipe 擷取 stdout，沒有 flush 時
    # 可能因輸出緩衝而看起來像程式沒有執行。
    print("HMI 心跳程式啟動", flush=True)

    try:
        while True:
            # ------------------ 狀態 A：尚未連線/已斷線 ------------------
            # connect() 成功後直接往下執行本輪 tick；失敗則等待固定時間重試。
            if not heartbeat.connected:
                if heartbeat.connect():
                    retry_count = 0
                    if has_connected:
                        print("PLC 重新連線成功，恢復心跳", flush=True)
                    else:
                        print("PLC 連線成功", flush=True)
                        has_connected = True
                else:
                    retry_count += 1

                    # 只印第 1、5、10、15...次失敗，避免長時間斷線洗版。
                    if retry_count == 1 or retry_count % 5 == 0:
                        print(
                            f"PLC 尚未連線：{heartbeat.last_error}；"
                            f"{reconnect_delay:g} 秒後重試",
                            flush=True,
                        )
                    time.sleep(reconnect_delay)
                    continue

            # --------------------- 狀態 B：執行心跳 ---------------------
            # tick() 會同步完成「讀 D1100~D1105 -> 計算 -> 寫 D1005」。
            result = heartbeat.tick()

            # 讀寫途中若發生 Modbus/網路錯誤，tick() 會把 connected 清為 False。
            # 此處顯示一次斷線原因，下一輪再回到狀態 A 自動重連。
            if not heartbeat.connected:
                retry_count = 0
                print(
                    f"PLC 通訊中斷：{result.message}；"
                    f"{reconnect_delay:g} 秒後自動重連",
                    flush=True,
                )
                time.sleep(reconnect_delay)
                continue

            # 連線仍正常時，輸出本輪快照。第一輪 D1105 可能仍為 0，通常在
            # PLC 處理 HMI 回覆後，下一輪才變成 1。
            print(
                f"OK={result.ok} | "
                f"PLC_Index={result.plc_index} | "
                f"HMI_ReturnIndex={result.return_index} | "
                f"HMI_CommStatus={result.hmi_comm_status} | "
                f"{result.message}",
                flush=True,
            )

            # 單檔測試每 0.5 秒交換一次。正式系統可調整，但此間隔必須明顯
            # 短於 PLC ST 程式設定的 HMI 通訊 Timeout，否則 PLC 會誤判離線。
            time.sleep(0.5)

    except KeyboardInterrupt:
        # 使用者在終端按 Ctrl+C 時走正常結束流程，不顯示 traceback。
        print("停止 HMI 心跳", flush=True)

    finally:
        # 無論正常中止或未預期離開，都嘗試釋放 TCP Socket。
        heartbeat.close()
        print("PLC 連線關閉", flush=True)
