"""Find every Control Rig the picker can drive.

Two sources, merged into a single list of RigEntry objects:

1. Live rigs bound on the Level Sequence currently open in Sequencer.
   Selecting controls on these highlights them in the viewport / anim panel.
2. Every ControlRigBlueprint asset in the project (Asset Registry scan).
   Selecting controls on these drives the Control Rig asset editor.
"""

import unreal


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
        if bp:
            # ControlRigBlueprint exposes its hierarchy as a property.
            try:
                return bp.hierarchy
            except AttributeError:
                return bp.get_editor_property("hierarchy")
        return None

    def is_valid(self):
        try:
            return self.get_hierarchy() is not None
        except Exception:
            return False


# ---------------------------------------------------------------------- scans

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
    """Every ControlRigBlueprint asset in the project."""
    entries = []
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    class_path = unreal.TopLevelAssetPath("/Script/ControlRigDeveloper", "ControlRigBlueprint")
    assets = registry.get_assets_by_class(class_path, search_sub_classes=True) or []
    for asset_data in assets:
        path = str(asset_data.get_editor_property("package_name"))
        name = str(asset_data.get_editor_property("asset_name"))
        entries.append(RigEntry(
            label=name,
            source=RigEntry.SOURCE_ASSET,
            blueprint_path=path,
        ))
    entries.sort(key=lambda e: e.label.lower())
    return entries


def find_all_rigs():
    """Sequencer rigs first (most likely what the animator wants), then assets."""
    return find_sequencer_rigs() + find_asset_rigs()
