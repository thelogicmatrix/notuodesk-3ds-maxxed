"""Max snap settings, magnetic picking and base-point transforms."""

import math

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane, intersect_point_line


TYPES = (
    ("grid_points", "Grid Points"), ("pivot", "Pivot"),
    ("perpendicular", "Perpendicular"), ("bounding_box", "Bounding Box"),
    ("tangent", "Tangent"), ("vertex", "Vertex"),
    ("endpoint", "Endpoint"), ("edge", "Edge/Segment"),
    ("midpoint", "Midpoint"), ("face", "Face"),
    ("center_face", "Center Face"), ("grid_lines", "Grid Lines"),
)
MODES = [("2D", "2D", "Active construction grid only"),
         ("2_5D", "2.5D", "Project snap targets onto the construction plane"),
         ("3D", "3D", "Snap directly to geometry in three dimensions")]
TABS = [("SNAPS", "Snaps", ""), ("OPTIONS", "Options", ""),
        ("HOME", "Home Grid", ""), ("USER", "User Grids", "")]
_preview = {}
_handle = None
_spinner_busy = False
_spinner_values = {}
_context_pending = False


def settings(context):
    return context.preferences.addons[__package__].preferences.snap_settings


def _redraw(context):
    if context.window_manager:
        for w in context.window_manager.windows:
            for area in w.screen.areas:
                area.tag_redraw()


def _radii(self, context):
    if self.preview_radius < self.snap_radius:
        self.preview_radius = self.snap_radius
    _redraw(context)


def _preview_radius(self, context):
    if self.snap_radius > self.preview_radius:
        self.snap_radius = self.preview_radius
    _redraw(context)


def _grid(self, context):
    if context.window_manager:
        for w in context.window_manager.windows:
            for area in w.screen.areas:
                if area.type == "VIEW_3D":
                    ov = area.spaces.active.overlay
                    ov.grid_scale = self.grid_spacing
                    ov.grid_subdivisions = self.major_lines
    _redraw(context)


class MaxSnapSettings(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Snaps Toggle", items=MODES, default="3D")
    grid_points: BoolProperty(name="Grid Points", default=True)
    pivot: BoolProperty(name="Pivot")
    perpendicular: BoolProperty(name="Perpendicular")
    bounding_box: BoolProperty(name="Bounding Box")
    tangent: BoolProperty(name="Tangent", description="Analytic spline tangent snapping is not available")
    vertex: BoolProperty(name="Vertex")
    endpoint: BoolProperty(name="Endpoint")
    edge: BoolProperty(name="Edge/Segment")
    midpoint: BoolProperty(name="Midpoint")
    face: BoolProperty(name="Face")
    center_face: BoolProperty(name="Center Face")
    grid_lines: BoolProperty(name="Grid Lines")
    marker: BoolProperty(name="Display", default=True)
    marker_size: IntProperty(name="Size", default=20, min=2, max=100)
    rubber_band: BoolProperty(name="Display Rubber Band", default=True)
    preview_radius: IntProperty(name="Snap Preview Radius", default=30, min=1, max=500, update=_preview_radius)
    snap_radius: IntProperty(name="Snap Radius", default=20, min=1, max=500, update=_radii)
    angle: FloatProperty(name="Angle", default=5.0, min=.001, max=180, precision=1)
    percent: FloatProperty(name="Percent", default=10.0, min=.001, max=1000, precision=1)
    angle_snap: BoolProperty(name="Angle Snap Toggle")
    percent_snap: BoolProperty(name="Percent Snap Toggle")
    spinner_snap: BoolProperty(name="Spinner Snap Toggle", default=True)
    spinner_increment: FloatProperty(name="Snap", default=1.0, min=.0001)
    snap_frozen: BoolProperty(name="Snap to frozen objects", default=False)
    axis_constraints: BoolProperty(name="Use Axis Constraints", default=True)
    grid_spacing: FloatProperty(name="Grid Spacing", default=10, min=.0001, unit="LENGTH", update=_grid)
    major_lines: IntProperty(name="Major Lines every Nth Grid Line", default=10, min=2, max=100, update=_grid)
    grid_extent: IntProperty(name="Perspective View Grid Extent", default=7, min=1, max=1000)
    inhibit_subdivision: BoolProperty(name="Inhibit Grid Subdivision Below Grid Spacing", default=True)
    activate_grids: BoolProperty(name="Activate grids when creating")
    autogrid_space: EnumProperty(items=[("WORLD", "World space", ""), ("OBJECT", "Object space", "")])
    override: EnumProperty(name="Snap Override", items=[("NONE", "Override OFF", ""), ("OFF", "None", "")] + [(k, n, "") for k, n in TYPES],
                           default="NONE", options={"SKIP_SAVE"})
    last_override: EnumProperty(items=[("NONE", "None", "")] + [(k, n, "") for k, n in TYPES],
                                default="NONE", options={"SKIP_SAVE"})


def snap_angle(settings, angle):
    step = math.radians(settings.angle)
    return round(angle / step) * step if settings.angle_snap else angle


def snap_scale(settings, factor):
    step = settings.percent / 100
    return 1 + round((factor - 1) / step) * step if settings.percent_snap else factor


def _plane(plane):
    origin, normal = plane
    normal = Vector(normal).normalized()
    u = Vector((1, 0, 0)) if abs(normal.x) < .9 else Vector((0, 1, 0))
    u = (u - normal * u.dot(normal)).normalized()
    return Vector(origin), normal, u, normal.cross(u)


def _project(point, plane):
    origin, n = plane[:2]
    return point - n * (point - origin).dot(n)


def _screen(region, rv3d, p):
    return view3d_utils.location_3d_to_region_2d(region, rv3d, p)


def _edge_point(region, rv3d, co, a, b):
    """Closest screen point on a segment, with perspective-correct interpolation."""
    pa, pb = _screen(region, rv3d, a), _screen(region, rv3d, b)
    if pa is None or pb is None:
        return None
    d = pb - pa
    t = max(0, min(1, (Vector(co) - pa).dot(d) / d.length_squared)) if d.length_squared else 0
    wa = (rv3d.perspective_matrix @ a.to_4d()).w
    wb = (rv3d.perspective_matrix @ b.to_4d()).w
    den = (1 - t) * wb + t * wa
    if abs(den) > 1e-10:
        t = t * wa / den
    return a.lerp(b, t)


def _geometry(context, region, rv3d, co, enabled, objects, base=None, source=False):
    if not enabled - {"grid_points", "grid_lines", "tangent", "OFF"}:
        return
    deps = context.evaluated_depsgraph_get()
    for ob in objects:
        if ob is None or not ob.visible_get():
            continue
        s = settings(context)
        if not source and ob.hide_select and not s.snap_frozen:
            continue
        mw = ob.matrix_world
        if "pivot" in enabled:
            yield mw.translation.copy(), "pivot"
        if "bounding_box" in enabled and ob.type != "EMPTY":
            for v in ob.bound_box:
                yield mw @ Vector(v), "bounding_box"
        if not enabled & {"vertex", "endpoint", "edge", "midpoint", "perpendicular", "face", "center_face"}:
            continue
        if ob.type not in {"MESH", "CURVE", "SURFACE", "FONT"}:
            continue
        edit = ob.type == "MESH" and ob.mode == "EDIT"
        eo = None
        if edit:
            bm = bmesh.from_edit_mesh(ob.data)
            verts = [v for v in bm.verts if not v.hide]
            coords = {v: mw @ v.co for v in verts}
            if source:
                coords = {v: p for v, p in coords.items() if v.select}
            else:
                coords = {v: p for v, p in coords.items() if not v.select}
            if "vertex" in enabled or "endpoint" in enabled:
                for p in coords.values():
                    yield p, "vertex" if "vertex" in enabled else "endpoint"
            edges = [(coords[e.verts[0]], coords[e.verts[1]]) for e in bm.edges
                     if not e.hide and all(v in coords for v in e.verts)]
            if "center_face" in enabled:
                for f in bm.faces:
                    if not f.hide and all(v in coords for v in f.verts):
                        yield mw @ f.calc_center_median(), "center_face"
        else:
            eo = ob.evaluated_get(deps)
            mesh = eo.to_mesh()
            if mesh is None:
                continue
            try:
                coords = [mw @ v.co for v in mesh.vertices]
                if "vertex" in enabled or "endpoint" in enabled:
                    for p in coords:
                        yield p, "vertex" if "vertex" in enabled else "endpoint"
                edges = [(coords[e.vertices[0]], coords[e.vertices[1]]) for e in mesh.edges]
                if "center_face" in enabled:
                    mesh.calc_loop_triangles()
                    for tri in mesh.loop_triangles:
                        yield sum((coords[i] for i in tri.vertices), Vector()) / 3, "center_face"
            finally:
                eo.to_mesh_clear()
        for a, b in edges:
            if "midpoint" in enabled:
                yield (a + b) * .5, "midpoint"
            if "edge" in enabled:
                p = _edge_point(region, rv3d, co, a, b)
                if p is not None:
                    yield p, "edge"
            if "perpendicular" in enabled and base is not None and (b - a).length_squared:
                p, t = intersect_point_line(base, a, b)
                if 0 <= t <= 1:
                    yield p, "perpendicular"
        if "face" in enabled and not source and eo is not None:
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
            inv = mw.inverted_safe()
            hit, loc, normal, _ = eo.ray_cast(inv @ origin, inv.to_3x3() @ direction)
            if hit and normal.dot(inv.to_3x3() @ direction) < 0:
                yield mw @ loc, "face"


def _pick(context, region, rv3d, co, point, plane, enabled, objects, base=None,
          axis=None, pixels_per_unit=None, source=False):
    s = settings(context)
    origin, n, u, v = _plane(plane)
    plane = (origin, n)
    candidates = []
    if {"grid_points", "grid_lines"} & enabled:
        spacing = s.grid_spacing
        # Anchor grid lines to world zero, not the start of the current drag.
        p = _project(point, plane)
        a, b = p.dot(u), p.dot(v)
        au, bv = round(a / spacing) * spacing, round(b / spacing) * spacing
        anchor = n * origin.dot(n)
        if axis is not None:
            axis = Vector(axis).normalized()
            level = point.dot(axis)
            p = point + axis * (round(level / spacing) * spacing - level)
            if "grid_points" in enabled:
                candidates.append((p, "grid_points"))
        else:
            if "grid_points" in enabled:
                candidates.append((anchor + u * au + v * bv, "grid_points"))
            if "grid_lines" in enabled:
                candidates.extend(((anchor + u * au + v * b, "grid_lines"),
                                   (anchor + u * a + v * bv, "grid_lines")))
    if s.mode != "2D" or source:
        candidates.extend(_geometry(context, region, rv3d, co, enabled, objects, base, source))
    best, rank = None, (float("inf"), 9)
    for p, kind in candidates:
        if s.mode == "2_5D" and not source and not (axis is not None and kind == "grid_points"):
            p = _project(p, plane)
        if axis is not None and base is not None and s.axis_constraints:
            p = base + axis * (p - base).dot(axis)
        xy = _screen(region, rv3d, p)
        if xy is None:
            continue
        if pixels_per_unit is not None and axis is not None and kind == "grid_points":
            distance = (p - point).length * pixels_per_unit
        else:
            distance = (xy - Vector(co)).length
        key = (round(distance, 5), 1 if kind.startswith("grid_") else 0)
        if distance <= s.preview_radius and key < rank:
            rank, best = key, (p.copy(), kind, distance)
    return best


def snap_point(context, region, rv3d, co, point, plane, *, exclude=(), base=None,
               axis=None, pixels_per_unit=None):
    """Magnetically snap a world point within Snap Radius screen pixels.

    `co` is region-relative. `plane` is (world origin, world normal).
    Exclude the object being created or transformed. For height creation pass
    `axis`, and pixels_per_unit when that axis points at the viewer.
    The returned Vector stays unchanged outside the radius. Preview never rounds.
    """
    point = Vector(point)
    s = settings(context)
    if not context.scene.tool_settings.use_snap and s.override == "NONE":
        clear_preview(region)
        return point
    if s.override == "OFF":
        clear_preview(region)
        return point
    enabled = {s.override} if s.override != "NONE" else {k for k, _ in TYPES if getattr(s, k)}
    excluded = set(exclude)
    objects = [ob for ob in context.view_layer.objects if ob not in excluded]
    hit = _pick(context, region, rv3d, co, point, plane, enabled, objects, base,
                axis, pixels_per_unit)
    key = region.as_pointer() if hasattr(region, "as_pointer") else id(region)
    _preview[key] = (hit, Vector(base) if base is not None else None, point.copy())
    return hit[0].copy() if hit and hit[2] <= s.snap_radius else point


def clear_preview(region=None):
    if region is None:
        _preview.clear()
    else:
        key = region.as_pointer() if hasattr(region, "as_pointer") else id(region)
        _preview.pop(key, None)


def consume_override(context):
    settings(context).override = "NONE"


def _draw():
    context = bpy.context
    region = context.region
    if region is None or context.region_data is None:
        return
    item = _preview.get(region.as_pointer())
    if item is None:
        return
    hit, base, raw = item
    s = settings(context)
    if not s.marker:
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    lines = []
    target = hit[0] if hit else raw
    p = _screen(region, context.region_data, target)
    b = _screen(region, context.region_data, base) if base is not None else None
    size = s.marker_size * .5
    if hit and p is not None:
        x, y = p
        kind = hit[1]
        if kind in {"vertex", "endpoint", "pivot", "center_face"}:
            pts = [(x + size * math.cos(i * math.tau / 16), y + size * math.sin(i * math.tau / 16)) for i in range(17)]
            lines.extend(q for i in range(16) for q in (pts[i], pts[i + 1]))
        else:
            lines.extend(((x - size, y), (x + size, y), (x, y - size), (x, y + size)))
        blf.size(0, 11)
        blf.color(0, 0, 1, 1, 1)
        blf.position(0, x + size + 5, y + size + 4, 0)
        blf.draw(0, dict(TYPES).get(kind, kind))
    if b is not None and p is not None and s.rubber_band:
        lines.extend((tuple(b), tuple(p)))
        x, y = b
        pts = [(x + size * math.cos(i * math.tau / 16), y + size * math.sin(i * math.tau / 16)) for i in range(17)]
        lines.extend(q for i in range(16) for q in (pts[i], pts[i + 1]))
    if lines:
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(1.5)
        shader.bind()
        shader.uniform_float("color", (0, 1, 1, 1))
        batch_for_shader(shader, "LINES", {"pos": lines}).draw(shader)
        gpu.state.line_width_set(1)
        gpu.state.blend_set("NONE")


def spinner_params(params, context):
    """Apply Spinner Snap to changed primitive fields in the Command Panel."""
    global _spinner_busy
    if _spinner_busy or not context.region or context.region.type != "UI":
        return
    s = settings(context)
    _spinner_busy = True
    try:
        for prop in params.bl_rna.properties:
            if prop.type != "FLOAT" or prop.is_readonly or prop.is_array:
                continue
            name = prop.identifier
            value = getattr(params, name)
            key = (params.id_data.as_pointer(), name)
            old = _spinner_values.get(key, value)
            if s.spinner_snap and value != old:
                value = max(prop.hard_min, min(prop.hard_max,
                            round(value / s.spinner_increment) * s.spinner_increment))
                setattr(params, name, value)
            _spinner_values[key] = value
    finally:
        _spinner_busy = False


def remember_spinners(params):
    for prop in params.bl_rna.properties:
        if prop.type == "FLOAT" and not prop.is_array:
            _spinner_values[(params.id_data.as_pointer(), prop.identifier)] = getattr(params, prop.identifier)


@persistent
def _load_settings(_unused=None):
    clear_preview()
    _spinner_values.clear()
    if __package__ in bpy.context.preferences.addons:
        _grid(settings(bpy.context), bpy.context)
        for ob in bpy.context.scene.objects:
            if hasattr(ob, "max_prim") and ob.max_prim.kind:
                remember_spinners(ob.max_prim)


def _field(layout, s, prop, label=None):
    row = layout.row(align=True)
    row.label(text=(label or s.bl_rna.properties[prop].name) + ":")
    sub = row.row(align=True)
    sub.ui_units_x = 5
    sub.prop(s, prop, text="")


def draw_settings(layout, context, tab):
    s = settings(context)
    layout.use_property_split = False
    if tab == "SNAPS":
        layout.label(text="Standard")
        # Max's checkbox matrix reads down each column.
        row = layout.row()
        for column in (TYPES[:6], TYPES[6:]):
            col = row.column(align=True)
            for k, name in column:
                r = col.row()
                r.enabled = k != "tangent"
                r.prop(s, k, text=name)
        layout.label(text="Tangent requires analytic spline support", icon="INFO")
        layout.label(text="Override OFF" if s.override == "NONE" else "Override: " + dict(TYPES).get(s.override, "None"))
        layout.operator("max.snap_clear", text="Clear All")
    elif tab == "OPTIONS":
        box = layout.box()
        box.label(text="Marker")
        box.prop(s, "marker")
        _field(box, s, "marker_size")
        box = layout.box()
        box.label(text="General")
        for k in ("preview_radius", "snap_radius", "angle", "percent"):
            _field(box, s, k)
        box.prop(s, "snap_frozen")
        box = layout.box()
        box.label(text="Translation")
        box.prop(s, "axis_constraints")
        box.prop(s, "rubber_band")
        box = layout.box()
        box.label(text="Spinner Snap")
        _field(box, s, "spinner_increment")
        box.label(text="Primitive parameter fields only", icon="INFO")
    elif tab == "HOME":
        box = layout.box()
        box.label(text="Grid Dimensions")
        _field(box, s, "grid_spacing")
        _field(box, s, "major_lines")
        row = box.column()
        row.enabled = False
        _field(row, s, "grid_extent")
        row.prop(s, "inhibit_subdivision")
        layout.label(text="Blender controls visible grid extent and subdivision", icon="INFO")
    else:
        box = layout.box()
        box.enabled = False
        box.label(text="Grid object automation")
        box.prop(s, "activate_grids")
        box = layout.box()
        box.enabled = False
        box.label(text="AutoGrid")
        for value, label in (("WORLD", "World space"), ("OBJECT", "Object space")):
            box.emboss = "NONE"
            box.prop_enum(s, "autogrid_space", value, text=label,
                          icon="RADIOBUT_ON" if s.autogrid_space == value else "RADIOBUT_OFF")
        layout.label(text="User grid helpers and AutoGrid are not available", icon="INFO")


class MAX_OT_snap_settings(bpy.types.Operator):
    """Set snap targets, magnetic radius, angle, percent and home grid"""
    bl_idname = "max.snap_settings"
    bl_label = "Grid and Snap Settings"
    tab: EnumProperty(items=TABS, default="SNAPS", options={"SKIP_SAVE"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        self.layout.prop(self, "tab", expand=True)
        draw_settings(self.layout, context, self.tab)

    def execute(self, context):
        if context.preferences.use_preferences_save:
            bpy.ops.wm.save_userpref()
        return {"FINISHED"}

    def cancel(self, context):
        if context.preferences.use_preferences_save:
            bpy.ops.wm.save_userpref()


class MAX_OT_snap_clear(bpy.types.Operator):
    bl_idname = "max.snap_clear"
    bl_label = "Clear All"

    def execute(self, context):
        for k, _ in TYPES:
            setattr(settings(context), k, False)
        return {"FINISHED"}


class MAX_OT_snap_override(bpy.types.Operator):
    """Use one snap type for the next completed creation point or transform"""
    bl_idname = "max.snap_override"
    bl_label = "Snap Override"
    kind: EnumProperty(items=[("NONE", "Clear Override", ""), ("OFF", "None", ""),
                              ("LAST", "Last", "")] + [(k, n, "") for k, n in TYPES])

    def execute(self, context):
        s = settings(context)
        kind = s.last_override if self.kind == "LAST" else self.kind
        s.override = kind
        if kind in dict(TYPES):
            s.last_override = kind
        active = _tool(context)
        for k, name in (("MOVE", "move"), ("ROTATE", "rotate"), ("SCALE", "scale")):
            if active in {"builtin." + name, "max.snap_" + name}:
                select_transform(context, k)
                break
        return {"FINISHED"}


class MAX_OT_snap_cycle(bpy.types.Operator):
    """Cycle one-shot overrides among enabled snap types (Alt+S)"""
    bl_idname = "max.snap_cycle"
    bl_label = "Cycle Snap Override"

    def execute(self, context):
        s = settings(context)
        active = [k for k, _ in TYPES if getattr(s, k) and k != "tangent"]
        if active:
            index = active.index(s.override) + 1 if s.override in active else 0
            bpy.ops.max.snap_override(kind=active[index % len(active)])
        return {"FINISHED"}


class MAX_MT_snap_standard(bpy.types.Menu):
    bl_label = "Standard"

    def draw(self, context):
        for k, n in TYPES:
            row = self.layout.row()
            row.enabled = k != "tangent"
            row.operator("max.snap_override", text=n).kind = k


class MAX_OT_snap_quad(bpy.types.Operator):
    """One-shot snap override and snap options (Shift+right-click)"""
    bl_idname = "max.snap_quad"
    bl_label = "Snaps"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=390)

    def draw(self, context):
        self.layout.operator_context = "INVOKE_DEFAULT"
        s = settings(context)
        split = self.layout.split(factor=.5)
        left, right = split.column(), split.column()
        left.operator("max.snap_settings", text="Grid and Snap Settings...", emboss=False)
        left.prop(s, "snap_frozen", text="Snaps To Frozen Objects")
        left.prop(s, "axis_constraints", text="Snaps Use Axis Constraints")
        left.label(text="snap options")
        row = right.row()
        row.enabled = False
        row.label(text="NURBS (not available)")
        right.menu("MAX_MT_snap_standard", text="Standard")
        row = right.row()
        row.enabled = context.scene.tool_settings.use_snap
        row.operator("max.snap_override", text="None", emboss=False).kind = "OFF"
        row = right.row()
        row.enabled = s.last_override != "NONE"
        row.operator("max.snap_override", text="Last", emboss=False).kind = "LAST"
        right.label(text="snap override")
        right.separator()
        right.label(text="snap toggles")
        for k in ("grid_points", "pivot", "vertex", "midpoint", "edge", "face"):
            right.prop(s, k)

    def execute(self, context):
        return {"FINISHED"}


class MAX_MT_snap_modes(bpy.types.Menu):
    bl_label = "Snaps Toggle"

    def draw(self, context):
        self.layout.prop_enum(settings(context), "mode", "2D")
        self.layout.prop_enum(settings(context), "mode", "2_5D")
        self.layout.prop_enum(settings(context), "mode", "3D")


def _tool(context):
    try:
        return context.workspace.tools.from_space_view3d_mode(context.mode, create=False).idname
    except (AttributeError, KeyError):
        return ""


def select_transform(context, kind):
    s = settings(context)
    use = context.scene.tool_settings.use_snap or s.override != "NONE"
    use |= (kind == "ROTATE" and s.angle_snap) or (kind == "SCALE" and s.percent_snap)
    use = use and context.mode in {"OBJECT", "EDIT_MESH"}
    names = {"MOVE": "move", "ROTATE": "rotate", "SCALE": "scale"}
    name = names[kind]
    bpy.ops.wm.tool_set_by_id(name="max.snap_" + name if use else "builtin." + name)


class MAX_OT_select_transform(bpy.types.Operator):
    bl_idname = "max.select_transform"
    bl_label = "Select and Transform"
    kind: EnumProperty(items=[("MOVE", "Select and Move", ""), ("ROTATE", "Select and Rotate", ""),
                              ("SCALE", "Select and Uniform Scale", "")])

    def execute(self, context):
        select_transform(context, self.kind)
        return {"FINISHED"}


def toggle(context, kind):
    s, ts = settings(context), context.scene.tool_settings
    if kind == "SNAP":
        ts.use_snap = not ts.use_snap
    else:
        attr = {"ANGLE_SNAP": "angle_snap", "PERCENT_SNAP": "percent_snap", "SPINNER_SNAP": "spinner_snap",
                "AXIS_CONSTRAINTS": "axis_constraints"}[kind]
        setattr(s, attr, not getattr(s, attr))
    # Keep native geometry snapping free of incremental grid steps.
    enabled = {"VERTEX"} if s.vertex else {"EDGE"} if s.edge else {"FACE"} if s.face else {"VERTEX"}
    ts.snap_elements = enabled
    ts.snap_target = "CLOSEST"
    ts.use_snap_translate = True
    ts.use_snap_rotate = s.angle_snap
    ts.use_snap_scale = s.percent_snap
    active = _tool(context)
    for kind, name in (("MOVE", "move"), ("ROTATE", "rotate"), ("SCALE", "scale")):
        if active in {"builtin." + name, "max.snap_" + name}:
            select_transform(context, kind)
            break
    clear_preview()
    _redraw(context)


class MAX_OT_snap_toggle(bpy.types.Operator):
    """Toggle snaps. Right-click opens Grid and Snap Settings"""
    bl_idname = "max.snap_toggle"
    bl_label = "Snaps Toggle"
    kind: EnumProperty(items=[(k, n, "") for k, n in (("SNAP", "Snaps Toggle"),
                       ("ANGLE_SNAP", "Angle Snap Toggle"), ("PERCENT_SNAP", "Percent Snap Toggle"),
                       ("SPINNER_SNAP", "Spinner Snap Toggle"),
                       ("AXIS_CONSTRAINTS", "Enable Axis Constraints in Snaps Toggle"))])

    @classmethod
    def description(cls, context, properties):
        return dict(SNAP="Snaps Toggle (S)", ANGLE_SNAP="Angle Snap Toggle (A)",
                    PERCENT_SNAP="Percent Snap Toggle (Ctrl+Shift+P)",
                    SPINNER_SNAP="Spinner Snap Toggle",
                    AXIS_CONSTRAINTS="Enable Axis Constraints in Snaps Toggle (Alt+F3)")[properties.kind] + ". Right-click for Grid and Snap Settings"

    def execute(self, context):
        toggle(context, self.kind)
        return {"FINISHED"}


def button_context(self, context):
    global _context_pending
    op = getattr(context, "button_operator", None)
    if op and op.bl_rna.identifier == "MAX_OT_snap_toggle":
        if _context_pending:
            return
        tab = "SNAPS" if op.kind == "SNAP" else "OPTIONS"
        window, area, region = context.window, context.area, context.region
        _context_pending = True

        def open_dialog():
            global _context_pending
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.max.snap_settings("INVOKE_DEFAULT", tab=tab)
            finally:
                _context_pending = False
            return None

        bpy.app.timers.register(open_dialog, first_interval=.01)


def draw_toolbar(layout, context):
    s, ts = settings(context), context.scene.tool_settings
    row = layout.row(align=True)
    row.operator("max.snap_toggle", text=dict((k, n) for k, n, _ in MODES)[s.mode],
                 icon="SNAP_ON", depress=ts.use_snap).kind = "SNAP"
    row.menu("MAX_MT_snap_modes", text="", icon="DOWNARROW_HLT")
    for kind, icon, value in (("ANGLE_SNAP", "DRIVER_ROTATIONAL_DIFFERENCE", s.angle_snap),
                              ("PERCENT_SNAP", "MOD_PHYSICS", s.percent_snap),
                              ("SPINNER_SNAP", "ARROW_LEFTRIGHT", s.spinner_snap)):
        row.operator("max.snap_toggle", text="", icon=icon, depress=value).kind = kind


class MAX_OT_snap_transform(bpy.types.Operator):
    """Drag a snap base to a target. Release commits, right-click cancels"""
    bl_idname = "max.snap_transform"
    bl_label = "Snap Transform"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}
    kind: EnumProperty(items=[("MOVE", "Move", ""), ("ROTATE", "Rotate", ""), ("SCALE", "Scale", "")])

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D" and context.mode in {"OBJECT", "EDIT_MESH"}

    def invoke(self, context, event):
        from .create import construction_frame
        self.region = context.region
        self.rv3d = context.region_data
        if self.rv3d is None:
            return {"CANCELLED"}
        self.start_co = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.value == "CLICK_DRAG":
            self.start_co = Vector((event.mouse_prev_press_x - self.region.x,
                                    event.mouse_prev_press_y - self.region.y))
        self.u, self.v, self.n = construction_frame(self.rv3d)
        self.plane = (Vector((0, 0, 0)), self.n)
        self.objects = list(context.objects_in_mode_unique_data) if context.mode == "EDIT_MESH" else list(context.selected_objects)
        self.meshes = []
        self.matrices = []
        for ob in self.objects:
            if ob.mode == "EDIT":
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.index_update()
                vertices = [(v.index, v.co.copy()) for v in bm.verts if v.select and not v.hide]
                self.meshes.append((ob, vertices))
            else:
                self.matrices.append((ob, ob.matrix_world.copy()))
        s = settings(context)
        enabled = {s.override} if s.override != "NONE" else {k for k, _ in TYPES if getattr(s, k)}
        center = sum((ob.matrix_world.translation for ob in self.objects), Vector()) / max(1, len(self.objects))
        hit = None
        if context.scene.tool_settings.use_snap or s.override not in {"NONE", "OFF"}:
            cursor = self._ray(self.start_co, self.plane[0], self.n)
            hit = _pick(context, self.region, self.rv3d, self.start_co,
                        cursor if cursor is not None else center, self.plane,
                        enabled, self.objects, source=True)
        if hit:
            self.base = hit[0]
        elif self.objects:
            # Grid-only and angle/percent transforms start at the picked surface.
            view_n = self.rv3d.view_rotation @ Vector((0, 0, 1))
            self.base = self._ray(self.start_co, center, view_n) if self.kind == "MOVE" else center.copy()
            if self.base is None:
                return {"CANCELLED"}
        else:
            return {"CANCELLED"}
        self.axis = None
        self.number = ""
        self.pivot = self.base.copy()
        self.reference = center - self.pivot
        self.view_n = self.rv3d.view_rotation @ Vector((0, 0, 1))
        self.drag_n = self.n if s.mode != "3D" else self.view_n
        self.drag_origin = self._ray(self.start_co, self.base, self.drag_n)
        if self.drag_origin is None:
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Snap base picked. Drag to target. X/Y/Z: axis. Right-click: cancel")
        return {"RUNNING_MODAL"}

    def _ray(self, co, point, normal):
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, co)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, co)
        return intersect_line_plane(origin, origin + direction, point, normal)

    def _apply(self, context, matrix):
        for ob, saved in self.matrices:
            ob.matrix_world = matrix @ saved
        for ob, vertices in self.meshes:
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            local = ob.matrix_world.inverted_safe() @ matrix @ ob.matrix_world
            for index, saved in vertices:
                bm.verts[index].co = local @ saved
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        context.view_layer.update()

    def _update(self, context, co):
        s = settings(context)
        point = self._ray(co, self.base, self.drag_n)
        if point is None:
            return
        raw = self.base + point - self.drag_origin
        point = snap_point(context, self.region, self.rv3d, co, raw, self.plane,
                           exclude=[ob for ob in self.objects if ob.mode != "EDIT"],
                           base=self.base, axis=self.axis)
        if self.kind == "MOVE":
            delta = point - self.base
            if self.axis is not None and s.axis_constraints:
                delta = self.axis * delta.dot(self.axis)
            if self.number not in {"", "-", ".", "-."}:
                delta = (self.axis if self.axis is not None else self.u) * float(self.number)
            mat = Matrix.Translation(delta)
        else:
            axis = self.axis if self.axis is not None else self.view_n
            if self.kind == "ROTATE":
                angle = (co.x - self.start_co.x) * .01
                preview = _preview.get(self.region.as_pointer())
                if preview and preview[0] and preview[0][2] <= s.snap_radius:
                    a = self.reference - axis * self.reference.dot(axis)
                    b = point - self.pivot
                    b -= axis * b.dot(axis)
                    if a.length > 1e-6 and b.length > 1e-6:
                        angle = math.atan2(axis.dot(a.cross(b)), a.dot(b))
                if self.number not in {"", "-", ".", "-."}:
                    angle = math.radians(float(self.number))
                mat = Matrix.Rotation(snap_angle(s, angle), 4, axis)
            else:
                factor = 1 + (co.x - self.start_co.x) / 100
                preview = _preview.get(self.region.as_pointer())
                if preview and preview[0] and preview[0][2] <= s.snap_radius and self.reference.length > 1e-6:
                    factor = (point - self.pivot).length / self.reference.length
                if self.number not in {"", "-", ".", "-."}:
                    factor = float(self.number) / 100
                factor = snap_scale(s, factor)
                mat = Matrix.Scale(factor, 4, self.axis) if self.axis is not None else Matrix.Scale(factor, 4)
            mat = Matrix.Translation(self.pivot) @ mat @ Matrix.Translation(-self.pivot)
        self._apply(context, mat)
        context.area.tag_redraw()

    def _finish(self, context, cancel=False):
        if cancel:
            self._apply(context, Matrix.Identity(4))
        else:
            consume_override(context)
        clear_preview(self.region)
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        return {"CANCELLED"} if cancel else {"FINISHED"}

    def modal(self, context, event):
        co = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.value == "PRESS" and event.type == "S":
            if event.alt:
                bpy.ops.max.snap_cycle()
            else:
                toggle(context, "SNAP")
            self._update(context, co)
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            return self._finish(context, True)
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "RELEASE":
            self._update(context, co)
            return self._finish(context)
        if event.value == "PRESS":
            if event.type in {"X", "Y", "Z"}:
                self.axis = Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[event.type])
                settings(context).axis_constraints = True
            elif event.type == "BACK_SPACE":
                self.number = self.number[:-1]
            elif event.ascii and event.ascii in "0123456789.-":
                candidate = self.number + event.ascii
                try:
                    float(candidate) if candidate not in {"-", ".", "-."} else None
                    self.number = candidate
                except ValueError:
                    pass
        if event.type == "MOUSEMOVE" or event.value == "PRESS":
            self._update(context, co)
        return {"RUNNING_MODAL"}


class _SnapTool:
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_widget = None
    bl_options = set()


def _make_tool(name, label, kind, mode):
    return type("MAX_WST_" + name + "_" + mode, (_SnapTool, bpy.types.WorkSpaceTool), {
        "bl_idname": "max.snap_" + name,
        "bl_label": label,
        "bl_description": "Drag a snap base to its target. Right-click cancels",
        "bl_context_mode": mode,
        "bl_icon": {"MOVE": "ops.transform.translate", "ROTATE": "ops.transform.rotate", "SCALE": "ops.transform.resize"}[kind],
        "bl_keymap": (("max.snap_transform", {"type": "LEFTMOUSE", "value": "CLICK_DRAG"}, {"properties": [("kind", kind)]}),
                      ("view3d.select", {"type": "LEFTMOUSE", "value": "CLICK"}, {"properties": [("deselect_all", True)]})),
    })


tools = tuple(_make_tool(name, label, kind, mode) for mode in ("OBJECT", "EDIT_MESH")
              for name, label, kind in (("move", "Select and Move", "MOVE"),
                                        ("rotate", "Select and Rotate", "ROTATE"),
                                        ("scale", "Select and Uniform Scale", "SCALE")))


classes = (MaxSnapSettings, MAX_OT_snap_settings, MAX_OT_snap_clear, MAX_OT_snap_override,
           MAX_OT_snap_cycle, MAX_MT_snap_standard, MAX_OT_snap_quad, MAX_MT_snap_modes,
           MAX_OT_select_transform, MAX_OT_snap_toggle, MAX_OT_snap_transform)


def register_props():
    global _handle
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")
        for tool in tools:
            bpy.utils.register_tool(tool, separator=False, group=False)
        bpy.app.timers.register(_load_settings, first_interval=1.1)
    bpy.app.handlers.load_post.append(_load_settings)
    menu = getattr(bpy.types, "UI_MT_button_context_menu", None) or bpy.types.WM_MT_button_context
    menu.append(button_context)


def unregister_props():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
    if not bpy.app.background:
        for tool in reversed(tools):
            bpy.utils.unregister_tool(tool)
    if bpy.app.timers.is_registered(_load_settings):
        bpy.app.timers.unregister(_load_settings)
    if _load_settings in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_settings)
    menu = getattr(bpy.types, "UI_MT_button_context_menu", None) or bpy.types.WM_MT_button_context
    menu.remove(button_context)
    _spinner_values.clear()
    clear_preview()
