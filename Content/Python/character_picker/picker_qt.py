"""The picker window (PySide6).

Header: rig dropdown, Refresh / All / None. Below it, a canvas of
color-matched buttons placed from the auto-generated layout; buttons
reposition on resize. Click selects a control, Shift+click adds to the
selection. Hover shows the control name.
"""

import unreal
from PySide6 import QtCore, QtGui, QtWidgets

from character_picker import layout, rig_discovery, selection

WINDOW_OBJECT_NAME = "CharacterPickerWindow"
BUTTON_SIZE = 16
CANVAS_MARGIN = 18

_window = None  # keep a Python ref so the window isn't garbage collected


def _qcolor(linear_color):
    def to8(v):
        return max(0, min(255, int(round(float(v) ** (1.0 / 2.2) * 255))))
    return QtGui.QColor(to8(linear_color.r), to8(linear_color.g), to8(linear_color.b))


class PickerCanvas(QtWidgets.QWidget):
    """Absolutely-positioned control buttons, rescaled on resize."""

    picked = QtCore.Signal(object)  # unreal.RigElementKey

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = []  # (norm_x, norm_y, QPushButton)
        self.setMinimumSize(220, 260)

    def set_buttons(self, infos):
        for _, _, btn in self._buttons:
            btn.deleteLater()
        self._buttons = []
        for info in infos:
            btn = QtWidgets.QPushButton("", self)
            size = max(10, int(BUTTON_SIZE * info.scale))
            if info.shape == "square":
                # Wider rectangle, sharp corners — reads like a spine block.
                btn.setFixedSize(int(size * 1.6), size)
                radius = 2
            else:
                btn.setFixedSize(size, size)
                radius = size // 2
            btn.setToolTip(info.name)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            color = _qcolor(info.color)
            btn.setStyleSheet(
                "QPushButton {{background-color: {0}; border: 1px solid #1a1a1a;"
                " border-radius: {1}px;}}"
                "QPushButton:hover {{border: 2px solid #ffffff;}}"
                "QPushButton:pressed {{background-color: #ffffff;}}"
                .format(color.name(), radius)
            )
            btn.clicked.connect(lambda _=False, key=info.key: self.picked.emit(key))
            btn.show()
            self._buttons.append((info.x, info.y, btn))
        self._reposition()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self):
        w = max(1, self.width() - 2 * CANVAS_MARGIN)
        h = max(1, self.height() - 2 * CANVAS_MARGIN)
        for nx, ny, btn in self._buttons:
            x = CANVAS_MARGIN + int(nx * w) - btn.width() // 2
            y = CANVAS_MARGIN + int(ny * h) - btn.height() // 2
            btn.move(x, y)


class PickerWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Character Picker")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.resize(420, 680)
        self.setStyleSheet(
            "QWidget {background-color: #2b2b2b; color: #cccccc; font-size: 11px;}"
            "QComboBox, QPushButton {background-color: #3c3c3c; border: 1px solid #555;"
            " border-radius: 3px; padding: 3px 8px;}"
            "QPushButton:hover {border-color: #888;}"
        )

        self._entries = []
        self._entry = None
        self._buttons = []

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        self.combo = QtWidgets.QComboBox()
        self.combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
        header.addWidget(self.combo, 1)
        for label, slot in (("Refresh", self._on_refresh),
                            ("All", self._on_select_all),
                            ("None", self._on_clear)):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(slot)
            header.addWidget(btn)
        root.addLayout(header)

        self.canvas = PickerCanvas()
        self.canvas.picked.connect(self._on_pick)
        root.addWidget(self.canvas, 1)

        footer = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("")
        footer.addWidget(self.status, 1)
        hint = QtWidgets.QLabel("Shift+click: add to selection")
        hint.setStyleSheet("color: #777;")
        footer.addWidget(hint)
        root.addLayout(footer)

        self.combo.currentIndexChanged.connect(self._on_rig_changed)
        self.refresh_rigs()

    # ------------------------------------------------------------------ data

    def refresh_rigs(self):
        previous = self._entry.label if self._entry else None
        self._entries = [e for e in rig_discovery.find_all_rigs() if e.is_valid()]

        self.combo.blockSignals(True)
        self.combo.clear()
        for entry in self._entries:
            self.combo.addItem(entry.label)
        self.combo.blockSignals(False)

        if not self._entries:
            self._entry = None
            self.canvas.set_buttons([])
            self._set_status("No Control Rigs found in this project")
            return

        # Prefer a live [Sequencer] rig: that's the one whose selection shows
        # in the viewport. Fall back to whatever was selected before.
        index = 0
        previous_was_live = previous is not None and previous.startswith("[Sequencer]")
        has_live = self._entries[0].source == rig_discovery.RigEntry.SOURCE_SEQUENCER
        if previous and (previous_was_live or not has_live):
            for i, entry in enumerate(self._entries):
                if entry.label == previous:
                    index = i
                    break
        self.combo.setCurrentIndex(index)
        self._load_entry(self._entries[index])

    def _load_entry(self, entry):
        self._entry = entry
        hierarchy = entry.get_hierarchy()
        if hierarchy is None:
            self._buttons = []
            self.canvas.set_buttons([])
            self._set_status(f"No hierarchy on {entry.label}")
            return
        self._buttons = layout.build_layout(hierarchy)
        self.canvas.set_buttons(self._buttons)
        self._set_status(f"{len(self._buttons)} controls — {entry.label}")

    def _set_status(self, text):
        self.status.setText(text)
        unreal.log(f"[CharacterPicker] {text}")

    # ------------------------------------------------------------- callbacks

    def _additive(self):
        mods = QtWidgets.QApplication.keyboardModifiers()
        return bool(mods & QtCore.Qt.ShiftModifier)

    def _on_pick(self, key):
        if self._entry:
            selection.select_control(self._entry, key, add=self._additive())

    def _on_rig_changed(self, index):
        if 0 <= index < len(self._entries):
            self._load_entry(self._entries[index])

    def _on_refresh(self):
        self.refresh_rigs()

    def _on_select_all(self):
        if self._entry:
            keys = [b.key for b in self._buttons]
            selection.select_controls(self._entry, keys, add=self._additive())

    def _on_clear(self):
        if self._entry:
            selection.clear_selection(self._entry)


def open_picker():
    """Open (or reopen) the picker window."""
    from character_picker import qt_app

    global _window
    qt_app.get_app()

    # Close any previous instance, including ones orphaned by module reloads.
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    _window = PickerWindow()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window
