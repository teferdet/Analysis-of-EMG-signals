import tkinter as tk
import logging
from src import storage
from src.table_manager import TableManager
from tkinter import filedialog, messagebox
from src.table_view import TableView
from winrt.windows.ui.viewmanagement import UISettings, UIColorType

class GUI(tk.Tk):
    # Initialization of main window params
    def __init__(self):
        super().__init__()
        self.title('Analysis of EMG signals')
        self.iconbitmap("./data/program.ico")
        self.geometry("900x700")
        self.minsize(1200, 700)
        self.filename = None
        self._get_windows_theme_info()

        self._workspace()

    # Create main workspace
    def _workspace(self):
        # Main workspace
        main = tk.Frame(self, bg=self.background_color, bd=1, relief="solid")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # Left sidebar
        left = tk.Frame(main, bg=self.background_color, width=180)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)

        # Params of buttons style
        button_style = dict(
            bg=self.accent, fg="white",
            activebackground=self.accent_light, activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            font=("Helvetica", 10), height=2
        )

        tk.Button(left, text="Show graphic", **button_style).pack(
            fill="x", pady=(0, 6))

        tk.Button(left, text="Show table",
                  command=self._open_table, **button_style).pack(fill="x", pady=(0, 6))

        # Space between button
        tk.Frame(left, bg=self.background_color).pack(fill="both", expand=True)

        # Current file
        self.file_label = tk.Label(left,
            text=f"Current file: {self.filename}",bg=self.background_color, fg=self.text,
            font=("Helvetica", 9))
        self.file_label.pack(anchor="w")

        tk.Button(left, text="Open file",
            command=self._open_file, **button_style).pack(
            fill="x", pady=(0, 4))

        # Workspace
        self.workspace = tk.Frame(main, bg=self.workspace_color, bd=1, relief="solid")
        self.workspace.pack(side="left", fill="both",
                            expand=True, padx=(4, 8), pady=8)

        self.placeholder = tk.Label(
            self.workspace,
            text="Choose file, witch you want to read",
            bg=self.workspace_color, fg=self.text,
            font=("Helvetica", 14), justify="center"
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # Pop-up menu with choose file and save user choose
    def _open_file(self):
        """
        At first open file manager with choose only CSV type of files.
        Alter, start work table manager witch check file for supporting their.
        In the end, user get notification about his file
        """

        path = filedialog.askopenfilename(filetypes=[("CSV file", "*.csv")])
        if not path:
            return

        logging.info(f"Try change direction to {path}. Start check user's table")

        try:
            tm = TableManager(path)
        except (ValueError, FileNotFoundError) as e:
            logging.error(f"Failed to load file '{path}': {e}")
            messagebox.showerror(title="Error opening file", message=f"Could not read the file:\n\n{e}")
            return

        if tm.check_table():
            messagebox.showinfo(
                title="Success",
                message=f"File {path} was successfully opened!\n{tm.info()}"
            )
            storage.update(path)
            self.filename = storage.file["filename"]
            self.file_label.config(text=f"Current file: {self.filename}")
            self.tm = tm
        else:
            messagebox.showerror(title="Unsupported data", message="Your data format is unsupported.")

    # Open table with navigation buttons
    def _open_table(self):
        if not hasattr(self, "tm"):
            messagebox.showwarning(title="No file", message="Please open a CSV file first.")
            return

        # clear workspace for change page
        for widget in self.workspace.winfo_children():
            widget.destroy()

        # Show tables
        TableView(
            self.workspace,
            df=self.tm.df
        ).pack(fill="both", expand=True)

    # Show graphic at workspace with navigation buttons
    def _open_graphic(self):
        ...

    # Get systems theme colors for app style
    def _get_windows_theme_info(self):
        """
        This function call only once and don't support dynamic color change with system,
        after change systems colors this app MUST BE REBOOTED.
        """
        settings = UISettings()

        # Converts a Windows color object to a HEX string
        def to_hex(color) -> str:
            # {:02x} formats the number in hexadecimal notation, adding a leading 0 if necessary
            return f"#{color.r:02x}{color.g:02x}{color.b:02x}".upper()

        self.accent: str = to_hex(settings.get_color_value(UIColorType.ACCENT))
        self.accent_light: str = to_hex(settings.get_color_value(UIColorType.ACCENT_LIGHT1))
        self.accent_dark: str = to_hex(settings.get_color_value(UIColorType.ACCENT_DARK1))
        self.background_color = "#FFFFFF"
        self.workspace_color = "#FFFFFF"
        self.text = "#55555"

        # If turn on dark mode, bg is black, if this true, change for different dark color
        if to_hex(settings.get_color_value(UIColorType.BACKGROUND)) == "#000000":
            self.background_color = "#2B2D30"
            self.workspace_color = "#1E1E1E"
            self.text = "#FFFFFF"

        storage.set_theme(
            self.accent, self.accent_light, self.accent_dark,
            self.workspace_color, self.text, self.background_color
        )