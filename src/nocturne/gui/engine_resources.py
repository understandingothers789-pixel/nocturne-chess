"""Prominent, engine-advertised resource controls shared by menus and toolbar."""

import os

from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget,
)

from ..engine.uci_types import UciOption
from .hardware import hash_budget_mb


def resource_option(profile, name):
    raw = profile.get("options", {}).get(name) if profile else None
    if not isinstance(raw, dict):
        return None
    try:
        option = UciOption(**raw)
        if (
            option.name != name or option.kind != "spin"
            or option.minimum < 1 or option.maximum < option.minimum
        ):
            return None
        option.validate(option.default)
        return option
    except (TypeError, ValueError):
        return None


def resource_limits(option, allocated_mb=0):
    maximum = min(option.maximum, 2147483647)
    if option.name == "Hash" and (budget := hash_budget_mb(allocated_mb)) is not None:
        maximum = min(maximum, budget)
    return option.minimum, maximum


def validate_resource(profile, name, value, allocated_mb=0):
    option = resource_option(profile, name)
    if option is None:
        raise ValueError(f"This engine does not advertise a supported {name} option")
    value = int(option.validate(option.default if value is None else value))
    minimum, maximum = resource_limits(option, allocated_mb)
    if maximum < minimum:
        raise ValueError(f"{name}: the engine minimum ({minimum:,} MB) exceeds the current memory budget")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name}: choose {minimum:,}–{maximum:,}" + (" MB" if name == "Hash" else ""))
    return value


class EngineResources(QWidget):
    def __init__(self, profile, connection, apply, detect, parent=None):
        super().__init__(parent)
        self.profile, self.connection, self.apply = profile, connection, apply
        self.menus, self.buttons = {}, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        for name in ("Threads", "Hash"):
            menu = QMenu(name, self)
            menu.aboutToShow.connect(self.refresh)
            button = QToolButton()
            button.setAccessibleName(f"Engine {name}")
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setMenu(menu)
            button.setMinimumHeight(30)
            row.addWidget(button, 1)
            self.menus[name], self.buttons[name] = menu, button
        layout.addLayout(row)
        self.state = QLabel("Choose an engine to configure Threads and Hash")
        self.state.setObjectName("muted")
        self.state.setWordWrap(True)
        self.state.setAccessibleName("Engine resource settings status")
        layout.addWidget(self.state)
        self.detect = detect

    def allocated_hash(self):
        connection = self.connection()
        return int(connection.confirmed.get("Hash", 0)) if connection and connection.alive else 0

    def refresh(self):
        profile = self.profile()
        connection = self.connection()
        confirmed = connection.confirmed if connection and connection.alive else {}
        same_engine = bool(
            profile and connection and connection.path == os.path.abspath(profile["path"])
        )
        matches, supported = True, 0
        for name, menu in self.menus.items():
            menu.clear()
            option = resource_option(profile, name)
            if option is None:
                text = "Choose an engine first" if not profile else "Not advertised by this engine"
                if profile and not profile.get("options") and not profile.get("options_detected"):
                    text = "Detect engine options first"
                    menu.addAction("Detect engine options…", self.detect)
                menu.addAction(text).setEnabled(False)
                self.buttons[name].setText(f"{name}: —")
                menu.setTitle(name)
                continue
            supported += 1
            unit = " MB" if name == "Hash" else ""
            value = profile["values"].get(name, option.default)
            try:
                value = int(option.validate(value))
            except ValueError:
                value = "invalid"
            current = f"{value:,}" if isinstance(value, int) else value
            self.buttons[name].setText(f"{name}: {current}{unit}")
            menu.setTitle(f"{name} ({current}{unit})")
            matches = matches and same_engine and confirmed.get(name) == str(value)
            minimum, maximum = resource_limits(option, self.allocated_hash())
            presets = (
                (1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128)
                if name == "Threads"
                else (16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536)
            )
            choices = {p for p in presets if option.minimum <= p <= option.maximum}
            if isinstance(value, int):
                choices.add(value)
            for preset in sorted(choices):
                action = menu.addAction(f"{preset:,}{unit}")
                action.setCheckable(True)
                action.setChecked(value == preset and name in profile["values"])
                action.setEnabled(minimum <= preset <= maximum)
                action.setData(preset)
                action.triggered.connect(
                    lambda checked=False, n=name, v=preset, p=profile: self._choose(p, n, v)
                )
            menu.addSeparator()
            custom = menu.addAction("Custom…")
            custom.setEnabled(minimum <= maximum)
            custom.triggered.connect(lambda checked=False, n=name, p=profile: self._custom(p, n))
            default = menu.addAction(f"Engine default ({int(option.default):,}{unit})")
            default.setCheckable(True)
            default.setChecked(name not in profile["values"])
            default.setEnabled(minimum <= int(option.default) <= maximum)
            default.triggered.connect(lambda checked=False, n=name, p=profile: self._choose(p, n, None))
            menu.addSeparator()
            menu.addAction(
                f"Engine range: {option.minimum:,}–{option.maximum:,}{unit}"
            ).setEnabled(False)
            if maximum < option.maximum and name == "Hash":
                menu.addAction(f"Current memory limit: {maximum:,} MB").setEnabled(False)
        self.state.setText(
            "Choose an engine to configure Threads and Hash" if not profile
            else "Resource options unavailable" if not supported
            else "Applied to engine" if matches
            else "Saved · applies before the next search"
        )

    def _choose(self, profile, name, value):
        if self.profile() is profile:
            self.apply(name, value)

    def _custom(self, profile, name):
        option = resource_option(profile, name)
        if option is None:
            return
        minimum, maximum = resource_limits(option, self.allocated_hash())
        if maximum < minimum:
            return
        try:
            value = int(option.validate(profile["values"].get(name, option.default)))
        except ValueError:
            value = minimum
        number, accepted = QInputDialog.getInt(
            self, f"Engine {name}",
            "Hash size in MB:" if name == "Hash" else "Search threads:",
            min(maximum, max(minimum, value)), minimum, maximum, 1,
        )
        if accepted:
            self._choose(profile, name, number)
