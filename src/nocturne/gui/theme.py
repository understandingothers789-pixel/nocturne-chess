"""A restrained native studio palette and shared spacing."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
BOARD_THEMES = {
    "Forest": ("#d6dfc4", "#648274"),
    "Walnut": ("#e7d6b8", "#967356"),
    "Slate": ("#d3dce2", "#6c8191"),
    "Midnight": ("#98aaa1", "#3c5b50"),
}


def stylesheet(light: bool = False) -> str:
    bg, panel, raised, text, muted, border = (
        ("#e8ece6", "#f6f7f2", "#e0e7dd", "#21372c", "#637469", "#ccd6c8") if light else
        ("#101714", "#18221d", "#202e26", "#eef2e7", "#92a397", "#2a3930")
    )
    accent = "#507a3f" if light else "#a9cc94"
    return f"""
    QWidget {{ background: transparent; color: {text}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {bg}; }}
    QFrame#panel, QFrame#playerCard {{ background: {panel}; border: 1px solid {border}; border-radius: 14px; }}
    QFrame#sidebar {{ background: {panel}; border-right: 1px solid {border}; }}
    QLabel#brand {{ font-size: 21px; font-weight: 700; letter-spacing: 2px; }}
    QLabel#title {{ font-size: 28px; font-weight: 600; }}
    QLabel#subtitle, QLabel#muted {{ color: {muted}; }}
    QLabel#eyebrow {{ color: {muted}; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }}
    QLabel#score {{ font-size: 30px; font-weight: 600; }}
    QLabel#clock {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 28px; font-weight: 600; }}
    QLabel#activeClock {{ background: #b5d99d; color: #17241b; border-radius: 8px; padding: 5px 12px;
        font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 28px; font-weight: 600; }}
    QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 8px; padding: 9px 14px; font-weight: 500; }}
    QPushButton:hover {{ border-color: #76956c; background: #334b39; color: #f3f7ed; }}
    QPushButton:pressed {{ background: #46613e; }}
    QPushButton:disabled {{ color: {muted}; background: transparent; border-color: {border}; }}
    QPushButton#primary {{ background: #b5d99d; color: #19291c; border: none; font-weight: 700; }}
    QPushButton#primary:hover {{ background: #c6e9af; }}
    QPushButton#nav {{ text-align: left; border: none; background: transparent; padding: 12px 16px; color: {muted}; }}
    QPushButton#nav:checked {{ background: #2b4231; color: #c8e6b4; }}
    QPushButton#quiet {{ background: transparent; color: {muted}; border: none; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {{ background: {raised}; border: 1px solid {border}; border-radius: 7px; padding: 8px; selection-background-color: #547348; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {panel}; selection-background-color: #395039; padding: 5px; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; color: {muted}; padding: 11px 17px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
    QTableWidget, QListWidget {{ background: transparent; border: none; gridline-color: {border}; outline: none; }}
    QTableWidget::item, QListWidget::item {{ padding: 8px; border-radius: 5px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{ background: #344b35; color: #d7ecc6; }}
    QHeaderView::section {{ background: {panel}; color: {muted}; border: none; padding: 7px; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #405546; border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QCheckBox {{ spacing: 9px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #667f65; background: {raised}; }}
    QCheckBox::indicator:checked {{ background: #a7ca91; }}
    QMenuBar {{ background: {panel}; color: {text}; padding: 3px; }}
    QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
    QMenuBar::item:selected {{ background: {raised}; }}
    QMenu {{ background: {panel}; border: 1px solid {border}; padding: 5px; }}
    QMenu::item {{ padding: 8px 24px; }}
    QMenu::item:selected {{ background: #344b35; color: #eef2e7; border-radius: 4px; }}
    QStatusBar {{ color: {muted}; font-size: 11px; }}
    QSplitter::handle {{ background: transparent; width: 12px; }}
    """
