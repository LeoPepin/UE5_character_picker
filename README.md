# UE Character Picker

A rig-agnostic character picker for Unreal Engine **5.5+**. It discovers every
Control Rig in the project, auto-generates a 2D picker layout from each rig's
control shapes (no per-rig setup), and selects controls either on the live rig
in **Sequencer** or inside the **Control Rig asset editor**.

Built with Python + a PySide6 (Qt) window — no C++, no compiling. UMG was the
original plan, but UE does not expose widget trees to Python (`widget_tree` /
`get_widget_from_name` are unavailable), so the UI is Qt, pumped from a Slate
post-tick callback — the standard pattern for Python tools inside the editor.

## How it works

- **Discovery** — scans the Asset Registry for every `ControlRigBlueprint`,
  plus any rigs bound on the level sequence currently open in Sequencer
  (those appear first in the dropdown, prefixed `[Sequencer]`).
- **Layout** — each control's shape transform (initial pose) is projected to a
  front view. The horizontal axis is chosen automatically from whichever world
  axis (X or Y) has the wider spread, so it works regardless of which way the
  character faces. Buttons inherit each control's shape color.
- **Selection** — sequencer rigs are driven through `ControlRig.select_control`
  (syncs with the viewport and Anim Outliner); asset rigs go through the
  blueprint's hierarchy controller (syncs with the Control Rig editor).

## Install

1. Enable these plugins in your UE project: **Python Editor Script Plugin**,
   **Editor Scripting Utilities**, **Control Rig** (usually already on).
2. Copy (or symlink) `Content/Python/` into your project's `Content/` folder,
   merging with any existing `Content/Python`.
3. Restart the editor. A **Character Picker** entry appears under **Tools**.

You can also open it from the Python console:

```python
import character_picker
character_picker.open_picker()
```

## First run

The tool installs **PySide6** automatically into `Content/Python/libs` using
the engine's own `python.exe` (one-time, ~100 MB download — the editor may
pause for a minute). If that fails (offline machine, proxy), install manually:

```
<Engine>/Binaries/ThirdParty/Python3/Win64/python.exe -m pip install --target "<Project>/Content/Python/libs" PySide6-Essentials
```

## Using it

- **Dropdown** — pick which rig the picker shows.
- **Click a button** — selects that control (replaces the selection).
- **Shift+click** — adds to the selection instead of replacing.
- **All / None** — select every control / clear the selection.
- **Refresh** — rescan rigs (use after opening a sequence or adding a rig).
- The window stays on top of the editor so it behaves like a docked panel.

Hover any button to see the control's name.

## Development

```python
import character_picker
character_picker.reload_and_open()   # hot-reload all modules
```

## Layout notes / known limits

- Layout quality depends on shape placement: stacked controls (e.g. spine FK
  over IK) will overlap. A per-rig JSON layout override is the natural next
  step if you want hand-tweaked layouts.
- Controls with `shape_visible` off or `Visual Cue` animation type are skipped.
