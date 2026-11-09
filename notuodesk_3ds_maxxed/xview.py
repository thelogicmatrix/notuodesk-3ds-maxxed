"""xView mesh checks, cached highlights and viewport result actions."""

from dataclasses import dataclass, field
from array import array
from math import floor, frexp, isfinite
from itertools import product
from time import perf_counter

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


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
CONFIGURABLE = {"OVERLAPPING_VERTICES", "OVERLAPPING_FACES"}
GREEN = (0.0, 1.0, 0.0, 1.0)
_states = {}
_handles = []
_hits = {}
_last_view = ((0.0, 0.0, 1.0), None)
STEP_BUDGET = .008


@dataclass
class Result:
    domain: str
    indices: set
    points: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    seconds: float = 0.0
    batches: object = None
    orientation: object = field(default_factory=lambda: array('d'))
    face_triangles: object = field(default_factory=lambda: array('d'))
    face_ranges: object = field(default_factory=lambda: array('i'))
    views: dict = field(default_factory=dict)
    selection_safe: bool = True
    complete: bool = False
    revision: int = 0


@dataclass
class State:
    cache: dict = field(default_factory=dict)
    jobs: dict = field(default_factory=dict)
    view_jobs: dict = field(default_factory=dict)
    dirty: set = field(default_factory=set)
    watched: dict = field(default_factory=dict)
    key: object = None
    status: str = ""
    changed: bool = False
    requested_views: dict = field(default_factory=dict)


class Job:
    def __init__(self, ob, check, tolerance, view, depsgraph):
        self.view = view
        self.result = Result(DOMAINS[check], set())
        self.steps = _analyze_steps(ob, check, tolerance, view, depsgraph, self.result)

    def close(self):
        self.steps.close()

    def advance(self, deadline):
        while perf_counter() < deadline:
            try:
                next(self.steps)
            except StopIteration:
                self.result.complete = True
                return True
        return False


def _orientation_steps(source, view, result):
    direction = Vector(view[0])
    origin = Vector(view[1]) if view[1] is not None else None
    for k in range(0, len(source.orientation), 7):
        i = int(source.orientation[k])
        normal = Vector(source.orientation[k+1:k+4])
        center = Vector(source.orientation[k+4:k+7])
        if normal.dot(origin-center if origin is not None else direction) < 0:
            result.indices.add(i)
            start, end = source.face_ranges[i*2:i*2+2]
            for j in range(start, end, 3):
                result.triangles.append(Vector(source.face_triangles[j:j+3]))
                yield
            result.revision += 1
        yield


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


def _triangle_overlap(a, b, tolerance, uv):
    if uv:
        aa, bb = a, b
    else:
        normal = (a[1]-a[0]).cross(a[2]-a[0])
        other = (b[1]-b[0]).cross(b[2]-b[0])
        if normal.length_squared < 1e-24 or other.length_squared < 1e-24:
            return False
        normal.normalize()
        other.normalize()
        if abs(normal.dot(other)) < .99999:
            return False
        if max(abs(normal.dot(p-a[0])) for p in b) > tolerance + 1e-7:
            return False
        drop = max(range(3), key=lambda k: abs(normal[k]))
        axes = [k for k in range(3) if k != drop]
        aa = [Vector((p[axes[0]], p[axes[1]])) for p in a]
        bb = [Vector((p[axes[0]], p[axes[1]])) for p in b]
    return _intersection_area(aa, bb) > 1e-12


def _triangle_indices(points):
    if len(points) == 3:
        return ((0, 1, 2),)
    triangles = tessellate_polygon([points]) if len(points) > 3 else ()
    if not triangles or isinstance(triangles[0][0], int):
        return triangles
    # Accept both index-returning and vector-returning Blender tessellators.
    lookup = {tuple(p): i for i, p in enumerate(points)}
    return (tuple(lookup[tuple(p)] for p in tri) for tri in triangles)


def _triangles(points):
    return (tuple(points[i] for i in tri) for tri in _triangle_indices(points))


def _clear_evaluated(evaluated):
    try:
        evaluated.to_mesh_clear()
    except ReferenceError:
        # File load / undo can dispose the evaluated object before load_post.
        pass


def _mesh_overlap_steps(ob, check, tolerance, depsgraph, result):
    """Compact numeric snapshots avoid Python GC pauses on large overlap jobs."""
    started = perf_counter()
    evaluated = None
    uv = check == "OVERLAPPED_UVW"
    coords, tri_coords, bounds = array('d'), array('d'), array('d')
    # Each display triangle stores face, three original vertex IDs and selection.
    triangles, levels = array('i'), {}
    try:
        yield
        editing = ob.mode == "EDIT"
        world = ob.matrix_world.copy()
        preserve = editing and bpy.context.tool_settings.mesh_select_mode[2]
        if editing:
            data = bmesh.from_edit_mesh(ob.data)
            data.verts.ensure_lookup_table()
            data.verts.index_update()
            data.faces.index_update()
            vertices, faces = data.verts, data.faces
            layer = data.loops.layers.uv.active
        else:
            if any(m.show_viewport for m in ob.modifiers):
                evaluated = ob.evaluated_get(depsgraph or bpy.context.evaluated_depsgraph_get())
                data = evaluated.to_mesh()
                result.selection_safe = False
            else:
                data = ob.data
            vertices, faces = data.vertices, data.polygons
            layer = data.uv_layers.active
        yield
        for v in vertices:
            coords.extend(world @ v.co)
            yield
        for face in faces:
            if face.hide or (uv and layer is None):
                yield
                continue
            loops = tuple(face.loops) if editing else tuple(data.loops[i] for i in face.loop_indices)
            vi = tuple(l.vert.index if editing else l.vertex_index for l in loops)
            points = [Vector(coords[i*3:i*3+3]) for i in vi]
            local_tris = _triangle_indices(points)
            uvs = ([l[layer].uv.copy() for l in loops] if editing else
                   [layer.data[l.index].uv.copy() for l in loops]) if uv else None
            for local in local_tris:
                source = [Vector((*uvs[i], 0)) for i in local] if uv else [points[i] for i in local]
                if not all(all(isfinite(v) for v in p) for p in source):
                    yield
                    continue
                triangles.extend((face.index, *(vi[i] for i in local), int(preserve and face.select)))
                for p in source:
                    tri_coords.extend(p)
                yield
            yield
        vertices = faces = data = layer = None
        if evaluated is not None:
            _clear_evaluated(evaluated)
            evaluated = None
        padding = 0 if uv else tolerance*.5
        tri_levels = array('i')
        for i in range(len(triangles)//5):
            p = tri_coords[i*9:i*9+9]
            lo = tuple(min(p[k], p[k+3], p[k+6])-padding for k in range(3))
            hi = tuple(max(p[k], p[k+3], p[k+6])+padding for k in range(3))
            bounds.extend((*lo, *hi))
            size = max(max(hi[k]-lo[k] for k in range(3)), 1e-12)
            level = frexp(size)[1]
            levels[level] = max(levels.get(level, 0), size)
            tri_levels.append(level)
            yield
        grids = {}
        for i in range(len(triangles)//5):
            a = bounds[i*6:i*6+6]
            level = tri_levels[i]
            cell_size = levels[level]
            cell = tuple(floor((a[k]+a[k+3])*.5/cell_size) for k in range(3))
            if level not in grids:
                grids[level] = ({}, list(cell), list(cell))
            grid, lower, upper = grids[level]
            grid.setdefault(cell, array('i')).append(i)
            for k in range(3):
                lower[k] = min(lower[k], cell[k])
                upper[k] = max(upper[k], cell[k])
            yield
        found = result.indices
        for i in range(len(triangles)//5):
            fi = triangles[i*5]
            a = bounds[i*6:i*6+6]
            for level, (grid, lower, upper) in grids.items():
                if level < tri_levels[i]:
                    continue
                cell_size = levels[level]
                cell = tuple(floor((a[k]+a[k+3])*.5/cell_size) for k in range(3))
                ranges = [range(max(lower[k], cell[k]-1), min(upper[k], cell[k]+1)+1) for k in range(3)]
                for key in product(*ranges):
                    for j in grid.get(key, ()):
                        fj = triangles[j*5]
                        if ((level != tri_levels[i] or j > i) and fi != fj
                                and not (fi in found and fj in found)):
                            b = bounds[j*6:j*6+6]
                            extent = [min(a[k+3], b[k+3])-max(a[k], b[k]) for k in range(3)]
                            if min(extent) >= 0 and sum(v > 2*padding+1e-12 for v in extent) >= 2:
                                aa = [Vector(tri_coords[i*9+k:i*9+k+3]) for k in (0,3,6)]
                                bb = [Vector(tri_coords[j*9+k:j*9+k+3]) for k in (0,3,6)]
                                if _triangle_overlap(aa, bb, tolerance, uv):
                                    found.update((fi, fj))
                        yield
                    yield
            yield
        for i in range(len(triangles)//5):
            fi, a, b, c, selected = triangles[i*5:i*5+5]
            if fi in found and not selected:
                for vi in (a,b,c):
                    result.triangles.append(Vector(coords[vi*3:vi*3+3]))
                result.revision += 1
            yield
        result.seconds = perf_counter()-started
    finally:
        if evaluated is not None:
            _clear_evaluated(evaluated)


def _analyze_steps(ob, check, tolerance, view, depsgraph, result):
    """Read evaluated geometry or the live cage in bounded, cancellable steps."""
    if check in {"OVERLAPPING_FACES", "OVERLAPPED_UVW"}:
        yield from _mesh_overlap_steps(ob, check, tolerance, depsgraph, result)
        return
    started = perf_counter()
    evaluated = None
    try:
        yield
        editing = ob.mode == "EDIT"
        world = ob.matrix_world.copy()
        preserve = editing and bpy.context.tool_settings.mesh_select_mode[
            ("VERT", "EDGE", "FACE").index(result.domain)]
        if editing:
            data = bmesh.from_edit_mesh(ob.data)
            for seq in (data.verts, data.edges, data.faces):
                seq.ensure_lookup_table()
                seq.index_update()
                yield
            vertices, edges, faces = data.verts, data.edges, data.faces
            layer = data.loops.layers.uv.active
        else:
            if any(m.show_viewport for m in ob.modifiers):
                evaluated = ob.evaluated_get(depsgraph or bpy.context.evaluated_depsgraph_get())
                data = evaluated.to_mesh()
                result.selection_safe = False
            else:
                data = ob.data
            vertices, edges, faces = data.vertices, data.edges, data.polygons
            layer = data.uv_layers.active
        yield
        coords = array('d')
        hidden, selected = bytearray(), bytearray()
        for v in vertices:
            coords.extend(world @ v.co)
            hidden.append(v.hide)
            selected.append(v.select)
            yield
        n = len(hidden)
        degree = array('I', [0])*n
        ends, counts, first = array('I'), array('I'), array('I')
        edge_hidden, edge_selected, winding = bytearray(), bytearray(), bytearray()
        topology = check in {"OPEN_EDGES", "MULTIPLE_EDGES", "ISOLATED_VERTICES", "T_VERTICES"}
        if topology:
            for e in edges:
                a, b = (v.index for v in e.verts) if editing else e.vertices
                ends.extend((a,b))
                degree[a] += 1
                degree[b] += 1
                edge_hidden.append(e.hide)
                edge_selected.append(e.select)
                counts.append(0)
                first.append(0)
                winding.append(0)
                yield
        direction = Vector(view[0])
        origin = Vector(view[1]) if view[1] is not None else None
        face_check = check in {"FACE_ORIENTATION", "MISSING_UVW", "FLIPPED_UVW"}
        if face_check or check in {"OPEN_EDGES", "MULTIPLE_EDGES", "T_VERTICES"}:
            for face in faces:
                loops = tuple(face.loops) if editing else tuple(data.loops[i] for i in face.loop_indices)
                if topology:
                    for loop in loops:
                        edge = loop.edge.index if editing else loop.edge_index
                        a = loop.vert.index if editing else loop.vertex_index
                        if counts[edge] == 0:
                            first[edge] = a
                        elif counts[edge] == 1:
                            winding[edge] = first[edge] == a
                        counts[edge] += 1
                    yield
                    continue
                # Save only numeric face ranges, not millions of nested containers.
                result.face_ranges.extend((len(result.face_triangles), len(result.face_triangles)))
                if face.hide:
                    yield
                    continue
                vi = tuple(loop.vert.index if editing else loop.vertex_index for loop in loops)
                points = [Vector(coords[i*3:i*3+3]) for i in vi]
                bad = False
                if check == "FACE_ORIENTATION":
                    normal = sum((points[k].cross(points[(k+1) % len(points)])
                                  for k in range(len(points))), Vector())
                    center = sum(points, Vector())/len(points)
                    result.orientation.extend((face.index, *normal, *center))
                    bad = normal.dot(origin-center if origin is not None else direction) < 0
                else:
                    uvs = ([loop[layer].uv.copy() for loop in loops] if editing else
                           [layer.data[loop.index].uv.copy() for loop in loops]) if layer else None
                    if check == "MISSING_UVW":
                        bad = uvs is None or any(not all(isfinite(v) for v in uv) for uv in uvs)
                    elif uvs is not None and len(uvs) >= 3:
                        bad = sum(_cross(uvs[0], uvs[k], uvs[k+1]) for k in range(1, len(uvs)-1)) < -1e-12
                if bad:
                    result.indices.add(face.index)
                if not (preserve and face.select) and (bad or check == "FACE_ORIENTATION"):
                    for triangle in _triangles(points):
                        if check == "FACE_ORIENTATION":
                            for p in triangle:
                                result.face_triangles.extend(p)
                        if bad:
                            result.triangles.extend(triangle)
                            result.revision += 1
                        yield
                result.face_ranges[-1] = len(result.face_triangles)
                yield
        vertices = edges = faces = data = layer = None
        if evaluated is not None:
            _clear_evaluated(evaluated)
            evaluated = None
        ids = result.indices
        if check in {"OPEN_EDGES", "MULTIPLE_EDGES"}:
            for i, count in enumerate(counts):
                bad = count == 1 if check == "OPEN_EDGES" else count > 2 or (count == 2 and winding[i])
                if not edge_hidden[i] and bad:
                    ids.add(i)
                    if not (preserve and edge_selected[i]):
                        for vi in ends[i*2:i*2+2]:
                            result.lines.append(Vector(coords[vi*3:vi*3+3]))
                        result.revision += 1
                yield
        elif check in {"ISOLATED_VERTICES", "T_VERTICES"}:
            closed = bytearray([1])*n
            if check == "T_VERTICES":
                for i, count in enumerate(counts):
                    if count != 2:
                        for vi in ends[i*2:i*2+2]:
                            closed[vi] = 0
                    yield
            for i in range(n):
                if not hidden[i] and (degree[i] == 0 if check == "ISOLATED_VERTICES" else
                                      degree[i] == 3 and closed[i]):
                    ids.add(i)
                yield
        elif check == "OVERLAPPING_VERTICES":
            grid = {}
            for i in range(n):
                if not hidden[i]:
                    co = Vector(coords[i*3:i*3+3])
                    key = tuple(floor(v/tolerance) for v in co)
                    for delta in product((-1, 0, 1), repeat=3):
                        for j in grid.get(tuple(key[k]+delta[k] for k in range(3)), ()):
                            if (co-Vector(coords[j*3:j*3+3])).length <= tolerance:
                                ids.update((i,j))
                            yield
                        yield
                    grid.setdefault(key, array('I')).append(i)
                yield
        if result.domain == "VERT":
            for i in ids:
                if not (preserve and selected[i]):
                    result.points.append(Vector(coords[i*3:i*3+3]))
                    result.revision += 1
                yield
        result.seconds = perf_counter()-started
    finally:
        if evaluated is not None:
            _clear_evaluated(evaluated)


def analyze(ob, check, tolerance=.01, view_direction=(0, 0, 1), view_origin=None):
    """Blocking analysis for scripts. UI entry points use refresh's bounded jobs."""
    result = Result(DOMAINS[check], set())
    for _ in _analyze_steps(ob, check, tolerance, (view_direction, view_origin), None, result):
        pass
    result.complete = True
    return result


def select_results(context, results):
    """Select exact base-mesh elements in Edit Poly, across checked objects."""
    if any(not result.selection_safe or not result.complete for result in results.values()):
        return False
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


def _cancel(state, name):
    for key in tuple(state.view_jobs):
        if key[0] == name:
            state.view_jobs.pop(key).close()
    job = state.jobs.pop(name, None)
    if job is not None:
        job.close()


def clear_cache(*_args):
    for state in _states.values():
        for job in (*state.jobs.values(), *state.view_jobs.values()):
            job.close()
    _states.clear()
    _hits.clear()


def state_for(context):
    key = (context.scene.as_pointer(), context.view_layer.as_pointer())
    return _states.setdefault(key, State())


def _settings(settings, context):
    return (settings.check, settings.tolerance, settings.selected_only,
            tuple(context.tool_settings.mesh_select_mode))


def cached_results(context, view=None):
    """Read only this scene/layer/check generation. Never start work in drawing."""
    state = state_for(context)
    settings = context.scene.max_xview
    if settings.check == "NONE" or state.key != _settings(settings, context):
        return {}
    view = view or _last_view
    if settings.check == "FACE_ORIENTATION" and context.region and context.region_data:
        state.requested_views[context.region.as_pointer()] = view
    results = {name: entry[1] for name, entry in state.cache.items()}
    for name, job in state.jobs.items():
        if name not in results:
            results[name] = job.result
    if settings.check == "FACE_ORIENTATION":
        return {name: result.views.get(view, Result("FACE", set(), selection_safe=result.selection_safe))
                for name, result in results.items()}
    return results


def _redraw(context=None):
    context = context or bpy.context
    for win in context.window_manager.windows:
        if context.scene != win.scene or context.view_layer != win.view_layer:
            continue
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _changed(self, context):
    # Keep other windows' scene/layer results intact.
    for key, state in _states.items():
        if key[0] == self.id_data.as_pointer():
            state.changed = True
    _redraw(context)


def _get_tolerance(self):
    return self.face_tolerance if self.check == "OVERLAPPING_FACES" else self.vertex_tolerance


def _set_tolerance(self, value):
    if self.check == "OVERLAPPING_FACES":
        self.face_tolerance = value
    else:
        self.vertex_tolerance = value


class MAX_PG_xview(bpy.types.PropertyGroup):
    check: EnumProperty(name="xView", items=[("NONE", "Hide", "Hide xView")]+
                        [(key, label, "") for key, label, _ in CHECKS], default="NONE", update=_changed)
    selected_only: BoolProperty(name="Selected Only", default=True, update=_changed)
    # Autodesk 2026 SDK CheckerImplementations.h, independent mTolerance members.
    vertex_tolerance: FloatProperty(name="Tolerance", default=.01, min=.0000001, precision=6,
                                    description="Maximum distance in Blender world units", update=_changed)
    face_tolerance: FloatProperty(name="Tolerance", default=.01, min=.0000001, precision=6,
                                  description="Maximum distance in Blender world units", update=_changed)
    tolerance: FloatProperty(name="Tolerance", get=_get_tolerance, set=_set_tolerance,
                             min=.0000001, precision=6)
    see_through: BoolProperty(name="See-Through", default=True, update=lambda s, c: _redraw(c))
    auto_update: BoolProperty(name="Auto Update", default=True, update=lambda s, c: _redraw(c))
    display_on_top: BoolProperty(name="Display On Top", default=False, update=lambda s, c: _redraw(c))


def refresh(context=None, force=False, view=None, budget=STEP_BUDGET):
    """Schedule, cancel and advance jobs within one shared main-thread budget."""
    deadline = perf_counter()+max(0., budget)
    context = context or bpy.context
    settings = context.scene.max_xview
    state = state_for(context)
    key = _settings(settings, context)
    changed = state.changed
    state.changed = False
    if key != state.key:
        for name in tuple(state.jobs):
            _cancel(state, name)
        for job in state.view_jobs.values():
            job.close()
        state.view_jobs.clear()
        state.cache.clear()
        state.key = key
        changed = True
    if settings.check == "NONE":
        state.watched.clear()
        state.dirty.clear()
        return {}
    view = view or _last_view
    visible = [ob for ob in context.view_layer.objects if ob.visible_get(view_layer=context.view_layer)
               and (not settings.selected_only or ob.select_get(view_layer=context.view_layer))]
    objects = [ob for ob in visible if ob.type == "MESH"]
    status = "" if objects else ("Unsupported object type" if visible else "No selection")
    changed |= status != state.status
    state.status = status
    names = {ob.name for ob in objects}
    for name in tuple(state.cache):
        if name not in names:
            _cancel(state, name)
            del state.cache[name]
            changed = True
    for name in tuple(state.jobs):
        if name not in names or name in state.dirty or force:
            _cancel(state, name)
            changed = True
    state.watched = {ob.name: (ob.as_pointer(), ob.data.as_pointer(), ob.mode) for ob in objects}
    for ob in objects:
        entry = state.cache.get(ob.name)
        signature = state.watched[ob.name]
        if ob.name not in state.jobs and (force or entry is None or entry[0] != signature or
                                         (settings.auto_update and ob.name in state.dirty)):
            _cancel(state, ob.name)
            state.jobs[ob.name] = Job(ob, settings.check, settings.tolerance, view, None)
            state.dirty.discard(ob.name)
            changed = True
    for name in tuple(state.jobs):
        if perf_counter() >= deadline:
            break
        job = state.jobs[name]
        previous = job.result.revision
        if job.advance(deadline):
            state.cache[name] = (state.watched[name], job.result)
            if settings.check == "FACE_ORIENTATION":
                job.result.views[job.view] = Result("FACE", job.result.indices, triangles=job.result.triangles,
                                               selection_safe=job.result.selection_safe, complete=True)
            del state.jobs[name]
            changed = True
        elif job.result.revision != previous:
            changed = True
    if settings.check == "FACE_ORIENTATION":
        requested = set(state.requested_views.values()) | {view}
        for name, (_, result) in state.cache.items():
            for requested_view in requested:
                vk = (name, requested_view)
                if requested_view not in result.views and vk not in state.view_jobs:
                    job = Job.__new__(Job)
                    job.result = Result("FACE", set(), selection_safe=result.selection_safe)
                    job.steps = _orientation_steps(result, requested_view, job.result)
                    state.view_jobs[vk] = job
        for vk in tuple(state.view_jobs):
            if perf_counter() >= deadline:
                break
            job = state.view_jobs[vk]
            if job.advance(deadline):
                source = state.cache[vk[0]][1]
                if len(source.views) >= 8:
                    source.views.clear()
                source.views[vk[1]] = job.result
                del state.view_jobs[vk]
                changed = True
    if changed:
        _redraw(context)
    return cached_results(context, view)


@persistent
def _depsgraph(scene, depsgraph):
    for state in _states.values():
        for update in depsgraph.updates:
            original = update.id.original
            ptr = original.as_pointer()
            for name, signature in state.watched.items():
                if ((isinstance(original, bpy.types.Mesh) and ptr == signature[1]) or
                    (isinstance(original, bpy.types.Object) and ptr == signature[0] and
                     (update.is_updated_geometry or update.is_updated_transform))):
                    state.dirty.add(name)


@persistent
def _on_load(*_args):
    clear_cache()


def _tick():
    if not hasattr(bpy.types.Scene, "max_xview"):
        return None
    deadline = perf_counter()+STEP_BUDGET
    seen, busy = set(), False
    for win in bpy.context.window_manager.windows:
        key = (win.scene.as_pointer(), win.view_layer.as_pointer())
        if key in seen:
            continue
        seen.add(key)
        with bpy.context.temp_override(window=win, scene=win.scene, view_layer=win.view_layer):
            refresh(budget=max(0., deadline-perf_counter()))
            state = state_for(bpy.context)
            busy |= bool(state.jobs or state.view_jobs)
    # Remove closed scenes/layers without waking or redrawing idle viewports.
    valid = {(s.as_pointer(), v.as_pointer()) for s in bpy.data.scenes for v in s.view_layers}
    for key in tuple(_states):
        if key not in valid:
            state = _states.pop(key)
            for job in (*state.jobs.values(), *state.view_jobs.values()):
                job.close()
    return .001 if busy else .2


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
        for name, result in cached_results(context, _view(context)).items():
            if not _visible(context, name):
                continue
            if result.batches is None:
                result.batches = []
            # Upload at most one small batch per draw. Partial results append only.
            counts = [sum(n for k, n, _ in result.batches if k == kind)
                      for kind in ("POINTS", "LINES", "TRIS")]
            for kind, coords, count in zip(("POINTS", "LINES", "TRIS"),
                                            (result.points, result.lines, result.triangles), counts):
                if len(coords) > count:
                    chunk = coords[count:count+1536]
                    result.batches.append((kind, len(chunk), batch_for_shader(shader, kind, {"pos": chunk})))
                    context.area.tag_redraw()
                    break
            for _, _, batch in result.batches:
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
    font = 0
    left, right = 0, region.width
    for side in context.area.regions:
        if side.type in {"UI", "TOOLS"} and side.width > 1:
            if side.alignment == "RIGHT":
                right = min(right, side.x-region.x)
            elif side.alignment == "LEFT":
                left = max(left, side.x+side.width-region.x)
    blf.size(font, 13*scale)
    count = sum(len(result.indices)
                for name, result in cached_results(context, _last_view).items() if _visible(context, name))
    unit = {"VERT": "Vertices", "EDGE": "Edges", "FACE": "Faces"}[DOMAINS[settings.check]]
    text = f"[ {LABELS[settings.check]}: {state_for(context).status or str(count)+' '+unit} ]"
    top = region.height
    area = context.area
    if region.y + region.height >= area.y + area.height - 2:
        for header in area.regions:
            if header.type in {"HEADER", "TOOL_HEADER"} and header.height > 1 and header.y >= region.y + region.height//2:
                top -= header.height
    y = top - 44*scale if settings.display_on_top else 85*scale
    rects = []

    def line(label, action, px, py):
        blf.color(font, *GREEN)
        blf.position(font, px, py, 0)
        blf.draw(font, label)
        width, height = blf.dimensions(font, label)
        rects.append((action, px, py-4*scale, px+width, py+height+4*scale))
        return width

    if state_for(context).jobs or state_for(context).view_jobs:
        text += " (Updating...)"
    def centered(label, action, py):
        width, _ = blf.dimensions(font, label)
        return line(label, action, (left+right-width)*.5, py)

    centered(text, "MENU", y)
    y -= 21*scale
    if settings.check in CONFIGURABLE:
        centered("Click Here To Configure", "CONFIGURE", y)
        y -= 21*scale
    if not settings.auto_update:
        centered("Click Here To Update", "UPDATE", y)
        y -= 21*scale
    # Requested shortcuts live below Max's stock result and configuration rows.
    results = cached_results(context, _last_view)
    safe = all(result.selection_safe for result in results.values())
    if safe:
        width = blf.dimensions(font, "Select Results")[0]+18*scale+blf.dimensions(font, "Hide")[0]
        x = (left+right-width)*.5
        x += line("Select Results", "SELECT", x, y)+18*scale
        line("Hide", "HIDE", x, y)
    else:
        centered("Select Results unavailable (evaluated modifiers)", "MENU", y)
        centered("Hide", "HIDE", y-21*scale)
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
            elif action == "UPDATE":
                bpy.ops.max.xview_update()
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
        if state_for(context).jobs or state_for(context).view_jobs:
            self._scene = context.scene
            self._layer = context.view_layer
            self._view = view
            self._timer = context.window_manager.event_timer_add(.03, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        return self._select(context, results)

    def _select(self, context, results):
        if any(not r.selection_safe for r in results.values()):
            self.report({"WARNING"}, "Select Results unavailable for evaluated modifiers. Enter Edit Poly to check the cage")
            return {"CANCELLED"}
        if not results or not any(r.indices for r in results.values()):
            self.report({"INFO"}, "No results")
            return {"CANCELLED"}
        select_results(context, results)
        return {"FINISHED"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} or context.scene != self._scene or context.view_layer != self._layer:
            context.window_manager.event_timer_remove(self._timer)
            return {"CANCELLED"}
        if event.type == "TIMER":
            results = refresh(context, view=self._view)
            if not state_for(context).jobs and not state_for(context).view_jobs:
                context.window_manager.event_timer_remove(self._timer)
                return self._select(context, results)
        return {"PASS_THROUGH"}


class MAX_OT_xview_update(bpy.types.Operator):
    bl_idname = "max.xview_update"
    bl_label = "Click Here To Update"

    @classmethod
    def poll(cls, context):
        return context.scene.max_xview.check != "NONE"

    def execute(self, context):
        refresh(context, force=True)
        _redraw(context)
        return {"FINISHED"}


class MAX_OT_xview_configure(bpy.types.Operator):
    bl_idname = "max.xview_configure"
    bl_label = "xView Configuration"
    tolerance: FloatProperty(name="Tolerance", min=.0000001, precision=6, default=.01)

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
        if not settings.auto_update:
            lay.operator("max.xview_update", text="Click Here To Update")
        lay.separator()
        for prop in ("selected_only", "see_through", "auto_update", "display_on_top"):
            lay.prop(settings, prop)
        lay.separator()
        lay.operator("max.xview_configure", text="Configure...")
        if settings.check != "NONE":
            lay.operator("max.xview_check", text="Hide").check = "NONE"


classes = (MAX_PG_xview, MAX_OT_xview_check, MAX_OT_xview_select, MAX_OT_xview_update,
           MAX_OT_xview_configure, MAX_MT_xview)


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
