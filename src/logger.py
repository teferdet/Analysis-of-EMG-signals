import logging
import os
from pathlib import Path

def setup_logger():
    app_name = "Analysis of EMG signals"

    local_app_data: str = os.getenv('LOCALAPPDATA')

    # Create the full path: C:\Users\<Username>\AppData\Local\AoEMGS\logs
    log_dir = Path(local_app_data) / app_name / "logs"

    # Create the directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "app.log"

    # Set up the basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            # File handler for saving logs to the system drive
            logging.FileHandler(log_file, encoding='utf-8'),
            # Only for dev in PyCharm
            logging.StreamHandler()
        ]
    )

    logging.info(f"Logging initialized successfully. Log file path: {log_file}")
