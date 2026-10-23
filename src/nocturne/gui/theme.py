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
        return dict(bg="#edf1f5", panel="#ffffff", raised="#e7edf3", text="#253447",
                    muted="#63758a", border="#d4dee8", accent="#287d70", hover="#dde8ed",
                    pressed="#d0dfe6", selection="#d9e9ec", selected_text="#173d43",
                    primary="#237b6d", primary_text="#ffffff", primary_hover="#2e8d7c",
                    scroll="#9bacbb", analysis_white="#27394a", analysis_black="#77634f",
                    history="#426581", metric="#176c8a", metadata="#667689",
                    maia="#7251a3", maia_soft="#f0eaf8", soft="#f5f8fb", card="#f8fafc",
                    maia_fill="#d8c9ed", quality_fill="#bfdfd5")
    return dict(bg="#10161e", panel="#171f2a", raised="#222e3c", text="#dce5ef",
                muted="#94a6b9", border="#2a394a", accent="#88cfc0", hover="#2a3a4a",
                pressed="#34495a", selection="#2b4554", selected_text="#e7f7f3",
                primary="#8bd2c0", primary_text="#112d29", primary_hover="#a0e1d1",
                scroll="#50667b", analysis_white="#dce5ef", analysis_black="#bba991",
                history="#b2c6da", metric="#8ed5ef", metadata="#93a6ba",
                maia="#c2a7eb", maia_soft="#2b263e", soft="#1b2633", card="#1b2532",
                maia_fill="#654b8b", quality_fill="#285e58")


def stylesheet(light: bool = False) -> str:
    c = palette(light)
    bg, panel, raised, text, muted, border, accent = (
        c[key] for key in ("bg", "panel", "raised", "text", "muted", "border", "accent"))
    hover, pressed, selection, selected_text, primary, primary_text, primary_hover, scroll = (
        c[key] for key in ("hover", "pressed", "selection", "selected_text", "primary",
                          "primary_text", "primary_hover", "scroll"))
    check_icon = (ASSETS / ("check-light.svg" if light else "check-dark.svg")).as_posix()
    return f"""
    QWidget {{ background: transparent; color: {text}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {bg}; }}
    QDockWidget {{ font-size: 12px; }}
    QDockWidget::title {{ background: {raised}; color: {muted}; padding: 5px 9px;
        border-bottom: 1px solid {border}; text-align: left; }}
    QMainWindow#dockSurface::separator {{ background: {bg}; width: 7px; height: 7px; }}
    QMainWindow#dockSurface::separator:hover {{ background: {scroll}; }}
    QFrame#panel, QFrame#playerCard {{ background: {panel}; border: 1px solid {border}; border-radius: 12px; }}
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
    QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 8px; padding: 8px 12px; font-weight: 500; }}
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
    QTabBar#studyTabs::tab {{ background: {bg}; margin-right: 4px; border-top-left-radius: 8px;
        border-top-right-radius: 8px; padding: 10px 14px; }}
    QTabBar#studyTabs::tab:selected {{ background: {panel}; color: {text}; border-bottom-color: {accent}; }}
    QTabBar#studyTabs::tab:!selected:hover {{ background: {raised}; }}
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
    QCheckBox::indicator:checked {{ background: {accent}; image: url("{check_icon}"); }}
    QMenuBar {{ background: {panel}; color: {text}; padding: 3px; }}
    QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
    QMenuBar::item:selected {{ background: {raised}; }}
    QMenu {{ background: {panel}; border: 1px solid {border}; padding: 5px; }}
    QMenu::item {{ padding: 8px 24px; }}
    QMenu::item:disabled {{ color: {muted}; }}
    QMenu::item:selected {{ background: {selection}; color: {selected_text}; border-radius: 4px; }}
    QStatusBar {{ color: {muted}; font-size: 11px; }}
    QSplitter::handle {{ background: transparent; width: 10px; }}
    QSplitter::handle:hover {{ background: {border}; }}
    QToolTip {{ background: {raised}; color: {text}; border: 1px solid {border}; padding: 6px 8px; }}
    QFrame#insightCard {{ background: {c['card']}; border: 1px solid {border}; border-radius: 10px; }}
    QLabel#sectionNumber {{ color: {c['maia']}; background: {c['maia_soft']}; border-radius: 5px;
        font-size: 10px; font-weight: 700; padding: 3px 5px; }}
    QLabel#sectionTitle {{ color: {text}; font-size: 13px; font-weight: 600; }}
    QLabel#sectionNote {{ color: {muted}; font-size: 11px; }}
    QLabel#maiaHeading {{ color: {c['maia']}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; }}
    QLabel#engineEval {{ background: {c['soft']}; color: {c['metric']}; padding: 5px 9px;
        border: 1px solid {border}; border-radius: 7px; font-size: 22px; font-weight: 600; }}
    QLabel#telemetryStrip {{ background: {c['soft']}; border-radius: 6px; padding: 6px 7px; }}
    QLabel#gameLineHeading {{ color: {muted}; padding-top: 10px; padding-bottom: 4px;
        font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
    QWidget#candidateRow {{ border-radius: 4px; }}
    QWidget#candidateRow[alternate="true"] {{ background: {c['soft']}; }}
    QWidget#analysisTools QPushButton {{ padding: 6px 9px; font-size: 12px; }}
    QWidget#analysisTools QComboBox {{ padding: 5px 7px; font-size: 12px; min-width: 62px; }}
    QWidget#analysisTools QCheckBox {{ spacing: 6px; font-size: 12px; }}
    QComboBox#blendChoice {{ padding: 5px 7px; }}
    QProgressBar#humanMeter::chunk {{ background: {c['maia_fill']}; }}
    QProgressBar#qualityMeter::chunk {{ background: {c['quality_fill']}; }}
    QLabel#blendResult {{ color: {c['maia']}; font-size: 22px; font-weight: 600; }}
    QToolButton#curveLegend {{ padding: 3px 6px; border-radius: 5px; background: transparent; }}
    QToolButton#curveLegend:checked {{ background: {raised}; border-color: {border}; }}
    QToolButton#curveLegend:!checked {{ color: {muted}; border-color: transparent; }}
    QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {raised}; }}
    QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; border: 2px solid {panel};
        border-radius: 7px; background: {accent}; }}
    """
