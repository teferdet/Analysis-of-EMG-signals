import logging
from src.storage import read


class TableManager:
    """
    Table Manager use for check tables and for 'first look' for user.
    """

    # Standard table format for check user's table
    TABLE_FORMAT = {
        "time":     ("i", False),
        "channel1": ("f", False),
        "channel2": ("f", False),
        "channel3": ("f", False),
        "channel4": ("f", False),
        "channel5": ("f", False),
        "channel6": ("f", False),
        "channel7": ("f", False),
        "channel8": ("f", False),
        "class":    ("i", False),
        "label":    ("i", False),
    }

    def __init__(self, path: str):
        self.path = path
        try:
            self.df = read(path)
            self._original_df = self.df.copy()
        except (FileNotFoundError, ValueError) as e:
            raise ValueError(f"Cannot load table: {e}") from e

    def check_table(self) -> bool:
        """
        Validate that the loaded DataFrame matches the expected schema.
        Returns True if the table is valid, False otherwise.
        """

        missing = [col for col in self.TABLE_FORMAT if col not in self.df.columns]
        if missing:
            logging.warning(f"[check_table] Missing columns: {missing}")
            return False

        extra = [col for col in self.df.columns if col not in self.TABLE_FORMAT]
        if extra:
            logging.warning(f"[check_table] Unexpected columns: {extra}")
            return False

        for col, (kind, nullable) in self.TABLE_FORMAT.items():
            series = self.df[col]

            if not nullable and series.isnull().any():
                logging.warning(f"[check_table] Column '{col}' contains null values.")
                return False

            if series.dtype.kind != kind:
                expected = "float" if kind == "f" else "integer"
                logging.warning(
                    f"[check_table] Column '{col}' has dtype '{series.dtype}', "
                    f"expected {expected}."
                )
                return False

        return True

    def info(self) -> str:
        """Return a human-readable summary of the table"""

        rows = len(self.df)
        cols = len(self.df.columns)
        elements = self.df.size
        channels = [c for c in self.df.columns if c.startswith("channel")]
        classes = sorted(self.df["class"].unique().tolist()) if "class" in self.df.columns else []
        labels = sorted(self.df["label"].unique().tolist()) if "label" in self.df.columns else []

        return (
            f"Rows: {rows}\n"
            f"Columns: {cols}\n"
            f"Elements: {elements}\n"
            f"Channels: {len(channels)}\n"
            f"Classes: {classes}\n"
            f"Labels: {labels}"
        )
