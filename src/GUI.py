import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import os
import sys
import threading
from src import storage
from src.table_manager import TableManager
from src.table_view import TableView
from src.signal_view import SignalView
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from tkinterdnd2 import TkinterDnD, DND_FILES


def resource_path(relative_path):
    """Returns the absolute path to the resource; works for both scripts and .exe files."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class GUI(TkinterDnD.Tk):
    """Main application window with drag-and-drop CSV support."""

    def __init__(self):
        super().__init__()
        self.title("Analysis of EMG signals")
        self.iconbitmap(resource_path("data/program.ico"))
        self.geometry("1200x750")
        self.minsize(1200, 750)
        self.filename = None
        self._get_windows_theme_info()
        self._workspace()
        self._register_drop()

    # ------------------------------------------------------------------ #
    #  Layout                                                              #
    # ------------------------------------------------------------------ #

    def _workspace(self):
        """Build the main window layout: left sidebar + right workspace."""
        main = tk.Frame(self, bg=self.background_color, bd=1, relief="solid")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # Left sidebar
        left = tk.Frame(main, bg=self.background_color, width=180)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)

        button_style = dict(
            bg=self.accent, fg="white",
            activebackground=self.accent_light, activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            font=("Helvetica", 10), height=2,
        )

        tk.Button(left, text="Show graphic",
                  command=self._open_graphic, **button_style).pack(
            fill="x", pady=(0, 6))

        tk.Button(left, text="Show table",
                  command=self._open_table, **button_style).pack(
            fill="x", pady=(0, 6))

        # Spacer
        tk.Frame(left, bg=self.background_color).pack(fill="both", expand=True)

        self.file_label = tk.Label(
            left, text=f"Current file: {self.filename}",
            bg=self.background_color, fg=self.text,
            font=("Helvetica", 9), wraplength=160, justify="left",
        )
        self.file_label.pack(anchor="w", pady=(0, 4))

        tk.Button(left, text="Open file",
                  command=self._open_file, **button_style).pack(
            fill="x", pady=(0, 4))

        # Right workspace panel
        self.workspace = tk.Frame(main, bg=self.workspace_color,
                                  bd=1, relief="solid")
        self.workspace.pack(side="left", fill="both",
                            expand=True, padx=(4, 8), pady=8)

        self._build_placeholder()

    def _build_placeholder(self):
        """Show the initial placeholder panel inside the workspace."""
        ph_frame = tk.Frame(self.workspace, bg=self.workspace_color)
        ph_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(ph_frame, text="📂",
                 bg=self.workspace_color, fg=self.text,
                 font=("Segoe UI Emoji", 42)).pack(pady=(0, 8))

        tk.Label(ph_frame,
                 text="Choose a file to get started",
                 bg=self.workspace_color, fg=self.text,
                 font=("Helvetica", 15, "bold"), justify="center").pack()

        tk.Label(ph_frame,
                 text="Only CSV files are supported\nYou can also drag & drop a file here",
                 bg=self.workspace_color, fg="#888888",
                 font=("Helvetica", 10), justify="center").pack(pady=(4, 0))

        badge = tk.Frame(ph_frame, bg=self.accent, padx=10, pady=4)
        badge.pack(pady=(12, 0))
        tk.Label(badge, text="Supported format: .csv",
                 bg=self.accent, fg="white",
                 font=("Consolas", 9, "bold")).pack()

        self.placeholder = ph_frame

    # ------------------------------------------------------------------ #
    #  Drag-and-drop                                                       #
    # ------------------------------------------------------------------ #

    def _register_drop(self):
        """Register the entire window as a drop target for files."""
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        """Handle a file drop onto the window."""
        raw: str = event.data.strip()
        # Parse Tcl list: strip outer braces for a single-item list
        if raw.startswith("{") and raw.endswith("}"):
            path = raw[1:-1]
        else:
            path = raw.split()[0]

        if not path.lower().endswith(".csv"):
            messagebox.showwarning(
                title="Unsupported file",
                message="Only CSV files are supported.\n\nDrop a .csv file to open it.",
            )
            return
        self._load_path(path)

    # ------------------------------------------------------------------ #
    #  File handling                                                       #
    # ------------------------------------------------------------------ #

    def _open_file(self):
        """Open a file dialog restricted to CSV files."""
        path = filedialog.askopenfilename(filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        self._load_path(path)

    def _load_path(self, path: str):
        """
        Load a CSV from *path* in a background thread while showing a
        progress overlay in the workspace.  UI is never blocked.
        """
        logging.info(f"Attempting to load: {path}")
        self._show_loading_overlay(path)

        result: dict = {}

        def worker():
            try:
                result["tm"] = TableManager(path)
            except Exception as exc:
                result["error"] = exc
            finally:
                # Schedule UI update back on the main thread
                self.after(0, lambda: self._finish_loading(path, result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_loading_overlay(self, path: str):
        """Render an animated indeterminate progress bar over the workspace."""
        # Remove any previous overlay first
        self._destroy_loading_overlay()

        overlay = tk.Frame(self.workspace, bg=self.workspace_color)
        overlay.place(relwidth=1.0, relheight=1.0)
        self._loading_overlay = overlay

        center = tk.Frame(overlay, bg=self.workspace_color)
        center.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(center, text="⏳",
                 bg=self.workspace_color, fg=self.text,
                 font=("Segoe UI Emoji", 36)).pack(pady=(0, 10))

        tk.Label(center, text="Loading file…",
                 bg=self.workspace_color, fg=self.text,
                 font=("Helvetica", 13, "bold")).pack()

        tk.Label(center, text=os.path.basename(path),
                 bg=self.workspace_color, fg="#888888",
                 font=("Consolas", 9)).pack(pady=(4, 12))

        # Style the progress bar to use the accent colour
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar",
                        troughcolor=self._darken(self.workspace_color, 12),
                        background=self.accent,
                        bordercolor=self.workspace_color,
                        lightcolor=self.accent,
                        darkcolor=self.accent)

        bar = ttk.Progressbar(center, mode="indeterminate", length=240)
        bar.pack()
        bar.start(10)          # animate every 10 ms
        self._loading_bar = bar

    def _destroy_loading_overlay(self):
        """Remove the loading overlay if it exists."""
        overlay = getattr(self, "_loading_overlay", None)
        if overlay and overlay.winfo_exists():
            bar = getattr(self, "_loading_bar", None)
            if bar:
                bar.stop()
            overlay.destroy()
        self._loading_overlay = None
        self._loading_bar = None

    def _finish_loading(self, path: str, result: dict):
        """Called on the main thread after the worker finishes."""
        self._destroy_loading_overlay()

        if "error" in result:
            e = result["error"]
            logging.error(f"Failed to load '{path}': {e}")
            messagebox.showerror(
                title="Error opening file",
                message=f"Could not read the file:\n\n{e}",
            )
            return

        tm: TableManager = result["tm"]
        if tm.check_table():
            storage.update(path)
            self.filename = storage.file["filename"]
            self.file_label.config(text=f"Current file: {self.filename}")
            self.tm = tm
            logging.info(f"File loaded: {path}")
            self._show_ready_screen(tm)
        else:
            messagebox.showerror(
                title="Unsupported format",
                message="The file format is not supported.\n\n"
                        "Expected columns: time, channel1–8, class, label",
            )

    def _show_ready_screen(self, tm: TableManager):
        """Replace the workspace content with a clean 'file ready' action screen."""
        self._clear_workspace()

        bg      = self.workspace_color
        acc     = self.accent
        # Match sidebar / toolbar look
        card_bg = self._darken(bg, 8) if self.text == "#FFFFFF" else "#EFEFEF"
        tile_bg = self._darken(bg, 14) if self.text == "#FFFFFF" else "#E2E2E2"
        muted   = "#888888"
        d = tm.info_dict()

        # ── Outer centering container ────────────────────────────────────
        outer = tk.Frame(self.workspace, bg=bg)
        outer.place(relx=0.5, rely=0.5, anchor="center")

        # ── Card ─────────────────────────────────────────────────────────
        card = tk.Frame(outer, bg=card_bg, padx=40, pady=28)
        card.pack()

        # ── Status badge ─────────────────────────────────────────────────
        badge = tk.Frame(card, bg=acc, padx=10, pady=3)
        badge.pack(pady=(0, 6))
        tk.Label(badge, text="FILE LOADED", bg=acc, fg="white",
                 font=("Consolas", 8, "bold")).pack()

        # ── File name ────────────────────────────────────────────────────
        tk.Label(card, text=self.filename,
                 bg=card_bg, fg=self.text,
                 font=("Consolas", 14, "bold")).pack(pady=(4, 0))

        # Thin accent underline
        tk.Frame(card, bg=acc, height=2, width=280).pack(pady=(8, 16))

        # ── Stat tiles ───────────────────────────────────────────────────
        tile_row = tk.Frame(card, bg=card_bg)
        tile_row.pack(pady=(0, 18))

        def stat_tile(parent, label, value):
            f = tk.Frame(parent, bg=tile_bg, padx=18, pady=10)
            f.pack(side="left", padx=5)
            tk.Label(f, text=value, bg=tile_bg, fg=self.text,
                     font=("Consolas", 13, "bold")).pack()
            tk.Label(f, text=label, bg=tile_bg, fg=muted,
                     font=("Consolas", 8)).pack()

        stat_tile(tile_row, "Rows",     f"{d['rows']:,}")
        stat_tile(tile_row, "Channels", str(d["channels"]))
        stat_tile(tile_row, "Classes",  d["classes_str"])
        stat_tile(tile_row, "Labels",   d["labels_str"])

        # ── Separator ────────────────────────────────────────────────────
        sep = tk.Frame(card, bg=self._darken(card_bg, 12), height=1)
        sep.pack(fill="x", pady=(0, 14))

        # ── Action buttons ───────────────────────────────────────────────
        tk.Label(card, text="Choose an action:",
                 bg=card_bg, fg=muted,
                 font=("Consolas", 8)).pack(pady=(0, 8))

        btn_row = tk.Frame(card, bg=card_bg)
        btn_row.pack()

        btn_cfg = dict(
            bg=acc, fg="white",
            activebackground=self.accent_light, activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            font=("Consolas", 10, "bold"),
            padx=20, pady=8,
        )
        tk.Button(btn_row, text="Show Graphic",
                  command=self._open_graphic, **btn_cfg).pack(
            side="left", padx=(0, 8))
        tk.Button(btn_row, text="Show Table",
                  command=self._open_table, **btn_cfg).pack(side="left")



    # ------------------------------------------------------------------ #
    #  Views                                                               #
    # ------------------------------------------------------------------ #

    def _open_table(self):
        """Clear the workspace and render the paginated TableView."""
        if not self._require_file():
            return
        self._clear_workspace()
        TableView(self.workspace, df=self.tm.df).pack(fill="both", expand=True)

    def _open_graphic(self):
        """Clear the workspace and render the SignalView with chart + analysis."""
        if not self._require_file():
            return
        self._clear_workspace()
        SignalView(self.workspace, df=self.tm.df).pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _require_file(self) -> bool:
        """Show a warning and return False if no file has been loaded yet."""
        if not hasattr(self, "tm"):
            messagebox.showwarning(
                title="No file loaded",
                message="Please open a CSV file first.",
            )
            return False
        return True

    def _clear_workspace(self):
        """Destroy all child widgets inside the workspace frame."""
        for widget in self.workspace.winfo_children():
            widget.destroy()

    @staticmethod
    def _darken(hex_color: str, amount: int) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{max(0, r - amount):02x}{max(0, g - amount):02x}{max(0, b - amount):02x}"

    # ------------------------------------------------------------------ #
    #  Theme                                                               #
    # ------------------------------------------------------------------ #

    def _get_windows_theme_info(self):
        """
        Read the Windows accent and background colors once at startup.
        Dynamic theme changes require an app restart.
        """
        settings = UISettings()

        def to_hex(color) -> str:
            return f"#{color.r:02x}{color.g:02x}{color.b:02x}".upper()

        self.accent           = to_hex(settings.get_color_value(UIColorType.ACCENT))
        self.accent_light     = to_hex(settings.get_color_value(UIColorType.ACCENT_LIGHT1))
        self.accent_dark      = to_hex(settings.get_color_value(UIColorType.ACCENT_DARK1))
        self.background_color = "#FFFFFF"
        self.workspace_color  = "#FFFFFF"
        self.text             = "#555"

        if to_hex(settings.get_color_value(UIColorType.BACKGROUND)) == "#000000":
            self.background_color = "#2B2D30"
            self.workspace_color  = "#1E1E1E"
            self.text             = "#FFFFFF"

        storage.set_theme(
            self.accent, self.accent_light, self.accent_dark,
            self.workspace_color, self.text, self.background_color,
        )
