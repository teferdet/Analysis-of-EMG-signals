import tkinter as tk
import logging
import os
import sys
from src import storage
from src.table_manager import TableManager
from tkinter import filedialog, messagebox
from src.table_view import TableView
from src.signal_view import SignalView
from winrt.windows.ui.viewmanagement import UISettings, UIColorType

def resource_path(relative_path):
    """ Returns the absolute path to the resource; works for both scripts and .exe files """
    try:
        # PyInstaller creates a temporary folder and stores the path in sys._MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # If we run a standard .py file
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class GUI(tk.Tk):
    # Initialization of main window params
    def __init__(self):
        super().__init__()
        self.title("Analysis of EMG signals")
        self.iconbitmap(resource_path('data/program.ico')) 
        self.geometry("1200x700")
        self.minsize(1200, 700)
        self.filename = None
        self._get_windows_theme_info()
        self._workspace()


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
            font=("Helvetica", 9),
        )
        self.file_label.pack(anchor="w")

        tk.Button(left, text="Open file",
                  command=self._open_file, **button_style).pack(
            fill="x", pady=(0, 4))

        # Right workspace panel
        self.workspace = tk.Frame(main, bg=self.workspace_color,
                                  bd=1, relief="solid")
        self.workspace.pack(side="left", fill="both",
                            expand=True, padx=(4, 8), pady=8)

        self.placeholder = tk.Label(
            self.workspace,
            text="Choose a file to get started",
            bg=self.workspace_color, fg=self.text,
            font=("Helvetica", 14), justify="center",
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------------------------------------------ #
    #  File handling                                                     #
    # ------------------------------------------------------------------ #

    def _open_file(self):
        """
        Open a file dialog restricted to CSV files.
        Validate the selected file with TableManager and notify the user.
        """
        path = filedialog.askopenfilename(filetypes=[("CSV file", "*.csv")])
        if not path:
            return

        logging.info(f"Attempting to load: {path}")

        try:
            tm = TableManager(path)
        except (ValueError, FileNotFoundError) as e:
            logging.error(f"Failed to load '{path}': {e}")
            messagebox.showerror(
                title="Error opening file",
                message=f"Could not read the file:\n\n{e}",
            )
            return

        if tm.check_table():
            messagebox.showinfo(
                title="File opened",
                message=f"File loaded successfully!\n\n{tm.info()}",
            )
            storage.update(path)
            self.filename = storage.file["filename"]
            self.file_label.config(text=f"Current file: {self.filename}")
            self.tm = tm
            logging.info(f"File loaded: {path}")
        else:
            messagebox.showerror(
                title="Unsupported format",
                message="The file format is not supported.",
            )

    # ------------------------------------------------------------------ #
    #  Views                                                             #
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
    #  Helpers                                                           #
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

    # ------------------------------------------------------------------ #
    #  Theme                                                             #
    # ------------------------------------------------------------------ #

    def _get_windows_theme_info(self):
        """
        Read the Windows accent and background colors once at startup.
        Dynamic theme changes require an app restart.
        """
        settings = UISettings()

        def to_hex(color) -> str:
            return f"#{color.r:02x}{color.g:02x}{color.b:02x}".upper()

        self.accent = to_hex(settings.get_color_value(UIColorType.ACCENT))
        self.accent_light = to_hex(settings.get_color_value(UIColorType.ACCENT_LIGHT1))
        self.accent_dark = to_hex(settings.get_color_value(UIColorType.ACCENT_DARK1))
        self.background_color = "#FFFFFF"
        self.workspace_color = "#FFFFFF"
        self.text = "#555"

        if to_hex(settings.get_color_value(UIColorType.BACKGROUND)) == "#000000":
            self.background_color = "#2B2D30"
            self.workspace_color = "#1E1E1E"
            self.text = "#FFFFFF"

        storage.set_theme(
            self.accent, self.accent_light, self.accent_dark,
            self.workspace_color, self.text, self.background_color,
        )
