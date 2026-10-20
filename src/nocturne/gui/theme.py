"""A restrained native studio palette and shared spacing."""

from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QMenu, QProxyStyle, QStyle

ASSETS = Path(__file__).resolve().parent.parent / "assets"
BOARD_THEMES = {
    "Classic": ("#f0d9b5", "#b58863"),
    "Grey": ("#dedede", "#929292"),
    "Forest": ("#d6dfc4", "#648274"),
    "Walnut": ("#e7d6b8", "#967356"),
    "Slate": ("#d3dce2", "#6c8191"),
    "Midnight": ("#98aaa1", "#3c5b50"),
}

CANDIDATE_MARKERS = ("#65a9ab", "#62a460", "#d3c75d")


class MenuStripeStyle(QProxyStyle):
    """Add quiet alternating row fills to native menus."""

    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.ControlElement.CE_MenuItem and isinstance(widget, QMenu):
            action = widget.actionAt(option.rect.center())
            if action is not None and not action.isSeparator():
                items = [candidate for candidate in widget.actions() if not candidate.isSeparator()]
                if items.index(action) % 2:
                    app = QApplication.instance()
                    light = bool(app.property("nocturneLightAppearance")) if app else False
                    base = widget.palette().color(QPalette.ColorRole.Window)
                    stripe = base.darker(104) if light else base.lighter(118)
                    painter.save()
                    painter.fillRect(option.rect, stripe)
                    painter.restore()
        super().drawControl(element, option, painter, widget)


def install_menu_stripes(app: QApplication) -> None:
    """Install the menu-row style once, before the application stylesheet."""
    if app.property("nocturneMenuStripeStyle"):
        return
    proxy = MenuStripeStyle(app.style())
    proxy.setParent(app)
    app.setStyle(proxy)
    app.setProperty("nocturneMenuStripeStyle", True)


def palette(light: bool = False) -> dict[str, str]:
    if light:
        return dict(bg="#efefed", panel="#fafaf8", raised="#e7e7e4", text="#393c40",
                    muted="#687580", border="#cececa", accent="#486984", hover="#ddddda",
                    pressed="#d0d0cc", selection="#d4dfeb", selected_text="#20344b",
                    primary="#3d4a56", primary_text="#ffffff", primary_hover="#526373",
                    scroll="#a9a9a5", analysis_white="#43484e", analysis_black="#6a5d55",
                    history="#476987", metric="#276e92", metadata="#65696f")
    return dict(bg="#171717", panel="#222222", raised="#2c2c2c", text="#c9cdd2",
                muted="#97a6b2", border="#3c3c3c", accent="#b5c8da", hover="#383838",
                pressed="#444444", selection="#394b5d", selected_text="#d8e3ee",
                primary="#dedbd4", primary_text="#202020", primary_hover="#f0ede7",
                scroll="#575f67", analysis_white="#c9cdd2", analysis_black="#b4a99f",
                history="#a4bace", metric="#78bedb", metadata="#a5a7aa")


def stylesheet(light: bool = False) -> str:
    c = palette(light)
    bg, panel, raised, text, muted, border, accent = (
        c[key] for key in ("bg", "panel", "raised", "text", "muted", "border", "accent"))
    hover, pressed, selection, selected_text, primary, primary_text, primary_hover, scroll = (
        c[key] for key in ("hover", "pressed", "selection", "selected_text", "primary",
                          "primary_text", "primary_hover", "scroll"))
    return f"""
    QWidget {{ background: transparent; color: {text}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {bg}; }}
    QDockWidget {{ font-size: 12px; }}
    QDockWidget::title {{ background: {raised}; color: {muted}; padding: 5px 9px;
        border-bottom: 1px solid {border}; text-align: left; }}
    QMainWindow#dockSurface::separator {{ background: {bg}; width: 7px; height: 7px; }}
    QMainWindow#dockSurface::separator:hover {{ background: {scroll}; }}
    QFrame#panel, QFrame#playerCard {{ background: {panel}; border: 1px solid {border}; border-radius: 14px; }}
    QFrame#clockStrip {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}
    QFrame#sidebar {{ background: {panel}; border-right: 1px solid {border}; }}
    QLabel#brand {{ font-size: 21px; font-weight: 700; letter-spacing: 2px; }}
    QLabel#title {{ font-size: 28px; font-weight: 600; }}
    QLabel#subtitle, QLabel#muted {{ color: {muted}; }}
    QLabel#eyebrow {{ color: {muted}; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }}
    QLabel#score {{ font-size: 30px; font-weight: 600; }}
    QLabel#clock {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 28px; font-weight: 600; }}
    QLabel#analysisClock {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 23px; font-weight: 600; }}
    QLabel#activeClock {{ background: {primary}; color: {primary_text}; border-radius: 8px;
        font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 28px; font-weight: 600; }}
    QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 8px; padding: 9px 14px; font-weight: 500; }}
    QPushButton:hover {{ border-color: {accent}; background: {hover}; color: {text}; }}
    QPushButton:pressed {{ background: {pressed}; }}
    QPushButton:disabled {{ color: {muted}; background: transparent; border-color: {border}; }}
    QToolButton {{ background: {raised}; border: 1px solid {border}; border-radius: 6px; padding: 6px 12px; font-weight: 500; }}
    QToolButton:hover {{ border-color: {accent}; }}
    QPushButton#primary {{ background: {primary}; color: {primary_text}; border: none; font-weight: 700; }}
    QPushButton#primary:hover {{ background: {primary_hover}; }}
    QPushButton#nav {{ text-align: left; border: none; background: transparent; padding: 12px 16px; color: {muted}; }}
    QPushButton#nav:checked {{ background: {selection}; color: {selected_text}; }}
    QPushButton#quiet {{ background: transparent; color: {muted}; border: none; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {{ background: {raised}; border: 1px solid {border}; border-radius: 7px; padding: 8px; selection-background-color: {selection}; selection-color: {selected_text}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {panel}; selection-background-color: {selection}; selection-color: {selected_text}; padding: 5px; }}
    QTabWidget::pane {{ border: none; }}
    QTextBrowser {{ background: transparent; border: none; }}
    QTabBar::tab {{ background: transparent; color: {muted}; padding: 11px 17px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
    QTabBar#studyTabs::tab {{ background: {bg}; }}
    QTableWidget, QListWidget {{ background: transparent; border: none; gridline-color: {border}; outline: none; }}
    QTableWidget::item, QListWidget::item {{ padding: 8px; border-radius: 5px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{ background: {selection}; color: {selected_text}; }}
    QHeaderView::section {{ background: {panel}; color: {muted}; border: none; padding: 7px; }}
    QProgressBar {{ background: {raised}; border: none; border-radius: 5px; text-align: center; color: {text}; min-height: 17px; }}
    QProgressBar::chunk {{ background: {border}; border-radius: 5px; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QCheckBox {{ spacing: 9px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {muted}; background: {raised}; }}
    QCheckBox::indicator:checked {{ background: {accent}; }}
    QMenuBar {{ background: {panel}; color: {text}; padding: 3px; }}
    QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
    QMenuBar::item:selected {{ background: {raised}; }}
    QMenu {{ background: {panel}; border: 1px solid {border}; padding: 5px; }}
    QMenu::item {{ padding: 8px 24px; }}
    QMenu::item:disabled {{ color: {muted}; }}
    QMenu::item:selected {{ background: {selection}; color: {selected_text}; border-radius: 4px; }}
    QStatusBar {{ color: {muted}; font-size: 11px; }}
    QSplitter::handle {{ background: transparent; width: 12px; }}
    """
