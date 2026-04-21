import pandas as pd
import os

# Base information about file
file: dict = {
    "filename": "",
    "path": ""
}

# Theme of system
theme: dict = {
    "accent": "",
    "accent_light": "",
    "accent_dark": "",
    "background_color": "",
    "workspace_color": "",
    "text": ""
}

# Set theme for cache
def set_theme(
    accent: str, accent_light: str, accent_dark: str,
    workspace_color: str, text: str, background_color: str):
    theme.update({
        "accent": accent,
        "accent_light": accent_light,
        "accent_dark": accent_dark,
        "background_color": background_color,
        "workspace_color": workspace_color,
        "text": text
    })

# Update name and path after change direction
def update(path):
    file["filename"] = path.split("/")[-1]
    file["path"] = path

# Open and read files
def read(path: str) -> pd.DataFrame:
    """
    Raises if...
    FileNotFoundError if file does not exist.
    ValueError if file is empty or has no parseable columns.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    if os.path.getsize(path) == 0:
        raise ValueError(f"File is empty: {path}")

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise ValueError(f"File has no columns to parse (empty or malformed CSV): {path}")
    except pd.errors.ParserError as e:
        raise ValueError(f"Failed to parse CSV file '{path}': {e}")

    if df.empty and len(df.columns) == 0:
        raise ValueError(f"No data found in file: {path}")

    return df
