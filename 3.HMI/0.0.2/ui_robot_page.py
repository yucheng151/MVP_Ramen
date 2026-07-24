"""Robot arm communication and status page."""
import tkinter as tk

from ui_common import BasePage, PANEL, TEXT, MUTED, BLUE, GREEN, button_style, status_color


class RobotPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "ROBOT ARM")

        body = tk.Frame(self, bg=PANEL)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        self.labels = {}
        rows = (
            "Arm Status",
            "Communication",
            "Status Source",
            "Last Error",
        )
        for row, name in enumerate(rows):
            tk.Label(
                body,
                text=name,
                bg=PANEL,
                fg=MUTED,
                font=("Segoe UI", 13),
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", padx=(28, 18), pady=18)
            value = tk.Label(
                body,
                text="--",
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 15, "bold"),
                anchor="w",
            )
            value.grid(row=row, column=1, sticky="ew", padx=(18, 28), pady=18)
            self.labels[name] = value

        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)

        actions = tk.Frame(self, bg=PANEL)
        actions.pack(fill="x", padx=24, pady=(0, 18))

        tk.Label(
            actions,
            text="手臂操作（尚未綁定 PLC）",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 13),
        ).pack(anchor="w", padx=28, pady=(18, 10))

        buttons = tk.Frame(actions, bg=PANEL)
        buttons.pack(fill="x", padx=28, pady=(0, 20))
        tk.Button(
            buttons,
            text="甩麵",
            **button_style(BLUE),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(
            buttons,
            text="煮麵",
            **button_style(GREEN),
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

    def refresh(self):
        online = self.app.snapshot.get("arm_online")
        status = "Online" if online is True else "Offline" if online is False else "Unknown"
        configured = online is not None
        values = {
            "Arm Status": status,
            "Communication": "Connected" if online is True else "Disconnected",
            "Status Source": "Robot signal" if configured else "Not configured",
            "Last Error": "None" if online is True else "Arm status unavailable",
        }
        for name, value in values.items():
            self.labels[name].configure(text=value, fg=status_color(value))
