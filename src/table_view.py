import tkinter as tk
from tkinter import ttk
import pandas as pd
from src import storage


class TableView(tk.Frame):
    """
    Embeddable paginated table widget for tkinter.

    Usage:
        view = TableView(parent, df=dataframe)
        view.pack(fill="both", expand=True)
    """

    PAGE_SIZES = [30, 45, 60]

    def __init__(self, parent, df: pd.DataFrame, **kwargs):
        self.bg = storage.theme["workspace_color"]
        self.accent = storage.theme["accent"]
        self.text_color = storage.theme["text"]

        super().__init__(parent, bg=self.bg, **kwargs)

        self.df           = df
        self.current_page = 0
        self.page_size    = tk.IntVar(value=self.PAGE_SIZES[0])

        self._build()
        self._render_page()

    # Create page with table
    def _build(self):
        # Table area
        table_frame = tk.Frame(self, bg=self.bg)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        vsb = ttk.Scrollbar(table_frame, orient="vertical")
        hsb = ttk.Scrollbar(table_frame, orient="horizontal")
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Table.Treeview",
            background=self.bg,
            foreground=self.text_color,
            fieldbackground=self.bg,
            rowheight=26,
            font=("Consolas", 9),
            borderwidth=0,
        )
        style.configure(
            "Table.Treeview.Heading",
            background=self.accent,
            foreground="white",
            font=("Consolas", 9, "bold"),
            relief="flat",
        )
        style.map(
            "Table.Treeview",
            background=[("selected", self.accent)],
            foreground=[("selected", "white")],
        )
        style.map(
            "Table.Treeview.Heading",
            background=[("active", storage.theme["accent_light"])],
        )

        # height=1 prevents Treeview from reserving extra blank rows
        # when the widget is taller than the actual data
        self.tree = ttk.Treeview(
            table_frame,
            style="Table.Treeview",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="browse",
            show="headings",
            height=1,
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        self.tree.pack(fill="both", expand=True)

        self.tree.tag_configure("odd",  background=self.bg)
        self.tree.tag_configure("even", background=self._darken(self.bg, 15))

        cols = list(self.df.columns)
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=max(80, len(col) * 11),
                             anchor="center", minwidth=60)

        # Navigation bar
        nav = tk.Frame(self, bg=self.bg, pady=6)
        nav.pack(fill="x", padx=8, pady=(4, 8))

        btn_style = dict(
            bg=self.accent,
            fg="white",
            activebackground=storage.theme["accent_light"],
            activeforeground="white",
            relief="flat", bd=0,
            font=("Consolas", 9, "bold"),
            cursor="hand2",
            padx=14, pady=4,
        )

        self.btn_first = tk.Button(nav, text="«", command=self._go_first, **btn_style)
        self.btn_first.pack(side="left", padx=(0, 4))

        self.btn_prev = tk.Button(nav, text="‹ Prev", command=self._go_prev, **btn_style)
        self.btn_prev.pack(side="left", padx=(0, 4))

        self.lbl_page = tk.Label(
            nav, text="", bg=self.bg, fg=self.text_color,
            font=("Consolas", 9)
        )
        self.lbl_page.pack(side="left", padx=8)

        self.btn_next = tk.Button(nav, text="Next ›", command=self._go_next, **btn_style)
        self.btn_next.pack(side="right", padx=(4, 0))

        self.btn_last = tk.Button(nav, text="»", command=self._go_last, **btn_style)
        self.btn_last.pack(side="right", padx=(4, 0))

        #  Rows-per-page dropdown (center)
        center = tk.Frame(nav, bg=self.bg)
        center.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            center, text="Rows per page:", bg=self.bg, fg=self.text_color,
            font=("Consolas", 9)
        ).pack(side="left", padx=(0, 6))

        style.configure(
            "Nav.TCombobox",
            fieldbackground=self.bg,
            background=self.accent,
            foreground=self.text_color,
            selectbackground=self.accent,
            selectforeground="white",
            arrowcolor="white",
        )

        self.combo = ttk.Combobox(
            center,
            textvariable=self.page_size,
            values=self.PAGE_SIZES,
            state="readonly",
            width=5,
            style="Nav.TCombobox",
            font=("Consolas", 9),
        )
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._on_page_size_change)

    # Rendering page
    def _render_page(self):
        """Clear the tree and insert exactly the rows for the current page."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        size  = self.page_size.get()
        start = self.current_page * size
        end   = min(start + size, len(self.df))
        page  = self.df.iloc[start:end]

        for i, (_, row) in enumerate(page.iterrows()):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=[self._fmt(v) for v in row], tags=(tag,))

        total_pages = self._total_pages()
        self.lbl_page.config(
            text=f"Page {self.current_page + 1} / {total_pages}"
                 f"   ({start + 1}–{end} of {len(self.df)} rows)"
        )

        at_first = self.current_page == 0
        at_last  = self.current_page >= total_pages - 1

        self._set_btn_state(self.btn_first, not at_first)
        self._set_btn_state(self.btn_prev,  not at_first)
        self._set_btn_state(self.btn_next,  not at_last)
        self._set_btn_state(self.btn_last,  not at_last)

    # Functional part of work with navigation
    def _go_first(self):
        self.current_page = 0
        self._render_page()

    def _go_prev(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_page()

    def _go_next(self):
        if self.current_page < self._total_pages() - 1:
            self.current_page += 1
            self._render_page()

    def _go_last(self):
        self.current_page = self._total_pages() - 1
        self._render_page()

    def _on_page_size_change(self, _event=None):
        self.current_page = 0
        self._render_page()


    def load(self, df: pd.DataFrame):
        """Replace the current DataFrame and reset to page 1."""
        self.df = df
        self.current_page = 0
        self._render_page()


    # information part of page, how much pages...
    def _total_pages(self) -> int:
        size = self.page_size.get()
        return max(1, -(-len(self.df) // size))

    @staticmethod
    def _fmt(value) -> str:
        if isinstance(value, float):
            return f"{value:.2e}" if abs(value) < 0.01 and value != 0 else f"{value:.5g}"
        return str(value)

    @staticmethod
    def _set_btn_state(btn: tk.Button, enabled: bool):
        btn.config(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )

    @staticmethod
    def _darken(hex_color: str, amount: int) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{max(0,r-amount):02x}{max(0,g-amount):02x}{max(0,b-amount):02x}"