"""Character Picker — a rig-agnostic control picker for Unreal Engine 5.5+.

Discovers every Control Rig in the project, auto-generates a 2D picker
layout from each rig's control shapes, and selects controls either on the
live rig bound in Sequencer or inside the Control Rig asset editor.

The UI is a PySide6 window driven from UE's Python (UMG widget trees are
not scriptable from Python). PySide6 is auto-installed on first run.

Usage (from the UE Python console or the Tools menu):
    import character_picker
    character_picker.open_picker()
"""

from importlib import reload


def open_picker():
    from character_picker import qt_app
    if not qt_app.ensure_qt():
        return
    from character_picker import picker_qt
    picker_qt.open_picker()


def diagnose():
    """Print what the picker can see (sequencer, rigs) to the Output Log."""
    import unreal
    from character_picker import rig_discovery
    try:
        seq = unreal.LevelSequenceEditorBlueprintLibrary.get_focused_level_sequence()
        unreal.log(f"[CharacterPicker] Focused sequence: "
                   f"{seq.get_path_name() if seq else None}")
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] Sequence query failed: {exc}")
    for entry in rig_discovery.find_all_rigs():
        unreal.log(f"[CharacterPicker]   {entry.source:9s} | {entry.label} "
                   f"| valid={entry.is_valid()}")


def reload_and_open():
    """Dev helper: reload all modules then reopen the picker."""
    from character_picker import rig_discovery, layout, layout_store, selection, picker_qt
    for mod in (rig_discovery, layout, layout_store, selection, picker_qt):
        reload(mod)
    picker_qt.open_picker()
