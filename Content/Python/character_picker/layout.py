"""Auto-generate a 2D picker layout from a rig hierarchy.

Every control's shape transform (initial pose) is projected to a front
view. The horizontal screen axis is chosen automatically: of the two world
horizontal axes (X and Y), the one with the wider spread across all
controls is treated as the character's left/right axis. Z is always up.
This keeps the layout correct whether a character faces +X or +Y.
"""

import math
import re
from collections import defaultdict

import unreal


class PickerButton:
    def __init__(self, key, name, x, y, color, scale, shape="round", label=""):
        self.key = key        # unreal.RigElementKey
        self.name = name      # str control name
        self.x = x            # 0..1 normalized canvas position
        self.y = y
        self.color = color    # unreal.LinearColor
        self.scale = scale    # relative size hint (1.0 = default)
        self.shape = shape    # "round" or "square"
        self.label = label    # short text drawn inside the button ("IK")


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
    """Keep only real animatable controls with a visible shape.

    Filters out animation channels, visual cues and shape-less utility
    controls. Nulls, connectors and sockets never reach this point (the key
    type filter only lets CONTROL elements through)."""
    if settings is None:
        return True  # settings unreadable in this build: keep rather than hide
    try:
        anim_type = settings.get_editor_property("animation_type")
        # PROXY_CONTROL stays: proxies are visible, selectable driver shapes.
        if anim_type not in (unreal.RigControlAnimationType.ANIMATION_CONTROL,
                             unreal.RigControlAnimationType.PROXY_CONTROL):
            return False
    except Exception:
        pass
    # Note: shape_visible is deliberately NOT checked — rigs hide FK shapes
    # behind IK/FK switches, and the picker is exactly how an animator grabs
    # those hidden controls.
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
    if any(hint in name.lower() for hint in ("spine", "body")):
        return "square"
    return "round"


def build_layout(hierarchy):
    """Return a list of PickerButton with normalized 0..1 positions."""
    raw = []
    missing_settings = 0
    for key in _control_keys(hierarchy):
        name = str(key.name)
        # Tangent controls (chest_tan_ctrl...) are rig plumbing, useless to
        # the animator.
        if re.search(r"(?:^|_)tan(?:_|$)", name.lower()):
            continue
        settings = _control_settings(hierarchy, key)
        if settings is None:
            missing_settings += 1
        if not _is_pickable(settings):
            continue
        x, y, z = _shape_position(hierarchy, key)
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
        label = "IK" if re.search(r"(?:^|_)ik(?:_|$)", name.lower()) else ""
        buttons.append(PickerButton(key, name, nx, ny, color, 1.0, shape, label))

    # Mirror left/right if needed so the picker reads like a mirror
    # (character's left on screen right is the usual animator convention —
    # here we keep world orientation; flip in the UI if preferred).
    return _finalize(buttons)


# Virtual canvas the de-overlap pass works in, sized to the picker window's
# default canvas (420x680 window minus header/margins). Button sizes mirror
# picker_qt (BUTTON_SIZE=16, squares 1.6x wide).
_VIRTUAL_W = 360.0
_VIRTUAL_H = 520.0
_BTN = 16.0
_PAD = 2.0


def _finalize(buttons):
    """Make the auto-layout readable: align name-numbered chains, then push
    everything apart so no button overlaps on first load."""
    n = len(buttons)
    if n < 2:
        return buttons

    xs = [b.x * _VIRTUAL_W for b in buttons]
    ys = [b.y * _VIRTUAL_H for b in buttons]
    radii = []
    for b in buttons:
        w = _BTN * (1.6 if b.shape == "square" else 1.0) * b.scale
        h = _BTN * b.scale
        radii.append(max(w, h) / 2.0 + _PAD)

    # Root / global / body-offset controls go to a pinned row in the
    # top-left corner; they are excluded from every other pass.
    anchors = _layout_anchor_block(buttons, xs, ys, radii)
    anchor_set = set(anchors)

    # Controls sitting near the character's center line snap onto an exact
    # vertical column (head, jaw, neck, chest, spine, hips...). Side-paired
    # controls (eyes, clavicles...) are never centerline controls, even when
    # they project close to the axis.
    pairs = _side_pairs(buttons)
    paired_set = {i for pair in pairs for i in pair}
    midline = _snap_midline(xs, exclude=anchor_set | paired_set)

    # Fingers get a dedicated hand-block layout; they are excluded from the
    # generic chain alignment below.
    hand_blocks, finger_idxs = _layout_fingers(buttons, xs, ys, radii)

    # Legs stack into one vertical column per side, anatomical order.
    leg_blocks, leg_idxs = _layout_leg_columns(
        buttons, xs, ys, radii, exclude=anchor_set | finger_idxs)

    chains = _chain_groups(buttons, exclude=finger_idxs | anchor_set | leg_idxs)
    for chain in chains:
        _align_chain(xs, ys, radii, chain)

    # Chains, hand/leg blocks and the anchor row move as rigid blocks during
    # the de-overlap pass; everything else is its own group of one.
    rigid = chains + hand_blocks + leg_blocks + ([anchors] if anchors else [])
    gid = list(range(n))
    for c, group in enumerate(rigid):
        for i in group:
            gid[i] = n + c
    members = defaultdict(list)
    for i in range(n):
        members[gid[i]].append(i)

    pinned = {gid[anchors[0]]} if anchors else set()
    # Groups made only of midline controls may only slide vertically, so the
    # center column stays a column.
    y_only = {g for g, idxs in members.items()
              if g not in pinned and all(i in midline for i in idxs)}

    # Stack the center column explicitly (pairwise relaxation cannot expel a
    # control trapped between two links of a rigid chain).
    _pack_column(ys, radii, members, y_only)

    # Strict left/right symmetry: start from a mirrored pose, then relax with
    # both sides colliding normally while re-symmetrizing every pair after
    # each iteration (average the two sides, mirror back). Symmetry is exact
    # by construction and collisions stay resolved on both sides.
    _apply_mirror(xs, ys, pairs)

    _relax(xs, ys, radii, gid, members, pinned, y_only, sym_pairs=pairs)

    for b, x, y in zip(buttons, xs, ys):
        b.x = x / _VIRTUAL_W
        b.y = y / _VIRTUAL_H
    return buttons


# ------------------------------------------------------- anchors and midline

# Name tokens of "scene scope" controls shown as a row in the top-left
# corner (like wrld/gbl/loc on hand-made pickers).
_ANCHOR_TOKENS = {"root", "global", "world", "main", "master", "god",
                  "gbl", "wrld", "loc", "placement", "trajectory"}


def _layout_anchor_block(buttons, xs, ys, radii):
    """Pin root/global/body-offset controls as a row in the top-left corner.
    Returns their indices (one rigid, immovable group)."""
    idxs = []
    for idx, b in enumerate(buttons):
        name = b.name.lower()
        tokens = set(re.split(r"[^a-z0-9]+", name))
        if (tokens & _ANCHOR_TOKENS) or "body_offset" in name:
            idxs.append(idx)
    if not idxs:
        return []

    order = ("world", "wrld", "global", "gbl", "main", "master", "god",
             "placement", "trajectory", "root", "loc", "body")

    def priority(i):
        name = buttons[i].name.lower()
        for rank, keyword in enumerate(order):
            if keyword in name:
                return (rank, name)
        return (len(order), name)

    idxs.sort(key=priority)
    step = 2.0 * max(radii[i] for i in idxs) + 2.0 * _PAD
    for k, i in enumerate(idxs):
        xs[i] = radii[i] + _PAD + k * step
        ys[i] = radii[i] + _PAD
    return idxs


def _snap_midline(xs, exclude=frozenset(), threshold=0.07):
    """Snap controls projected near the horizontal center onto the exact
    center line. Returns the set of snapped indices."""
    mid = _VIRTUAL_W / 2.0
    snapped = set()
    for i, x in enumerate(xs):
        if i in exclude:
            continue
        if abs(x - mid) <= threshold * _VIRTUAL_W:
            xs[i] = mid
            snapped.add(i)
    return snapped


# ------------------------------------------------------------------- fingers

_FINGER_ORDER = ("pinky", "ring", "middle", "index", "thumb")


def _finger_rank(name):
    """Slot in a finger column, read top to bottom:
    metacarpal (0), curl (1), 01 (2), 02 (3), 03 (4)..."""
    if "metacarpal" in name:
        return 0.0
    if "curl" in name:
        return 1.0
    match = re.search(r"\d+", name)
    if match:
        return 1.0 + int(match.group())
    return 0.5  # unknown finger part: tuck it between metacarpal and curl


def _layout_fingers(buttons, xs, ys, radii):
    """Arrange finger controls as one block per hand: one vertical column per
    finger (metacarpal at the top, then curl, 01, 02, 03 going down),
    columns running pinky on the outside of the hand to thumb toward the
    body. Left/right hands mirror automatically.

    Returns (hand_blocks, finger_indices): the per-hand index groups (kept
    rigid during de-overlap) and the set of all finger button indices."""
    hands = defaultdict(list)  # side -> [(finger, rank, idx)]
    for idx, b in enumerate(buttons):
        name = b.name.lower()
        finger = next((f for f in _FINGER_ORDER if f in name), None)
        if finger is None:
            continue
        match = re.search(r"(?:^|_)(l|r|left|right)(?:_|$|\d)", name)
        if match:
            side = match.group(1)[0]
        else:  # no side token: infer from which half of the canvas it is on
            side = "l" if xs[idx] < _VIRTUAL_W / 2.0 else "r"
        hands[side].append((finger, _finger_rank(name), idx))

    hand_blocks = []
    finger_idxs = set()
    for items in hands.values():
        idxs = [i for _, _, i in items]
        finger_idxs.update(idxs)
        cx = sum(xs[i] for i in idxs) / len(idxs)
        cy = sum(ys[i] for i in idxs) / len(idxs)
        # Outside of the hand = away from the canvas center.
        direction = 1.0 if cx >= _VIRTUAL_W / 2.0 else -1.0

        present = [f for f in _FINGER_ORDER if any(f == fg for fg, _, _ in items)]
        spacing = 2.0 * max(radii[i] for i in idxs) + 2.0 * _PAD
        ranks = [r for _, r, _ in items]
        rank_min = min(ranks)
        cols = len(present)
        for finger, rank, idx in items:
            col = present.index(finger)
            xs[idx] = cx + direction * ((cols - 1) / 2.0 - col) * spacing
            # Rows hang below the hand (the fingers project at hand height,
            # which would crowd the wrist row): rank 0 one row under the
            # block's center, going down.
            ys[idx] = cy + (rank - rank_min + 1.0) * spacing
        hand_blocks.append(idxs)
    return hand_blocks, finger_idxs


# ---------------------------------------------------------- legs and mirror

_LEG_TOKENS = ("thigh", "calf", "knee", "leg", "foot", "ball",
               "heel", "tip", "toe", "ankle", "shin")


def _layout_leg_columns(buttons, xs, ys, radii, exclude=frozenset()):
    """Stack each side's leg/foot controls into one vertical column,
    anatomical (projected top-to-bottom) order, like a hand-made picker.
    Returns (blocks, indices): one rigid group per side."""
    sides = defaultdict(list)
    for idx, b in enumerate(buttons):
        if idx in exclude:
            continue
        name = b.name.lower()
        if not any(token in name for token in _LEG_TOKENS):
            continue
        match = re.search(r"(?:^|_)(l|r|left|right)(?:_|$|\d)", name)
        if match:
            sides[match.group(1)[0]].append(idx)

    blocks = []
    leg_idxs = set()
    for idxs in sides.values():
        if len(idxs) < 2:
            continue
        leg_idxs.update(idxs)
        cx = sum(xs[i] for i in idxs) / len(idxs)
        cy = sum(ys[i] for i in idxs) / len(idxs)
        ordered = sorted(idxs, key=lambda i: ys[i])
        total = sum(2.0 * radii[i] + _PAD for i in ordered) - _PAD
        cursor = cy - total / 2.0
        for i in ordered:
            xs[i] = cx
            ys[i] = cursor + radii[i]
            cursor += 2.0 * radii[i] + _PAD
        blocks.append(idxs)
    return blocks, leg_idxs


def _side_pairs(buttons):
    """(right_index, left_index) for every control with a side counterpart."""
    by_name = {b.name.lower(): i for i, b in enumerate(buttons)}
    pairs = []
    for i, b in enumerate(buttons):
        name = b.name.lower()
        left_name = None
        for r_token, l_token in (("_r_", "_l_"), ("_right_", "_left_"),
                                 ("right_", "left_")):
            if r_token in name:
                left_name = name.replace(r_token, l_token, 1)
                break
        if left_name is None and name.endswith("_r"):
            left_name = name[:-2] + "_l"
        if left_name is None:
            continue
        j = by_name.get(left_name)
        if j is not None and j != i:
            pairs.append((i, j))
    return pairs


def _apply_mirror(xs, ys, pairs):
    """Left controls take the mirrored position of their right counterpart
    (same height, x flipped around the center line)."""
    mid = _VIRTUAL_W / 2.0
    for r_idx, l_idx in pairs:
        xs[l_idx] = 2.0 * mid - xs[r_idx]
        ys[l_idx] = ys[r_idx]


def _chain_groups(buttons, exclude=frozenset()):
    """Indices of controls whose names differ only by their numbers,
    e.g. arm_01_l_ctrl / arm_02_l_ctrl / arm_03_l_ctrl, sorted numerically."""
    by_pattern = defaultdict(list)
    for idx, b in enumerate(buttons):
        if idx in exclude or not re.search(r"\d", b.name):
            continue
        pattern = re.sub(r"\d+", "#", b.name)
        numbers = tuple(int(s) for s in re.findall(r"\d+", b.name))
        by_pattern[pattern].append((numbers, idx))
    chains = []
    for members in by_pattern.values():
        if len(members) >= 2:
            members.sort()
            chains.append([idx for _, idx in members])
    return chains


def _align_chain(xs, ys, radii, chain):
    """Place the chain's buttons evenly along its principal axis.

    The axis comes from the spread of the projected positions, so a spine
    stays vertical and a tail stays oblique. Stacked chains default to
    vertical. Spacing is at least one button diameter."""
    pts = [(xs[i], ys[i]) for i in chain]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - cx) ** 2 for p in pts)
    syy = sum((p[1] - cy) ** 2 for p in pts)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)

    if sxx + syy < 1.0:  # all stacked: no direction to read, go vertical
        ux, uy = 0.0, 1.0
    else:
        angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
        ux, uy = math.cos(angle), math.sin(angle)

    ts = [(p[0] - cx) * ux + (p[1] - cy) * uy for p in pts]
    # Keep the chain's natural reading direction: if numeric order runs
    # against the axis, flip the axis.
    drift = sum(k * t for k, t in enumerate(ts))
    if drift < 0:
        ux, uy, ts = -ux, -uy, [-t for t in ts]

    step = max(2.0 * max(radii[i] for i in chain) + _PAD,
               (max(ts) - min(ts)) / max(len(chain) - 1, 1))
    start = -step * (len(chain) - 1) / 2.0
    for k, i in enumerate(chain):
        t = start + k * step
        xs[i] = cx + ux * t
        ys[i] = cy + uy * t


def _pack_column(ys, radii, members, column_groups):
    """1D top-to-bottom packing of the center-column groups: keep their
    vertical order, but shift groups down so none of their spans overlap."""
    spans = []
    for group in column_groups:
        idxs = members[group]
        top = min(ys[k] - radii[k] for k in idxs)
        bottom = max(ys[k] + radii[k] for k in idxs)
        spans.append((top + bottom, group, top, bottom))
    spans.sort()

    cursor = None
    for _, group, top, bottom in spans:
        shift = 0.0
        if cursor is not None and top < cursor:
            shift = cursor - top
            for k in members[group]:
                ys[k] += shift
        cursor = bottom + shift + _PAD


def _relax(xs, ys, radii, gid, members, pinned=frozenset(), y_only=frozenset(),
           sym_pairs=()):
    """Iterative pairwise de-overlap. Each colliding pair is separated along
    the line between them (deterministic fan-out when perfectly stacked),
    moving whole groups rigidly, then groups are clamped to the canvas.

    Constraints: `pinned` groups never move (others yield to them);
    `y_only` groups slide vertically only (keeps the center column straight);
    `sym_pairs` (right_idx, left_idx) are re-symmetrized after every
    iteration so left/right stay exact mirrors.
    """
    n = len(xs)

    def push(group, dx, dy):
        if group in pinned:
            return
        if group in y_only:
            dx = 0.0
        for k in members[group]:
            xs[k] += dx
            ys[k] += dy

    for _ in range(200):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                if gid[i] == gid[j]:
                    continue
                if gid[i] in pinned and gid[j] in pinned:
                    continue
                need = radii[i] + radii[j]
                dx = xs[j] - xs[i]
                dy = ys[j] - ys[i]
                dist_sq = dx * dx + dy * dy
                if dist_sq >= need * need:
                    continue
                dist = math.sqrt(dist_sq)
                if dist < 1e-3:
                    angle = (i * 7 + j * 13) * 0.618034
                    dx, dy = math.cos(angle), math.sin(angle)
                    dist = 1.0
                ux, uy = dx / dist, dy / dist
                total = (need - dist) + 0.02
                # A pinned neighbor takes none of the correction.
                wi = 0.0 if gid[i] in pinned else (1.0 if gid[j] in pinned else 0.5)
                wj = 0.0 if gid[j] in pinned else (1.0 if gid[i] in pinned else 0.5)
                push(gid[i], -ux * total * wi, -uy * total * wi)
                push(gid[j], ux * total * wj, uy * total * wj)
                moved = True
        for group, idxs in members.items():
            if group in pinned:
                continue
            push_x = max(max(radii[k] - xs[k] for k in idxs), 0.0) \
                or -max(max(xs[k] + radii[k] - _VIRTUAL_W for k in idxs), 0.0)
            push_y = max(max(radii[k] - ys[k] for k in idxs), 0.0) \
                or -max(max(ys[k] + radii[k] - _VIRTUAL_H for k in idxs), 0.0)
            if group in y_only:
                push_x = 0.0
            if push_x or push_y:
                for k in idxs:
                    xs[k] += push_x
                    ys[k] += push_y
        mid = _VIRTUAL_W / 2.0
        for r_i, l_i in sym_pairs:
            mirrored_left_x = 2.0 * mid - xs[l_i]
            avg_x = (xs[r_i] + mirrored_left_x) / 2.0
            avg_y = (ys[r_i] + ys[l_i]) / 2.0
            xs[r_i], ys[r_i] = avg_x, avg_y
            xs[l_i], ys[l_i] = 2.0 * mid - avg_x, avg_y
        if not moved:
            break
