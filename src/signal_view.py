import tkinter as tk
from tkinter import ttk
import threading
import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import RectangleSelector
from src import storage
from src.analysis_signal import AnalysisSignal


# ── Minimal toolbar: coordinates display only ─────────────────────────────────

class _MinimalToolbar(NavigationToolbar2Tk):
    """Navigation toolbar with no buttons — shows only cursor coordinates.

    Zoom interactions:
        - Left-drag  : rubber-band rectangle zoom
        - Scroll     : zoom X-axis anchored to cursor
        - Ctrl+Scroll: zoom Y-axis anchored to cursor
        - Middle-btn : reset to autoscale
    """

    toolitems: list = []   # no buttons at all

    def __init__(self, canvas, parent, bg: str, fg: str):
        super().__init__(canvas, parent, pack_toolbar=False)
        self.config(background=bg)
        for child in self.winfo_children():
            try:
                child.config(background=bg, foreground=fg,
                             relief="flat", bd=0)
            except tk.TclError:
                pass
        self.pack(side="bottom", fill="x")

    def set_message(self, msg: str):  # noqa: D401
        """Forward cursor-coordinate messages to the built-in label."""
        super().set_message(msg)



# ── Signal processing pipeline ────────────────────────────────────────────────

FS: float = 200.0   # MYO bracelet sampling rate (Hz)

# Maximum number of data points passed to matplotlib for the overview chart.
# matplotlib handles ~10–20k points without visible lag on modern hardware.
# Raising this from 4k to 15k means small files (< 15k rows) are never
# downsampled, so fill_between always has the full signal shape.
MAX_DISPLAY_POINTS: int = 15_000


def _downsample_stride(time_axis: np.ndarray,
                       signal:    np.ndarray,
                       max_pts:   int = MAX_DISPLAY_POINTS,
                       ) -> tuple[np.ndarray, np.ndarray]:
    """
    Uniform-stride decimation — take every N-th sample.

    This is the correct approach for overview visualisation because:
      * The output x-values are strictly monotonic  →  fill_between works.
      * It is a 2-line numpy index → essentially free (no reshape/argmin).
      * For an overview chart the exact peak amplitude of individual
        samples is irrelevant; the global waveform shape matters.

    For 4 M samples and max_pts=15 000 the stride is ~266, reducing the
    render load by 99.6% while preserving the visible signal envelope.
    """
    n = len(signal)
    if n <= max_pts:
        return time_axis, signal
    stride = max(1, n // max_pts)
    return time_axis[::stride], signal[::stride]


# ── EMG signal processing pipeline ───────────────────────────────────────────
#
# Surface EMG from MYO bracelet characteristics:
#   • Sampling rate : 200 Hz  →  Nyquist = 100 Hz
#   • Useful band   : 20–90 Hz (most sEMG power is 50–150 Hz, capped at Nyquist)
#   • DC / drift    : removed by highpass at 20 Hz
#   • Motion artefacts: low-frequency (<20 Hz), removed by same highpass
#   • Power line    : 50 Hz (Europe) — removed by IIR notch filter
#   • Transient artefacts: electrode pop / motion spikes — clipped via MAD threshold
#
# Pipeline:
#   Step 1  Raw       – unprocessed
#   Step 2  Denoised  – highpass 20 Hz + notch 50 Hz + artefact clipping
#   Step 3  Filtered  – bandpass 20–90 Hz (tight) applied to denoised signal
#   Step 4  Rectified – full-wave rectification of filtered
#   Step 5  Envelope  – RMS envelope with 100 ms sliding window
# ─────────────────────────────────────────────────────────────────────────────

def _butter(cutoff, btype, fs=FS, order=4):
    """Return (b, a) Butterworth coefficients. cutoff: scalar or [low, high]."""
    nyq = fs / 2.0
    norm = [c / nyq for c in cutoff] if isinstance(cutoff, (list, tuple)) else cutoff / nyq
    return butter(order, norm, btype=btype)


def _notch(freq=50.0, q=30.0, fs=FS):
    """Return (b, a) IIR notch (band-stop) coefficients."""
    from scipy.signal import iirnotch
    return iirnotch(freq / (fs / 2.0), q)


def _clip_artifacts(sig: np.ndarray, k: float = 4.0) -> np.ndarray:
    """
    Soft-clip transient artefacts using k × MAD threshold.

    MAD (Median Absolute Deviation) is robust to outliers unlike std.
    Samples exceeding ±k·MAD are clipped to ±k·MAD.
    k=4 retains ~99.9% of a Gaussian but clips electrode pop spikes.
    """
    mad = np.median(np.abs(sig - np.median(sig)))
    if mad == 0:
        return sig.copy()
    threshold = k * mad
    return np.clip(sig, -threshold, threshold)


def pipeline_raw(series: np.ndarray, **_) -> np.ndarray:
    """Step 1: raw signal as-is — no processing."""
    return series.copy()


def pipeline_denoised(series: np.ndarray, fs: float = FS, **_) -> np.ndarray:
    """
    Step 2: denoise — remove DC, motion artefacts, and power-line interference.

    Operations (in order):
        1. Highpass at 20 Hz   → removes DC offset and low-frequency motion artefacts
        2. Notch at 50 Hz      → removes European power-line interference
        3. MAD artefact clipping (k=4) → removes electrode pop transients
    """
    b, a = _butter(20.0, "high", fs)
    sig = filtfilt(b, a, series)

    b_n, a_n = _notch(50.0, q=30.0, fs=fs)
    sig = filtfilt(b_n, a_n, sig)

    return _clip_artifacts(sig, k=4.0)


def pipeline_filtered(series: np.ndarray, fs: float = FS, **_) -> np.ndarray:
    """
    Step 3: bandpass 20–90 Hz (Butterworth, order 4) on the denoised signal.

    At fs=200 Hz the Nyquist limit is 100 Hz; 90 Hz is a safe upper bound.
    20 Hz lower cut removes residual motion artefacts not caught by the notch.
    Applied after denoising so the bandpass operates on a clean baseline.
    """
    denoised = pipeline_denoised(series, fs)
    b, a = _butter([20.0, 90.0], "band", fs)
    return filtfilt(b, a, denoised)


def pipeline_rectified(series: np.ndarray, **kwargs) -> np.ndarray:
    """Step 4: full-wave rectification — absolute value of the filtered signal."""
    return np.abs(pipeline_filtered(series, **kwargs))


def pipeline_envelope(series: np.ndarray, window_ms: int = 100,
                      fs: float = FS, **kwargs) -> np.ndarray:
    """
    Step 5: RMS envelope with a sliding window of *window_ms* milliseconds.

    RMS envelope is preferred over moving average (Step 4 in older literature)
    because it preserves the energy content of the signal and avoids
    phase distortion introduced by simple averaging.

    Window of 100 ms is standard for gesture-recognition sEMG
    (Phinyomark et al., 2012; Merletti & Parker, 2004).
    """
    rectified   = pipeline_rectified(series, fs=fs, **kwargs)
    window_size = max(1, int(window_ms * fs / 1000))
    # Compute squared signal, then sliding mean, then sqrt
    sq = rectified ** 2
    kernel = np.ones(window_size) / window_size
    rms_env = np.sqrt(np.convolve(sq, kernel, mode="same"))
    return rms_env


PIPELINE_STEPS = {
    "1. Raw signal":  pipeline_raw,
    "2. Denoised":    pipeline_denoised,
    "3. Filtered":    pipeline_filtered,
    "4. Rectified":   pipeline_rectified,
    "5. Envelope":    pipeline_envelope,
}



# ── Widget ────────────────────────────────────────────────────────────────────

class SignalView(tk.Frame):
    """
    Embeddable signal viewer widget for tkinter.

    Two modes toggled by tabs:
        Overview  – full dataset time-series with processing pipeline selector
        Single    – bar chart for one row + analysis info panel

    Features:
        - Cached signal processing (invalidated on load())
        - draw_idle() for non-blocking redraws
        - NavigationToolbar2Tk (Pan / Zoom / Save / History)
        - Scroll-to-zoom: MouseWheel → X-axis, Ctrl+MouseWheel → Y-axis
        - Middle-click → reset zoom (autoscale)
        - "Reset zoom" button in each bottom panel

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

        # Cache: (step_name, channel) → processed np.ndarray
        self._overview_cache: dict[tuple, np.ndarray] = {}

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
        chart_frame.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        self.fig = Figure(figsize=(10, 4.0), dpi=96, facecolor=self.bg)
        self.ax  = self.fig.add_subplot(111)
        self._style_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # ── Coordinates-only toolbar ─────────────────────────────────────────
        self.toolbar = _MinimalToolbar(
            self.canvas, chart_frame,
            bg=self.bg, fg=self.text_color,
        )
        self.toolbar.update()

        # ── Rectangle drag-to-zoom (left mouse button) ──────────────────────
        self._rect_selector = RectangleSelector(
            self.ax,
            self._on_rect_select,
            useblit=True,
            button=[1],                  # left button only
            minspanx=5, minspany=5,
            spancoords="pixels",
            interactive=False,
            props=dict(
                facecolor=self.accent, edgecolor=self.accent,
                alpha=0.25, fill=True, linewidth=1.5,
            ),
        )

        # ── Scroll-to-zoom + middle-click reset ─────────────────────────
        self.canvas.get_tk_widget().bind("<MouseWheel>",  self._on_scroll)
        self.canvas.get_tk_widget().bind("<Button-2>",    self._on_middle_click)

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
        # 'clam' is the only built-in theme that reliably honours
        # custom fieldbackground / foreground on Windows (readonly combobox).
        style.theme_use("clam")
        style.configure(
            "Sig.TCombobox",
            fieldbackground=self.bg,
            background=self.accent,
            foreground=self.text_color,
            selectbackground=self.accent,
            selectforeground="white",
            arrowcolor="white",
            bordercolor=self._darken(self.bg, 10),
            lightcolor=self.bg,
            darkcolor=self.bg,
        )
        style.map(
            "Sig.TCombobox",
            fieldbackground=[("readonly", self.bg)],
            foreground=[("readonly", self.text_color)],
            selectbackground=[("readonly", self.bg)],
            selectforeground=[("readonly", self.text_color)],
            background=[("readonly", self.accent)],
            arrowcolor=[("readonly", "white")],
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

        tk.Button(
            self._overview_ctrl, text="↺ Reset zoom",
            command=self._reset_zoom, **btn_cfg,
        ).pack(side="left", padx=(6, 0))

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

        tk.Button(
            nav, text="↺ Reset zoom",
            command=self._reset_zoom, **btn_cfg,
        ).pack(side="left", padx=(12, 0))

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
            "SNR":               make_row(right_col, "SNR (est.)"),
            "Signal quality":    make_row(right_col, "Signal quality"),
            "Activity":          make_row(right_col, "Activity"),
            "Mismatch":          make_row(left_col,  "Label mismatch"),
            "Dominant channels": make_row(right_col, "Dominant ch."),
            "Recording series":  make_row(left_col,  "Recording series"),
        }

    # ------------------------------------------------------------------ #
    #  Overview rendering                                                  #
    # ------------------------------------------------------------------ #

    # ── render token: cancels stale callbacks from old threads ────────────
    _render_token: int = 0

    def _render_overview(self):
        """
        Draw the full-dataset time-series chart.

        Cache hit  → plot immediately on the main thread (fast path).
        Cache miss → show a 'Computing…' indicator, compute the signal
                     processing pipeline in a daemon thread, then plot.

        A render token prevents stale thread callbacks from overwriting
        a newer render when the user switches pipeline/channel rapidly.
        """
        step_name = self.pipeline_var.get()
        channel   = self.channel_var.get()
        cache_key = (step_name, channel)

        if cache_key in self._overview_cache:
            # ── Fast path: cached ───────────────────────────────────────
            t_ds, s_ds = self._overview_cache[cache_key]
            self._plot_overview(t_ds, s_ds, step_name, channel)
            return

        # ── Slow path: compute in background ───────────────────────────
        SignalView._render_token += 1
        my_token = SignalView._render_token

        self._show_chart_busy(f"Processing {step_name}…")

        fn = PIPELINE_STEPS[step_name]
        result: dict = {}

        def worker():
            time_axis = self.df["time"].values
            if channel == "All":
                raw = np.mean(
                    [fn(self.df[ch].values) for ch in self.CHANNEL_COLS],
                    axis=0,
                )
            else:
                raw = fn(self.df[channel].values)
            t_ds, s_ds = _downsample_stride(time_axis, raw)
            result["data"] = (t_ds, s_ds)
            self.after(0, finish)

        def finish():
            # Discard if a newer render was requested in the meantime
            if my_token != SignalView._render_token:
                return
            self._overview_cache[cache_key] = result["data"]
            t_ds, s_ds = result["data"]
            self._plot_overview(t_ds, s_ds, step_name, channel)

        threading.Thread(target=worker, daemon=True).start()

    def _show_chart_busy(self, msg: str = "Computing…"):
        """Show a centred status message on the axes while computing."""
        self.ax.clear()
        self._style_axes()
        self.ax.text(
            0.5, 0.5, msg,
            transform=self.ax.transAxes,
            ha="center", va="center",
            fontsize=13, color=self.text_color,
            fontfamily="monospace", alpha=0.55,
        )
        self.canvas.draw_idle()

    def _plot_overview(self, time_axis: np.ndarray, processed: np.ndarray,
                       step_name: str, channel: str):
        """Render the processed (and possibly down-sampled) signal.

        fill_between is skipped for downsampled data because min-max
        interleaving causes polygon artefacts (\"tent\" shapes between
        consecutive min/max pairs with widely different y-values).
        """
        ch_label = "Mean of all channels" if channel == "All" else channel

        self.ax.clear()
        self._style_axes()

        n_displayed    = len(time_axis)
        is_downsampled = n_displayed < self.total

        if not is_downsampled:
            # Full-resolution: fill is visually clean (points are dense).
            self.ax.fill_between(time_axis, processed, alpha=0.30,
                                 color=self.accent, zorder=2)
        # Downsampled (stride ~280 pts): fill_between draws huge polygons
        # across gaps; a clean line is always correct at any stride level.
        self.ax.plot(time_axis, processed, color=self.accent,
                     linewidth=0.8, zorder=3)

        ds_note = (
            f"  (\u2193 {n_displayed:,} pts)"
            if is_downsampled else ""
        )
        self.ax.set_title(
            f"{step_name}  \u00b7  {ch_label}  \u00b7  {self.total:,} samples{ds_note}",
            fontsize=9, color=self.text_color, pad=8, fontfamily="monospace",
        )
        self.ax.set_xlabel("Time (ms)", fontsize=8, color=self.text_color)
        self.ax.set_ylabel("Amplitude (V)", fontsize=8, color=self.text_color)

        self.fig.tight_layout(pad=1.2)
        self.canvas.draw_idle()

        self.lbl_overview_info.config(
            text=f"{self.total:,} rows \u00b7 {step_name}{ds_note}")




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
                clip_on=True,          # clipped to axes bounds on zoom
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

        # Give 12% headroom above the tallest bar so value labels
        # are fully visible at default zoom level
        if max(abs_values) > 0:
            self.ax.set_ylim(bottom=0,
                             top=max(abs_values) * 1.18)

        self.fig.tight_layout(pad=1.2)
        self.canvas.draw_idle()


    def _update_info(self, analysis: AnalysisSignal):
        dominant_str = ", ".join(f"ch{i}" for i in analysis.dominant_channels)

        status_color = {"Active": "#4CAF50", "Passive": self._muted()}.get(
            analysis.status, self.text_color)
        load_colors  = {
            "None":   self._muted(),
            "Low":    "#8BC34A",
            "Medium": "#FFC107",
            "High":   "#F44336",
        }
        quality_colors = {
            "No signal": self._muted(),
            "Noise":     "#FF9800",
            "Weak":      "#FFC107",
            "Normal":    "#8BC34A",
            "Strong":    "#4CAF50",
        }
        mismatch_color = "#FF5722" if analysis.activity_mismatch else "#4CAF50"
        mismatch_text  = "⚠ Yes" if analysis.activity_mismatch else "✓ No"

        updates = {
            "Gesture":           (analysis.gesture_name,  self.text_color),
            "Status":            (analysis.status,         status_color),
            "Load level":        (analysis.load_level,     load_colors.get(analysis.load_level, self.text_color)),
            "Body part":         (analysis.body_part,      self.text_color),
            "RMS amplitude":     (f"{analysis.rms:.3e} V", self.text_color),
            "SNR":               (f"{analysis.snr_db:+.1f} dB", self.text_color),
            "Signal quality":    (analysis.signal_quality, quality_colors.get(analysis.signal_quality, self.text_color)),
            "Activity":          (analysis.activity_label, "#4CAF50" if analysis.activity_detected else self._muted()),
            "Mismatch":          (mismatch_text,           mismatch_color),
            "Dominant channels": (dominant_str,            self.text_color),
            "Recording series":  (analysis.series_label,   self.text_color),
        }
        for key, (val, color) in updates.items():
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
    #  Zoom — rectangle drag, scroll, middle-click                        #
    # ------------------------------------------------------------------ #

    def _on_rect_select(self, eclick, erelease):
        """Zoom into the rectangle drawn by left-drag."""
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata

        # Ignore clicks that produce no valid data coords or degenerate rect
        if None in (x1, y1, x2, y2):
            return
        if abs(x2 - x1) < 1e-12 or abs(y2 - y1) < 1e-12:
            return

        self.ax.set_xlim(min(x1, x2), max(x1, x2))
        self.ax.set_ylim(min(y1, y2), max(y1, y2))
        self.canvas.draw_idle()

    def _on_scroll(self, event: tk.Event):
        """Scroll wheel: zoom X-axis. Ctrl+scroll: zoom Y-axis.

        Zooms anchored to the cursor position so the point under the
        mouse stays fixed — the same behaviour as most scientific tools.

        Coordinate pipeline:
            tkinter widget pixels → matplotlib figure pixels (flip Y) →
            axes data coordinates.
        """
        factor = 1 / 1.15 if event.delta > 0 else 1.15  # zoom in / out

        # tkinter gives (x, y) relative to the widget top-left.
        # Matplotlib display coords have origin at figure bottom-left → flip Y.
        widget = self.canvas.get_tk_widget()
        fig_x = event.x
        fig_y = widget.winfo_height() - event.y

        try:
            x_data, y_data = self.ax.transData.inverted().transform((fig_x, fig_y))
        except Exception:
            return

        if event.state & 0x0004:  # Ctrl held → zoom Y, anchored to cursor
            ymin, ymax = self.ax.get_ylim()
            frac = (y_data - ymin) / (ymax - ymin) if ymax != ymin else 0.5
            new_range = (ymax - ymin) * factor
            self.ax.set_ylim(y_data - frac * new_range,
                             y_data + (1.0 - frac) * new_range)
        else:                      # zoom X, anchored to cursor
            xmin, xmax = self.ax.get_xlim()
            frac = (x_data - xmin) / (xmax - xmin) if xmax != xmin else 0.5
            new_range = (xmax - xmin) * factor
            self.ax.set_xlim(x_data - frac * new_range,
                             x_data + (1.0 - frac) * new_range)

        self.canvas.draw_idle()

    def _on_middle_click(self, _event=None):
        """Middle mouse button — reset zoom to autoscale."""
        self._reset_zoom()

    def _reset_zoom(self):
        """Reset both axes to auto-scale limits."""
        self.ax.autoscale()
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def load(self, df: pd.DataFrame):
        """Replace the dataset, clear the cache and reset to the first row."""
        self.df          = df
        self.total       = len(df)
        self.current_idx = 0
        self._overview_cache.clear()   # invalidate cache on new data
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