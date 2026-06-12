"""Qt runtime inside Unreal.

UMG widget trees are not reachable from Python (no `widget_tree` /
`get_widget_from_name` exposure), so the picker UI is a PySide6 window
instead. Qt's event loop is pumped from a Slate post-tick callback — the
standard pattern for Qt tools inside the UE editor.

PySide6 is installed once, on demand, into Content/Python/libs using the
engine's own python.exe, so nothing pollutes the system Python.
"""

import importlib
import os
import subprocess
import sys

import unreal

_LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs")
_tick_handle = None


def ensure_qt():
    """Make PySide6 importable, installing it on first run. Returns bool."""
    if _LIBS not in sys.path:
        sys.path.insert(0, _LIBS)
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        pass

    try:
        py = unreal.get_interpreter_executable_path()
    except AttributeError:
        py = None
    if not py or not os.path.exists(py):
        unreal.log_error(
            "[CharacterPicker] Could not locate the engine's python.exe to "
            "install PySide6. Install it manually:\n"
            f'  <Engine>/Binaries/ThirdParty/Python3/Win64/python.exe -m pip '
            f'install --target "{_LIBS}" PySide6-Essentials'
        )
        return False

    unreal.log(
        "[CharacterPicker] Installing PySide6 into Content/Python/libs "
        "(one-time, ~100 MB, editor may pause for a minute)..."
    )
    cmd = [py, "-m", "pip", "install", "--target", _LIBS, "PySide6-Essentials"]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if result.returncode != 0:
        unreal.log_error(f"[CharacterPicker] pip install failed:\n{result.stderr[-2000:]}")
        return False

    importlib.invalidate_caches()
    try:
        import PySide6  # noqa: F401
    except ImportError as exc:
        unreal.log_error(f"[CharacterPicker] PySide6 installed but import failed: {exc}")
        return False
    unreal.log("[CharacterPicker] PySide6 ready.")
    return True


def get_app():
    """Return the QApplication, creating it and the tick pump if needed."""
    from PySide6 import QtWidgets

    global _tick_handle
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(["unreal"])
        app.setQuitOnLastWindowClosed(False)
    if _tick_handle is None:
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)
        unreal.register_python_shutdown_callback(_shutdown)
    return app


def _tick(_delta_seconds):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.processEvents()


def _shutdown():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None
