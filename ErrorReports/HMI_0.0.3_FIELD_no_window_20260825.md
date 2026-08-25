# HMI 0.0.3 FIELD 啟動無視窗 — IPC 端診斷報告

- 日期：2026-08-25
- 診斷機器：`52-0B40685-01`（帳號 `User`）— HMI IPC
- 部署路徑：`C:\Users\User\Desktop\MVP_Ramen_HMI_0.0.3_FIELD_20260825\HMI_0.0.3_FIELD_20260825`
- 範圍：僅 IPC 端部署與測試，**未修改 IPC 上任何原始碼**

---

## 1. 結論

**不是環境問題，是程式 bug。** `ui_main_page.py` 第 333 行在 FIELD 模式下必定拋出
`AttributeError`，發生在 Tk `mainloop()` 之前，因此視窗完全不會出現。
`pythonw.exe` 把 traceback 吞掉，所以現場看起來像「什麼都沒發生」。

FIELD 一定失敗、SIMULATION 一定成功，原因是該行用了 `and` 短路：
SIMULATION 時左半邊為 False，右半邊的錯誤程式碼根本不會被執行。
這也解釋為何開發機的 Mock/SIMULATION 回歸測試全部通過卻沒抓到。

---

## 2. 錯誤日誌（實際重現）

```text
Traceback (most recent call last):
  File "...\main_hmi.py", line 184, in <module>
    raise SystemExit(main())
  File "...\main_hmi.py", line 175, in main
    ui = HMIUI(ip=args.ip, port=args.port, mock=args.mock,
               start_page=args.page, runtime_profile=args.profile)
  File "...\HMI_ui.py", line 159, in __init__
    self.show_page(self.current_page)
  File "...\HMI_ui.py", line 286, in show_page
    self.pages[name].refresh()
  File "...\ui_main_page.py", line 620, in refresh
    self._side_nav.refresh()
  File "...\ui_main_page.py", line 333, in refresh
    and snapshot.get("auto_live", {}).get("available")
AttributeError: 'NoneType' object has no attribute 'get'
```

---

## 3. 根因

`HMI_ui.py` `_empty_snapshot()` 第 263 行設定 `"auto_live": None`。

`dict.get(key, default)` 的 default **只在 key 不存在時生效**；此處 key 存在、值為
`None`，所以 `snapshot.get("auto_live", {})` 回傳 `None` 而不是 `{}`，接著呼叫
`.get("available")` 就爆掉。

`_empty_snapshot()` 是啟動當下唯一的 snapshot——poll thread（`self._worker.start()`）
在 `show_page()` **之後**才啟動，所以 `auto_live` 在這個時間點永遠是 `None`。

同一段第 337 行寫法正確（`if snapshot.get("auto_live")` 只做真值判斷），可作為對照。

---

## 4. 重現步驟

必定重現（IPC 上已驗證）：

```cmd
cd /d C:\Users\User\Desktop\MVP_Ramen_HMI_0.0.3_FIELD_20260825\HMI_0.0.3_FIELD_20260825
.venv\Scripts\python.exe main_hmi.py --profile field --ip 192.168.1.5 --port 502
```

用 `python.exe`（非 `pythonw.exe`）才看得到 traceback。

對照組（同一份未修改的部署包）：

```cmd
.venv\Scripts\python.exe main_hmi.py --profile simulation --mock
```
→ 視窗正常開啟，無錯誤。

---

## 5. 建議修正（請在開發電腦執行，IPC 未改）

檔案：`3.HMI/0.0.3/ui_main_page.py` 第 333 行

```python
# 修改前
                   and snapshot.get("auto_live", {}).get("available")

# 修改後
                   and (snapshot.get("auto_live") or {}).get("available")
```

**注意：開發電腦的 `3.HMI/0.0.3/ui_main_page.py` 有完全相同的 bug（同樣在第 333 行），
所以這是既有缺陷，不是打包造成的。**

| 檔案 | SHA-256 |
|---|---|
| 部署包 `ui_main_page.py` | `F68857B5D5A437ECF139590C54DC801D2CF4682ABCEB9E8020C2D1F567526871` |
| 開發機 repo `ui_main_page.py` | `F411FB7EB178547DCA1D9BB55FBCB370965FD6DB3295A35627FAD7DEB7E7CD40` |

（兩份內容不同——部署包較新，但第 333 行的 bug 兩邊都有。）

---

## 6. 修正驗證結果

在**暫存複本**（非 IPC 部署資料夾）套用上述一行修改後：

| 測試 | 結果 |
|---|---|
| `compileall` 全模組編譯 | PASS |
| `--profile field --ip 192.168.1.5 --port 502`（PLC 離線） | PASS，視窗開啟並持續運行 25 秒無錯誤 |
| `--profile field ... --page AutoSystemPage`（`start_field_live_monitor.cmd` 路徑） | PASS |

PLC 192.168.1.5:502 在測試期間確實無法連線，修正後 HMI 仍能正常顯示介面，
符合「PLC 離線時應顯示離線狀態而非無聲退出」的要求。

---

## 7. 環境事實（handoff 要求回報）

| 項目 | 實際值 |
|---|---|
| Python（IPC venv） | **3.13.14** (MSC v.1944 64 bit) |
| tkinter | OK |
| Pillow | 12.3.0 |
| pymodbus | 3.15.0 |
| `.venv` | 已存在且健康（`setup_ipc.cmd` 已成功執行過） |
| `.venv\Scripts\pythonw.exe` | 存在 |
| `py.exe` | 存在於 `C:\Users\User\AppData\Local\Programs\Python\Launcher\py.exe` |

**環境完全正常，四項 runtime import 全部通過。** handoff 中「先查 Python、Tk、Pillow、
pymodbus」的假設在本機已排除。

---

## 8. 與 handoff 文件不符之處

1. **`hmi_launcher.pyw` 不存在於 IPC 部署包**，`3.HMI/deploy/` 資料夾在本機也不存在。
   handoff 所述的四個啟動修正檔案**尚未進入這個部署包**。
2. 部署包內 `start_hmi.cmd` 仍是 8/23 舊版（直接呼叫 `pythonw.exe main_hmi.py`）。
3. 即使補上 `hmi_launcher.pyw`，**也不會讓 FIELD 視窗出現**——它只會把 traceback 寫進
   `logs/hmi_startup_error.log` 並跳錯誤對話框。啟動包裝器是有價值的診斷工具，
   但真正的修復是第 5 節那一行。

---

## 9. 建議後續順序

1. 開發電腦修正 `ui_main_page.py` 第 333 行。
2. 順便加入 `hmi_launcher.pyw` 啟動包裝器（避免未來 `pythonw` 再次靜默失敗）。
3. **FIELD 模式必須納入回歸測試**——目前回歸只跑 Mock/SIMULATION，
   短路邏輯使 FIELD 專屬分支從未被執行。建議至少加一項「FIELD + PLC 離線可開窗」冒煙測試。
4. 重新打包部署 ZIP、重算 SHA-256、重新傳到 IPC。
5. `ui_auto_page.py` 另有 5 處 FIELD 專屬分支（611、1051、1067、1099、1114 行），
   本次已驗證修正後的 AUTO 頁可開啟，但完整 FIELD 功能仍需連上 PLC 後再測。

---

## 10. IPC 端變更紀錄

- 未修改任何 `.py` 原始碼（已用 mtime 驗證）
- 未修改 `data/auto_hmi_state.json`
- 僅 `__pycache__/` 因執行而重新產生（gitignored，無影響）
- 測試用的修正複本位於暫存區，未寫入部署資料夾
