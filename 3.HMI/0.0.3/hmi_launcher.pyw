"""Visible startup error reporting for the field HMI launched by pythonw."""

from pathlib import Path
import sys
import traceback


def report_startup_error(error_text):
    base = Path(__file__).resolve().parent
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "hmi_startup_error.log"
    log_path.write_text(error_text, encoding="utf-8")

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "MVP Ramen HMI startup failed",
            "HMI 無法啟動。\n\n錯誤紀錄：\n{}".format(log_path),
            parent=root,
        )
        root.destroy()
    except Exception:
        pass


try:
    if sys.version_info < (3, 10):
        raise RuntimeError(
            "Python 3.10 or newer is required; current version is {}".format(
                sys.version.replace("\n", " ")
            )
        )

    from main_hmi import main

    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    report_startup_error(traceback.format_exc())
    raise SystemExit(1)
