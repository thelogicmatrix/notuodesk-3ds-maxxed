"""xView mesh checks, cached highlights and viewport result actions."""

from dataclasses import dataclass, field
from math import frexp, isfinite
from time import perf_counter

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from mathutils import Vector
from mathutils.kdtree import KDTree


# Autodesk 2026 xView Menu / Using xView. Both text and flagged geometry are green.
# GUID-74ABCC3C-73E3-40E4-B8D3-ED802E05E2E7
# GUID-72946D6A-B24A-4228-B038-16FA45D4354E
CHECKS = (
    ("FACE_ORIENTATION", "Face Orientation", "FACE"),
    ("OVERLAPPING_FACES", "Overlapping Faces", "FACE"),
    ("OPEN_EDGES", "Open Edges", "EDGE"),
    ("MULTIPLE_EDGES", "Multiple Edges", "EDGE"),
    ("ISOLATED_VERTICES", "Isolated Vertices", "VERT"),
    ("OVERLAPPING_VERTICES", "Overlapping Vertices", "VERT"),
    ("T_VERTICES", "T-Vertices", "VERT"),
    ("MISSING_UVW", "Missing UVW Coordinates", "FACE"),
    ("FLIPPED_UVW", "Flipped UVW Faces", "FACE"),
    ("OVERLAPPED_UVW", "Overlapped UVW Faces", "FACE"),
)
LABELS = {key: label for key, label, _ in CHECKS}
DOMAINS = {key: domain for key, _, domain in CHECKS}
CONFIGURABLE = {"OVERLAPPING_VERTICES", "OVERLAPPING_FACES", "T_VERTICES"}
GREEN = (0.0, 1.0, 0.0, 1.0)
_cache = {}
_dirty = set()
_handles = []
_hits = {}
_settings_key = None
_selection_key = None
_status = ""
_last_view = ((0.0, 0.0, 1.0), None)


@dataclass
class Result:
    domain: str
    indices: set
    points: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    seconds: float = 0.0
    batches: object = None
    orientation: list = field(default_factory=list)
    face_triangles: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)


def _cross(a, b, c):
    return (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x)


def _intersection_area(a, b):
    """Positive triangle intersection area, excluding shared points and edges."""
    poly = list(a)
    sign = 1 if _cross(*b) >= 0 else -1
    for i in range(3):
        p, q = b[i], b[(i+1) % 3]
        source, poly = poly, []
        if not source:
            return 0.0
        prev = source[-1]
        dp = sign * _cross(p, q, prev)
        for curr in source:
            dc = sign * _cross(p, q, curr)
            if (dc > 0) != (dp > 0):
                poly.append(prev + (curr-prev) * (dp/(dp-dc)))
            if dc >= 0:
                poly.append(curr)
            prev, dp = curr, dc
    if len(poly) < 3:
        return 0.0
    # Translate before summing to keep small islands far from the origin stable.
    return abs(sum(_cross(poly[0], poly[i], poly[i+1])
                   for i in range(1, len(poly)-1))) * 0.5


def _bounds_pairs(tris, padding):
    """Size-bucketed KD trees also find coplanar containment and crossing faces."""
    bounds = [(tuple(min(p[k] for p in triangle)-padding for k in range(3)),
               tuple(max(p[k] for p in triangle)+padding for k in range(3))) for _, triangle in tris]
    centers, radii, groups = [], [], {}
    for i, (_, triangle) in enumerate(tris):
        center = sum(triangle, Vector())/3
        radius = max((p-center).length for p in triangle) + padding*2
        centers.append(center)
        radii.append(radius)
        groups.setdefault(frexp(radius)[1], []).append(i)
    trees = []
    for indices in groups.values():
        kd = KDTree(len(indices))
        for i in indices:
            kd.insert(centers[i], i)
        kd.balance()
        trees.append((kd, max(radii[i] for i in indices)))
    for i, center in enumerate(centers):
        a = bounds[i]
        for tree, radius in trees:
            for _, j, _ in tree.find_range(center, radii[i]+radius+1e-7):
                if j <= i:
                    continue
                b = bounds[j]
                overlap = [min(a[1][k], b[1][k])-max(a[0][k], b[0][k]) for k in range(3)]
                # Positive area needs positive extent along at least two axes.
                if min(overlap) >= 0 and sum(v > 2*padding+1e-12 for v in overlap) >= 2:
                    yield i, j


def _face_overlaps(tris, tolerance, uv=False):
    """Bounding-box broad phase, then positive-area coplanar intersection."""
    if not tris:
        return set()
    found = set()
    for i, j in _bounds_pairs(tris, 0 if uv else tolerance*.5):
        if tris[i][0] == tris[j][0]:
            continue
        fi, a = tris[i]
        fj, b = tris[j]
        if fi in found and fj in found:
            continue
        if uv:
            aa, bb = a, b
        else:
            normal = (a[1]-a[0]).cross(a[2]-a[0])
            other = (b[1]-b[0]).cross(b[2]-b[0])
            if normal.length_squared < 1e-24 or other.length_squared < 1e-24:
                continue
            normal.normalize()
            other.normalize()
            if abs(normal.dot(other)) < .99999:
                continue
            if max(abs(normal.dot(p-a[0])) for p in b) > tolerance + 1e-7:
                continue
            drop = max(range(3), key=lambda k: abs(normal[k]))
            axes = [k for k in range(3) if k != drop]
            aa = [Vector((p[axes[0]], p[axes[1]])) for p in a]
            bb = [Vector((p[axes[0]], p[axes[1]])) for p in b]
        if _intersection_area(aa, bb) > 1e-12:
            found.update((fi, fj))
    return found


def analyze(ob, check, tolerance=.001, view_direction=(0, 0, 1), view_origin=None):
    """Check the editable cage, in world units, without changing its selection."""
    started = perf_counter()
    owned = ob.mode != "EDIT"
    bm = bmesh.new() if owned else bmesh.from_edit_mesh(ob.data)
    if owned:
        bm.from_mesh(ob.data)
    try:
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for seq in (bm.verts, bm.edges, bm.faces):
            seq.index_update()
        world = ob.matrix_world
        coords = [world @ v.co for v in bm.verts]
        ids = set()
        orientation = []
        domain = DOMAINS[check]
        if check == "OPEN_EDGES":
            ids = {e.index for e in bm.edges if not e.hide and len(e.link_faces) == 1}
        elif check == "MULTIPLE_EDGES":
            ids = {e.index for e in bm.edges if not e.hide and
                   (len(e.link_faces) > 2 or (len(e.link_faces) == 2 and not e.is_contiguous))}
        elif check == "ISOLATED_VERTICES":
            ids = {v.index for v in bm.verts if not v.hide and not v.link_edges and not v.link_faces}
        elif check in {"OVERLAPPING_VERTICES", "T_VERTICES"}:
            kd = KDTree(len(coords))
            for i, co in enumerate(coords):
                kd.insert(co, i)
            kd.balance()
            if check == "OVERLAPPING_VERTICES":
                for v in bm.verts:
                    if not v.hide:
                        for _, j, _ in kd.find_range(coords[v.index], tolerance):
                            if j != v.index and not bm.verts[j].hide:
                                ids.update((v.index, j))
            else:
                # Max documents vertices sharing three edges. Include unwelded
                # geometric T-junctions too, using the requested distance tolerance.
                ids = {v.index for v in bm.verts if not v.hide and len(v.link_edges) == 3}
                for edge in bm.edges:
                    if edge.hide:
                        continue
                    a, b = (coords[v.index] for v in edge.verts)
                    delta = b-a
                    length = delta.length
                    if length <= 2*tolerance:
                        continue
                    ends = {v.index for v in edge.verts}
                    for co, j, _ in kd.find_range((a+b)*.5, length*.5+tolerance):
                        if j in ends or j in ids or bm.verts[j].hide or not bm.verts[j].link_edges:
                            continue
                        t = (co-a).dot(delta) / delta.length_squared
                        if tolerance/length < t < 1-tolerance/length and (co-a-t*delta).length <= tolerance:
                            ids.add(j)
        elif check == "FACE_ORIENTATION":
            direction = Vector(view_direction)
            origin = Vector(view_origin) if view_origin is not None else None
            for face in bm.faces:
                if face.hide or len(face.verts) < 3:
                    continue
                points = [coords[v.index] for v in face.verts]
                # Newell normal handles concave polygons and mirrored transforms.
                normal = sum((points[i].cross(points[(i+1) % len(points)])
                              for i in range(len(points))), Vector())
                toward_eye = origin - sum(points, Vector())/len(points) if origin is not None else direction
                orientation.append((face.index, normal, sum(points, Vector())/len(points)))
                if normal.dot(toward_eye) < 0:
                    ids.add(face.index)
        elif check == "OVERLAPPING_FACES":
            triangles = [(loops[0].face.index, [coords[l.vert.index] for l in loops])
                         for loops in bm.calc_loop_triangles() if not loops[0].face.hide]
            ids = _face_overlaps(triangles, tolerance)
        else:
            uv_layer = bm.loops.layers.uv.active
            if check == "MISSING_UVW":
                ids = {f.index for f in bm.faces if not f.hide and
                       (uv_layer is None or any(not all(isfinite(v) for v in l[uv_layer].uv) for l in f.loops))}
            elif uv_layer is not None:
                if check == "FLIPPED_UVW":
                    for face in bm.faces:
                        if face.hide:
                            continue
                        uvs = [l[uv_layer].uv.copy() for l in face.loops]
                        if len(uvs) >= 3 and sum(_cross(uvs[0], uvs[i], uvs[i+1])
                                                  for i in range(1, len(uvs)-1)) < -1e-12:
                            ids.add(face.index)
                elif check == "OVERLAPPED_UVW":
                    triangles = [(loops[0].face.index, [Vector((*l[uv_layer].uv, 0)) for l in loops])
                                 for loops in bm.calc_loop_triangles() if not loops[0].face.hide
                                 and all(all(isfinite(v) for v in l[uv_layer].uv) for l in loops)]
                    ids = _face_overlaps(triangles, 0, uv=True)
        result = Result(domain, ids)
        result.orientation = orientation
        selection_mode = bpy.context.tool_settings.mesh_select_mode
        preserve_selection = ob.mode == "EDIT" and selection_mode[("VERT", "EDGE", "FACE").index(domain)]
        elems = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[domain]
        drawn = {i for i in ids if not preserve_selection or not elems[i].select}
        if check == "FACE_ORIENTATION":
            for loops in bm.calc_loop_triangles():
                if not preserve_selection or not loops[0].face.select:
                    result.face_triangles.setdefault(loops[0].face.index, []).extend(coords[l.vert.index] for l in loops)
        if domain == "VERT":
            result.points = [coords[i] for i in sorted(drawn)]
        elif domain == "EDGE":
            result.lines = [coords[v.index] for i in sorted(drawn) for v in bm.edges[i].verts]
        elif drawn:
            result.triangles = [coords[l.vert.index] for loops in bm.calc_loop_triangles()
                                if loops[0].face.index in drawn for l in loops]
        result.seconds = perf_counter()-started
        return result
    finally:
        if owned:
            bm.free()


def _oriented(result, view):
    if not result.orientation:
        return result
    if view not in result.views:
        direction, origin = Vector(view[0]), Vector(view[1]) if view[1] is not None else None
        ids = {i for i, normal, center in result.orientation
               if normal.dot(origin-center if origin is not None else direction) < 0}
        filtered = Result("FACE", ids, triangles=[p for i in sorted(ids) for p in result.face_triangles.get(i, ())])
        if len(result.views) >= 8:
            result.views.clear()
        result.views[view] = filtered
    return result.views[view]


def select_results(context, results):
    """Select exact base-mesh elements in Edit Poly, across checked objects."""
    objects = [context.view_layer.objects.get(name) for name in results]
    objects = [ob for ob in objects if ob is not None and ob.type == "MESH" and not ob.hide_get()]
    if not objects:
        return False
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for ob in context.view_layer.objects:
        ob.select_set(ob in objects)
    context.view_layer.objects.active = objects[0]
    domain = next(iter(results.values())).domain
    context.tool_settings.mesh_select_mode = tuple(domain == kind for kind in ("VERT", "EDGE", "FACE"))
    context.window_manager.max_sublevel = {"VERT": 1, "EDGE": 2, "FACE": 4}[domain]
    bpy.ops.object.mode_set(mode="EDIT")
    # Linked duplicates share one BMesh. Merge their results before changing it.
    by_mesh = {}
    for ob in objects:
        by_mesh.setdefault(ob.data.as_pointer(), (ob, set()))[1].update(results[ob.name].indices)
    for ob, indices in by_mesh.values():
        bm = bmesh.from_edit_mesh(ob.data)
        for seq in (bm.verts, bm.edges, bm.faces):
            seq.ensure_lookup_table()
            seq.index_update()
            for elem in seq:
                elem.select_set(False)
        elems = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[domain]
        for i in indices:
            if i < len(elems):
                elems[i].hide_set(False)
                elems[i].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
    return True


def clear_cache(*_args):
    global _settings_key, _selection_key
    _cache.clear()
    _dirty.clear()
    _hits.clear()
    _settings_key = _selection_key = None


def _redraw(context=None):
    context = context or bpy.context
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _changed(self, context):
    clear_cache()
    _redraw(context)


class MAX_PG_xview(bpy.types.PropertyGroup):
    check: EnumProperty(name="xView", items=[("NONE", "Hide", "Hide xView")]+
                        [(key, label, "") for key, label, _ in CHECKS], default="NONE", update=_changed)
    selected_only: BoolProperty(name="Selected Only", default=True, update=_changed)
    # Autodesk's public help does not publish a numeric default. See README.
    tolerance: FloatProperty(name="Tolerance", default=.001, min=0.0000001, precision=6,
                             description="Maximum distance in Blender world units", update=_changed)
    see_through: BoolProperty(name="See-Through", default=True, update=lambda s, c: _redraw(c))
    auto_update: BoolProperty(name="Auto Update", default=True)
    display_on_top: BoolProperty(name="Display On Top", default=False, update=lambda s, c: _redraw(c))


def refresh(context=None, force=False, view=None):
    """Recompute only dirty checked objects. Draw callbacks never analyze meshes."""
    global _settings_key, _selection_key, _status
    context = context or bpy.context
    settings = context.scene.max_xview
    if settings.check == "NONE":
        clear_cache()
        return {}
    view = view or _last_view
    key = (context.scene.as_pointer(), context.view_layer.as_pointer(), settings.check,
           settings.tolerance, settings.selected_only, tuple(context.tool_settings.mesh_select_mode))
    objects = [ob for ob in context.view_layer.objects if ob.type == "MESH" and ob.visible_get()
               and (not settings.selected_only or ob.select_get())]
    selection = tuple((ob.name, ob.as_pointer(), ob.data.as_pointer(), ob.mode) for ob in objects)
    if key != _settings_key:
        _cache.clear()
        _settings_key = key
    if selection != _selection_key:
        names = {ob.name for ob in objects}
        for name in list(_cache):
            if name not in names:
                del _cache[name]
        _selection_key = selection
    _status = "" if objects else ("No selection" if settings.selected_only else "Unsupported object type")
    for ob in objects:
        entry = _cache.get(ob.name)
        signature = (ob.as_pointer(), ob.data.as_pointer(), ob.mode)
        if force or entry is None or entry[0] != signature or (settings.auto_update and ob.name in _dirty):
            result = analyze(ob, settings.check, settings.tolerance, *view)
            _cache[ob.name] = (signature, result)
            _dirty.discard(ob.name)
    return {name: _oriented(entry[1], view) if settings.check == "FACE_ORIENTATION" else entry[1]
            for name, entry in _cache.items()}


@persistent
def _depsgraph(scene, depsgraph):
    if not _cache:
        return
    watched = {signature[0]: name for name, (signature, _) in _cache.items()}
    meshes = {}
    for name, (signature, _) in _cache.items():
        meshes.setdefault(signature[1], []).append(name)
    for update in depsgraph.updates:
        original = update.id.original
        ptr = original.as_pointer()
        if isinstance(original, bpy.types.Mesh):
            _dirty.update(meshes.get(ptr, ()))
        elif isinstance(original, bpy.types.Object) and ptr in watched and (update.is_updated_geometry or update.is_updated_transform):
            _dirty.add(watched[ptr])


@persistent
def _on_load(*_args):
    clear_cache()


def _tick():
    if not hasattr(bpy.types.Scene, "max_xview"):
        return None
    if bpy.context.scene.max_xview.check != "NONE":
        refresh()
        _redraw()
    return .2


def _visible(context, name):
    ob = context.view_layer.objects.get(name)
    settings = context.scene.max_xview
    return ob is not None and ob.visible_get() and (not settings.selected_only or ob.select_get())


def _draw_geometry():
    import gpu
    from gpu_extras.batch import batch_for_shader
    context = bpy.context
    if context.scene.max_xview.check == "NONE":
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    old_depth = gpu.state.depth_test_get()
    old_mask = gpu.state.depth_mask_get()
    old_blend = gpu.state.blend_get()
    try:
        gpu.state.depth_test_set("NONE" if context.scene.max_xview.see_through else "LESS_EQUAL")
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set("ALPHA")
        gpu.state.point_size_set(6.0)
        gpu.state.line_width_set(3.0)
        shader.bind()
        shader.uniform_float("color", GREEN)
        for name, (_, result) in _cache.items():
            if not _visible(context, name):
                continue
            if context.scene.max_xview.check == "FACE_ORIENTATION":
                result = _oriented(result, _view(context))
            if result.batches is None:
                result.batches = [batch_for_shader(shader, kind, {"pos": coords})
                                  for kind, coords in (("POINTS", result.points), ("LINES", result.lines),
                                                       ("TRIS", result.triangles)) if coords]
            for batch in result.batches:
                batch.draw(shader)
    finally:
        gpu.state.depth_test_set(old_depth)
        gpu.state.depth_mask_set(old_mask)
        gpu.state.blend_set(old_blend)
        gpu.state.point_size_set(1.0)
        gpu.state.line_width_set(1.0)


def _view(context):
    rv3d = context.region_data
    direction = rv3d.view_rotation @ Vector((0, 0, 1))
    origin = rv3d.view_matrix.inverted().translation if rv3d.is_perspective else None
    return tuple(direction), tuple(origin) if origin is not None else None


def _draw_text():
    import blf
    global _last_view
    context = bpy.context
    region = context.region
    if region is None or context.region_data is None:
        return
    settings = context.scene.max_xview
    if settings.check == "NONE":
        _hits.pop(region.as_pointer(), None)
        return
    _last_view = _view(context)
    scale = context.preferences.system.ui_scale
    font, x = 0, 12*scale
    blf.size(font, 13*scale)
    count = sum(len((_oriented(result, _last_view) if settings.check == "FACE_ORIENTATION" else result).indices)
                for name, (_, result) in _cache.items() if _visible(context, name))
    unit = {"VERT": "Vertices", "EDGE": "Edges", "FACE": "Faces"}[DOMAINS[settings.check]]
    text = f"{LABELS[settings.check]}: {_status or str(count)+' '+unit}"
    top = region.height
    area = context.area
    if region.y + region.height >= area.y + area.height - 2:
        for header in area.regions:
            if header.type in {"HEADER", "TOOL_HEADER"} and header.height > 1 and header.y >= region.y + region.height//2:
                top -= header.height
    y = top - 44*scale if settings.display_on_top else 43*scale
    rects = []

    def line(label, action, px, py):
        blf.color(font, *GREEN)
        blf.position(font, px, py, 0)
        blf.draw(font, label)
        width, height = blf.dimensions(font, label)
        rects.append((action, px, py-4*scale, px+width, py+height+4*scale))
        return width

    line(text, "MENU", x, y)
    y -= 21*scale
    if settings.check in CONFIGURABLE:
        x += line("Click Here To Configure", "CONFIGURE", x, y) + 18*scale
    x += line("Select Results", "SELECT", x, y) + 18*scale
    line("Hide", "HIDE", x, y)
    _hits[region.as_pointer()] = rects


def click(context, event):
    """Called before normal label/selection clicks. No persistent modal tool."""
    if context.scene.max_xview.check == "NONE":
        return False
    for action, x0, y0, x1, y1 in _hits.get(context.region.as_pointer(), ()):
        if x0 <= event.mouse_region_x <= x1 and y0 <= event.mouse_region_y <= y1:
            if action == "MENU":
                bpy.ops.wm.call_menu(name="MAX_MT_xview")
            elif action == "CONFIGURE":
                bpy.ops.max.xview_configure("INVOKE_DEFAULT")
            elif action == "SELECT":
                bpy.ops.max.xview_select()
            else:
                context.scene.max_xview.check = "NONE"
            return True
    return False


class MAX_OT_xview_check(bpy.types.Operator):
    bl_idname = "max.xview_check"
    bl_label = "xView"
    check: EnumProperty(items=[("NONE", "Hide", "")]+[(k, l, "") for k, l, _ in CHECKS])

    def execute(self, context):
        settings = context.scene.max_xview
        settings.check = "NONE" if settings.check == self.check else self.check
        view = _view(context) if context.region_data is not None else None
        refresh(context, force=True, view=view)
        _redraw(context)
        return {"FINISHED"}


class MAX_OT_xview_select(bpy.types.Operator):
    bl_idname = "max.xview_select"
    bl_label = "Select Results"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.max_xview.check != "NONE" and context.mode in {"OBJECT", "EDIT_MESH"}

    def execute(self, context):
        view = _view(context) if context.region_data is not None else None
        results = refresh(context, force=True, view=view)
        if not results or not any(r.indices for r in results.values()):
            self.report({"INFO"}, "No results")
            return {"CANCELLED"}
        select_results(context, results)
        return {"FINISHED"}


class MAX_OT_xview_configure(bpy.types.Operator):
    bl_idname = "max.xview_configure"
    bl_label = "xView Configuration"
    tolerance: FloatProperty(name="Tolerance", min=.0000001, precision=6, default=.001)

    @classmethod
    def poll(cls, context):
        return context.scene.max_xview.check in CONFIGURABLE

    def invoke(self, context, event):
        self.tolerance = context.scene.max_xview.tolerance
        return context.window_manager.invoke_props_dialog(self, width=220)

    def draw(self, context):
        row = self.layout.row(align=True)
        row.label(text="Tolerance:")
        row.prop(self, "tolerance", text="")

    def execute(self, context):
        context.scene.max_xview.tolerance = self.tolerance
        refresh(context, force=True)
        return {"FINISHED"}


class MAX_MT_xview(bpy.types.Menu):
    bl_label = "xView"
    bl_idname = "MAX_MT_xview"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = "INVOKE_DEFAULT"
        settings = context.scene.max_xview
        from .viewport_menus import _space
        space = _space(context)
        stats = space is not None and space.overlay.show_stats
        lay.operator("max.toggle", text="Show Statistics",
                     icon="CHECKMARK" if stats else "BLANK1").what = "STATS"
        for key, label, _ in CHECKS:
            lay.operator("max.xview_check", text=label,
                         icon="CHECKMARK" if settings.check == key else "BLANK1").check = key
        lay.separator()
        lay.operator("max.xview_select", text="Select Results")
        lay.separator()
        for prop in ("selected_only", "see_through", "auto_update", "display_on_top"):
            lay.prop(settings, prop)
        lay.separator()
        lay.operator("max.xview_configure", text="Configure...")
        if settings.check != "NONE":
            lay.operator("max.xview_check", text="Hide").check = "NONE"


classes = (MAX_PG_xview, MAX_OT_xview_check, MAX_OT_xview_select, MAX_OT_xview_configure, MAX_MT_xview)


def register():
    bpy.types.Scene.max_xview = PointerProperty(type=MAX_PG_xview)
    if not bpy.app.background:
        _handles.extend((bpy.types.SpaceView3D.draw_handler_add(_draw_geometry, (), "WINDOW", "POST_VIEW"),
                         bpy.types.SpaceView3D.draw_handler_add(_draw_text, (), "WINDOW", "POST_PIXEL")))
        bpy.app.timers.register(_tick, first_interval=.2, persistent=True)
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.undo_post.append(_on_load)
    bpy.app.handlers.redo_post.append(_on_load)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for handle in _handles:
        bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
    _handles.clear()
    for handlers, fn in ((bpy.app.handlers.depsgraph_update_post, _depsgraph),
                         (bpy.app.handlers.load_post, _on_load),
                         (bpy.app.handlers.undo_post, _on_load),
                         (bpy.app.handlers.redo_post, _on_load)):
        if fn in handlers:
            handlers.remove(fn)
    clear_cache()
    del bpy.types.Scene.max_xview
