from pathlib import Path
import tkinter as tk
from tkinter import ttk

BG = "#101820"
PANEL = "#1b2733"
PANEL_2 = "#243442"
INPUT_BG = "#111c25"
DIVIDER = "#596168"
TEXT = "#f2f6f8"
MUTED = "#9fb0bd"
GREEN = "#23c483"
RED = "#ff4d5a"
YELLOW = "#f2bd42"
BLUE = "#3399ff"
GRAY = "#667784"


def configure_dark_theme(root):
    """Apply one low-glare theme to classic Tk and ttk controls."""
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.option_add("*Entry.background", INPUT_BG)
    root.option_add("*Entry.foreground", TEXT)
    root.option_add("*Entry.insertBackground", TEXT)
    root.option_add("*Entry.selectBackground", BLUE)
    root.option_add("*Entry.selectForeground", "#ffffff")
    root.option_add("*Text.background", INPUT_BG)
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", TEXT)
    root.option_add("*Listbox.background", INPUT_BG)
    root.option_add("*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.background", INPUT_BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", BLUE)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style.configure(".", background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure(
        "TNotebook", background=BG, borderwidth=0,
        bordercolor=DIVIDER, lightcolor=DIVIDER, darkcolor=DIVIDER,
        tabmargins=(0, 0, 0, 0),
    )
    style.map(
        "TNotebook",
        bordercolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        lightcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        darkcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
    )
    style.configure(
        "TNotebook.Tab", background=PANEL, foreground=MUTED,
        borderwidth=1, bordercolor=DIVIDER,
        lightcolor=DIVIDER, darkcolor=DIVIDER, padding=(16, 8),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", PANEL_2), ("active", "#2d4151")],
        foreground=[("selected", TEXT), ("active", TEXT)],
        bordercolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
        lightcolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
        darkcolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
    )
    style.configure(
        "TCombobox", background=PANEL_2, fieldbackground=INPUT_BG,
        foreground=TEXT, arrowcolor=TEXT, bordercolor=DIVIDER,
        lightcolor=DIVIDER, darkcolor=DIVIDER,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", INPUT_BG), ("disabled", PANEL)],
        foreground=[("readonly", TEXT), ("disabled", GRAY)],
        selectbackground=[("readonly", INPUT_BG)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        lightcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        darkcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
    )
    style.configure(
        "Treeview", background=PANEL, fieldbackground=PANEL,
        foreground=TEXT, bordercolor=DIVIDER, rowheight=28,
    )
    style.map(
        "Treeview",
        background=[("selected", "#315773")],
        foreground=[("selected", "#ffffff")],
        bordercolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        lightcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        darkcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
    )
    style.configure(
        "Treeview.Heading", background=PANEL_2, foreground=TEXT,
        relief="flat", bordercolor=DIVIDER,
    )
    style.map(
        "Treeview.Heading",
        background=[("active", "#315773")],
        bordercolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
        lightcolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
        darkcolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
    )
    style.configure(
        "TScrollbar", background=PANEL_2, troughcolor=BG,
        arrowcolor=TEXT, bordercolor=BG, lightcolor=PANEL_2,
        darkcolor=PANEL_2,
    )
    style.configure(
        "TProgressbar", background=GREEN, troughcolor=PANEL,
        bordercolor=PANEL, lightcolor=GREEN, darkcolor=GREEN,
    )


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
        self._flash_generation = 0
        super().__init__(
            parent,
            image=self._normal_image,
            command=self._toggle_latched,
            bg=BG,
            activebackground=BG,
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
        self.configure(image=self._pressed_image, bg=BG, relief="sunken")

    def _show_released(self, _event=None):
        self.after(140, self._restore_if_unlatched)

    def _restore_if_unlatched(self):
        if not self._latched:
            self.configure(image=self._normal_image, bg=BG, relief="flat")

    def _toggle_latched(self):
        new_state = not self._latched
        if not self._external_command(new_state):
            self._restore_if_unlatched()
            return
        for button in tuple(self._instances):
            if button.winfo_exists():
                button._set_latched(new_state)

    def _set_latched(self, latched):
        latched = bool(latched)
        self._flash_generation += 1
        generation = self._flash_generation
        self._latched = latched
        if latched:
            if self._flash_job is not None:
                self.after_cancel(self._flash_job)
                self._flash_job = None
            self._flash_on = True
            self._flash(generation)
        else:
            if self._flash_job is not None:
                self.after_cancel(self._flash_job)
                self._flash_job = None
            self._flash_on = False
            self.configure(image=self._normal_image, bg=BG, relief="flat")

    def set_latched(self, latched):
        """Synchronize this page's EMC animation with the HMI request state."""
        if bool(latched) != self._latched:
            self._set_latched(latched)

    def _flash(self, generation=None):
        if generation is None:
            generation = self._flash_generation
        if not self._latched or generation != self._flash_generation:
            return
        if self._flash_on:
            self.configure(image=self._pressed_image, bg=BG, relief="sunken")
        else:
            self.configure(image=self._normal_image, bg=BG, relief="sunken")
        self._flash_on = not self._flash_on
        self._flash_job = self.after(420, lambda: self._flash(generation))


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
        "Complete": GREEN, "Idle": YELLOW, "Rejected": RED,
        "Warning": YELLOW, "Busy": YELLOW,
        "Alarm": RED, "Timeout": RED, "Jam": RED, "Empty": RED,
        "Driver Offline": RED, "Low Material": YELLOW,
        "Offline": GRAY, "Unknown": GRAY, "Stop": GRAY,
        "Detected": GREEN, "Not Detected": GRAY,
        "Future": "#78909c", "Reserved": "#78909c", "Future / Reserved": "#78909c",
    }.get(value, BLUE)


def value_card(parent, title):
    frame = tk.Frame(parent, bg=PANEL, highlightbackground=DIVIDER, highlightthickness=1)
    tk.Label(frame, text=title, bg=PANEL, fg=MUTED, font=("Microsoft JhengHei UI", 12)).pack(anchor="w", padx=16, pady=(12, 3))
    label = tk.Label(frame, text="--", bg=PANEL, fg=TEXT, font=("Microsoft JhengHei UI", 20, "bold"))
    label.pack(anchor="w", padx=16, pady=(0, 12))
    return frame, label
