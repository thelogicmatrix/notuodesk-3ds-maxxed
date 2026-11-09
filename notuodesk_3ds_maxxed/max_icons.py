"""Original Max-style icons, owned by one preview collection."""

from pathlib import Path

import bpy.utils.previews
from bpy.props import EnumProperty
from bpy.types import Operator

_collection = None
DIRECTORY = Path(__file__).with_name("icons")

# Field keys and tool names match the pending feature branches. Their integrator
# can use these names without replacing the SVG family or changing the loader.
CADDY_FIELDS = {key: "caddy_" + key for key in (
    "amount", "height", "extrusion_type", "bevel_type", "local_bias", "base_width",
    "threshold", "segments", "open", "tension", "tess_tension", "taper", "bias", "smooth", "twist1", "twist2",
    "bridge_selection", "pinch", "slide", "smoothness", "tessellate_type", "relax", "iterations",
    "hold_boundary", "hold_outer", "individual", "pick1", "pick2", "separate_smoothing",
    "separate_materials", "weld_counts")}


def tooltip(context, label, idname, **properties):
    """Show the name and an active configured keyboard shortcut, when present."""
    if context is None or context.window_manager is None:
        return label
    keyconfigs = context.window_manager.keyconfigs
    names = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "SIX": "6",
             "SEVEN": "7", "EIGHT": "8", "NINE": "9", "ZERO": "0", "SPACE": "Space",
             "RET": "Enter", "ESC": "Esc", "BACK_SPACE": "Backspace", "DEL": "Delete"}
    for config in (keyconfigs.user, keyconfigs.addon):
        if config is None:
            continue
        for keymap in config.keymaps:
            for item in keymap.keymap_items:
                if not item.active or item.idname != idname or item.value not in {"PRESS", "CLICK"}:
                    continue
                if item.map_type != "KEYBOARD" or item.any or item.key_modifier != "NONE":
                    continue
                if not all(getattr(item.properties, key, None) == value for key, value in properties.items()):
                    continue
                keys = [name for flag, name in ((item.ctrl, "Ctrl"), (item.shift, "Shift"),
                                                (item.alt, "Alt"), (item.oskey, "OS")) if flag]
                keys.append(names.get(item.type, item.type.replace("_", " ")))
                return label + " (" + "+".join(keys) + ")"
    return label


_TOOLS = {
    "MOVE": ("builtin.move", "Select and Move"),
    "ROTATE": ("builtin.rotate", "Select and Rotate"),
    "SCALE": ("builtin.scale", "Select and Uniform Scale"),
    "RECT": ("builtin.select_box", "Rectangular Selection Region"),
    "CIRCLE": ("builtin.select_circle", "Circular Selection Region"),
    "FENCE": ("builtin.select_lasso", "Fence Selection Region"),
}


class MAX_OT_icon_tool(Operator):
    """Activate the existing tool with a Max name in its icon tooltip."""
    bl_idname = "max.icon_tool"
    bl_label = "Select Tool"

    tool: EnumProperty(items=[(key, label, "") for key, (_, label) in _TOOLS.items()])

    @classmethod
    def description(cls, context, props):
        tool, label = _TOOLS[props.tool]
        return tooltip(context, label, "wm.tool_set_by_id", name=tool)

    def execute(self, context):
        import bpy
        return bpy.ops.wm.tool_set_by_id(name=_TOOLS[self.tool][0])


_SNAPS = {
    "SNAP": ("use_snap", "Snaps Toggle"),
    "ANGLE_SNAP": ("use_snap_rotate", "Angle Snap Toggle"),
    "PERCENT_SNAP": ("use_snap_scale", "Percent Snap Toggle"),
}


class MAX_OT_icon_snap(Operator):
    """Toggle the same native setting with a Max name in its icon tooltip."""
    bl_idname = "max.icon_snap"
    bl_label = "Snaps Toggle"

    kind: EnumProperty(items=[(key, label, "") for key, (_, label) in _SNAPS.items()])

    @classmethod
    def description(cls, context, props):
        return tooltip(context, _SNAPS[props.kind][1], "max.toggle", what=props.kind)

    def execute(self, context):
        data = context.scene.tool_settings
        key = _SNAPS[self.kind][0]
        setattr(data, key, not getattr(data, key))
        return {"FINISHED"}


classes = (MAX_OT_icon_tool, MAX_OT_icon_snap)


def icon(name):
    """Return the custom icon ID, or zero when its artwork is unavailable."""
    preview = _collection.get(name) if _collection is not None else None
    return preview.icon_id if preview is not None else 0


def ui(name, fallback):
    """UILayout keyword arguments retaining the original Blender fallback."""
    value = icon(name)
    return {"icon_value": value} if value else {"icon": fallback}


def enum_items(items):
    """Enum buttons take custom IDs in their items, not prop_enum keywords."""
    return [(key, label, description, icon(key.lower()) or fallback, number)
            for key, label, description, fallback, number in items]


def register():
    global _collection
    if _collection is not None:
        return
    _collection = bpy.utils.previews.new()
    for source in sorted((DIRECTORY / "src").glob("*.svg")):
        # 64px artwork gives Blender enough pixels at doubled UI scale.
        path = DIRECTORY / (source.stem + "@2x.png")
        if not path.is_file():
            path = DIRECTORY / (source.stem + ".png")
        if path.is_file():
            try:
                preview = _collection.load(source.stem, str(path), "IMAGE")
                # Eager pixels avoid transparent lazy thumbnails during startup.
                pixels = preview.image_pixels_float[:]
                preview.icon_size = preview.image_size
                preview.icon_pixels_float = pixels
            except (OSError, RuntimeError) as exc:
                print(f"[3ds Maxxed] icon {source.stem}: {exc}")


def unregister():
    global _collection
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
