from pathlib import Path
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


class EmergencyStopButton(tk.Button):
    """Shared E-stop control with immediate press/release visual feedback."""

    _instances = []

    def __init__(self, parent, command):
        asset_dir = Path(__file__).resolve().parent / "assets"
        self._normal_image = tk.PhotoImage(file=str(asset_dir / "emergency_stop.png"))
        self._pressed_image = tk.PhotoImage(file=str(asset_dir / "emergency_stop_pressed.png"))
        self._external_command = command
        self._latched = False
        self._flash_on = False
        self._flash_job = None
        super().__init__(
            parent,
            image=self._normal_image,
            command=self._toggle_latched,
            bg=BG,
            activebackground="#401010",
            width=78,
            height=78,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.bind("<ButtonPress-1>", self._show_pressed, add="+")
        self.bind("<ButtonRelease-1>", self._show_released, add="+")
        self.bind("<Leave>", self._show_released, add="+")
        self._instances.append(self)

    def _show_pressed(self, _event=None):
        self.configure(image=self._pressed_image, bg="#401010", relief="sunken")

    def _show_released(self, _event=None):
        self.after(140, self._restore_if_unlatched)

    def _restore_if_unlatched(self):
        if not self._latched:
            self.configure(image=self._normal_image, bg=BG, relief="flat")

    def _toggle_latched(self):
        new_state = not self._latched
        for button in tuple(self._instances):
            if button.winfo_exists():
                button._set_latched(new_state)
        self._external_command()

    def _set_latched(self, latched):
        self._latched = latched
        if latched:
            self._flash_on = True
            self._flash()
        else:
            if self._flash_job is not None:
                self.after_cancel(self._flash_job)
                self._flash_job = None
            self._flash_on = False
            self.configure(image=self._normal_image, bg=BG, relief="flat")

    def _flash(self):
        if not self._latched:
            return
        if self._flash_on:
            self.configure(image=self._pressed_image, bg="#7a1010", relief="sunken")
        else:
            self.configure(image=self._pressed_image, bg="#260606", relief="sunken")
        self._flash_on = not self._flash_on
        self._flash_job = self.after(420, self._flash)


class BasePage(tk.Frame):
    def __init__(self, parent, app, title: str):
        super().__init__(parent, bg=BG)
        self.app = app
        # Lazy import avoids a module cycle while keeping one shared visual system.
        from ui_main_page import MainControlPanel, SideNavigation

        header = tk.Frame(self, bg=BG, height=100)
        header.pack(fill="x", padx=24, pady=(14, 4))
        header.pack_propagate(False)
        title_frame = tk.Frame(header, bg=BG)
        title_frame.pack(side="left", fill="y")
        title_label = tk.Label(title_frame, text=title, bg=BG, fg=TEXT,
                               font=("Segoe UI", 25, "bold"))
        title_label.pack(anchor="w")
        tk.Label(
            title_frame, text="SELECT PAGE FROM LEFT MENU",
            bg=BG, fg=MUTED, font=("Segoe UI", 10),
        ).pack(anchor="w")

        self._global_controls = MainControlPanel(header, app)
        self._global_controls.pack(side="right")
        self._side_nav = SideNavigation(self, app)
        self._side_nav.pack(side="left", fill="y", padx=(24, 6), pady=(6, 12))

    def update_global_status(self):
        self._global_controls.refresh()
        self._side_nav.refresh()

    def refresh(self):
        pass


def button_style(color=BLUE):
    return dict(bg=color, fg="white", activebackground=color, activeforeground="white",
                relief="flat", bd=0, padx=18, pady=10,
                font=("Microsoft JhengHei UI", 13, "bold"), cursor="hand2")


def status_color(value: str):
    return {
        "Normal": GREEN, "Ready": GREEN, "Online": GREEN, "Auto": GREEN,
        "Running": BLUE, "Stopping": YELLOW, "Manual": YELLOW, "Semi Auto": BLUE,
        "Warning": YELLOW, "Busy": YELLOW,
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
