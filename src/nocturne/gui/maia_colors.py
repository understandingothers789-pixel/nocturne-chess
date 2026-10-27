"""Shared move colors for Maia's rating curves and board markers."""
from PySide6.QtWidgets import QApplication

COLORS = ("#8ed5ef", "#d6b46d", "#91c6a4", "#c2a7eb", "#e3a394")
LIGHT_COLORS = ("#197b9c", "#a16c22", "#377e56", "#7b50a8", "#b95844")


def curve_colors(light=None):
    if light is None:
        light = bool(QApplication.instance().property("nocturneLightAppearance"))
    return LIGHT_COLORS if light else COLORS
