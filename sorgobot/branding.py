"""Product identity; internal module names and saved project paths stay stable."""
from pathlib import Path
from PySide6.QtGui import QIcon

NAME = 'StreamerMod'
DESKTOP_ID = 'streamermod'
ICON = Path(__file__).resolve().parent / 'resources/StreamerMod.png'

def configure(app):
    app.setApplicationName(NAME)
    app.setApplicationDisplayName(NAME)
    app.setDesktopFileName(DESKTOP_ID)
    app.setWindowIcon(QIcon(str(ICON)))
