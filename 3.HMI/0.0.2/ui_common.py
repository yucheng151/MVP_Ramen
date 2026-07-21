import tkinter as tk

BG = "#101820"
PANEL = "#1b2733"
PANEL_2 = "#243442"
TEXT = "#f2f6f8"
MUTED = "#9fb0bd"
GREEN = "#23c483"
RED = "#ff4d5a"
YELLOW = "#f2bd42"
BLUE = "#3399ff"
GRAY = "#667784"


class BasePage(tk.Frame):
    def __init__(self, parent, app, title: str):
        super().__init__(parent, bg=BG)
        self.app = app
        header = tk.Frame(self, bg=BG, height=84)
        header.pack(fill="x", padx=24, pady=(14, 4))
        header.pack_propagate(False)
        title_frame = tk.Frame(header, bg=BG)
        title_frame.pack(side="left", fill="y")
        title_label = tk.Label(title_frame, text=title, bg=BG, fg=TEXT,
                               font=("Segoe UI", 25, "bold"), cursor="hand2")
        title_label.pack(anchor="w")
        back_action = lambda _event: app.show_page("MainPage")
        title_label.bind("<Button-1>", back_action)
        subtitle = tk.Button(title_frame, text="← BACK TO HOME", command=lambda: app.show_page("MainPage"),
                             bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
                             relief="flat", bd=0, padx=0, pady=0,
                             font=("Segoe UI", 10), cursor="hand2")
        subtitle.pack(anchor="w")
        for widget in (title_frame, title_label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", back_action)

        summary = tk.Frame(header, bg=BG)
        summary.pack(side="right", fill="y")
        cards = (
            ("MODE", "Manual", app.toggle_mode),
            ("SYSTEM", "--", lambda: app.toggle_page("AlarmPage")),
            ("PLC", "--", lambda: app.toggle_page("CommunicationPage")),
            ("IPC", "--", lambda: app.toggle_page("IPCCommunicationPage")),
        )
        labels = {}
        for column, (caption_text, value_text, action) in enumerate(cards):
            box = tk.Frame(summary, bg=PANEL, width=118, height=58)
            box.grid(row=0, column=column, padx=3)
            box.grid_propagate(False)
            caption = tk.Label(box, text=caption_text, bg=PANEL, fg=MUTED,
                               font=("Segoe UI", 8), anchor="w", cursor="hand2")
            caption.pack(fill="x", padx=12, pady=(6, 0))
            value = tk.Label(box, text=value_text, width=10, bg=PANEL, fg=TEXT,
                             font=("Segoe UI", 13, "bold"), anchor="w", cursor="hand2")
            value.pack(fill="x", padx=12)
            for widget in (box, caption, value):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _event, callback=action: callback())
            labels[caption_text] = value
        self._mode_button = labels["MODE"]
        self._system_button = labels["SYSTEM"]
        self._plc_button = labels["PLC"]
        self._ipc_button = labels["IPC"]

    def update_global_status(self):
        mode = self.app.machine_mode
        self._mode_button.configure(text=mode, fg=status_color(mode))
        system = self.app.snapshot["system"]
        self._system_button.configure(text=system, fg=status_color(system))
        online = self.app.snapshot["online"]
        self._plc_button.configure(text="Online" if online else "Offline",
                                   fg=GREEN if online else GRAY)
        ipc_online = self.app.snapshot["ipc_online"]
        self._ipc_button.configure(text="Online" if ipc_online else "Offline",
                                   fg=GREEN if ipc_online else GRAY)

    def refresh(self):
        pass


def button_style(color=BLUE):
    return dict(bg=color, fg="white", activebackground=color, activeforeground="white",
                relief="flat", bd=0, padx=18, pady=10,
                font=("Microsoft JhengHei UI", 13, "bold"), cursor="hand2")


def status_color(value: str):
    return {
        "Normal": GREEN, "Ready": GREEN, "Online": GREEN, "Auto": GREEN,
        "Running": BLUE, "Manual": YELLOW, "Warning": YELLOW, "Busy": YELLOW,
        "Alarm": RED, "Timeout": RED, "Jam": RED, "Empty": RED,
        "Driver Offline": RED, "Low Material": YELLOW,
        "Offline": GRAY, "Unknown": GRAY, "Stop": GRAY,
        "Detected": GREEN, "Not Detected": GRAY,
        "Future": "#78909c", "Reserved": "#78909c", "Future / Reserved": "#78909c",
    }.get(value, BLUE)


def value_card(parent, title):
    frame = tk.Frame(parent, bg=PANEL, highlightbackground="#334554", highlightthickness=1)
    tk.Label(frame, text=title, bg=PANEL, fg=MUTED, font=("Microsoft JhengHei UI", 12)).pack(anchor="w", padx=16, pady=(12, 3))
    label = tk.Label(frame, text="--", bg=PANEL, fg=TEXT, font=("Microsoft JhengHei UI", 20, "bold"))
    label.pack(anchor="w", padx=16, pady=(0, 12))
    return frame, label
