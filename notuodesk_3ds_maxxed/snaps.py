"""Max snap settings, magnetic picking and base-point transforms."""

import math

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty, IntProperty
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
_settings_windows = set()
_button_guards = set()
_guard_generation = 0
_quad_open = False


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
    tab: EnumProperty(items=TABS, default="SNAPS", options={"SKIP_SAVE"})
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
    inhibit_resize: BoolProperty(name="Inhibit Perspective View Grid Resize")
    grid_update: EnumProperty(items=[("ACTIVE", "Active Viewport", ""), ("ALL", "All Viewports", "")], default="ALL")
    shape_angle: BoolProperty(name="Enable Shape Angle Constraints")
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


def _grid_points(region, rv3d, co, anchor, u, v, spacing, radius):
    """Search the grid under the pixel disk, not just the rounded world point."""
    # The grid plane maps to the screen through a 3x3 homography. Inverting
    # the preview square bounds every intersection inside its pixel disk.
    m = rv3d.perspective_matrix
    a = m @ u.to_4d()
    b = m @ v.to_4d()
    c = m @ anchor.to_4d()
    # Directions must have w=0 before projection.
    a -= m.col[3]
    b -= m.col[3]
    h = Matrix(((a.x, b.x, c.x), (a.y, b.y, c.y), (a.w, b.w, c.w)))
    if abs(h.determinant()) < 1e-12:
        return
    inv = h.inverted()
    bounds = []
    for x, y in ((-radius, -radius), (-radius, radius), (radius, -radius), (radius, radius)):
        p = inv @ Vector(((co[0] + x) * 2 / region.width - 1,
                          (co[1] + y) * 2 / region.height - 1, 1))
        if abs(p.z) < 1e-9:
            return
        bounds.append(p)
    # At the horizon the inverse footprint is unbounded. Search the finite
    # visible portion using samples on both sides of the cursor instead.
    if min(p.z for p in bounds) * max(p.z for p in bounds) <= 0:
        bounds = []
        for i in range(33):
            angle = i * math.tau / 32
            p = inv @ Vector(((co[0] + radius * math.cos(angle)) * 2 / region.width - 1,
                              (co[1] + radius * math.sin(angle)) * 2 / region.height - 1, 1))
            if p.z > 1e-6:
                bounds.append(p)
        if not bounds:
            return
    coords = [(p.x / p.z / spacing, p.y / p.z / spacing) for p in bounds]
    lo = [math.floor(min(p[i] for p in coords)) for i in (0, 1)]
    hi = [math.ceil(max(p[i] for p in coords)) for i in (0, 1)]
    # Iterate the shorter grid dimension. On each projected grid line the
    # closest intersection is one of the two integers beside its closest
    # continuous point. This avoids a quadratic scan when zoomed far out.
    swap = hi[0] - lo[0] > hi[1] - lo[1]
    if swap:
        u, v = v, u
        lo.reverse()
        hi.reverse()
    for i in range(lo[0], hi[0] + 1):
        line = anchor + u * (i * spacing)
        p = m @ line.to_4d()
        d = m @ v.to_4d() - m.col[3]
        pa = Vector(((p.x + p.w) * region.width / 2, (p.y + p.w) * region.height / 2, p.w))
        direction = Vector(((d.x + d.w) * region.width / 2, (d.y + d.w) * region.height / 2, d.w))
        edge = pa.cross(direction)
        if edge.x * edge.x + edge.y * edge.y < 1e-12:
            continue
        distance = (edge.x * co[0] + edge.y * co[1] + edge.z) / (edge.x * edge.x + edge.y * edge.y)
        xy = Vector((co[0] - edge.x * distance, co[1] - edge.y * distance))
        p = inv @ Vector((xy.x * 2 / region.width - 1, xy.y * 2 / region.height - 1, 1))
        if abs(p.z) < 1e-9:
            continue
        t = (p.x if swap else p.y) / p.z / spacing
        for j in {math.floor(t), math.ceil(t), lo[1], hi[1]}:
            yield line + v * (j * spacing)


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
          axis=None, pixels_per_unit=None, source=False, constraint_plane=None):
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
            if "grid_points" in enabled:
                for index in {math.floor(level / spacing), math.ceil(level / spacing)}:
                    candidates.append((point + axis * (index * spacing - level), "grid_points"))
        else:
            if "grid_points" in enabled:
                candidates.extend((q, "grid_points") for q in
                                  _grid_points(region, rv3d, co, anchor, u, v, spacing, s.preview_radius))
            if "grid_lines" in enabled:
                candidates.extend(((anchor + u * au + v * b, "grid_lines"),
                                   (anchor + u * a + v * bv, "grid_lines")))
    candidates.extend(_geometry(context, region, rv3d, co, enabled, objects, base, source))
    best, rank = None, (float("inf"), 9)
    for p, kind in candidates:
        if s.mode == "2D" and not source and not kind.startswith("grid_"):
            tolerance = 1e-6 * max(1, s.grid_spacing, (p - origin).length)
            if abs((p - origin).dot(n)) > tolerance:
                continue
        if s.mode == "2_5D" and not source and not (axis is not None and kind == "grid_points"):
            p = _project(p, plane)
        if axis is not None and base is not None and s.axis_constraints:
            p = base + axis * (p - base).dot(axis)
        if constraint_plane is not None and s.axis_constraints:
            p = _project(p, constraint_plane)
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
               axis=None, pixels_per_unit=None, constraint_plane=None):
    """Magnetically snap a world point within Snap Radius screen pixels.

    `co` is region-relative. `plane` is (world origin, world normal).
    Exclude the object being created or transformed. For height creation pass
    `axis`, and pixels_per_unit when that axis points at the viewer.
    `constraint_plane` is an optional (world origin, world normal) pair.
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
                axis, pixels_per_unit, constraint_plane=constraint_plane)
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
    global _guard_generation
    from . import snap_quad
    snap_quad.close_all()
    _guard_generation += 1
    _button_guards.clear()
    clear_preview()
    _spinner_values.clear()
    if __package__ in bpy.context.preferences.addons:
        _grid(settings(bpy.context), bpy.context)
        for ob in bpy.context.scene.objects:
            if hasattr(ob, "max_prim") and ob.max_prim.kind:
                remember_spinners(ob.max_prim)
        if not bpy.app.background and not bpy.app.timers.is_registered(_ensure_button_listeners):
            bpy.app.timers.register(_ensure_button_listeners, first_interval=.1)


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
        box.enabled = False
        box.label(text="Shape Creation")
        box.prop(s, "shape_angle")
        layout.label(text="Shape angle constraints require the Line tool integration", icon="INFO")
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
        row.prop(s, "inhibit_resize")
        box = layout.box()
        box.enabled = False
        box.label(text="Dynamic Update")
        for value, label in (("ACTIVE", "Active Viewport"), ("ALL", "All Viewports")):
            row = box.row()
            row.emboss = "NONE"
            row.prop_enum(s, "grid_update", value, text=label,
                          icon="RADIOBUT_ON" if s.grid_update == value else "RADIOBUT_OFF")
        layout.label(text="Blender controls visible grid extent and subdivision", icon="INFO")
        layout.label(text="Grid changes update all viewports immediately", icon="INFO")
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
        global _quad_open
        _quad_open = False
        settings(context).tab = self.tab
        live = {w.as_pointer() for w in context.window_manager.windows}
        _settings_windows.intersection_update(live)
        if _settings_windows:
            _redraw(context)
            return {"FINISHED"}
        # Reuse the native floating preferences window for its usable initial
        # size, then replace its contents with a dedicated editor sidebar.
        existing = next(((w, a) for w in context.window_manager.windows for a in w.screen.areas
                         if a.type == "PREFERENCES"), None)
        if existing:
            w, a = existing
            with context.temp_override(window=w, area=a, region=next(r for r in a.regions if r.type == "WINDOW")):
                bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
        else:
            bpy.ops.screen.userpref_show("INVOKE_DEFAULT")
        window = next((w for w in context.window_manager.windows if w.as_pointer() not in live), None)
        if window is None:
            return {"CANCELLED"}
        _settings_windows.add(window.as_pointer())
        area = window.screen.areas[0]
        area.type = "NODE_EDITOR"
        space = area.spaces.active
        space.tree_type = "ShaderNodeTree"
        space.pin = True
        space.show_region_ui = True
        space.show_region_toolbar = False
        space.show_region_header = False

        def activate():
            try:
                if window.as_pointer() not in _settings_windows or area.spaces.active is None:
                    return
                # The duplicated area finishes initializing on the next redraw.
                area.spaces.active.show_region_ui = True
                area.spaces.active.show_region_toolbar = False
                area.spaces.active.show_region_header = False
                area.tag_redraw()
            except ReferenceError:
                pass
        bpy.app.timers.register(activate, first_interval=.1)
        return {"FINISHED"}

    def execute(self, context):
        if context.preferences.use_preferences_save:
            bpy.ops.wm.save_userpref()
        return {"FINISHED"}


class MAX_PT_snap_settings(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Item"
    bl_label = "Grid and Snap Settings"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return context.window.as_pointer() in _settings_windows

    def draw(self, context):
        s = settings(context)
        row = self.layout.row()
        row.label(text="Grid and Snap Settings")
        row.operator("max.snap_settings_close", text="", icon="X")
        self.layout.prop(s, "tab", expand=True)
        draw_settings(self.layout, context, s.tab)


class MAX_OT_snap_settings_close(bpy.types.Operator):
    bl_idname = "max.snap_settings_close"
    bl_label = "Close Grid and Snap Settings"

    def execute(self, context):
        _settings_windows.discard(context.window.as_pointer())
        if context.preferences.use_preferences_save:
            bpy.ops.wm.save_userpref()
        bpy.ops.wm.window_close()
        return {"FINISHED"}


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
        global _quad_open
        _quad_open = False
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


from .snap_quad import MAX_OT_snap_quad


def override_event(operator, context, event, *, dragging=True):
    """Suspend a live tool for the quad, then resume on a fresh left press."""
    global _quad_open
    if event.type == "RIGHTMOUSE" and event.value == "PRESS" and event.shift:
        operator._snap_quad_wait = True
        bpy.ops.max.snap_quad("INVOKE_DEFAULT")
        return True
    if getattr(operator, "_snap_quad_wait", False):
        if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
            return True
        if _quad_open:
            return True
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            operator._snap_quad_wait = False
            return False
        if dragging and not (event.type == "LEFTMOUSE" and event.value == "PRESS"):
            return True
        operator._snap_quad_wait = False
        # This press resumes the existing drag. It must not start a new point.
        return dragging
    return False


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


def orientation_basis(context):
    """World-space axes for the selected reference coordinate system."""
    from . import max_rotate, max_gizmos
    operation = max_gizmos.kind(context)
    if operation in {"MOVE", "SCALE"} and getattr(max_rotate.settings(context),"use_"+operation.lower()+"_reference"):
        return max_rotate.reference_basis(context,operation=operation)
    slot = context.scene.transform_orientation_slots[0]
    kind = slot.type
    ob = context.active_object
    if slot.custom_orientation is not None:
        return slot.custom_orientation.matrix.copy().normalized()
    if kind == "VIEW" and context.region_data:
        return context.region_data.view_rotation.to_matrix()
    if kind == "CURSOR":
        return context.scene.cursor.matrix.to_3x3().normalized()
    if kind in {"LOCAL", "NORMAL", "GIMBAL"} and ob:
        local = ob.matrix_world.to_3x3().normalized()
        if kind == "NORMAL" and ob.mode == "EDIT" and ob.type == "MESH":
            bm = bmesh.from_edit_mesh(ob.data)
            normals = [f.normal for f in bm.faces if f.select and not f.hide]
            if not normals:
                normals = [v.normal for v in bm.verts if v.select and not v.hide]
            normal = sum(normals, Vector())
            if normal.length > 1e-8:
                z = (ob.matrix_world.to_3x3().inverted_safe().transposed() @ normal).normalized()
                x = local.col[0] - z * local.col[0].dot(z)
                if x.length < 1e-8:
                    x = local.col[1] - z * local.col[1].dot(z)
                x.normalize()
                return Matrix((x, z.cross(x), z)).transposed()
        if kind == "GIMBAL" and ob.rotation_mode not in {"QUATERNION", "AXIS_ANGLE"}:
            # Euler axes include only the rotations later in the Euler order.
            axes = []
            order = ob.rotation_mode
            for i in range(3):
                angles = ob.rotation_euler.copy()
                for component in order[:order.index("XYZ"[i]) + 1]:
                    angles["XYZ".index(component)] = 0
                axes.append(angles.to_matrix().col[i].copy())
            parent = ob.parent.matrix_world.to_3x3().normalized() if ob.parent else Matrix.Identity(3)
            return parent @ Matrix(axes).transposed()
        return local
    return Matrix.Identity(3)


def _selection_center(context):
    points = []
    if context.mode == "EDIT_MESH":
        for ob in context.objects_in_mode_unique_data:
            points.extend(ob.matrix_world @ v.co for v in bmesh.from_edit_mesh(ob.data).verts if v.select and not v.hide)
    else:
        points = [ob.matrix_world.translation for ob in context.selected_objects]
    return sum(points, Vector()) / max(1, len(points))


def select_transform(context, kind):
    if context.mode in {"OBJECT", "EDIT_MESH"}:
        bpy.ops.wm.tool_set_by_id(name={"MOVE":"max.snap_move", "ROTATE":"max.rotate", "SCALE":"max.snap_scale"}[kind])
        return
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
        if active in {"builtin." + name, "max.snap_" + name, "max." + name}:
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


class MAX_OT_snap_button_listener(bpy.types.Operator):
    """Route toolbar RMB before Blender builds its button context menu."""
    bl_idname = "max.snap_button_listener"
    bl_label = "Snap Button Listener"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        self.generation = _guard_generation
        self.window_key = context.window.as_pointer()
        if self.window_key in _button_guards:
            return {"CANCELLED"}
        _button_guards.add(self.window_key)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if self.generation != _guard_generation:
            return {"CANCELLED"}
        if event.type != "RIGHTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}
        for area in context.window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type != "HEADER" or not (region.x <= event.mouse_x < region.x + region.width
                        and region.y <= event.mouse_y < region.y + region.height):
                    continue
                with context.temp_override(area=area, region=region):
                    # Blender exposes the hovered operator through Copy Python
                    # Command, but button_operator only inside the context menu.
                    # Preserve the clipboard and never let the native menu open.
                    if not bpy.ops.ui.copy_python_command_button.poll():
                        return {"PASS_THROUGH"}
                    clipboard = context.window_manager.clipboard
                    try:
                        bpy.ops.ui.copy_python_command_button()
                        command = context.window_manager.clipboard
                    finally:
                        context.window_manager.clipboard = clipboard
                    if command.startswith("bpy.ops.max.snap_toggle("):
                        tab = "SNAPS" if "'SNAP'" in command or '"SNAP"' in command else "OPTIONS"
                        bpy.ops.max.snap_settings("INVOKE_DEFAULT", tab=tab)
                        return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


def _ensure_button_listeners():
    if not bpy.app.background:
        for window in bpy.context.window_manager.windows:
            if window.as_pointer() not in _button_guards and any(a.type == "VIEW_3D" for a in window.screen.areas):
                with bpy.context.temp_override(window=window):
                    bpy.ops.max.snap_button_listener("INVOKE_DEFAULT")


def draw_toolbar(layout, context):
    if context.window.as_pointer() not in _button_guards and not bpy.app.timers.is_registered(_ensure_button_listeners):
        bpy.app.timers.register(_ensure_button_listeners, first_interval=.01)
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
    bl_options = {"REGISTER", "BLOCKING"}
    kind: EnumProperty(items=[("MOVE", "Move", ""), ("ROTATE", "Rotate", ""), ("SCALE", "Scale", "")])
    constraint_axis: BoolVectorProperty(size=3, default=(False, False, False), options={"SKIP_SAVE"})
    from_gizmo: BoolProperty(default=False, options={"SKIP_SAVE"})
    screen_plane: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D" and context.mode in {"OBJECT", "EDIT_MESH"}

    def invoke(self, context, event):
        from . import max_rotate, max_gizmos
        self._closed = False
        if self.kind == "ROTATE":
            axes = [i for i, enabled in enumerate(self.constraint_axis) if enabled]
            return bpy.ops.max.rotate("INVOKE_DEFAULT", handle="XYZ"[axes[0]] if len(axes) == 1 else "OFF")
        if self.from_gizmo:
            lock = "".join(c for c, enabled in zip("XYZ", self.constraint_axis) if enabled) or "XYZ"
            if not self.screen_plane:
                max_rotate.set_constraint(context, lock, self.kind)
        else:
            lock = max_rotate.constraint(context, self.kind)
            self.constraint_axis = tuple(c in lock for c in "XYZ")
        if self.kind == "MOVE" and context.scene.tool_settings.use_snap and not settings(context).axis_constraints:
            self.constraint_axis = (False, False, False)
        # Constraints' geometry transaction takes priority over magnetic targets.
        import sys
        poly = sys.modules.get(__package__ + ".poly_constraints")
        if self.kind == "MOVE" and poly is not None and poly.active(context):
            return poly.invoke_move(context, event, constraint_axis=self.constraint_axis, from_gizmo=self.from_gizmo)
        self.clone = None
        from .create import construction_frame
        self.region = context.region
        self.rv3d = context.region_data
        if self.rv3d is None:
            return {"CANCELLED"}
        if not context.selected_objects:
            return {"CANCELLED"}
        self.clone = max_rotate.begin_clone(context) if event.shift else None
        self.start_co = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.value == "CLICK_DRAG":
            self.start_co = Vector((event.mouse_prev_press_x - self.region.x,
                                    event.mouse_prev_press_y - self.region.y))
        self.u, self.v, self.n = construction_frame(self.rv3d)
        self.plane = (Vector((0, 0, 0)), self.n)
        self.objects = list(context.objects_in_mode_unique_data) if context.mode == "EDIT_MESH" else list(context.selected_objects)
        self.meshes = []
        self.matrices = []
        self.poly_targets = max_rotate.constraint_session(context) if self.kind == "SCALE" else None
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
        center = max_rotate.transform_center(context, self.kind)
        hit = None
        if context.scene.tool_settings.use_snap or s.override not in {"NONE", "OFF"}:
            cursor = self._ray(self.start_co, self.plane[0], self.n)
            hit = _pick(context, self.region, self.rv3d, self.start_co,
                        cursor if cursor is not None else center, self.plane,
                        enabled, self.objects, source=True)
        if hit and self.kind != "SCALE":
            self.base = hit[0]
        elif self.objects:
            # Grid-only and angle/percent transforms start at the picked surface.
            view_n = self.rv3d.view_rotation @ Vector((0, 0, 1))
            self.base = self._ray(self.start_co, center, view_n) if self.kind == "MOVE" else center.copy()
            if self.base is None:
                return self._abort_invoke(context)
        else:
            return self._abort_invoke(context)
        self.orientation = orientation_basis(context)
        rs = max_rotate.settings(context)
        self.individual = (self.kind == "SCALE" and
            (max_rotate.center_mode(context,"SCALE") == "PIVOT" or
             (rs.use_scale_reference and rs.scale_reference == "LOCAL")))
        self.object_pivots = {ob:matrix.translation.copy() for ob,matrix in self.matrices}
        for ob, vertices in self.meshes:
            if vertices:
                self.object_pivots[ob] = sum((ob.matrix_world@co for _,co in vertices),Vector())/len(vertices)
        self.axis = None
        self.constraint_normal = None
        self._set_constraint(self.constraint_axis)
        self.number = ""
        self.pivot = self.base.copy()
        self.reference = center - self.pivot
        self.view_n = self.rv3d.view_rotation @ Vector((0, 0, 1))
        self.drag_n = self.n if s.mode != "3D" else self.view_n
        if self.constraint_normal is not None:
            self.drag_n = self.constraint_normal
        self.drag_origin = self._ray(self.start_co, self.base, self.drag_n)
        if self.kind == "SCALE" and self.drag_origin is not None:
            self.reference = self.drag_origin-self.pivot
        if self.drag_origin is None:
            return self._abort_invoke(context)
        context.window_manager.modal_handler_add(self)
        max_gizmos.begin(context, self, self.kind, center, self.orientation, lock if lock != "XYZ" else "CENTER")
        context.workspace.status_text_set("Snap base picked. Drag to target. X/Y/Z: axis. Right-click: cancel")
        if event.value == "CLICK_DRAG":
            self._update(context, Vector((event.mouse_region_x, event.mouse_region_y)))
        return {"RUNNING_MODAL"}

    def _abort_invoke(self, context):
        from . import max_rotate
        max_rotate.close_constraints(context,self.poly_targets,True)
        if self.clone:
            max_rotate.cancel_clone(context,self.clone)
        self._closed = True
        return {"CANCELLED"}

    def _set_constraint(self, flags):
        indices = [i for i, enabled in enumerate(flags) if enabled]
        self.axis = self.orientation.col[indices[0]].normalized() if len(indices) == 1 else None
        self.constraint_normal = self.orientation.col[indices[0]].cross(self.orientation.col[indices[1]]).normalized() if len(indices) == 2 else None

    def _ray(self, co, point, normal):
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, co)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, co)
        return intersect_line_plane(origin, origin + direction, point, normal)

    def _apply(self, context, matrix):
        def individual_matrix(ob):
            if not self.individual:
                return matrix
            offset = self.object_pivots[ob]-self.pivot
            return Matrix.Translation(offset) @ matrix @ Matrix.Translation(-offset)
        targets = {}
        for ob, saved in self.matrices:
            ob.matrix_world = individual_matrix(ob) @ saved
        for ob, vertices in self.meshes:
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            local = ob.matrix_world.inverted_safe() @ individual_matrix(ob) @ ob.matrix_world
            targets[ob] = {index:ob.matrix_world @ local @ saved for index,saved in vertices}
            if self.poly_targets is None:
                for index, saved in vertices:
                    bm.verts[index].co = local @ saved
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        if self.poly_targets is not None:
            self.poly_targets.apply_targets(targets)
        context.view_layer.update()

    def _update(self, context, co):
        s = settings(context)
        if self.axis is not None and self.kind == "MOVE":
            from .create import ray_line_height
            point = self.base + self.axis * ray_line_height(self.region, self.rv3d, co, self.base, self.axis)
            start = self.base + self.axis * ray_line_height(self.region, self.rv3d, self.start_co, self.base, self.axis)
        else:
            point = self._ray(co, self.base, self.drag_n)
            start = self.drag_origin
        if point is None:
            return
        raw = self.base + point - start
        if self.constraint_normal is not None:
            raw -= self.constraint_normal * (raw - self.base).dot(self.constraint_normal)
        point = snap_point(context, self.region, self.rv3d, co, raw, self.plane,
                           exclude=[ob for ob in self.objects if ob.mode != "EDIT"],
                           base=self.base, axis=self.axis,
                           constraint_plane=(self.base, self.constraint_normal) if self.constraint_normal is not None else None)
        if self.kind == "MOVE":
            delta = point - self.base
            if self.axis is not None:
                delta = self.axis * delta.dot(self.axis)
            if self.constraint_normal is not None:
                delta -= self.constraint_normal * delta.dot(self.constraint_normal)
            if self.number not in {"", "-", ".", "-."}:
                delta = (self.axis if self.axis is not None else self.u) * float(self.number)
            mat = Matrix.Translation(delta)
            self.display_center = self.gizmo_pivot + delta
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
                self.scale_factor = factor
                if self.constraint_normal is not None:
                    n = self.constraint_normal
                    mat = Matrix(tuple(tuple((factor if i == j else 0) + (1 - factor) * n[i] * n[j]
                                             for j in range(3)) for i in range(3))).to_4x4()
                else:
                    mat = Matrix.Scale(factor, 4, self.axis) if self.axis is not None else Matrix.Scale(factor, 4)
                from . import max_rotate
                if max_rotate.settings(context).scale_mode == "SQUASH":
                    mat = max_rotate.squash_matrix(factor, self.constraint_axis, self.orientation).to_4x4()
                self.display_basis = mat.to_3x3() @ self.orientation
            mat = Matrix.Translation(self.pivot) @ mat @ Matrix.Translation(-self.pivot)
        self._apply(context, mat)
        context.area.tag_redraw()

    def _finish(self, context, cancel=False):
        from . import max_gizmos, max_rotate
        if self._closed:
            return {"CANCELLED"}
        self._closed = True
        max_gizmos.finish(self.region)
        max_rotate.close_constraints(context, self.poly_targets, cancel)
        if cancel:
            self._apply(context, Matrix.Identity(4))
            if self.clone:
                max_rotate.cancel_clone(context,self.clone)
        else:
            consume_override(context)
            if self.clone:
                max_rotate.defer_clone(context, self.clone)
            else:
                bpy.ops.ed.undo_push(message="Move" if self.kind == "MOVE" else "Scale")
        clear_preview(self.region)
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        return {"CANCELLED"} if cancel or self.clone else {"FINISHED"}

    def modal(self, context, event):
        if self._closed:
            return {"CANCELLED"}
        co = Vector((event.mouse_region_x, event.mouse_region_y))
        if override_event(self, context, event):
            return {"RUNNING_MODAL"}
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
            if event.type in {"F5", "F6", "F7", "F8"}:
                from . import max_rotate
                lock = max_rotate.set_constraint(context, {"F5":"X", "F6":"Y", "F7":"Z", "F8":"CYCLE"}[event.type], self.kind)
                self._set_constraint(tuple(c in lock for c in "XYZ"))
                self.drag_n = self.constraint_normal if self.constraint_normal is not None else self.view_n
                self.drag_origin = self._ray(self.start_co, self.base, self.drag_n)
                self.handle = lock
            if event.type in {"X", "Y", "Z"}:
                index = "XYZ".index(event.type)
                self._set_constraint(tuple((i != index) if event.shift else (i == index) for i in range(3)))
                self.drag_n = self.constraint_normal if self.constraint_normal is not None else (self.n if settings(context).mode != "3D" else self.view_n)
                self.drag_origin = self._ray(self.start_co, self.base, self.drag_n)
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

    def cancel(self, context):
        self._finish(context, True)


class _SnapTool:
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_widget = "MAX_GGT_max_transform"
    bl_options = set()


def _make_tool(name, label, kind, mode):
    return type("MAX_WST_" + name + "_" + mode, (_SnapTool, bpy.types.WorkSpaceTool), {
        "bl_idname": "max.snap_" + name,
        "bl_label": label,
        "bl_description": "Drag a snap base to its target. Right-click cancels",
        "bl_context_mode": mode,
        "bl_icon": {"MOVE": "ops.transform.translate", "ROTATE": "ops.transform.rotate", "SCALE": "ops.transform.resize"}[kind],
        "bl_keymap": (("max.snap_transform", {"type": "LEFTMOUSE", "value": "CLICK_DRAG"}, {"properties": [("kind", kind)]}),
                      ("max.snap_transform", {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "shift": True}, {"properties": [("kind", kind)]}),
                      ("view3d.select", {"type": "LEFTMOUSE", "value": "CLICK"}, {"properties": [("deselect_all", True)]})),
    })


tools = tuple(_make_tool(name, label, kind, mode) for mode in ("OBJECT", "EDIT_MESH")
              for name, label, kind in (("move", "Select and Move", "MOVE"),
                                        ("scale", "Select and Uniform Scale", "SCALE")))


class MAX_GGT_snap_transform(bpy.types.GizmoGroup):
    bl_idname = "MAX_GGT_snap_transform"
    bl_label = "Snap Transform"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        return False  # max_gizmos draws and picks the shared Max transform set.

    def setup(self, context):
        self.handles = []
        colors = ((1, .15, .15), (.3, 1, .2), (.2, .5, 1))
        for kind in ("MOVE", "ROTATE", "SCALE"):
            for i, color in enumerate(colors):
                gizmo = self.gizmos.new("GIZMO_GT_dial_3d" if kind == "ROTATE" else "GIZMO_GT_arrow_3d")
                if kind != "ROTATE":
                    gizmo.draw_style = "BOX" if kind == "SCALE" else "NORMAL"
                gizmo.color = color
                gizmo.alpha = .8
                gizmo.color_highlight = (1, 1, .2)
                gizmo.alpha_highlight = 1
                props = gizmo.target_set_operator("max.snap_transform")
                props.kind = kind
                props.from_gizmo = True
                props.constraint_axis = tuple(j == i for j in range(3))
                self.handles.append((gizmo, kind, i, False))
            if kind != "ROTATE":
                for i, color in enumerate(colors):
                    gizmo = self.gizmos.new("GIZMO_GT_primitive_3d")
                    gizmo.draw_style = "PLANE"
                    gizmo.color = color
                    gizmo.alpha = .25
                    gizmo.color_highlight = (1, 1, .2)
                    gizmo.alpha_highlight = .8
                    gizmo.scale_basis = .18
                    gizmo.use_draw_offset_scale = True
                    props = gizmo.target_set_operator("max.snap_transform")
                    props.kind = kind
                    props.from_gizmo = True
                    props.constraint_axis = tuple(j != i for j in range(3))
                    self.handles.append((gizmo, kind, i, True))
        gizmo = self.gizmos.new("GIZMO_GT_move_3d")
        gizmo.draw_style = "RING_2D"
        gizmo.color = (1, 1, 1)
        gizmo.alpha = .7
        gizmo.color_highlight = (1, 1, .2)
        gizmo.alpha_highlight = 1
        gizmo.scale_basis = .15
        self.center = gizmo

    def draw_prepare(self, context):
        kind = _tool(context).rsplit("_", 1)[-1].upper()
        basis = orientation_basis(context)
        center = _selection_center(context)
        for gizmo, operation, i, plane in self.handles:
            gizmo.hide = operation != kind
            normal = basis.col[i].normalized()
            if plane:
                axes = [basis.col[j] for j in range(3) if j != i]
                normal = axes[0].cross(axes[1]).normalized()
            matrix = normal.to_track_quat("Z", "Y").to_matrix().to_4x4()
            matrix.translation = center
            gizmo.matrix_basis = matrix
            if plane:
                # Put plane handles between their two axes, away from the center.
                a, b = [basis.col[j] for j in range(3) if j != i]
                local = matrix.to_3x3().inverted_safe() @ ((a + b) * 1.8)
                gizmo.matrix_offset = Matrix.Translation(local)
        self.center.matrix_basis = Matrix.Translation(center)
        props = self.center.target_set_operator("max.snap_transform")
        props.kind = kind
        props.from_gizmo = True


classes = (MaxSnapSettings, MAX_OT_snap_settings, MAX_PT_snap_settings, MAX_OT_snap_settings_close,
           MAX_OT_snap_button_listener, MAX_GGT_snap_transform, MAX_OT_snap_clear, MAX_OT_snap_override,
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


def unregister_props():
    global _handle, _guard_generation, _quad_open
    from . import snap_quad
    snap_quad.close_all()
    _guard_generation += 1
    _quad_open = False
    _button_guards.clear()
    for window in list(bpy.context.window_manager.windows):
        if window.as_pointer() in _settings_windows:
            with bpy.context.temp_override(window=window):
                bpy.ops.wm.window_close()
    _settings_windows.clear()
    if bpy.app.timers.is_registered(_ensure_button_listeners):
        bpy.app.timers.unregister(_ensure_button_listeners)
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
    _spinner_values.clear()
    clear_preview()
