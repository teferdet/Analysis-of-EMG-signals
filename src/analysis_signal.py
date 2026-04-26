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

        # Derived fields
        self._gesture  = self.GESTURE_MAP.get(self.class_id, self.GESTURE_MAP[0])
        self._rms      = self._compute_rms()
        self._dominant = self._dominant_channels()

    # ------------------------------------------------------------------ #
    #  Public properties                                                   #
    # ------------------------------------------------------------------ #

    @property
    def gesture_name(self) -> str:
        return self._gesture[0]

    @property
    def is_active(self) -> bool:
        """True if the hand is performing an active gesture."""
        return self._gesture[1]

    @property
    def status(self) -> str:
        return "Active" if self.is_active else "Passive"

    @property
    def load_level(self) -> str:
        return self.LOAD_LABELS[self._gesture[2]]

    @property
    def load_index(self) -> int:
        """Raw load index 0-3."""
        return self._gesture[2]

    @property
    def body_part(self) -> str:
        """Always forearm / hand for MYO bracelet data."""
        return "Forearm / Hand"

    @property
    def rms(self) -> float:
        """Root Mean Square amplitude across all 8 channels."""
        return self._rms

    @property
    def dominant_channels(self) -> list[int]:
        """1-based indices of the two most active channels."""
        return self._dominant

    @property
    def signal_quality(self) -> str:
        """Qualitative signal quality based on RMS magnitude."""
        if self._rms == 0:
            return "No signal"
        if self._rms < 1e-5:
            return "Weak"
        if self._rms < 5e-5:
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

        return (
            f"{'─' * 44}\n"
            f"  EMG Signal Analysis  |  Time: {self.time} ms\n"
            f"{'─' * 44}\n"
            f"  Gesture          : {self.gesture_name}\n"
            f"  Status           : {self.status}\n"
            f"  Load level       : {self.load_level}\n"
            f"  Body part        : {self.body_part}\n"
            f"  Recording series : {self.series_label}\n"
            f"{'─' * 44}\n"
            f"  RMS amplitude    : {self._rms:.3e} V\n"
            f"  Signal quality   : {self.signal_quality}\n"
            f"  Dominant channels: {dominant_str}\n"
            f"{'─' * 44}\n"
            f"  Channel values:\n"
            f"{channel_lines}\n"
            f"{'─' * 44}\n"
            f"  Description: {self._gesture[3]}\n"
            f"{'─' * 44}"
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
            "signal_quality": self.signal_quality,
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
            labels      - list of channel names ['channel1', ..., 'channel8']
            values      - raw signed amplitudes (float list)
            abs_values  - absolute amplitudes for bar chart y-axis
            rms         - scalar RMS value
            gesture     - gesture name string
            is_active   - bool
            load_index  - int 0-3
            class_id    - raw class integer
        """
        abs_vals = np.abs(self.signals).tolist()
        return {
            "labels": self.CHANNEL_COLS,
            "values": self.signals.tolist(),
            "abs_values": abs_vals,
            "rms": self._rms,
            "gesture": self.gesture_name,
            "is_active": self.is_active,
            "load_index": self.load_index,
            "class_id": self.class_id,
        }

    # ------------------------------------------------------------------ #
    #  Static: summarize full DataFrame                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def summarize_dataset(df: pd.DataFrame) -> str:
        """
        Return a statistical summary of the full dataset.
        Shows gesture distribution, active/passive ratio, and per-channel RMS.

        Parameters
        ----------
        df : full EMG DataFrame

        Example
        -------
            print(AnalysisSignal.summarize_dataset(tm.df))
        """
        total       = len(df)
        gesture_map = AnalysisSignal.GESTURE_MAP

        lines = [
            f"{'=' * 52}",
            f"  Dataset Summary  ({total} rows)",
            f"{'=' * 52}",
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
        n_active = df[df["class"].isin(active_ids)].shape[0]
        n_passive = total - n_active
        lines += [
            f"{'─' * 52}",
            f"  Active samples  : {n_active:>8} ({n_active / total * 100:.1f}%)",
            f"  Passive samples : {n_passive:>8} ({n_passive / total * 100:.1f}%)",
            f"{'─' * 52}",
            "  Per-channel RMS (mean across dataset):",
        ]

        for ch in AnalysisSignal.CHANNEL_COLS:
            rms_val = np.sqrt((df[ch] ** 2).mean())
            lines.append(f"    {ch}: {rms_val:.3e} V")

        lines.append(f"{'=' * 52}")
        return "\n".join(lines)

    def _compute_rms(self) -> float:
        """Compute Root Mean Square of all 8 channel values."""
        return float(np.sqrt(np.mean(self.signals ** 2)))

    def _dominant_channels(self) -> list[int]:
        """Return 1-based indices of the 2 channels with the highest absolute amplitude."""
        abs_vals = np.abs(self.signals)
        top2 = np.argsort(abs_vals)[-2:][::-1]
        return [int(i + 1) for i in top2]
