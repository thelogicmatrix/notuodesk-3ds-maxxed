"""Curated preferences over the installed settings, without a second schema."""
import bpy
from bpy.props import BoolProperty, EnumProperty
from . import get_prefs

FIELDS = ("use_keymap", "show_toolbar", "show_statusbar", "show_labels", "max_menubar",
          "random_colors", "auto_pivot_on_create", "show_viewcube", "viewcube_size",
          "viewcube_opacity", "viewcube_snap", "viewcube_upright")


class PreferenceDraft:
    def __init__(self, prefs):
        self.prefs = prefs
        self.values = {key: getattr(prefs, key) for key in FIELDS if prefs and hasattr(prefs, key)}
        self.closed = False

    def apply(self):
        if not self.closed and self.prefs:
            for key, value in self.values.items():
                if key in FIELDS and hasattr(self.prefs, key):
                    setattr(self.prefs, key, value)
        self.closed = True

    def cancel(self):
        self.closed = True


def _available(layout, data, prop, label=None):
    if data and hasattr(data, prop):
        layout.prop(data, prop, text=label or "")
    else:
        row = layout.row()
        row.enabled = False
        row.label(text=(label or prop) + " (unavailable)")


def draw_preferences(layout, context, data=None):
    data = data or get_prefs()
    if data is None:
        layout.label(text="Maxxed settings are unavailable in this session")
        return
    box = layout.box()
    box.label(text="General")
    _available(box, data, "use_keymap", "Use Max hotkeys")
    row = box.row(align=True)
    row.operator("max.import_hsx", text="Import Hotkeys (.hsx)")
    row.operator("max.clear_hsx_hotkeys", text="Clear Imported Hotkeys")
    _available(box, data, "random_colors", "Random Object Colors")
    _available(box, data, "auto_pivot_on_create", "Creation Pivot")
    box = layout.box()
    box.label(text="Viewports and Workspace")
    for key, label in (("show_toolbar", "Main Toolbar"), ("show_statusbar", "Status Bar"),
                       ("show_labels", "Viewport Labels"), ("max_menubar", "Menu Bar"),
                       ("show_viewcube", "ViewCube")):
        _available(box, data, key, label)
    row = box.row(align=True)
    _available(row, data, "viewcube_size", "Size")
    _available(row, data, "viewcube_opacity", "Opacity")
    _available(box, data, "viewcube_snap", "Snap to Closest View")
    _available(box, data, "viewcube_upright", "Keep Scene Upright")
    box = layout.box()
    box.label(text="Snaps and Transforms")
    box.operator("max.snap_settings", text="Grid and Snap Settings")
    box.operator("max.typein_dialog", text="Transform Type-In")
    box = layout.box()
    box.label(text="About Maxxed")
    box.label(text="Blender backend " + bpy.app.version_string)
    box.label(text="Python scripting. Native scenes use the .blend format.")
    box.operator("max.backend_preferences", text="Advanced: Blender Preferences")


class MAX_OT_preferences_dialog(bpy.types.Operator):
    """Edit supported Maxxed settings. Apply accepts changes, Cancel leaves them unchanged"""
    bl_idname = "max.preferences_dialog"
    bl_label = "Preference Settings"
    use_keymap: BoolProperty(default=True)
    show_toolbar: BoolProperty(default=True)
    show_statusbar: BoolProperty(default=True)
    show_labels: BoolProperty(default=True)
    max_menubar: BoolProperty(default=True)
    random_colors: BoolProperty(default=True)
    auto_pivot_on_create: EnumProperty(items=[(v, v.title(), "") for v in ("OFF", "BOTTOM", "CENTER")], default="OFF")
    show_viewcube: BoolProperty(default=True)
    viewcube_size: EnumProperty(items=[(v, v.title(), "") for v in ("TINY", "SMALL", "NORMAL", "LARGE")], default="SMALL")
    viewcube_opacity: EnumProperty(items=[(v, v + "%", "") for v in ("0", "25", "50", "70")], default="50")
    viewcube_snap: BoolProperty(default=True)
    viewcube_upright: BoolProperty(default=True)

    def invoke(self, context, event):
        self._draft = PreferenceDraft(get_prefs())
        if not self._draft.prefs:
            self.report({"WARNING"}, "Maxxed settings are unavailable")
            return {"CANCELLED"}
        for key, value in self._draft.values.items():
            setattr(self, key, value)
        return context.window_manager.invoke_props_dialog(self, width=540, confirm_text="Apply")

    def draw(self, context):
        draw_preferences(self.layout, context, self)

    def execute(self, context):
        draft = getattr(self, "_draft", None) or PreferenceDraft(get_prefs())
        draft.values = {key: getattr(self, key) for key in draft.values}
        draft.apply()
        return {"FINISHED"}

    def cancel(self, context):
        if hasattr(self, "_draft"):
            self._draft.cancel()


class MAX_OT_backend_preferences(bpy.types.Operator):
    """Open the actual Blender backend preferences for advanced configuration"""
    bl_idname = "max.backend_preferences"
    bl_label = "Advanced: Blender Preferences"

    def execute(self, context):
        if bpy.app.background:
            return {"CANCELLED"}
        return bpy.ops.screen.userpref_show("INVOKE_DEFAULT")


classes = (MAX_OT_preferences_dialog, MAX_OT_backend_preferences)
_installed = False


def install():
    global _installed
    if not _installed:
        for cls in classes:
            bpy.utils.register_class(cls)
        _installed = True


def uninstall():
    global _installed
    if _installed:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        _installed = False
