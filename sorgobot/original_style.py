"""Native widget styling based on the current official Streamer.bot desktop view."""
STYLE = '''
QWidget { background:#231f20; color:#eceeee; font-family:"Noto Sans"; font-size:12px; }
QMainWindow, QDialog { background:#231f20; }
QWidget#toolbar { border-bottom:1px solid #343636; }
QWidget#sidebar { background:#231f20; border-right:1px solid #393435; }
QWidget#brand, QWidget#brand QLabel { background:transparent; }
QLabel#brandName { font-size:20px; font-weight:600; }
QWidget#content { background:#292526; }
QLabel#pageTitle { font-size:21px; font-weight:600; padding:0px; }
QFrame#card { background:#342f30; border-radius:5px; }
QFrame#card QLabel { background:transparent; }
QLabel#sectionTitle { font-size:11px; font-weight:600; }
QLineEdit, QComboBox, QPlainTextEdit { background:#3c3738; border:1px solid #414444; border-radius:3px; padding:5px; selection-background-color:#42494d; }
QLineEdit:focus, QComboBox:focus { border:1px solid #737b80; }
QTreeWidget, QTableWidget { background:#342f30; border:1px solid #6e7272; border-radius:2px; outline:0; }
QTreeWidget::item { min-height:22px; padding:1px 3px; }
QTreeWidget::item:selected { background:#4a4148; color:white; }
QTreeWidget::item:hover { background:#383d3f; }
QHeaderView::section { background:#342f30; border:0; padding:5px 6px; font-size:11px; font-weight:600; }
QPushButton, QToolButton { background:#373133; border:1px solid #424646; border-radius:3px; padding:5px 10px; }
QPushButton:hover, QToolButton:hover { background:#404646; }
QPushButton:disabled, QToolButton:disabled { color:#717777; }
QToolButton#tool { background:transparent; border:0; border-radius:0; padding:7px 10px; }
QToolButton#tool:hover { background:#3e373b; }
QTreeWidget#navigation { background:#231f20; border:0; }
QTreeWidget#navigation::item { min-height:33px; padding:3px 7px; }
QTreeWidget#navigation::item:selected { background:#373133; border:0; border-left:3px solid #b967cd; border-radius:3px; }
QToolButton#sidebarSettings { text-align:left; border:0; border-top:1px solid #393435; padding:10px; background:transparent; }
QToolButton#sidebarSettings:checked { background:#373133; border-left:3px solid #b967cd; }
QTreeWidget#navigation::item:disabled { color:#727979; }
QSplitter::handle { background:#292526; }
QSplitter::handle:horizontal { width:8px; }
QSplitter::handle:vertical { height:8px; }
QMenu { background:#252929; border:1px solid #565d5d; padding:4px; }
QMenu::item { padding:5px 24px 5px 12px; }
QMenu::item:selected { background:#444c50; }
QMenu::item:disabled { color:#778080; }
QStatusBar { background:#231f20; color:#bcc3c3; font-size:11px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#292d2d; padding:7px 12px; }
QTabBar::tab:selected { background:#42494b; }
QTabBar::tab:disabled { color:#717777; }
QScrollBar:vertical { background:#252828; width:10px; }
QScrollBar::handle:vertical { background:#555e5e; min-height:25px; }
QScrollBar:horizontal { background:#252828; height:10px; }
QScrollBar::handle:horizontal { background:#555e5e; min-width:25px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QDialog { background:#20252b; }
QCheckBox { spacing:6px; background:transparent; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #7b8387; border-radius:3px; background:#333b40; }
QCheckBox::indicator:checked { background:#497fc1; }
'''


def set_palette(app):
    from PySide6.QtGui import QPalette,QColor
    palette=QPalette()
    for role,color in [(QPalette.ColorRole.Window,'#231f20'),(QPalette.ColorRole.WindowText,'#eceeee'),(QPalette.ColorRole.Base,'#342f30'),(QPalette.ColorRole.AlternateBase,'#3c3738'),(QPalette.ColorRole.Text,'#eceeee'),(QPalette.ColorRole.Button,'#373133'),(QPalette.ColorRole.ButtonText,'#eceeee'),(QPalette.ColorRole.Highlight,'#4a4148'),(QPalette.ColorRole.HighlightedText,'#ffffff')]:palette.setColor(role,QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.Text,QColor('#717777'))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText,QColor('#717777'))
    app.setPalette(palette)
