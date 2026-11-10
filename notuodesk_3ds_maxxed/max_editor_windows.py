"""Owned auxiliary windows with curated chrome and supported scene controls."""
from dataclasses import dataclass, field

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from . import scene_explorer, max_layers, max_dialogs

TITLES = {
    "MATERIAL": "Compact Material Editor", "RENDER_SETUP": "Render Setup",
    "ENVIRONMENT": "Environment and Effects", "CURVE_EDITOR": "Track View - Curve Editor",
    "DOPE_SHEET": "Track View - Dope Sheet", "SCENE_EXPLORER": "Scene Explorer",
    "SCHEMATIC": "Schematic View", "SCRIPT_EDITOR": "Python Script Editor",
    "LISTENER": "Python Listener", "SNAPS": "Grid and Snap Settings",
}
NATIVE = {"CURVE_EDITOR": "GRAPH_EDITOR", "DOPE_SHEET": "DOPESHEET_EDITOR",
          "SCRIPT_EDITOR": "TEXT_EDITOR", "LISTENER": "CONSOLE"}
_hosts = {}
_docked = {}
_setup_timers = {}
_draw_handles = []
_material_adapter = None
_installed = False
_engine_items = []
_saved_hosts = []


def renderer_items(context=None):
    # Keep strings alive for Blender's dynamic enum storage.
    found = {item.identifier: (item.identifier, item.name, item.description)
             for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    pending = list(bpy.types.RenderEngine.__subclasses__())
    while pending:
        engine = pending.pop()
        pending.extend(engine.__subclasses__())
        if getattr(engine, "is_registered", False) and hasattr(engine, "bl_idname"):
            found[engine.bl_idname] = (engine.bl_idname, engine.bl_label, "Installed renderer")
    if context and context.scene:
        current = context.scene.render.engine
        found.setdefault(current, (current, current, "Current renderer"))
    items = sorted(found.values())
    if items != _engine_items:
        _engine_items[:] = items
    return _engine_items


@dataclass
class EditorHost:
    window: object
    area: object
    kind: str
    scroll: int = 0
    hits: list = field(default_factory=list)
    original_type: str = ""
    ready: bool = False


def register_material_adapter(open_callback=None):
    """Wave 2 supplies the accepted Compact Material Editor host."""
    global _material_adapter
    _material_adapter = open_callback


def available(kind):
    return kind in TITLES and (kind != "MATERIAL" or _material_adapter is not None)


def relationships(scene):
    nodes = sorted(scene.objects, key=lambda obj: obj.name.casefold())
    edges = []
    first_data = {}
    for obj in nodes:
        if obj.parent and obj.parent.name in scene.objects:
            edges.append((obj.parent, obj, "Parent"))
        if obj.data:
            first = first_data.setdefault(obj.data.as_pointer(), obj)
            if first != obj:
                edges.append((first, obj, "Instance data"))
        for constraint in obj.constraints:
            target = getattr(constraint, "target", None)
            if target and target.name in scene.objects:
                edges.append((target, obj, "Constraint"))
        for modifier in obj.modifiers:
            target = getattr(modifier, "object", None)
            if target and target.name in scene.objects:
                edges.append((target, obj, "Modifier target"))
    return nodes, edges


def _live_hosts():
    windows = {w.as_pointer(): w for w in bpy.context.window_manager.windows}
    for pointer, host in list(_hosts.items()):
        if pointer not in windows:
            _dispose_host(host)
            del _hosts[pointer]
    return list(_hosts.values())


def is_host_area(area):
    """Auxiliary canvases are never modeling viewports."""
    pointer = area.as_pointer()
    return pointer in _docked or any(h.area.as_pointer() == pointer for h in _live_hosts())


def _dispose_host(host):
    _cancel_setup(host)
    if host.kind == "MATERIAL":
        from . import mtl_editor
        mtl_editor.close_host(host)


def attach_explorer(context, area):
    """Bind only the supplied dock area. The workspace owner chooses its position."""
    if bpy.app.background or not _installed:
        return False
    if area.as_pointer() in _docked:
        return True
    if area not in list(context.window.screen.areas):
        raise ValueError("Explorer dock must belong to the supplied window")
    host = EditorHost(context.window, area, "SCENE_EXPLORER", original_type=area.type)
    _docked[area.as_pointer()] = host
    _prepare_host(host)
    area.tag_redraw()
    return True


def detach_explorer(area):
    host = _docked.pop(area.as_pointer(), None)
    if host:
        _cancel_setup(host)
        area.type = host.original_type
        area.tag_redraw()


def owned_windows():
    return [host.window for host in _live_hosts()]


def _region(area):
    return next(r for r in area.regions if r.type == "WINDOW")


def _configure(host):
    area, kind = host.area, host.kind
    area.type = NATIVE.get(kind, "VIEW_3D")
    space = area.spaces.active
    for key in ("show_region_ui", "show_region_toolbar", "show_region_tool_header", "show_region_header"):
        if hasattr(space, key):
            setattr(space, key, False)
    if area.type == "VIEW_3D":
        space.overlay.show_overlays = False
        space.show_gizmo = False
    elif kind == "DOPE_SHEET":
        space.mode = "DOPESHEET"
    elif kind == "SCRIPT_EDITOR":
        space.text = bpy.data.texts.get("Maxxed Python") or bpy.data.texts.new("Maxxed Python")
        space.show_line_numbers = True
    elif kind == "LISTENER":
        with bpy.context.temp_override(window=host.window, area=area, region=_region(area)):
            bpy.ops.console.clear(scrollback=True, history=False)


def open_editor(context, kind):
    """Return an owned window, or None when unavailable/background. Never reuse user areas."""
    if not available(kind) or bpy.app.background:
        return None
    if kind == "MATERIAL":
        return _material_adapter(context)
    return open_host(context, kind)


def open_host(context, kind):
    """Create one full-area host. Material adapters use this without recursion."""
    if kind not in TITLES or bpy.app.background or not _installed:
        return None
    for host in _live_hosts():
        if host.kind == kind:
            return host.window
    source = context.area or (max(context.window.screen.areas, key=lambda a: a.width*a.height)
                              if context.window else None)
    if not source:
        return None
    before = {w.as_pointer() for w in context.window_manager.windows}
    with context.temp_override(window=context.window, area=source, region=_region(source)):
        result = bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
    if result != {"FINISHED"}:
        return None
    added = [w for w in context.window_manager.windows if w.as_pointer() not in before]
    if len(added) != 1:
        return None
    window = added[0]
    area = max(window.screen.areas, key=lambda a: a.width*a.height)
    host = EditorHost(window, area, kind)
    _hosts[window.as_pointer()] = host
    try:
        _prepare_host(host)
        area.tag_redraw()
    except Exception:
        close_editor(window)
        raise
    return window


def _start_interaction(context, host):
    with context.temp_override(window=host.window, area=host.area, region=_region(host.area)):
        bpy.ops.max.editor_interact("INVOKE_DEFAULT")


def _cancel_setup(host):
    callback = _setup_timers.pop(host.area.as_pointer(), None)
    if callback and bpy.app.timers.is_registered(callback):
        bpy.app.timers.unregister(callback)


def _prepare_host(host):
    """Configure the initialized area before returning it to callers."""
    # WM_window_open refreshes the duplicated screen before area_dupli returns.
    # Use its owning context so area-type updates initialize the correct regions.
    with bpy.context.temp_override(window=host.window, area=host.area):
        _configure(host)
        if host.kind == "MATERIAL":
            from . import mtl_editor
            mtl_editor.prepare_host(host, bpy.context)
        _start_interaction(bpy.context, host)
        host.ready = True
        host.area.tag_redraw()


def close_editor(window):
    pointer = window.as_pointer()
    host = _hosts.pop(pointer, None)
    if not host:
        return
    _dispose_host(host)
    windows = list(bpy.context.window_manager.windows)
    if pointer in {w.as_pointer() for w in windows}:
        fallback = next((w for w in windows if w != window and w.as_pointer() not in _hosts), None)
        fallback = fallback or next((w for w in windows if w != window), None)
        if fallback is None:
            raise RuntimeError("An editor must not close the last application window")
        # The inner override must restore a live window, including calls from timers.
        # Blender cannot restore a context whose original window was just removed.
        with bpy.context.temp_override(window=fallback):
            with bpy.context.temp_override(window=window):
                bpy.ops.wm.window_close()


@persistent
def close_all(*_):
    for host in list(_live_hosts()):
        close_editor(host.window)
    live_areas = {a.as_pointer(): a for w in bpy.context.window_manager.windows for a in w.screen.areas}
    for pointer in list(_docked):
        if pointer in live_areas:
            detach_explorer(live_areas[pointer])
        else:
            _docked.pop(pointer, None)


@persistent
def _before_save(*_):
    _saved_hosts[:] = [(host.kind, None) for host in _live_hosts()]
    _saved_hosts.extend(("DOCK", host.area) for host in _docked.values())
    close_all()


@persistent
def _after_save(*_):
    pending = list(_saved_hosts)
    _saved_hosts.clear()
    windows = list(bpy.context.window_manager.windows)
    if not windows:
        return
    window = windows[0]
    area = max(window.screen.areas, key=lambda a: a.width*a.height)
    with bpy.context.temp_override(window=window, area=area, region=_region(area)):
        for kind, dock in pending:
            if kind == "DOCK":
                if dock in list(window.screen.areas):
                    attach_explorer(bpy.context, dock)
            else:
                open_editor(bpy.context, kind)


def _op(name, **kwargs):
    def invoke(context, event):
        category, operation = name.split(".", 1)
        return getattr(getattr(bpy.ops, category), operation)("INVOKE_DEFAULT", **kwargs)
    return invoke


def _text(x, y, text, size=13, color=(.87, .87, .87, 1)):
    import blf
    blf.size(0, size)
    blf.position(0, x, y, 0)
    blf.color(0, *color)
    blf.draw(0, str(text))


def _rect(x, y, width, height, color):
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, "TRIS", {"pos": [(x, y), (x+width, y), (x+width, y+height),
                                               (x, y), (x+width, y+height), (x, y+height)]}).draw(shader)


def _line(a, b, color=(.45, .65, .8, 1)):
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": [a, b]}).draw(shader)


def _button(host, x, y, width, text, callback, selected=False, scale=1):
    height = 24 * scale
    _rect(x, y, width, height, (.22, .34, .4, 1) if selected else (.27, .27, .27, 1))
    import blf
    size = round(12*scale)
    blf.size(0, size)
    original = text
    end = len(original)
    while end > 0 and blf.dimensions(0, text)[0] > width-12*scale:
        end -= 1
        text = original[:end] + ("..." if end else "")
    _text(x+6*scale, y+7*scale, text, size)
    host.hits.append(((x, y, x+width, y+height), callback))


def _draw_explorer(host, context, width, height, scale):
    s = scale
    narrow = width < 700*s
    y = height - 78*s
    search = context.window_manager.max_explorer_search
    search_width = min(230*s, max(35*s, width-150*s))
    _button(host, 10*s, y, search_width, "Search: " + (search or "All objects"), _op("max.explorer_action", action="SEARCH"), scale=s)
    _button(host, search_width+15*s, y, 55*s, "Clear", _op("max.explorer_action", action="CLEAR"), scale=s)
    _button(host, search_width+75*s, y, 65*s, "Layers", _op("max.layer_dialog"), scale=s)
    y -= 30*s
    _text(14*s, y, "Name / Hierarchy", round(12*s))
    _text(max(85*s, width-105*s) if narrow else max(240*s, width-310*s), y, "Hide    Freeze" if narrow else "Layer        Hide     Freeze     Rename", round(12*s))
    rows = scene_explorer.scene_rows(context, search)
    capacity = max(1, int((height-240*s)/(29*s)))
    host.scroll = min(host.scroll, max(0, len(rows)-capacity))
    for entry in rows[host.scroll:host.scroll+capacity]:
        y -= 29*s
        obj = entry.obj
        collapsed = bool(obj.get("max_explorer_collapsed"))
        x = 10*s + (min(entry.depth, 1)*10*s if narrow else entry.depth*16*s)
        _button(host, x, y, 22*s, "+" if collapsed else "-", _op("max.explorer_action", action="EXPAND", object_name=obj.name, value=collapsed), scale=s)
        name_width = max(20*s, max(85*s, width-105*s)-x-29*s) if narrow else max(70*s, width-350*s-x)
        _button(host, x+24*s, y, name_width, obj.name, _op("max.explorer_action", action="SELECT", object_name=obj.name), obj.select_get(), s)
        x = max(85*s, width-105*s) if narrow else max(240*s, width-310*s)
        layer = max_layers.membership(context.scene, obj)
        if not narrow:
            _text(x, y+7*s, max_layers.label(layer)[:12], round(12*s))
        _button(host, x+(0 if narrow else 85)*s, y, 42*s if narrow else 52*s, "Hide", _op("max.explorer_action", action="HIDE", object_name=obj.name, value=not obj.hide_get()), obj.hide_get(), s)
        _button(host, x+(45 if narrow else 140)*s, y, 55*s if narrow else 60*s, "Freeze", _op("max.explorer_action", action="FREEZE", object_name=obj.name, value=not obj.max_frozen), obj.max_frozen, s)
        if not narrow:
            _button(host, x+205*s, y, 74*s, "Rename", _op("max.explorer_action", action="RENAME", object_name=obj.name), scale=s)
    y = 90*s
    _text(14*s, y+36*s, "Layers (separate from groups and hierarchy)", round(12*s))
    for layer in ([] if narrow else max_layers.catalogue(context.scene)[:2]):
        _text(14*s, y+7*s, max_layers.label(layer), round(12*s))
        x = 180*s
        for action, label, value in (("HIDE", "Hide", not layer.get("max_layer_hidden", False)),
                                     ("FREEZE", "Freeze", not layer.get("max_layer_frozen", False)),
                                     ("ASSIGN", "Move Selection", True), ("REMOVE", "Delete", True)):
            _button(host, x, y, 110*s, label, _op("max.layer_action", action=action, layer_id=layer[max_layers.MARKER], value=value), scale=s)
            x += 115*s
        y -= 28*s
    footer_width = max(60*s, (width-30*s)/2) if narrow else 140*s
    _button(host, 10*s, 20*s, footer_width, "Select From Scene", _op("max.scene_selection_dialog"), scale=s)
    _button(host, footer_width+15*s, 20*s, footer_width if narrow else 120*s, "Hide by Name", _op("max.scene_selection_dialog", hide=True), scale=s)
    _button(host, 10*s if narrow else 310*s, 52*s if narrow else 20*s, 150*s, "Move to Layer 0", _op("max.layer_action", action="ASSIGN"), scale=s)
    if narrow and context.active_object:
        _button(host, 165*s, 52*s, 95*s, "Rename", _op("max.explorer_action", action="RENAME", object_name=context.active_object.name), scale=s)


def _draw_schematic(host, context, width, height, scale):
    s = scale
    nodes, edges = relationships(context.scene)
    positions = {}
    for i, obj in enumerate(nodes):
        depth = max_dialogs._depth(obj)
        positions[obj] = (40*s + min(depth, 3)*180*s, height-110*s-i*65*s+host.scroll*40*s)
    for source, target, label in edges:
        a, b = positions[source], positions[target]
        if 65*s < a[1] < height-50*s and 65*s < b[1] < height-50*s:
            _line((a[0]+145*s, a[1]+12*s), (b[0], b[1]+12*s))
            _text((a[0]+b[0])/2+155*s, (a[1]+b[1])/2+15*s, label, round(11*s))
    for obj, (x, y) in positions.items():
        if 65*s < y < height-50*s:
            _button(host, x, y, 145*s, obj.name, _op("max.explorer_action", action="SELECT", object_name=obj.name), obj.select_get(), s)
    _rect(0, 0, width, 58*s, (.16, .16, .16, 1))
    _button(host, 10*s, 15*s, 175*s, "Link to Active Object", _op("max.relationship_link"), scale=s)
    _button(host, 195*s, 15*s, 100*s, "Unlink", _op("max.relationship_link", unlink=True), scale=s)
    _text(310*s, 23*s, "Ctrl-click nodes to select. Lines describe supported relationships.", round(11*s))


def _draw_settings(host, context, width, height, scale):
    s = scale
    y = height-85*s
    if host.kind == "RENDER_SETUP":
        scene, render = context.scene, context.scene.render
        groups = [("Common", [("Renderer", render.engine), ("Output Size", f"{render.resolution_x} x {render.resolution_y} ({render.resolution_percentage}%)"),
                             ("Time Output", f"{scene.frame_start} to {scene.frame_end}"), ("Output Path", render.filepath),
                             ("Format", render.image_settings.file_format)]),
                  ("Render Elements", [("Z Depth", context.view_layer.use_pass_z), ("Normal", context.view_layer.use_pass_normal)])]
        operation = "max.render_setup_dialog"
    elif host.kind == "ENVIRONMENT":
        world = context.scene.world
        background = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None) if world and world.use_nodes else None
        groups = [("Environment", [("Background", world.name if world else "No environment"),
                                  ("Color", tuple(round(v, 3) for v in world.color) if world else "None"),
                                  ("Strength", background.inputs["Strength"].default_value if background else "Color environment")]),
                  ("Exposure", [("Exposure", context.scene.view_settings.exposure), ("Gamma", context.scene.view_settings.gamma)]),
                  ("Effects", [("Atmospheric effects", "Use renderer-supported world nodes")])]
        operation = "max.environment_dialog"
    else:
        from . import snaps
        settings = snaps.settings(context)
        if not settings:
            _text(15*s, y, "Snap settings unavailable", round(13*s))
            return
        for index, (tab, text) in enumerate((("SNAPS", "Snaps"), ("OPTIONS", "Options"), ("HOME", "Home Grid"), ("USER", "User Grids"))):
            def select_page(context, event, tab=tab):
                snaps.settings(context).tab = tab
            _button(host, 15*s+index*125*s, y, 120*s, text, select_page, settings.tab == tab, s)
        y -= 35*s
        keys = {
            "SNAPS": ("mode", "grid_points", "grid_lines", "vertex", "edge", "face", "pivot", "midpoint", "endpoint", "center_face"),
            "OPTIONS": ("marker", "marker_size", "rubber_band", "snap_radius", "preview_radius", "snap_frozen", "axis_constraints", "angle", "percent", "spinner_increment"),
            "HOME": ("grid_spacing", "major_lines", "grid_extent", "inhibit_subdivision", "inhibit_resize", "grid_update"),
            "USER": ("shape_angle", "activate_grids", "autogrid_space"),
        }[settings.tab]
        groups = [(dict(SNAPS="Snaps", OPTIONS="Options", HOME="Home Grid", USER="User Grids")[settings.tab],
                   [(settings.bl_rna.properties[key].name, getattr(settings, key)) for key in keys])]
        operation = "max.snap_host_page"
    for title, values in groups:
        _text(20*s, y, title, round(15*s))
        y -= 33*s
        for label, value in values:
            _text(35*s, y, label, round(12*s))
            _text(min(width*.46, 340*s), y, str(value), round(12*s))
            y -= 27*s
        y -= 12*s
    _button(host, 20*s, 20*s, 160*s, "Edit Settings", _op(operation), scale=s)


def _draw():
    context = bpy.context
    if not context.window or not context.area or not context.region:
        return
    host = _docked.get(context.area.as_pointer()) or _hosts.get(context.window.as_pointer())
    if not host or not host.ready or host.area != context.area or context.region.type != "WINDOW":
        return
    import gpu
    scale = context.preferences.view.ui_scale
    width, height = context.region.width, context.region.height
    host.hits.clear()
    gpu.state.blend_set("ALPHA")
    try:
        if host.kind not in NATIVE:
            _rect(0, 0, width, height, (.18, .18, .18, 1))
        _rect(0, height-38*scale, width, 38*scale, (.12, .12, .12, 1))
        _text(14*scale, height-25*scale, TITLES[host.kind], round(15*scale))
        close = (lambda c, e: detach_explorer(host.area)) if host.original_type else (lambda c, e: close_editor(host.window))
        small = width < 300*scale
        _button(host, width-(35 if small else 90)*scale, height-32*scale, (25 if small else 78)*scale, "X" if small else "Close", close, scale=scale)
        if host.kind == "SCENE_EXPLORER":
            _draw_explorer(host, context, width, height, scale)
        elif host.kind == "MATERIAL":
            from . import mtl_editor
            mtl_editor.draw_host(host, context, width, height, scale)
        elif host.kind == "SCHEMATIC":
            _draw_schematic(host, context, width, height, scale)
        elif host.kind in {"RENDER_SETUP", "ENVIRONMENT", "SNAPS"}:
            _draw_settings(host, context, width, height, scale)
        elif host.kind == "SCRIPT_EDITOR":
            _button(host, width-220*scale, height-32*scale, 115*scale, "Run Python", _op("text.run_script"), scale=scale)
    finally:
        gpu.shader.unbind()
        gpu.state.blend_set("NONE")


class MAX_OT_editor_interact(bpy.types.Operator):
    """Operate the curated auxiliary window. Escape closes this owned window"""
    bl_idname = "max.editor_interact"
    bl_label = "Maxxed Editor"

    def invoke(self, context, event):
        self._pointer = context.window.as_pointer()
        self._area_pointer = context.area.as_pointer()
        if self._pointer not in _hosts and self._area_pointer not in _docked:
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        host = _docked.get(self._area_pointer) or _hosts.get(self._pointer)
        if not host:
            return {"FINISHED", "PASS_THROUGH"}
        if not context.window or context.window.as_pointer() != self._pointer:
            return {"PASS_THROUGH"}
        if host.kind == "MATERIAL":
            from . import mtl_editor
            if mtl_editor.host_event(host, context, event):
                return {"RUNNING_MODAL"}
        if host.original_type:
            region = _region(host.area)
            if not (region.x <= event.mouse_x < region.x+region.width and region.y <= event.mouse_y < region.y+region.height):
                return {"PASS_THROUGH"}
        if event.type == "ESC" and event.value == "PRESS":
            if host.original_type:
                return {"PASS_THROUGH"}
            close_editor(host.window)
            return {"FINISHED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            for (x1, y1, x2, y2), callback in reversed(host.hits):
                if x1 <= event.mouse_region_x <= x2 and y1 <= event.mouse_region_y <= y2:
                    callback(context, event)
                    if self._pointer in _hosts or self._area_pointer in _docked:
                        host.area.tag_redraw()
                        return {"RUNNING_MODAL"}
                    return {"FINISHED"}
        if host.kind not in NATIVE:
            if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
                host.scroll = max(0, host.scroll + (1 if event.type == "WHEELDOWNMOUSE" else -1))
                host.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


class MAX_OT_editor_window(bpy.types.Operator):
    """Open an independent Maxxed editor without replacing a user workspace"""
    bl_idname = "max.editor_window"
    bl_label = "Open Editor"
    editor: EnumProperty(items=[(kind, title, "") for kind, title in TITLES.items()])

    def execute(self, context):
        window = open_editor(context, self.editor)
        if not window:
            self.report({"WARNING"}, "This editor is unavailable in the current host")
            return {"CANCELLED"}
        return {"FINISHED"}


class MAX_OT_relationship_link(bpy.types.Operator):
    """Link selected objects to the active parent, or unlink without moving geometry"""
    bl_idname = "max.relationship_link"
    bl_label = "Link Objects"
    bl_options = {"REGISTER", "UNDO"}
    unlink: BoolProperty(default=False)

    def execute(self, context):
        target = None if self.unlink else context.view_layer.objects.active
        objects = [obj for obj in context.selected_objects if self.unlink or obj != target]
        if not objects or (not self.unlink and not target):
            return {"CANCELLED"}
        try:
            scene_explorer.reparent(context, objects, target)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class MAX_OT_render_setup_dialog(bpy.types.Operator):
    """Edit supported Common and Render Elements settings"""
    bl_idname = "max.render_setup_dialog"
    bl_label = "Render Setup"
    bl_options = {"REGISTER", "UNDO"}
    width: IntProperty(name="Width", default=1920, min=4, max=65536)
    height: IntProperty(name="Height", default=1080, min=4, max=65536)
    percentage: IntProperty(name="Output Size (%)", default=100, min=1, max=100)
    start: IntProperty(name="From", default=1)
    end: IntProperty(name="To", default=250)
    output: StringProperty(name="Output Path")
    depth: BoolProperty(name="Z Depth")
    normal: BoolProperty(name="Normal")
    engine: EnumProperty(name="Renderer", items=lambda self, context: renderer_items(context))
    format: EnumProperty(name="Output Format", items=[(item.identifier, item.name, item.description)
        for item in bpy.types.ImageFormatSettings.bl_rna.properties["file_format"].enum_items])

    def invoke(self, context, event):
        render = context.scene.render
        self.width, self.height, self.percentage = render.resolution_x, render.resolution_y, render.resolution_percentage
        self.start, self.end = context.scene.frame_start, context.scene.frame_end
        self.output = render.filepath
        self.depth, self.normal = context.view_layer.use_pass_z, context.view_layer.use_pass_normal
        self.engine, self.format = render.engine, render.image_settings.file_format
        return context.window_manager.invoke_props_dialog(self, width=430, confirm_text="Apply")

    def draw(self, context):
        self.layout.prop(self, "engine")
        box = self.layout.box()
        box.label(text="Common")
        for prop in ("width", "height", "percentage", "start", "end", "output"):
            box.prop(self, prop)
        box.prop(self, "format")
        box = self.layout.box()
        box.label(text="Render Elements")
        box.prop(self, "depth")
        box.prop(self, "normal")

    def execute(self, context):
        if self.end < self.start:
            self.report({"WARNING"}, "Time Output end must not precede its start")
            return {"CANCELLED"}
        render = context.scene.render
        render.engine = self.engine
        render.resolution_x, render.resolution_y, render.resolution_percentage = self.width, self.height, self.percentage
        context.scene.frame_start, context.scene.frame_end = self.start, self.end
        render.filepath = self.output
        render.image_settings.file_format = self.format
        context.view_layer.use_pass_z, context.view_layer.use_pass_normal = self.depth, self.normal
        return {"FINISHED"}


class MAX_OT_environment_dialog(bpy.types.Operator):
    """Edit supported environment background and color-management exposure"""
    bl_idname = "max.environment_dialog"
    bl_label = "Environment and Effects"
    bl_options = {"REGISTER", "UNDO"}
    color: FloatVectorProperty(name="Background Color", subtype="COLOR", size=3, min=0, max=1)
    strength: FloatProperty(name="Background Strength", min=0, default=1)
    exposure: FloatProperty(name="Exposure", min=-32, max=32)
    gamma: FloatProperty(name="Gamma", min=.01, max=5, default=1)

    def invoke(self, context, event):
        world = context.scene.world
        node = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None) if world and world.use_nodes else None
        self.color = tuple(node.inputs["Color"].default_value[:3]) if node else world.color if world else (0, 0, 0)
        self.strength = node.inputs["Strength"].default_value if node else 1
        self.exposure, self.gamma = context.scene.view_settings.exposure, context.scene.view_settings.gamma
        return context.window_manager.invoke_props_dialog(self, width=430, confirm_text="Apply")

    def draw(self, context):
        box = self.layout.box()
        box.label(text="Environment")
        box.prop(self, "color")
        box.prop(self, "strength")
        box = self.layout.box()
        box.label(text="Exposure")
        box.prop(self, "exposure")
        box.prop(self, "gamma")
        box = self.layout.box()
        box.label(text="Effects")
        box.label(text="Atmospheric effects require renderer world nodes.")

    def execute(self, context):
        world = context.scene.world
        if world and world.library:
            self.report({"WARNING"}, "Linked environment data is read-only")
            return {"CANCELLED"}
        node = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None) if world and world.use_nodes else None
        if world and world.use_nodes and (not node or node.inputs["Color"].is_linked or node.inputs["Strength"].is_linked):
            self.report({"WARNING"}, "Edit this environment's connected world nodes directly")
            return {"CANCELLED"}
        if world is None:
            world = context.scene.world = bpy.data.worlds.new("Environment")
        world.color = self.color
        if not world.use_nodes:
            world.use_nodes = True
            node = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if node:
            node.inputs["Color"].default_value = (*self.color, 1)
            node.inputs["Strength"].default_value = self.strength
        context.scene.view_settings.exposure, context.scene.view_settings.gamma = self.exposure, self.gamma
        return {"FINISHED"}


class MAX_OT_snap_host_page(bpy.types.Operator):
    """Edit the active Grid and Snap Settings page"""
    bl_idname = "max.snap_host_page"
    bl_label = "Grid and Snap Settings"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=460)

    def draw(self, context):
        from . import snaps
        settings = snaps.settings(context)
        if settings:
            snaps.draw_settings(self.layout, context, settings.tab)

    def execute(self, context):
        return {"FINISHED"}


classes = (MAX_OT_editor_interact, MAX_OT_editor_window, MAX_OT_relationship_link,
           MAX_OT_render_setup_dialog, MAX_OT_environment_dialog, MAX_OT_snap_host_page)


def install():
    global _installed
    if _installed:
        return
    for cls in classes:
        bpy.utils.register_class(cls)
    if not bpy.app.background:
        for space in (bpy.types.SpaceView3D, bpy.types.SpaceGraphEditor, bpy.types.SpaceDopeSheetEditor,
                      bpy.types.SpaceTextEditor, bpy.types.SpaceConsole):
            _draw_handles.append((space, space.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")))
    bpy.app.handlers.load_pre.append(close_all)
    bpy.app.handlers.save_pre.append(_before_save)
    bpy.app.handlers.save_post.append(_after_save)
    if hasattr(bpy.app.handlers, "save_post_fail"):
        bpy.app.handlers.save_post_fail.append(_after_save)
    _installed = True


def uninstall():
    global _installed
    close_all()
    if _installed:
        bpy.app.handlers.load_pre.remove(close_all)
        bpy.app.handlers.save_pre.remove(_before_save)
        bpy.app.handlers.save_post.remove(_after_save)
        if hasattr(bpy.app.handlers, "save_post_fail"):
            bpy.app.handlers.save_post_fail.remove(_after_save)
        for space, handle in _draw_handles:
            space.draw_handler_remove(handle, "WINDOW")
        _draw_handles.clear()
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        _installed = False
    _saved_hosts.clear()
    register_material_adapter(None)
