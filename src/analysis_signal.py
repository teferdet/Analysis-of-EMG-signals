import numpy as np
import pandas as pd


class AnalysisSignal:
    """
    Analyses a single EMG sample row from the MYO Thalamic bracelet dataset.

    Dataset context (UCI / Kaggle EMG gesture recognition):
        - 8 channels = sensors equally spaced around the forearm
        - class  : gesture label
            0 - unmarked / transitional data
            1 - hand at rest
            2 - hand clenched in a fist
            3 - wrist flexion
            4 - wrist extension
            5 - radial deviation
            6 - ulnar deviation
            7 - extended / spread fingers
        - label  : recording series number (1 or 2)

    Usage:
        row = df.iloc[42]
        analysis = AnalysisSignal(row)
        print(analysis.report())
        chart_data = analysis.chart_data()
    """

    CHANNEL_COLS = [f"channel{i}" for i in range(1, 9)]

    # Gesture metadata: (name, is_active, load_level 0-3, description)
    GESTURE_MAP = {
        0: ("Unmarked",          False, 0, "Transitional or unmarked state"),
        1: ("Rest",              False, 0, "Hand at rest, muscles relaxed"),
        2: ("Fist",              True,  3, "Full hand clenched into a fist"),
        3: ("Wrist Flexion",     True,  2, "Wrist bent toward the palm side"),
        4: ("Wrist Extension",   True,  2, "Wrist bent in the opposite direction"),
        5: ("Radial Deviation",  True,  1, "Wrist deviation toward the thumb side"),
        6: ("Ulnar Deviation",   True,  1, "Wrist deviation toward the little finger"),
        7: ("Fingers Spread",    True,  2, "Fingers extended and spread apart"),
    }

    LOAD_LABELS = {0: "None", 1: "Low", 2: "Medium", 3: "High"}

    # Activity detection: RMS above this threshold (V) is considered active
    # Based on typical MYO bracelet noise floor ~1–5 µV; 8 µV is a safe margin.
    ACTIVITY_THRESHOLD: float = 8e-6   # 8 µV

    # Noise floor estimate assumed when no reference is available (V)
    NOISE_FLOOR_ASSUMED: float = 2e-6  # 2 µV

    def __init__(self, row: pd.Series):
        """
        Parameters
        ----------
        row : pd.Series
            A single row from the EMG DataFrame.
            Must contain: channel1-channel8, class, label, time.
        """
        self.row      = row
        self.time     = int(row["time"])
        self.class_id = int(row["class"])
        self.series   = int(row["label"])
        self.signals  = np.array([float(row[c]) for c in self.CHANNEL_COLS])

        # Derived fields — computed once and cached
        self._gesture  = self.GESTURE_MAP.get(self.class_id, self.GESTURE_MAP[0])
        self._rms      = self._compute_rms()
        self._snr_db   = self._compute_snr_db()
        self._dominant = self._dominant_channels()
        self._activity = self._detect_activity()

    # ------------------------------------------------------------------ #
    #  Public properties                                                   #
    # ------------------------------------------------------------------ #

    @property
    def gesture_name(self) -> str:
        return self._gesture[0]

    @property
    def is_active(self) -> bool:
        """True if the hand is performing an active gesture (from class label)."""
        return self._gesture[1]

    @property
    def status(self) -> str:
        return "Active" if self.is_active else "Passive"

    @property
    def load_level(self) -> str:
        return self.LOAD_LABELS[self._gesture[2]]

    @property
    def load_index(self) -> int:
        """Raw load index 0–3."""
        return self._gesture[2]

    @property
    def body_part(self) -> str:
        """Always forearm / hand for MYO bracelet data."""
        return "Forearm / Hand"

    @property
    def rms(self) -> float:
        """Root Mean Square amplitude across all 8 channels (V)."""
        return self._rms

    @property
    def snr_db(self) -> float:
        """
        Estimated Signal-to-Noise Ratio in dB.

        Uses NOISE_FLOOR_ASSUMED as the noise reference when the row RMS
        is larger than the noise floor; clamps to 0 dB when below.
        """
        return self._snr_db

    @property
    def dominant_channels(self) -> list[int]:
        """1-based indices of the two most active channels (by absolute amplitude)."""
        return self._dominant

    @property
    def peak_channel(self) -> int:
        """1-based index of the single channel with the highest absolute amplitude."""
        return int(np.argmax(np.abs(self.signals)) + 1)

    @property
    def activity_detected(self) -> bool:
        """
        True when the measured RMS exceeds the ACTIVITY_THRESHOLD (8 µV).

        This is a *signal-level* check independent of the class label.
        It is useful for detecting mis-labelled rows or detecting unexpected
        muscle activation during labelled rest periods.
        """
        return self._activity

    @property
    def activity_label(self) -> str:
        """Human-readable activity detection result."""
        return "Detected" if self._activity else "Not detected"

    @property
    def activity_mismatch(self) -> bool:
        """
        True when the class label says Active but no signal activity was detected,
        or the label says Passive but signal activity was detected.

        Useful for data quality checks.
        """
        return self.is_active != self._activity

    @property
    def channel_balance(self) -> float:
        """
        Coefficient of Variation (σ/µ) of absolute channel amplitudes (0–∞).

        A low value means all channels contribute equally; a high value indicates
        that only a few channels dominate (typical for localised muscle activation).
        """
        abs_vals = np.abs(self.signals)
        mean = abs_vals.mean()
        if mean == 0:
            return 0.0
        return float(abs_vals.std() / mean)

    @property
    def signal_quality(self) -> str:
        """
        Qualitative signal quality based on both RMS magnitude and estimated SNR.

        Levels
        ------
        No signal : RMS == 0 exactly
        Noise     : activity not detected (RMS < threshold)
        Weak      : activity detected, SNR < 6 dB
        Normal    : SNR 6–20 dB
        Strong    : SNR > 20 dB
        """
        if self._rms == 0:
            return "No signal"
        if not self._activity:
            return "Noise"
        if self._snr_db < 6:
            return "Weak"
        if self._snr_db < 20:
            return "Normal"
        return "Strong"

    @property
    def series_label(self) -> str:
        return f"Series {self.series}"

    # ------------------------------------------------------------------ #
    #  Main output                                                         #
    # ------------------------------------------------------------------ #

    def report(self) -> str:
        """
        Return a formatted human-readable analysis report.

        Example
        -------
            row = df.iloc[0]
            print(AnalysisSignal(row).report())
        """
        dominant_str = ", ".join(f"ch{i}" for i in self.dominant_channels)
        channel_lines = "\n".join(
            f"    channel{i+1}: {v:+.3e}"
            for i, v in enumerate(self.signals)
        )
        mismatch_note = (
            "  ⚠  Activity mismatch (label vs signal)\n"
            if self.activity_mismatch else ""
        )

        return (
            f"{'─' * 48}\n"
            f"  EMG Signal Analysis  |  Time: {self.time} ms\n"
            f"{'─' * 48}\n"
            f"  Gesture          : {self.gesture_name}\n"
            f"  Status           : {self.status}\n"
            f"  Load level       : {self.load_level}\n"
            f"  Body part        : {self.body_part}\n"
            f"  Recording series : {self.series_label}\n"
            f"{'─' * 48}\n"
            f"  RMS amplitude    : {self._rms:.3e} V\n"
            f"  SNR (estimated)  : {self._snr_db:+.1f} dB\n"
            f"  Signal quality   : {self.signal_quality}\n"
            f"  Activity detected: {self.activity_label}\n"
            f"  Channel balance  : {self.channel_balance:.2f} (CV)\n"
            f"  Peak channel     : ch{self.peak_channel}\n"
            f"  Dominant channels: {dominant_str}\n"
            f"{mismatch_note}"
            f"{'─' * 48}\n"
            f"  Channel values:\n"
            f"{channel_lines}\n"
            f"{'─' * 48}\n"
            f"  Description: {self._gesture[3]}\n"
            f"{'─' * 48}"
        )

    def to_dict(self) -> dict:
        """
        Return the analysis as a plain dictionary.
        Useful for passing data to GUI widgets or logging.
        """
        return {
            "time": self.time,
            "gesture": self.gesture_name,
            "status": self.status,
            "is_active": self.is_active,
            "load_level": self.load_level,
            "load_index": self.load_index,
            "body_part": self.body_part,
            "series": self.series_label,
            "rms": round(self._rms, 10),
            "snr_db": round(self._snr_db, 2),
            "signal_quality": self.signal_quality,
            "activity_detected": self.activity_detected,
            "activity_mismatch": self.activity_mismatch,
            "peak_channel": self.peak_channel,
            "channel_balance": round(self.channel_balance, 4),
            "dominant_channels": self.dominant_channels,
            "channels": {
                f"channel{i+1}": float(v)
                for i, v in enumerate(self.signals)
            },
        }

    def chart_data(self) -> dict:
        """
        Return data prepared for a matplotlib chart.

        Returns
        -------
        dict with keys:
            labels           - list of channel names ['channel1', ..., 'channel8']
            values           - raw signed amplitudes (float list)
            abs_values       - absolute amplitudes for bar chart y-axis
            rms              - scalar RMS value
            snr_db           - estimated SNR in dB
            gesture          - gesture name string
            is_active        - bool (from class label)
            activity_detected- bool (from signal level)
            load_index       - int 0-3
            class_id         - raw class integer
            peak_channel     - 1-based int
        """
        abs_vals = np.abs(self.signals).tolist()
        return {
            "labels":            self.CHANNEL_COLS,
            "values":            self.signals.tolist(),
            "abs_values":        abs_vals,
            "rms":               self._rms,
            "snr_db":            self._snr_db,
            "gesture":           self.gesture_name,
            "is_active":         self.is_active,
            "activity_detected": self.activity_detected,
            "load_index":        self.load_index,
            "class_id":          self.class_id,
            "peak_channel":      self.peak_channel,
        }

    # ------------------------------------------------------------------ #
    #  Static: summarize full DataFrame                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def summarize_dataset(df: pd.DataFrame) -> str:
        """
        Return a statistical summary of the full dataset.
        Shows gesture distribution, active/passive ratio, per-channel RMS,
        and estimated percentage of activity-mismatch rows.

        Parameters
        ----------
        df : full EMG DataFrame

        Example
        -------
            print(AnalysisSignal.summarize_dataset(tm.df))
        """
        total       = len(df)
        gesture_map = AnalysisSignal.GESTURE_MAP
        ch_cols     = AnalysisSignal.CHANNEL_COLS

        lines = [
            f"{'=' * 56}",
            f"  Dataset Summary  ({total} rows)",
            f"{'=' * 56}",
            "  Gesture distribution:",
        ]

        counts = df["class"].value_counts().sort_index()
        for cls_id, count in counts.items():
            name = gesture_map.get(int(cls_id), ("?",))[0]
            pct = count / total * 100
            bar = "█" * int(pct / 2)
            lines.append(f"    [{cls_id}] {name:<22} {count:>7} ({pct:4.1f}%) {bar}")

        # Active / passive split
        active_ids = [k for k, v in gesture_map.items() if v[1]]
        n_active   = df[df["class"].isin(active_ids)].shape[0]
        n_passive  = total - n_active

        # Signal-level activity detection across full dataset
        rms_per_row = np.sqrt(
            (df[ch_cols].values ** 2).mean(axis=1)
        )
        n_signal_active = int((rms_per_row >= AnalysisSignal.ACTIVITY_THRESHOLD).sum())
        n_mismatch = int(((rms_per_row >= AnalysisSignal.ACTIVITY_THRESHOLD)
                          != df["class"].isin(active_ids).values).sum())

        lines += [
            f"{'─' * 56}",
            f"  Active samples   (label)  : {n_active:>8} ({n_active / total * 100:.1f}%)",
            f"  Passive samples  (label)  : {n_passive:>8} ({n_passive / total * 100:.1f}%)",
            f"  Active samples   (signal) : {n_signal_active:>8} ({n_signal_active / total * 100:.1f}%)",
            f"  Label/signal mismatches   : {n_mismatch:>8} ({n_mismatch / total * 100:.1f}%)",
            f"{'─' * 56}",
            "  Per-channel RMS (mean across dataset):",
        ]

        for ch in ch_cols:
            rms_val = np.sqrt((df[ch] ** 2).mean())
            lines.append(f"    {ch}: {rms_val:.3e} V")

        # Channel with highest mean RMS (most active on average)
        rms_vals = np.array([np.sqrt((df[ch] ** 2).mean()) for ch in ch_cols])
        dominant_ch = ch_cols[int(np.argmax(rms_vals))]

        lines += [
            f"{'─' * 56}",
            f"  Most active channel (mean RMS): {dominant_ch}",
            f"{'=' * 56}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _compute_rms(self) -> float:
        """Compute Root Mean Square of all 8 channel values."""
        return float(np.sqrt(np.mean(self.signals ** 2)))

    def _compute_snr_db(self) -> float:
        """
        Estimate SNR in dB.

        SNR = 20 * log10(RMS_signal / noise_floor)

        The noise floor is NOISE_FLOOR_ASSUMED (2 µV) — a conservative
        estimate for the MYO bracelet's typical electronic noise.
        Clamped to 0 dB when signal is at or below the noise level.
        """
        if self._rms <= self.NOISE_FLOOR_ASSUMED:
            return 0.0
        return float(20 * np.log10(self._rms / self.NOISE_FLOOR_ASSUMED))

    def _detect_activity(self) -> bool:
        """
        Returns True when RMS exceeds ACTIVITY_THRESHOLD (8 µV).

        Muscle activity in MYO bracelet data is reliably above ~5–10 µV.
        Rows below this are treated as electronic noise / rest artefacts.
        """
        return self._rms >= self.ACTIVITY_THRESHOLD

    def _dominant_channels(self) -> list[int]:
        """Return 1-based indices of the 2 channels with the highest absolute amplitude."""
        abs_vals = np.abs(self.signals)
        top2 = np.argsort(abs_vals)[-2:][::-1]
        return [int(i + 1) for i in top2]
