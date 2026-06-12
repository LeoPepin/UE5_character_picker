"""Auto-run by Unreal at editor startup (any Content/Python folder on the
Python path). Registers a 'Character Picker' entry in the Tools menu."""

import unreal


def _register_menu():
    menus = unreal.ToolMenus.get()
    tools_menu = menus.find_menu("LevelEditor.MainMenu.Tools")
    if tools_menu is None:
        unreal.log_warning("[CharacterPicker] Tools menu not found; use "
                           "'import character_picker; character_picker.open_picker()'")
        return

    entry = unreal.ToolMenuEntry(
        name="OpenCharacterPicker",
        type=unreal.MultiBlockType.MENU_ENTRY,
    )
    entry.set_label("Character Picker")
    entry.set_tool_tip("Open the auto-generated control rig picker")
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        custom_type="",
        string="import character_picker; character_picker.open_picker()",
    )
    tools_menu.add_menu_entry("Tools", entry)
    menus.refresh_all_widgets()


_register_menu()
