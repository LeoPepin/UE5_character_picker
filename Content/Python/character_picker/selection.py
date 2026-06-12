"""Select controls on a rig, whatever context it lives in.

Sequencer (live rig instance): ControlRig.select_control — selection shows
up in the viewport and the Anim Outliner.

Asset editor (ControlRigBlueprint): go through the blueprint's hierarchy
controller so the Control Rig editor's own selection updates.
"""

import unreal

from character_picker.rig_discovery import RigEntry


def _hierarchy_controller(entry):
    bp = entry.get_blueprint()
    if bp is None:
        return None
    try:
        return bp.get_hierarchy_controller()
    except Exception:
        try:
            return bp.hierarchy.get_controller()
        except Exception:
            return None


def clear_selection(entry):
    if entry.source == RigEntry.SOURCE_SEQUENCER and entry.control_rig:
        try:
            entry.control_rig.clear_control_selection()
            return
        except Exception:
            pass
    controller = _hierarchy_controller(entry)
    if controller:
        try:
            controller.clear_selection()
        except Exception as exc:
            unreal.log_warning(f"[CharacterPicker] clear_selection failed: {exc}")


def select_control(entry, key, add=False):
    """Select one control. add=False replaces the current selection."""
    if not add:
        clear_selection(entry)

    if entry.source == RigEntry.SOURCE_SEQUENCER and entry.control_rig:
        try:
            entry.control_rig.select_control(key.name, True)
            return True
        except Exception as exc:
            unreal.log_warning(f"[CharacterPicker] select_control failed: {exc}")
            return False

    controller = _hierarchy_controller(entry)
    if controller is None:
        unreal.log_warning(f"[CharacterPicker] No hierarchy controller for {entry.label}")
        return False
    try:
        controller.select_element(key, select=True)
        return True
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] select_element failed: {exc}")
        return False


def select_controls(entry, keys, add=False):
    if not add:
        clear_selection(entry)
    ok = True
    for key in keys:
        ok = select_control(entry, key, add=True) and ok
    return ok
