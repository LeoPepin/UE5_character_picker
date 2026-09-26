"""Per-rig picker layouts on disk, dwpicker-style.

The auto-generated layout is the starting point; in Edit mode the user
drags buttons into place and saves. Each rig gets one JSON file whose
shapes follow a simplified dwpicker schema:

    {"version": 1, "rig": "CR_Atom", "background": "Content/picker_bg.png",
     "shapes": [
        {"target": "spine_01_ctrl", "left": 0.45, "top": 0.52,
         "shape": "square", "scale": 1.0}, ...]}

`background` is optional: an image drawn behind the buttons, relative to
the project folder when it lives inside it, absolute otherwise.

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


def _read(rig_key):
    """The rig's raw layout file content, or {} if there is none."""
    path = path_for(rig_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] Could not read layout {path}: {exc}")
        return {}


def _write(rig_key, data):
    os.makedirs(layouts_dir(), exist_ok=True)
    path = path_for(rig_key)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return path


def load(rig_key):
    """Return {control_name: shape_dict} for this rig, or {} if no file."""
    data = _read(rig_key)
    return {s["target"]: s for s in data.get("shapes", []) if "target" in s}


def get_background(rig_key):
    """Absolute path of the rig's background image, or None."""
    stored = _read(rig_key).get("background")
    if not stored:
        return None
    if os.path.isabs(stored):
        return stored
    return os.path.normpath(os.path.join(unreal.Paths.project_dir(), stored))


def set_background(rig_key, image_path):
    """Store (or clear, with None) the rig's background image. Images inside
    the project are stored relative to it so the layout stays portable."""
    data = _read(rig_key) or {"version": VERSION, "rig": rig_key, "shapes": []}
    if image_path:
        project_dir = os.path.abspath(unreal.Paths.project_dir())
        image_path = os.path.abspath(image_path)
        try:
            relative = os.path.relpath(image_path, project_dir)
        except ValueError:  # other drive on Windows
            relative = None
        if relative and not relative.startswith(".."):
            image_path = relative
        data["background"] = image_path.replace("\\", "/")
    else:
        data.pop("background", None)
    return _write(rig_key, data)


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
    """Write the current button placement to the rig's layout file.

    Saved entries of controls not on the canvas (currently hidden) are kept,
    so they get their position back when they become visible again."""
    existing = _read(rig_key)
    shapes = {s["target"]: s for s in existing.get("shapes", []) if "target" in s}
    for b in buttons:
        shapes[b.name] = {
            "target": b.name,
            "left": round(b.x, 4),
            "top": round(b.y, 4),
            "shape": b.shape,
            "scale": round(b.scale, 3),
        }
    data = {
        "version": VERSION,
        "rig": rig_key,
        "shapes": list(shapes.values()),
    }
    if existing.get("background"):
        data["background"] = existing["background"]
    return _write(rig_key, data)
