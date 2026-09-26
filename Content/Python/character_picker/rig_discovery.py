"""Find every Control Rig the picker can drive.

Two sources, merged into a single list of RigEntry objects:

1. Live rigs bound on the Level Sequence currently open in Sequencer.
   Selecting controls on these highlights them in the viewport / anim panel.
2. Every ControlRigBlueprint asset under /Game (Asset Registry scan);
   engine and plugin rigs are left out.
   Selecting controls on these drives the Control Rig asset editor.
"""

import unreal

PROJECT_CONTENT_ROOT = "/Game/"


class RigEntry:
    """One pickable rig: a display label plus whatever object we select through."""

    SOURCE_SEQUENCER = "sequencer"
    SOURCE_ASSET = "asset"

    def __init__(self, label, source, control_rig=None, blueprint_path=None):
        self.label = label
        self.source = source
        self.control_rig = control_rig          # live unreal.ControlRig (sequencer)
        self.blueprint_path = blueprint_path    # asset path (asset source)
        self._blueprint = None                  # lazily loaded ControlRigBlueprint

    @property
    def rig_key(self):
        """Stable identifier shared by the sequencer and asset entries of a rig
        (used to key saved picker layouts)."""
        return self.label.replace("[Sequencer] ", "", 1)

    # ------------------------------------------------------------------ access

    def get_blueprint(self):
        if self._blueprint is None and self.blueprint_path:
            self._blueprint = unreal.load_asset(self.blueprint_path)
        return self._blueprint

    def get_hierarchy(self):
        """Return the URigHierarchy for layout generation, or None."""
        if self.source == self.SOURCE_SEQUENCER and self.control_rig:
            return self.control_rig.get_hierarchy()
        bp = self.get_blueprint()
        if not bp:
            return None
        # ControlRigBlueprint exposes its hierarchy as a property; the UE 5.8
        # ControlRigRuntimeAsset may expose it differently, so try each way.
        for getter in (lambda: bp.hierarchy,
                       lambda: bp.get_editor_property("hierarchy"),
                       lambda: bp.get_hierarchy(),
                       lambda: unreal.get_default_object(
                           bp.generated_class()).get_hierarchy()):
            try:
                hierarchy = getter()
            except Exception:
                continue
            if hierarchy is not None:
                return hierarchy
        unreal.log_warning(f"[CharacterPicker] No hierarchy accessor on "
                           f"{self.label} ({bp.get_class().get_name()}).")
        return None

    def is_valid(self):
        try:
            return self.get_hierarchy() is not None
        except Exception:
            return False


# ---------------------------------------------------------------------- scans

_RIG_ASSET_CLASSES = (
    unreal.TopLevelAssetPath("/Script/ControlRigDeveloper", "ControlRigBlueprint"),
    unreal.TopLevelAssetPath("/Script/ControlRig", "ControlRigRuntimeAsset"),
)

def find_sequencer_rigs():
    """Rigs bound on the level sequence currently focused in Sequencer."""
    entries = []
    try:
        level_sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_focused_level_sequence()
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] Cannot query focused sequence: {exc}")
        level_sequence = None
    if not level_sequence:
        unreal.log("[CharacterPicker] No level sequence open in Sequencer.")
        return entries

    try:
        proxies = unreal.ControlRigSequencerLibrary.get_control_rigs(level_sequence)
    except Exception as exc:
        unreal.log_warning(f"[CharacterPicker] Could not query sequencer rigs: {exc}")
        return entries

    unreal.log(f"[CharacterPicker] Sequence '{level_sequence.get_name()}': "
               f"{len(proxies)} control rig binding(s).")
    for proxy in proxies:
        rig = proxy.get_editor_property("control_rig")
        if not rig:
            continue
        rig_name = rig.get_class().get_name().replace("_C", "")
        entries.append(RigEntry(
            label=f"[Sequencer] {rig_name}",
            source=RigEntry.SOURCE_SEQUENCER,
            control_rig=rig,
        ))
    return entries


def find_asset_rigs():
    """Every ControlRigBlueprint asset in the project's own content.

    Engine and plugin rigs (modular/procedural rig parts under /ControlRig/,
    /Engine/, etc.) are skipped: only /Game/ assets are the project's rigs."""
    entries = []
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = []
    for class_path in _RIG_ASSET_CLASSES:
        assets += registry.get_assets_by_class(class_path, search_sub_classes=True) or []
    skipped = 0
    seen = set()
    for asset_data in assets:
        path = str(asset_data.get_editor_property("package_name"))
        if path in seen:
            continue
        seen.add(path)
        # Only the project's own content: skip rigs shipped with the engine
        # and plugins (/Engine/, /ControlRig/, ...).
        if not path.startswith(PROJECT_CONTENT_ROOT):
            skipped += 1
            continue
            continue
        name = str(asset_data.get_editor_property("asset_name"))
        entries.append(RigEntry(
            label=name,
            source=RigEntry.SOURCE_ASSET,
            blueprint_path=path,
        ))
    if skipped:
        unreal.log(f"[CharacterPicker] Skipped {skipped} engine/plugin rig asset(s).")
    entries.sort(key=lambda e: e.label.lower())
    return entries


def find_all_rigs():
    """Sequencer rigs first (most likely what the animator wants), then assets."""
    return find_sequencer_rigs() + find_asset_rigs()
