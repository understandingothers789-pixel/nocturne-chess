"""Accumulate wheel/trackpad deltas into deliberate single-ply steps."""

from PySide6.QtCore import Qt


class WheelSteps:
    def __init__(self):
        self.remainder = 0
        self.source = None

    def reset(self):
        self.remainder = 0
        self.source = None

    def consume(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.reset()
            return None
        pixels = event.pixelDelta().y()
        delta, threshold, source = (pixels, 40, "pixel") if pixels else (event.angleDelta().y(), 120, "angle")
        if not delta:
            return None
        if source != self.source or delta * self.remainder < 0:
            self.remainder = 0
        self.source = source
        self.remainder += delta
        steps = int(self.remainder / threshold)
        self.remainder -= steps * threshold
        return -steps  # Up: previous; down: next. Qt applies natural-scroll settings.
