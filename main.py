import tkinter as tk
import logging
from tkinter import messagebox

from src.logger import setup_logger
from src.GUI import GUI

def main():
    setup_logger()
    logging.info("Application is starting...")

    gui = GUI()
    gui.mainloop()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical(f"Critical error: {e}", exc_info=True)

        try:
            """
            In situation when have a critical error or problem with the GUI.
            """
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                title="Critical Error",
                message=f"An unexpected error occurred:\n\n{e}\n\nCheck logs for details."
            )
            root.destroy()
        except Exception:
            pass

    logging.info("Application is closing.")
