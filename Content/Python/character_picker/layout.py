"""Auto-generate a 2D picker layout from a rig hierarchy.

Every control's shape transform (initial pose) is projected to a front
view. The horizontal screen axis is chosen automatically: of the two world
horizontal axes (X and Y), the one with the wider spread across all
controls is treated as the character's left/right axis. Z is always up.
This keeps the layout correct whether a character faces +X or +Y.
"""

import unreal


class PickerButton:
    def __init__(self, key, name, x, y, color, scale, shape="round"):
        self.key = key        # unreal.RigElementKey
        self.name = name      # str control name
        self.x = x            # 0..1 normalized canvas position
        self.y = y
        self.color = color    # unreal.LinearColor
        self.scale = scale    # relative size hint (1.0 = default)
        self.shape = shape    # "round" or "square"


def _control_keys(hierarchy):
    keys = []
    for key in hierarchy.get_all_keys(traverse=True):
        if key.type == unreal.RigElementType.CONTROL:
            keys.append(key)
    return keys


def _shape_position(hierarchy, key):
    """World-space position of the control's shape in the initial pose."""
    try:
        xf = hierarchy.get_global_control_shape_transform(key, initial=True)
    except Exception:
        xf = hierarchy.get_global_transform(key, initial=True)
    loc = xf.translation
    return float(loc.x), float(loc.y), float(loc.z)


def _control_settings(hierarchy, key):
    # API exposure varies per build: try the direct getter, then go through
    # the control element itself.
    try:
        return hierarchy.get_control_settings(key)
    except Exception:
        pass
    try:
        element = hierarchy.find_control(key)
        if element:
            return element.get_editor_property("settings")
    except Exception:
        pass
    try:
        element = hierarchy.find_element(key)
        if element:
            return element.get_editor_property("settings")
    except Exception:
        pass
    return None


def _is_pickable(settings):
    """Skip controls the animator can't see or shouldn't grab."""
    if settings is None:
        return True
    try:
        if not settings.get_editor_property("shape_visible"):
            return False
    except Exception:
        pass
    try:
        if settings.get_editor_property("animation_type") in (
            unreal.RigControlAnimationType.VISUAL_CUE,
        ):
            return False
    except Exception:
        pass
    return True


_FALLBACK_COLOR = unreal.LinearColor(0.3, 0.6, 1.0, 1.0)


def _color_of(settings):
    if settings is not None:
        try:
            return settings.get_editor_property("shape_color")
        except Exception:
            pass
    return _FALLBACK_COLOR


# Rig shape names that should read as squares in the picker
# (Box_Thick, Square_Thin, Cube...). Plus a naming-convention rule: spine
# controls are drawn square regardless of their rig shape.
_SQUARE_HINTS = ("box", "square", "cube", "rectangle")


def _shape_kind(settings, name):
    shape_name = ""
    if settings is not None:
        try:
            shape_name = str(settings.get_editor_property("shape_name")).lower()
        except Exception:
            pass
    if any(hint in shape_name for hint in _SQUARE_HINTS):
        return "square"
    if "spine" in name.lower():
        return "square"
    return "round"


def build_layout(hierarchy):
    """Return a list of PickerButton with normalized 0..1 positions."""
    raw = []
    missing_settings = 0
    for key in _control_keys(hierarchy):
        settings = _control_settings(hierarchy, key)
        if settings is None:
            missing_settings += 1
        if not _is_pickable(settings):
            continue
        x, y, z = _shape_position(hierarchy, key)
        name = str(key.name)
        raw.append((key, name, (x, y, z), _color_of(settings),
                    _shape_kind(settings, name)))

    if not raw:
        return []

    if missing_settings:
        unreal.log_warning(
            f"[CharacterPicker] Could not read control settings for "
            f"{missing_settings} control(s) — those use the fallback color. "
            f"Paste this log line if colors look wrong."
        )

    xs = [p[2][0] for p in raw]
    ys = [p[2][1] for p in raw]
    zs = [p[2][2] for p in raw]
    # raw tuples: (key, name, position, color, shape_kind)

    # The wider horizontal axis is the character's left/right axis.
    spread_x = max(xs) - min(xs)
    spread_y = max(ys) - min(ys)
    h_values = ys if spread_y >= spread_x else xs

    h_min, h_max = min(h_values), max(h_values)
    v_min, v_max = min(zs), max(zs)
    h_range = max(h_max - h_min, 1e-3)
    v_range = max(v_max - v_min, 1e-3)

    # Keep the character's aspect ratio: pad the narrow axis so a tall
    # biped doesn't get stretched into a square.
    aspect = h_range / v_range
    buttons = []
    for i, (key, name, (x, y, z), color, shape) in enumerate(raw):
        h = h_values[i]
        nx = (h - h_min) / h_range
        ny = 1.0 - (z - v_min) / v_range  # canvas Y grows downward
        if aspect < 1.0:  # narrow character: center horizontally
            nx = 0.5 + (nx - 0.5) * aspect
        else:             # wide rig (quadruped side spread): center vertically
            ny = 0.5 + (ny - 0.5) / aspect
        buttons.append(PickerButton(key, name, nx, ny, color, 1.0, shape))

    # Mirror left/right if needed so the picker reads like a mirror
    # (character's left on screen right is the usual animator convention —
    # here we keep world orientation; flip in the UI if preferred).
    return buttons
