"""NotuoDesk 3ds Maxxed: makes Blender look and work like Autodesk 3ds Max.

* 3ds Max dark theme, yellow active-viewport border, white selection, red sub-objects
* A "3ds Max" workspace: Scene Explorer | quad viewports | Command Panel
* Quad viewports (Top / Front / Left / Perspective) with [+] [Perspective] labels
* 3ds Max hotkeys and navigation (MMB pan, Alt+MMB orbit, Q/W/E/R, 1-5 sub-objects...)
* Command Panel (Create / Modify / Hierarchy / Motion / Display / Utilities)
* Click-drag primitive creation, Max-named Modifier List (incl. Melt, Skew, Squeeze,
  Slice, Noise, Push, Spherify, FFD), quad menus, Main Toolbar
* Open / merge 3ds Max (.max) files and FBX from 3ds Max
* V-Ray workflow: VRayMtl, VRayLight, VRaySun, VRayPhysicalCamera, VRayPlane, and
  detection of Chaos "V-Ray for Blender" when installed
"""

bl_info = {
    "name": "NotuoDesk 3ds Maxxed",
    "author": "NotuoDesk",
    "version": (1, 8, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Command Panel",
    "description": "Makes Blender look and work like 3ds Max",
    "category": "Interface",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty, PointerProperty
from . import hsx_import

from . import create, ffd, keymap, max_import, operators, overlay, prims, theme, ui_menus, ui_panel, turbosmooth, updater, viewport_menus, vray, mtl_editor
from . import cut_loop
from . import keyboard_entry
from . import line_tool
from . import poly_tools
from . import freezing, plane_plus
from . import cursor_policy
from . import max_icons
from . import shift_clone
from . import max_export
from . import viewcube
from . import loft
from . import xview
from . import editable_poly
from . import snaps
from . import symmetry
from . import max_rotate, max_gizmos
from . import max_widgets
from . import mode_feedback


_prefs_cache = [None]


def get_prefs():
    """Add-on preferences (cached: this is called on every viewport redraw)."""
    p = _prefs_cache[0]
    if p is not None:
        try:
            p.bl_rna  # still valid?
            return p
        except ReferenceError:
            pass
    addon = bpy.context.preferences.addons.get(__package__)
    _prefs_cache[0] = addon.preferences if addon else None
    return _prefs_cache[0]


def _update_keymap(self, context):
    if self.use_keymap:
        keymap.register_keymaps()
    else:
        keymap.unregister_keymaps()


def _redraw(self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class MaxxedPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    snap_settings: PointerProperty(type=snaps.MaxSnapSettings)

    use_keymap: BoolProperty(name="3ds Max Hotkeys", default=True, update=_update_keymap,
                             description="Use 3ds Max default keyboard shortcuts and mouse navigation")
    show_toolbar: BoolProperty(name="Main Toolbar", default=True, update=_redraw,
                               description="Show the 3ds Max Main Toolbar in the viewport tool header")
    show_statusbar: BoolProperty(name="Status Bar Type-In", default=True, update=_redraw,
                                 description="Show X/Y/Z, Auto Key and Set Key in the status bar")
    show_labels: BoolProperty(name="Viewport Labels", default=True, update=_redraw,
                              description="Draw [+] [Perspective] [Standard] [Default Shading] labels")
    max_menubar: BoolProperty(name="3ds Max Menu Bar", default=True, update=_redraw,
                              description="Replace Blender's top menus and workspace tabs with the 3ds Max menu bar")
    update_repo: StringProperty(name="GitHub Repository", default="retcon26/notuodesk-3ds-maxxed",
                                description="owner/name of the GitHub repository to update from")
    github_token: StringProperty(name="GitHub Token", subtype="PASSWORD", default="",
                                 description="Needed while the repository is private: a fine-grained token "
                                             "with read-only access to Contents of this repository")
    auto_check_updates: BoolProperty(name="Check for Updates on Startup", default=True)
    random_colors: BoolProperty(name="Random Object Colors", default=True,
                                description="Give new objects a random wireframe/object color like 3ds Max")
    first_run_done: BoolProperty(default=False)
    imported_hsx: StringProperty(name="Imported 3ds Max Hotkeys", default="", options={"HIDDEN"})
    auto_pivot_on_create: EnumProperty(name="Auto Pivot on Create", default="OFF",
        items=[("OFF", "Off", "Keep the normal creation pivot"),
               ("BOTTOM", "Bottom", "Bottom center of the world bounding box"),
               ("CENTER", "Center", "Center of the world bounding box")],
        description="Set the pivot when finishing an add-on primitive or spline")
    show_viewcube: BoolProperty(name="Show the ViewCube", default=True, update=viewcube.update)
    viewcube_size: EnumProperty(name="ViewCube Size", items=[(s, s.title(), "") for s in
                                ("TINY", "SMALL", "NORMAL", "LARGE")], default="SMALL", update=viewcube.update)
    viewcube_opacity: EnumProperty(name="Inactive Opacity", items=[(str(n), f"{n}%", "") for n in
                                   (0, 25, 50, 70)], default="50", update=viewcube.update,
                                   description="Inactive opacity, below the fixed 80% active opacity")
    viewcube_snap: BoolProperty(name="Snap to Closest View", default=True)
    viewcube_upright: BoolProperty(name="Keep Scene Upright", default=True)

    def draw(self, context):
        lay = self.layout
        row = lay.row()
        row.scale_y = 1.4
        row.operator("max.apply", text="Apply 3ds Max Look", icon="CHECKMARK")
        row.operator("max.restore", text="Restore Blender Look", icon="LOOP_BACK")
        col = lay.column(heading="Features")
        for p in ("use_keymap", "max_menubar", "show_toolbar", "show_statusbar", "show_labels", "random_colors"):
            col.prop(self, p)
        col.prop(self, "auto_pivot_on_create")
        box = lay.box()
        box.label(text="ViewCube")
        viewcube.draw_settings(box, self)

        updater.draw_update_box(lay, self)
        hsx_import.draw_preferences(lay, self)

        box = lay.box()
        box.label(text="Hotkeys (active while '3ds Max Hotkeys' is on)", icon="KEYINGSET")
        grid = box.grid_flow(columns=3, even_columns=True)
        for keys, what in HOTKEY_CHEATSHEET:
            r = grid.row()
            r.label(text=keys)
            r.label(text=what)


HOTKEY_CHEATSHEET = (
    ("Q / W / E / R", "Select / Move / Rotate / Scale"),
    ("MMB / Alt+MMB", "Pan / Orbit"),
    ("Ctrl+Alt+MMB, Wheel", "Zoom"),
    ("Z / Ctrl+Shift+Z", "Zoom Extents Sel / All"),
    ("Alt+W", "Maximize viewport (quad)"),
    ("Alt+Ctrl+V / H", "ViewCube visibility / Home"),
    ("T F L B K P U C", "Top Front Left Bottom Back Persp User Camera"),
    ("1 2 3 4 5 (6)", "Vertex Edge Border Poly Element (exit)"),
    ("H", "Select From Scene"),
    ("Ctrl+A / D / I", "Select All / None / Invert"),
    ("Ctrl/Alt+Click", "Add / Remove from selection"),
    ("Right-click", "Quad menu"),
    ("Ctrl+Right-click", "Modeling quad menu"),
    ("F3 / F4", "Wireframe / Edged Faces"),
    ("Alt+X", "See-Through"),
    ("Alt+Q", "Isolate Selection"),
    ("G / X / 7", "Grid / Gizmo / Statistics"),
    ("S / A", "Snaps / Angle Snap"),
    ("N / K", "Auto Key / Set Key"),
    ("Ctrl+V", "Clone"),
    ("Ctrl+C", "Camera from view"),
    ("M / 8 / F10", "Material Ed / Environment / Render Setup"),
    ("Shift+Q / F9", "Render"),
    ("F12", "Transform Type-In"),
    ("Ctrl+X", "Expert Mode"),
    ("O", "Adaptive Degradation"),
    ("Shift+E", "Extrude (Edit Poly)"),
    ("Ctrl+Shift+E / C", "Connect / Chamfer"),
    ("Alt+C", "Cut"),
    ("Alt+1", "SwiftLoop"),
    ("Alt+L / Alt+R", "Loop / Ring"),
    ("Backspace", "Remove"),
    ("Ctrl+PgUp/PgDn", "Grow / Shrink"),
    ("PgUp / PgDn", "Select parent / child"),
    (", . Home End /", "Frame -/+ First Last Play"),
)


_classes = (
    snaps.classes + mode_feedback.classes + (MaxxedPreferences,) + max_icons.classes + editable_poly.classes + prims.classes + keyboard_entry.classes + freezing.classes + plane_plus.classes + operators.classes + create.classes + vray.classes + max_import.classes
    + viewport_menus.classes + mtl_editor.classes + updater.classes + turbosmooth.classes + ffd.classes
    + ui_menus.classes + line_tool.classes
    + cut_loop.classes
    + hsx_import.classes
    + poly_tools.classes
    + shift_clone.classes
    + viewcube.classes
    + loft.classes
    + xview.classes
    + symmetry.classes
    + max_rotate.classes + max_gizmos.classes
    + max_widgets.classes
    + ui_panel.classes + tuple(ui_panel.ROLLOUTS)
    + max_export.classes
)


def _first_run():
    """Apply the look the first time the add-on is enabled."""
    p = get_prefs()
    if p is None or p.first_run_done:
        return None
    try:
        bpy.ops.max.apply()
        p.first_run_done = True
    except Exception as exc:
        print(f"[3ds Maxxed] first-run apply failed: {exc}")
    return None


def _unlock_quads_once():
    try:
        operators.unlock_max_workspace_quads()
    except Exception as exc:
        print(f"[3ds Maxxed] unlock quads: {exc}")
    return None


def register():
    max_icons.register()
    for cls in _classes:
        if not shift_clone.retained_class(cls) and not max_rotate.retained_class(cls):
            bpy.utils.register_class(cls)
    shift_clone.register_macros()
    wm = bpy.types.WindowManager
    wm.max_cmd_tab = EnumProperty(name="Command Panel", items=max_icons.enum_items(ui_panel.TABS), default="CREATE", update=mode_feedback.command_tab_changed)
    wm.max_create_cat = EnumProperty(name="Category", items=max_icons.enum_items(ui_panel.CREATE_CATS), default="GEOMETRY")
    wm.max_sublevel = IntProperty(default=0, update=operators.sublevel_changed)
    wm.max_create_sub = EnumProperty(name="Type", items=[("STANDARD", "Standard", ""),
                                    ("EXTENDED", "Extended Primitives", ""), ("VRAY", "V-Ray", ""), ("JOKERMARTINI", "JokerMartini", ""), ("COMPOUND", "Compound Objects", "")])
    editable_poly.register_props()
    editable_poly.target_weld.register_handlers()
    prims.register_props()
    keyboard_entry.register_props()
    poly_tools.register()
    freezing.register_props()
    plane_plus.register_props()
    snaps.register_props()
    max_rotate.register()
    max_gizmos.register()
    max_widgets.set_spinner_policy(lambda context, data, prop: (
        snaps.settings(context).spinner_snap, snaps.settings(context).spinner_increment))
    ui_panel.register_props()
    mode_feedback.register()
    vray.register_props()
    mtl_editor.register_props()
    turbosmooth.register_props()
    ffd.register_props()
    line_tool.register_props()
    max_export.register_props()
    loft.register_props()
    ui_menus.register_draw()
    max_import.register_menus()
    max_export.register_menus()
    overlay.register()
    cursor_policy.register()
    xview.register()
    symmetry.register()
    p = get_prefs()
    if p is None or p.use_keymap:
        keymap.register_keymaps()
    viewcube.register()
    if not bpy.app.background:
        bpy.app.timers.register(_first_run, first_interval=0.5)
        bpy.app.timers.register(_unlock_quads_once, first_interval=1.0)
    updater.register_auto_check()


def unregister():
    symmetry.unregister()
    mode_feedback.unregister()
    cursor_policy.unregister()
    cut_loop.cancel_active()
    viewcube.unregister()
    editable_poly.poly_modal.teardown()
    editable_poly.target_weld.unregister_handlers()
    max_gizmos.cancel_all()
    _prefs_cache[0] = None
    shift_clone.unregister()
    keymap.unregister_keymaps()
    xview.unregister()
    overlay.unregister()
    max_export.unregister_menus()
    max_import.unregister_menus()
    ui_menus.unregister_draw()
    wm = bpy.types.WindowManager
    line_tool.unregister_props()
    max_export.unregister_props()
    loft.unregister_props()
    ffd.unregister_props()
    turbosmooth.unregister_props()
    mtl_editor.unregister_props()
    vray.unregister_props()
    ui_panel.unregister_props()
    freezing.unregister_props()
    plane_plus.unregister_props()
    max_gizmos.unregister()
    max_widgets.set_spinner_policy()
    max_rotate.unregister()
    snaps.unregister_props()
    prims.unregister_props()
    keyboard_entry.unregister_props()
    poly_tools.unregister()
    editable_poly.unregister_props()
    for prop in ("max_cmd_tab", "max_create_cat", "max_create_sub", "max_sublevel"):
        if hasattr(wm, prop):
            delattr(wm, prop)
    for cls in reversed(_classes):
        if not shift_clone.defer_unregister(cls) and not max_rotate.defer_unregister(cls):
            bpy.utils.unregister_class(cls)
    max_icons.unregister()
