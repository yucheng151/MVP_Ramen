#!/usr/bin/env python3
"""Verify that FIELD HMI opens while the PLC is offline.

This specifically covers startup branches that Mock/SIMULATION tests skip.
The window is withdrawn during automation, but real Tk widgets, FIELD profile,
the PLC client and all pages are constructed exactly as in start_hmi.cmd.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tkinter.messagebox as messagebox


TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parents[0]
HMI_DIR = (
    TEST_DIR
    if (TEST_DIR / "HMI_ui.py").exists()
    else ROOT / "3.HMI" / "0.0.3"
)
sys.path.insert(0, str(HMI_DIR))

from HMI_ui import HMIUI  # noqa: E402


def run() -> None:
    originals = (
        messagebox.showinfo,
        messagebox.showwarning,
        messagebox.showerror,
        messagebox.askyesno,
        messagebox.askokcancel,
    )
    messagebox.showinfo = lambda *_args, **_kwargs: "ok"
    messagebox.showwarning = lambda *_args, **_kwargs: "ok"
    messagebox.showerror = lambda *_args, **_kwargs: "ok"
    messagebox.askyesno = lambda *_args, **_kwargs: True
    messagebox.askokcancel = lambda *_args, **_kwargs: True

    app = None
    try:
        # Port 1 is deliberately unavailable.  FIELD must still construct and
        # display the UI instead of raising before Tk mainloop starts.
        app = HMIUI(
            ip="127.0.0.1",
            port=1,
            mock=False,
            runtime_profile="field",
            start_page="MainPage",
        )
        app.root.withdraw()
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.05)

        assert app.runtime_profile == "field"
        assert app.mock_mode is False
        assert "MainPage" in app.pages
        assert "AutoSystemPage" in app.pages
        assert hasattr(app.pages["AutoSystemPage"], "plc_debug_log_tree")

        app.show_page("AutoSystemPage")
        app.root.update()
        app.show_page("MainPage")
        app.root.update()

        print("RESULT: PASS - FIELD HMI opens and renders with PLC offline")
    finally:
        if app is not None:
            app._stop_event.set()
            app._worker.join(timeout=2.0)
            app.plc.close()
            try:
                app.root.destroy()
            except Exception:
                pass
        (
            messagebox.showinfo,
            messagebox.showwarning,
            messagebox.showerror,
            messagebox.askyesno,
            messagebox.askokcancel,
        ) = originals


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"RESULT: FAIL - {type(exc).__name__}: {exc}")
        raise
