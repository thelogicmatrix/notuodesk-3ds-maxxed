"""Compatibility commands for installations that still reference the old updater."""
from pathlib import Path
import tomllib

import bpy


RETIREMENT_MESSAGE = (
    "The built-in updater is retired. Manage updates through application "
    "preferences or your package distribution."
)
status = {"state": "RETIRED", "latest": ""}


def current_version():
    """Read the installed package version without contacting a release service."""
    try:
        metadata = tomllib.loads(
            Path(__file__).with_name("blender_manifest.toml").read_text(encoding="utf-8")
        )
        return str(metadata["version"])
    except (OSError, ValueError, KeyError):
        return "Unknown"


def draw_update_box(layout, settings=None):
    """Keep old drawing calls safe without reading saved repository or token data."""
    box = layout.box()
    box.label(text="Built-in updater retired")
    box.label(text="Manage updates in application preferences or your distribution")


def register_auto_check():
    """Old startup callers can keep calling this hook until they are removed."""
    return None


def _retired(operator):
    operator.report({"INFO"}, RETIREMENT_MESSAGE)
    return {"CANCELLED"}


class MAX_OT_check_update(bpy.types.Operator):
    bl_idname = "max.check_update"
    bl_label = "Check for Updates (Retired)"
    bl_description = "The built-in updater has been retired"

    def execute(self, context):
        return _retired(self)


class MAX_OT_install_update(bpy.types.Operator):
    bl_idname = "max.install_update"
    bl_label = "Update Now (Retired)"
    bl_description = "Manage package updates through application preferences or distribution"

    def execute(self, context):
        return _retired(self)


class MAX_OT_open_online_prefs(bpy.types.Operator):
    bl_idname = "max.open_online_prefs"
    bl_label = "Allow Online Access (Retired)"
    bl_description = "The retired updater does not need online access"

    def execute(self, context):
        return _retired(self)


classes = (MAX_OT_check_update, MAX_OT_install_update, MAX_OT_open_online_prefs)
