"""Per-rig picker layouts on disk, dwpicker-style.

The auto-generated layout is the starting point; in Edit mode the user
drags buttons into place and saves. Each rig gets one JSON file whose
shapes follow a simplified dwpicker schema:

    {"version": 1, "rig": "CR_Atom", "shapes": [
        {"target": "spine_01_ctrl", "left": 0.45, "top": 0.52,
         "shape": "square", "scale": 1.0}, ...]}

`left`/`top` are normalized 0..1 (dwpicker uses pixels; normalized keeps
the layout valid at any window size). Controls missing from the file keep
their auto position, so a rig update never breaks a saved layout.

Files live in <Project>/Content/Python/picker_layouts/ so they are shared
with the project (and can be versioned).
"""

import json
import os

import unreal

VERSION = 1


def layouts_dir():
    return os.path.join(unreal.Paths.project_content_dir(), "Python", "picker_layouts")


def path_for(rig_key):
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in rig_key)
    return os.path.join(layouts_dir(), safe + ".json")


def load(rig_key):
    """Return {control_name: shape_dict} for this rig, or {} if no file."""
    path = path_for(rig_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] Could not read layout {path}: {exc}")
        return {}
    return {s["target"]: s for s in data.get("shapes", []) if "target" in s}


def apply_overrides(buttons, overrides):
    """Apply saved positions/shapes onto auto-generated PickerButtons."""
    for button in buttons:
        shape = overrides.get(button.name)
        if not shape:
            continue
        button.x = float(shape.get("left", button.x))
        button.y = float(shape.get("top", button.y))
        button.shape = shape.get("shape", button.shape)
        button.scale = float(shape.get("scale", button.scale))
    return buttons


def save(rig_key, buttons):
    """Write the current button placement to the rig's layout file."""
    os.makedirs(layouts_dir(), exist_ok=True)
    data = {
        "version": VERSION,
        "rig": rig_key,
        "shapes": [
            {
                "target": b.name,
                "left": round(b.x, 4),
                "top": round(b.y, 4),
                "shape": b.shape,
                "scale": round(b.scale, 3),
            }
            for b in buttons
        ],
    }
    path = path_for(rig_key)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return path
