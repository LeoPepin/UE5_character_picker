"""The picker window (PySide6).

Header: rig dropdown, Refresh / All / None. Below it, a canvas of
color-matched buttons placed from the auto-generated layout; buttons
reposition on resize. Click selects a control, Shift+click adds to the
selection. Hover shows the control name.
"""

import os

import unreal
from PySide6 import QtCore, QtGui, QtWidgets

from character_picker import layout, layout_store, rig_discovery, selection

WINDOW_OBJECT_NAME = "CharacterPickerWindow"
BUTTON_SIZE = 16
CANVAS_MARGIN = 18

_window = None  # keep a Python ref so the window isn't garbage collected


def _qcolor(linear_color):
    def to8(v):
        return max(0, min(255, int(round(float(v) ** (1.0 / 2.2) * 255))))
    return QtGui.QColor(to8(linear_color.r), to8(linear_color.g), to8(linear_color.b))


class PickerCanvas(QtWidgets.QWidget):
    """Absolutely-positioned control buttons, rescaled on resize.

    In edit mode (dwpicker-style), buttons are dragged into place instead of
    selecting; the new normalized position is written back into the
    PickerButton info so the window can save it.
    """

    picked = QtCore.Signal(object)        # unreal.RigElementKey
    picked_many = QtCore.Signal(list)     # [RigElementKey] from a lasso (may be empty)
    layout_edited = QtCore.Signal()       # a button was moved

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = []  # (PickerButton info, QPushButton)
        self._edit_mode = False
        # Drag of one or more buttons in edit mode:
        # (press_global_pos, [(btn, info, start_pos), ...])
        self._drag = None
        # Lasso (rubber band) on the empty canvas, both modes:
        self._rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._marquee_origin = None
        self._group = set()  # QPushButtons grouped for a multi-move (edit mode)
        self.setMinimumSize(220, 260)

    def set_edit_mode(self, enabled):
        self._edit_mode = bool(enabled)
        if not self._edit_mode:
            self._set_group([])
        cursor = QtCore.Qt.OpenHandCursor if self._edit_mode else QtCore.Qt.PointingHandCursor
        for _, btn in self._buttons:
            btn.setCursor(cursor)

    def set_buttons(self, infos):
        for _, btn in self._buttons:
            btn.deleteLater()
        self._buttons = []
        for info in infos:
            btn = QtWidgets.QPushButton(getattr(info, "label", ""), self)
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
            # Black on light controls, white on dark ones.
            luminance = 0.299 * color.red() + 0.587 * color.green() \
                + 0.114 * color.blue()
            text_color = "#000000" if luminance > 140 else "#ffffff"
            base_style = (
                "QPushButton {{background-color: {0}; border: 1px solid #1a1a1a;"
                " border-radius: {1}px; color: {2}; font-size: 8px;"
                " font-weight: bold; padding: 0;}}"
                "QPushButton:hover {{border: 2px solid #ffffff;}}"
                "QPushButton:pressed {{background-color: #ffffff;}}"
                .format(color.name(), radius, text_color)
            )
            btn.setStyleSheet(base_style)
            btn._base_style = base_style
            btn.clicked.connect(lambda _=False, key=info.key: self.picked.emit(key))
            btn.installEventFilter(self)
            btn.show()
            self._buttons.append((info, btn))
        self._group = set()
        self.set_edit_mode(self._edit_mode)
        self._reposition()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _inner_rect(self):
        w = max(1, self.width() - 2 * CANVAS_MARGIN)
        h = max(1, self.height() - 2 * CANVAS_MARGIN)
        return w, h

    def _reposition(self):
        w, h = self._inner_rect()
        for info, btn in self._buttons:
            x = CANVAS_MARGIN + int(info.x * w) - btn.width() // 2
            y = CANVAS_MARGIN + int(info.y * h) - btn.height() // 2
            btn.move(x, y)

    # ------------------------------------------------- lasso (rubber band)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._marquee_origin = event.pos()
            self._rubber.setGeometry(QtCore.QRect(self._marquee_origin, QtCore.QSize()))
            self._rubber.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._marquee_origin is not None:
            self._rubber.setGeometry(
                QtCore.QRect(self._marquee_origin, event.pos()).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._marquee_origin is None:
            super().mouseReleaseEvent(event)
            return
        rect = QtCore.QRect(self._marquee_origin, event.pos()).normalized()
        self._marquee_origin = None
        self._rubber.hide()

        hits = [(info, btn) for info, btn in self._buttons
                if rect.intersects(btn.geometry())]
        if self._edit_mode:
            self._set_group([btn for _, btn in hits])
        else:
            # Empty lasso (a click in the void) emits [] so the window can
            # clear the selection, like dwpicker.
            self.picked_many.emit([info.key for info, _ in hits])
        super().mouseReleaseEvent(event)

    def _set_group(self, buttons):
        self._group = set(buttons)
        for _, btn in self._buttons:
            style = getattr(btn, "_base_style", "")
            if btn in self._group:
                style += "QPushButton {border: 2px dashed #ffffff;}"
            btn.setStyleSheet(style)

    # ------------------------------------------------------------- edit mode

    def eventFilter(self, obj, event):
        if not self._edit_mode or not isinstance(obj, QtWidgets.QPushButton):
            return super().eventFilter(obj, event)

        etype = event.type()
        if etype == QtCore.QEvent.MouseButtonPress \
                and event.button() == QtCore.Qt.LeftButton:
            # Dragging a grouped button moves the whole group; dragging an
            # ungrouped one dissolves the group and moves it alone.
            if obj not in self._group:
                self._set_group([])
                grabbed = [obj]
            else:
                grabbed = [btn for _, btn in self._buttons if btn in self._group]
            targets = [(btn, info, btn.pos())
                       for info, btn in self._buttons if btn in grabbed]
            self._drag = (event.globalPosition().toPoint(), targets)
            obj.setCursor(QtCore.Qt.ClosedHandCursor)
            return True  # swallow: no selection while editing

        if etype == QtCore.QEvent.MouseMove and self._drag:
            press_pos, targets = self._drag
            delta = event.globalPosition().toPoint() - press_pos
            for btn, _, start_pos in targets:
                btn.move(start_pos + delta)
            return True

        if etype == QtCore.QEvent.MouseButtonRelease and self._drag:
            _, targets = self._drag
            self._drag = None
            obj.setCursor(QtCore.Qt.OpenHandCursor)
            w, h = self._inner_rect()
            for btn, info, _ in targets:
                center = btn.pos() + QtCore.QPoint(btn.width() // 2, btn.height() // 2)
                info.x = min(1.0, max(0.0, (center.x() - CANVAS_MARGIN) / w))
                info.y = min(1.0, max(0.0, (center.y() - CANVAS_MARGIN) / h))
            self._reposition()  # snap back inside the canvas if dragged out
            self.layout_edited.emit()
            return True

        return super().eventFilter(obj, event)


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

        self.edit_toggle = QtWidgets.QPushButton("Edit")
        self.edit_toggle.setCheckable(True)
        self.edit_toggle.setToolTip("Edit mode: drag buttons to rearrange the picker")
        self.edit_toggle.setStyleSheet(
            "QPushButton:checked {background-color: #7a5c1e; border-color: #c9982f;}")
        self.edit_toggle.toggled.connect(self._on_edit_toggled)
        header.addWidget(self.edit_toggle)

        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setToolTip("Write this rig's layout to JSON (loaded automatically, "
                                 "editable by hand with live reload)")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save_layout)
        header.addWidget(self.save_btn)
        root.addLayout(header)

        self.canvas = PickerCanvas()
        self.canvas.picked.connect(self._on_pick)
        self.canvas.picked_many.connect(self._on_pick_many)
        self.canvas.layout_edited.connect(self._on_layout_edited)
        root.addWidget(self.canvas, 1)

        footer = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("")
        footer.addWidget(self.status, 1)
        hint = QtWidgets.QLabel("Drag: lasso • Shift: add")
        hint.setStyleSheet("color: #777;")
        footer.addWidget(hint)
        root.addLayout(footer)

        self.combo.currentIndexChanged.connect(self._on_rig_changed)
        self.refresh_rigs()

        # Live reload: watch the package's .py files and the current rig's
        # layout JSON; edits on disk update the picker without restarting.
        self._watch_mtimes = {}
        self._refresh_watch_snapshot()
        self._watch_timer = QtCore.QTimer(self)
        self._watch_timer.timeout.connect(self._check_watched_files)
        self._watch_timer.start(1000)

    # ---------------------------------------------------------- live reload

    def _watched_files(self):
        files = []
        package_dir = os.path.dirname(os.path.abspath(__file__))
        for name in os.listdir(package_dir):
            if name.endswith(".py"):
                files.append(os.path.join(package_dir, name))
        if self._entry:
            json_path = layout_store.path_for(self._entry.rig_key)
            if os.path.exists(json_path):
                files.append(json_path)
        return files

    def _refresh_watch_snapshot(self):
        self._watch_mtimes = {}
        for path in self._watched_files():
            try:
                self._watch_mtimes[path] = os.path.getmtime(path)
            except OSError:
                pass

    def _check_watched_files(self):
        py_changed = False
        json_changed = False
        for path in self._watched_files():
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime != self._watch_mtimes.get(path):
                self._watch_mtimes[path] = mtime
                if path.endswith(".py"):
                    py_changed = True
                else:
                    json_changed = True

        if py_changed:
            self._watch_timer.stop()
            self._set_status("Code changed on disk — reloading picker...")
            # Defer: let this timer callback finish before the module that
            # owns it is reloaded and the window replaced.
            QtCore.QTimer.singleShot(0, _reload_package)
        elif json_changed and self._entry:
            self._load_entry(self._entry)
            self._set_status(f"Layout reloaded from disk — {self._entry.label}")

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
        overrides = layout_store.load(entry.rig_key)
        if overrides:
            layout_store.apply_overrides(self._buttons, overrides)
        self.canvas.set_buttons(self._buttons)
        suffix = " (saved layout)" if overrides else ""
        self._set_status(f"{len(self._buttons)} controls — {entry.label}{suffix}")
        if hasattr(self, "_watch_mtimes"):  # not yet built during __init__
            self._refresh_watch_snapshot()

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

    def _on_pick_many(self, keys):
        if not self._entry:
            return
        if keys:
            selection.select_controls(self._entry, keys, add=self._additive())
        elif not self._additive():
            # Click/lasso in the void clears the selection (dwpicker behavior).
            selection.clear_selection(self._entry)

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

    def _on_edit_toggled(self, checked):
        self.canvas.set_edit_mode(checked)
        if checked:
            self._set_status("Edit mode: drag buttons, then Save")

    def _on_layout_edited(self):
        self.save_btn.setEnabled(True)

    def _on_save_layout(self):
        if not (self._entry and self._buttons):
            return
        path = layout_store.save(self._entry.rig_key, self._buttons)
        self.save_btn.setEnabled(False)
        self._set_status(f"Layout saved: {path}")
        # Our own write must not trigger the live-reload watcher.
        self._refresh_watch_snapshot()


def _reload_package():
    """Hot-reload all picker modules and rebuild the window (live reload)."""
    try:
        import character_picker
        character_picker.reload_and_open()
    except Exception as exc:
        unreal.log_error(f"[CharacterPicker] Live reload failed: {exc}")


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
