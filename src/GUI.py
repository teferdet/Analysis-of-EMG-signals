import tkinter as tk
from src import storage
from tkinter import filedialog
from winrt.windows.ui.viewmanagement import UISettings, UIColorType

class GUI(tk.Tk):
    # Initialization of main window params
    def __init__(self):
        super().__init__()
        self.title('Analysis of EMG signals')
        self.iconbitmap("./data/program.ico")
        self.geometry("900x700")
        self.minsize(900, 700)
        self._get_windows_theme_info()
        self.filename = storage.file["filename"]

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

        button_style = dict(
            bg=self.accent, fg="white",
            activebackground=self.accent_light, activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            font=("Helvetica", 10), height=2
        )

        tk.Button(left, text="Show graphic", **button_style).pack(
            fill="x", pady=(0, 6))

        tk.Button(left, text="Show table", **button_style).pack(
            fill="x", pady=(0, 6))

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
            text="Current empty workspace, please select function",
            bg=self.workspace_color, fg=self.text,
            font=("Helvetica", 14), justify="center"
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV file", "*.csv")])

        if path:
            storage.update(path)
            self.filename = storage.file["filename"]
            self.file_label.config(text=f"Current file: {self.filename}")

    # Change data in workspace
    def _rebuild(self):
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
        self.background_color = "white"
        self.workspace_color = "white"
        self.text = "555"

        # If turn on dark mode, bg is over black, if this true, change for different dark color
        if to_hex(settings.get_color_value(UIColorType.BACKGROUND)) == "#000000":
            self.background_color = "#2B2D30"
            self.workspace_color = "#1E1E1E"
            self.text = "white"


    # Request handler for change data in workspace
    def edit_workspace(self):
        pass
