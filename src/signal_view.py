import tkinter as tk
from tkinter import ttk
import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from src import storage
from src.analysis_signal import AnalysisSignal


# ── Signal processing pipeline ────────────────────────────────────────────────

def pipeline_raw(series: np.ndarray) -> np.ndarray:
    """Step 1: raw signal as-is."""
    return series.copy()


def pipeline_filtered(series: np.ndarray, fs: float = 200.0,
                      lowcut: float = 10.0, highcut: float = 90.0) -> np.ndarray:
    """Step 2: bandpass Butterworth filter (10–90 Hz) to remove noise and DC."""
    nyq = fs / 2.0
    low, high = lowcut / nyq, highcut / nyq
    b, a = butter(4, [low, high], btype="band")
    return filtfilt(b, a, series)


def pipeline_rectified(series: np.ndarray, **kwargs) -> np.ndarray:
    """Step 3: full-wave rectification — take absolute value of filtered signal."""
    return np.abs(pipeline_filtered(series, **kwargs))


def pipeline_envelope(series: np.ndarray, window_ms: int = 50,
                      fs: float = 200.0, **kwargs) -> np.ndarray:
    """Step 4: linear envelope via moving-average smoothing of the rectified signal."""
    rectified   = pipeline_rectified(series, fs=fs, **kwargs)
    window_size = max(1, int(window_ms * fs / 1000))
    kernel      = np.ones(window_size) / window_size
    return np.convolve(rectified, kernel, mode="same")


PIPELINE_STEPS = {
    "1. Raw signal":   pipeline_raw,
    "2. Filtered":     pipeline_filtered,
    "3. Rectified":    pipeline_rectified,
    "4. Envelope":     pipeline_envelope,
}


# ── Widget ────────────────────────────────────────────────────────────────────

class SignalView(tk.Frame):
    """
    Embeddable signal viewer widget for tkinter.

    Two modes toggled by tabs:
        Overview  – full dataset time-series with processing pipeline selector
        Single    – bar chart for one row + analysis info panel

    Usage:
        view = SignalView(parent, df=dataframe)
        view.pack(fill="both", expand=True)
    """

    CHANNEL_COLS = [f"channel{i}" for i in range(1, 9)]

    def __init__(self, parent, df: pd.DataFrame, **kwargs):
        self.bg         = storage.theme["workspace_color"]
        self.accent     = storage.theme["accent"]
        self.text_color = storage.theme["text"]
        self.bg_dark    = self._darken(self.bg, 12)

        super().__init__(parent, bg=self.bg, **kwargs)

        self.df          = df
        self.total       = len(df)
        self.current_idx = 0

        self._build()
        self._render_overview()

    # ------------------------------------------------------------------ #
    #  Layout                                                              #
    # ------------------------------------------------------------------ #

    def _build(self):
        # ── Tab bar ──────────────────────────────────────────────────────
        tab_bar = tk.Frame(self, bg=self.bg_dark)
        tab_bar.pack(fill="x", padx=8, pady=(8, 0))

        tab_cfg = dict(relief="flat", bd=0, font=("Consolas", 9, "bold"),
                       cursor="hand2", padx=16, pady=5)

        self.btn_tab_overview = tk.Button(
            tab_bar, text="Overview",
            bg=self.accent, fg="white",
            activebackground=storage.theme["accent_light"],
            activeforeground="white",
            command=self._switch_overview, **tab_cfg,
        )
        self.btn_tab_overview.pack(side="left", padx=(0, 2))

        self.btn_tab_single = tk.Button(
            tab_bar, text="Single row",
            bg=self.bg_dark, fg=self.text_color,
            activebackground=storage.theme["accent_light"],
            activeforeground="white",
            command=self._switch_single, **tab_cfg,
        )
        self.btn_tab_single.pack(side="left")

        # ── Shared chart area ────────────────────────────────────────────
        chart_frame = tk.Frame(self, bg=self.bg)
        chart_frame.pack(fill="both", expand=True, padx=8, pady=(6, 4))

        self.fig = Figure(figsize=(10, 4.0), dpi=96, facecolor=self.bg)
        self.ax  = self.fig.add_subplot(111)
        self._style_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # ── Bottom panel (swappable) ─────────────────────────────────────
        self.bottom = tk.Frame(self, bg=self.bg_dark, bd=1, relief="flat")
        self.bottom.pack(fill="x", padx=8, pady=(0, 8))

        self._build_overview_controls()
        self._build_single_controls()

        # Show overview controls by default
        self._overview_ctrl.pack(fill="x", padx=10, pady=6)
        self._single_ctrl.pack_forget()

    # ── Overview bottom controls ─────────────────────────────────────────

    def _build_overview_controls(self):
        self._overview_ctrl = tk.Frame(self.bottom, bg=self.bg_dark)

        tk.Label(
            self._overview_ctrl, text="Processing stage:",
            bg=self.bg_dark, fg=self.text_color, font=("Consolas", 9),
        ).pack(side="left", padx=(0, 8))

        style = ttk.Style()
        style.configure(
            "Sig.TCombobox",
            fieldbackground=self.bg,
            background=self.accent,
            foreground=self.text_color,
            selectbackground=self.accent,
            selectforeground="white",
            arrowcolor="white",
        )

        self.pipeline_var = tk.StringVar(value=list(PIPELINE_STEPS.keys())[0])
        self.pipeline_combo = ttk.Combobox(
            self._overview_ctrl,
            textvariable=self.pipeline_var,
            values=list(PIPELINE_STEPS.keys()),
            state="readonly", width=22,
            style="Sig.TCombobox",
            font=("Consolas", 9),
        )
        self.pipeline_combo.pack(side="left", padx=(0, 10))
        self.pipeline_combo.bind("<<ComboboxSelected>>", lambda _: self._render_overview())

        tk.Label(
            self._overview_ctrl, text="Channel:",
            bg=self.bg_dark, fg=self.text_color, font=("Consolas", 9),
        ).pack(side="left", padx=(0, 6))

        self.channel_var = tk.StringVar(value="All")
        channel_options  = ["All"] + self.CHANNEL_COLS
        self.channel_combo = ttk.Combobox(
            self._overview_ctrl,
            textvariable=self.channel_var,
            values=channel_options,
            state="readonly", width=12,
            style="Sig.TCombobox",
            font=("Consolas", 9),
        )
        self.channel_combo.pack(side="left", padx=(0, 10))
        self.channel_combo.bind("<<ComboboxSelected>>", lambda _: self._render_overview())

        btn_cfg = dict(
            bg=self.accent, fg="white",
            activebackground=storage.theme["accent_light"],
            activeforeground="white",
            relief="flat", bd=0,
            font=("Consolas", 9, "bold"),
            cursor="hand2", padx=14, pady=3,
        )
        tk.Button(
            self._overview_ctrl, text="Refresh",
            command=self._render_overview, **btn_cfg,
        ).pack(side="left")

        # Row count info (right side)
        self.lbl_overview_info = tk.Label(
            self._overview_ctrl, text="",
            bg=self.bg_dark, fg=self._muted(),
            font=("Consolas", 8),
        )
        self.lbl_overview_info.pack(side="right")

    # ── Single row bottom controls ───────────────────────────────────────

    def _build_single_controls(self):
        self._single_ctrl = tk.Frame(self.bottom, bg=self.bg_dark)

        btn_cfg = dict(
            bg=self.accent, fg="white",
            activebackground=storage.theme["accent_light"],
            activeforeground="white",
            relief="flat", bd=0,
            font=("Consolas", 9, "bold"),
            cursor="hand2", padx=12, pady=3,
        )

        # Navigation
        nav = tk.Frame(self._single_ctrl, bg=self.bg_dark)
        nav.pack(fill="x", pady=(4, 4))

        self.btn_prev = tk.Button(nav, text="‹ Prev", command=self._go_prev, **btn_cfg)
        self.btn_prev.pack(side="left", padx=(0, 6))

        self.btn_next = tk.Button(nav, text="Next ›", command=self._go_next, **btn_cfg)
        self.btn_next.pack(side="left")

        self.lbl_index = tk.Label(
            nav, text="", bg=self.bg_dark, fg=self.text_color,
            font=("Consolas", 9),
        )
        self.lbl_index.pack(side="left", padx=12)

        tk.Label(nav, text="Go to:", bg=self.bg_dark, fg=self.text_color,
                 font=("Consolas", 9)).pack(side="left", padx=(12, 4))

        self.jump_var = tk.StringVar()
        jump_entry = tk.Entry(
            nav, textvariable=self.jump_var, width=8,
            font=("Consolas", 9), bg=self.bg, fg=self.text_color,
            insertbackground=self.text_color, relief="flat", bd=1,
        )
        jump_entry.pack(side="left", padx=(0, 4))
        jump_entry.bind("<Return>", self._go_to_index)
        tk.Button(nav, text="Go", command=self._go_to_index, **btn_cfg).pack(side="left")

        # Separator
        tk.Frame(self._single_ctrl, bg=self._darken(self.bg_dark, 15), height=1).pack(
            fill="x", pady=(0, 4))

        # Info grid
        info_frame = tk.Frame(self._single_ctrl, bg=self.bg_dark)
        info_frame.pack(fill="x", pady=(0, 6))

        left_col  = tk.Frame(info_frame, bg=self.bg_dark)
        left_col.pack(side="left", fill="both", expand=True)
        right_col = tk.Frame(info_frame, bg=self.bg_dark)
        right_col.pack(side="left", fill="both", expand=True)

        lbl_cfg = dict(bg=self.bg_dark, font=("Consolas", 9))

        def make_row(parent, key):
            row = tk.Frame(parent, bg=self.bg_dark)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=key, fg=self._muted(), width=20,
                     anchor="w", **lbl_cfg).pack(side="left")
            v = tk.Label(row, text="—", fg=self.text_color, anchor="w", **lbl_cfg)
            v.pack(side="left")
            return v

        self._lbl = {
            "Gesture":           make_row(left_col,  "Gesture"),
            "Status":            make_row(left_col,  "Status"),
            "Load level":        make_row(left_col,  "Load level"),
            "Body part":         make_row(left_col,  "Body part"),
            "RMS amplitude":     make_row(right_col, "RMS amplitude"),
            "Signal quality":    make_row(right_col, "Signal quality"),
            "Dominant channels": make_row(right_col, "Dominant channels"),
            "Recording series":  make_row(right_col, "Recording series"),
        }

    # ------------------------------------------------------------------ #
    #  Overview rendering                                                  #
    # ------------------------------------------------------------------ #

    def _render_overview(self):
        """Draw the full-dataset time-series chart with selected processing."""
        step_name = self.pipeline_var.get()
        channel   = self.channel_var.get()
        fn        = PIPELINE_STEPS[step_name]

        self.ax.clear()
        self._style_axes()

        time_axis = self.df["time"].values

        if channel == "All":
            # Plot mean across all channels
            combined = np.mean(
                [fn(self.df[ch].values) for ch in self.CHANNEL_COLS], axis=0
            )
            self.ax.fill_between(time_axis, combined, alpha=0.35,
                                 color=self.accent, zorder=2)
            self.ax.plot(time_axis, combined, color=self.accent,
                         linewidth=0.8, zorder=3)
            ch_label = "Mean of all channels"
        else:
            processed = fn(self.df[channel].values)
            self.ax.fill_between(time_axis, processed, alpha=0.35,
                                 color=self.accent, zorder=2)
            self.ax.plot(time_axis, processed, color=self.accent,
                         linewidth=0.8, zorder=3)
            ch_label = channel

        self.ax.set_title(
            f"{step_name}  ·  {ch_label}  ·  {self.total} samples",
            fontsize=9, color=self.text_color, pad=8, fontfamily="monospace",
        )
        self.ax.set_xlabel("Time (ms)", fontsize=8, color=self.text_color)
        self.ax.set_ylabel("Amplitude (V)", fontsize=8, color=self.text_color)

        self.fig.tight_layout(pad=1.2)
        self.canvas.draw()

        self.lbl_overview_info.config(text=f"{self.total} rows · {step_name}")

    # ------------------------------------------------------------------ #
    #  Single row rendering                                                #
    # ------------------------------------------------------------------ #

    def _render_single(self, idx: int):
        """Draw bar chart and update info panel for the row at *idx*."""
        row      = self.df.iloc[idx]
        analysis = AnalysisSignal(row)
        data     = analysis.chart_data()

        self._draw_bar_chart(data, idx)
        self._update_info(analysis)
        self._update_nav(idx)

    def _draw_bar_chart(self, data: dict, idx: int):
        self.ax.clear()
        self._style_axes()

        channels   = data["labels"]
        abs_values = data["abs_values"]
        raw_values = data["values"]
        x          = np.arange(len(channels))

        colors = [
            self._bar_color(v, data["is_active"]) for v in raw_values
        ]
        bars = self.ax.bar(x, abs_values, color=colors, width=0.55,
                           zorder=3, linewidth=0)

        for bar, val in zip(bars, raw_values):
            h = bar.get_height()
            self.ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + max(abs_values) * 0.02,
                f"{val:+.1e}",
                ha="center", va="bottom",
                fontsize=7, color=self.text_color,
                fontfamily="monospace",
            )

        rms = data["rms"]
        self.ax.axhline(rms, color=self.accent, linewidth=1.2,
                        linestyle="--", alpha=0.7, zorder=2,
                        label=f"RMS = {rms:.2e} V")

        self.ax.set_xticks(x)
        self.ax.set_xticklabels(
            [c.replace("channel", "ch") for c in channels],
            fontsize=8, color=self.text_color, fontfamily="monospace",
        )
        self.ax.set_ylabel("Amplitude |V|", fontsize=8,
                           color=self.text_color, labelpad=6)
        self.ax.set_title(
            f"Row {idx}  ·  Gesture: {data['gesture']}  ·  "
            f"{'Active' if data['is_active'] else 'Passive'}",
            fontsize=9, color=self.text_color, pad=8, fontfamily="monospace",
        )
        self.ax.legend(
            fontsize=7, facecolor=self.bg_dark,
            edgecolor="none", labelcolor=self.text_color,
        )

        self.fig.tight_layout(pad=1.2)
        self.canvas.draw()

    def _update_info(self, analysis: AnalysisSignal):
        dominant_str = ", ".join(f"ch{i}" for i in analysis.dominant_channels)
        mapping = {
            "Gesture":           analysis.gesture_name,
            "Status":            analysis.status,
            "Load level":        analysis.load_level,
            "Body part":         analysis.body_part,
            "RMS amplitude":     f"{analysis.rms:.3e} V",
            "Signal quality":    analysis.signal_quality,
            "Dominant channels": dominant_str,
            "Recording series":  analysis.series_label,
        }
        status_color = {"Active": "#4CAF50", "Passive": self._muted()}.get(
            analysis.status, self.text_color)
        load_colors  = {"None": self._muted(), "Low": "#8BC34A",
                        "Medium": "#FFC107", "High": "#F44336"}

        for key, val in mapping.items():
            color = self.text_color
            if key == "Status":
                color = status_color
            elif key == "Load level":
                color = load_colors.get(val, self.text_color)
            self._lbl[key].config(text=val, fg=color)

    def _update_nav(self, idx: int):
        self.lbl_index.config(text=f"Row {idx + 1} / {self.total}")
        self._set_btn(self.btn_prev, idx > 0)
        self._set_btn(self.btn_next, idx < self.total - 1)

    # ------------------------------------------------------------------ #
    #  Tab switching                                                       #
    # ------------------------------------------------------------------ #

    def _switch_overview(self):
        self.btn_tab_overview.config(bg=self.accent, fg="white")
        self.btn_tab_single.config(bg=self.bg_dark, fg=self.text_color)
        self._single_ctrl.pack_forget()
        self._overview_ctrl.pack(fill="x", padx=10, pady=6)
        self._render_overview()

    def _switch_single(self):
        self.btn_tab_single.config(bg=self.accent, fg="white")
        self.btn_tab_overview.config(bg=self.bg_dark, fg=self.text_color)
        self._overview_ctrl.pack_forget()
        self._single_ctrl.pack(fill="x", padx=10, pady=6)
        self._render_single(self.current_idx)

    # ------------------------------------------------------------------ #
    #  Navigation (single mode)                                            #
    # ------------------------------------------------------------------ #

    def _go_prev(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._render_single(self.current_idx)

    def _go_next(self):
        if self.current_idx < self.total - 1:
            self.current_idx += 1
            self._render_single(self.current_idx)

    def _go_to_index(self, _event=None):
        raw = self.jump_var.get().strip()
        if not raw.isdigit():
            return
        idx = max(0, min(int(raw) - 1, self.total - 1))
        self.current_idx = idx
        self._render_single(self.current_idx)
        self.jump_var.set("")

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def load(self, df: pd.DataFrame):
        """Replace the dataset and reset to the first row."""
        self.df          = df
        self.total       = len(df)
        self.current_idx = 0
        self._render_overview()

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _style_axes(self):
        self.ax.set_facecolor(self.bg_dark)
        self.ax.tick_params(colors=self.text_color, labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(self._darken(self.bg_dark, 20))
        self.ax.yaxis.label.set_color(self.text_color)
        self.ax.xaxis.label.set_color(self.text_color)
        self.ax.grid(axis="y", color=self._darken(self.bg_dark, 25),
                     linewidth=0.6, zorder=0)

    def _bar_color(self, value: float, is_active: bool) -> str:
        if not is_active:
            return self._muted()
        return self._lighten(self.accent, 30) if value >= 0 else self._darken(self.accent, 20)

    def _muted(self) -> str:
        return "#777777"

    @staticmethod
    def _set_btn(btn: tk.Button, enabled: bool):
        btn.config(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )

    @staticmethod
    def _darken(hex_color: str, amount: int) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{max(0, r-amount):02x}{max(0, g-amount):02x}{max(0, b-amount):02x}"

    @staticmethod
    def _lighten(hex_color: str, amount: int) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{min(255, r+amount):02x}{min(255, g+amount):02x}{min(255, b+amount):02x}"