"""Quad caps, round/even edge loops, and bounding-box pivots."""

import math

import bmesh
import bpy
from bpy.props import EnumProperty, FloatProperty
from mathutils import Matrix, Vector
from mathutils.geometry import normal


PIVOT_OFFSET = "max_pivot_offset"


def edge_chains(edges):
    """Order disjoint non-branching edge chains. Reject ambiguous junctions."""
    adjacency = {}
    for e in edges:
        for v in e.verts:
            adjacency.setdefault(v, []).append(e)
    if any(len(es) > 2 for es in adjacency.values()):
        raise ValueError("Select separate loops or open chains without branches")
    remaining = set(edges)
    result = []
    while remaining:
        seed = min(remaining, key=lambda e: e.index)
        component, todo = set(), [seed]
        while todo:
            e = todo.pop()
            if e in component:
                continue
            component.add(e)
            todo.extend(x for v in e.verts for x in adjacency[v] if x not in component)
        ends = [v for e in component for v in e.verts if len(adjacency[v]) == 1]
        start = min(ends or list({v for e in component for v in e.verts}), key=lambda v: v.index)
        verts, ordered, v = [start], [], start
        while True:
            candidates = [e for e in adjacency[v] if e in remaining]
            if not candidates:
                break
            e = min(candidates, key=lambda e: e.index)
            remaining.remove(e)
            ordered.append(e)
            v = e.other_vert(v)
            if v == start:
                break
            verts.append(v)
        result.append((verts, ordered, v == start))
    return result


def selected_borders(bm):
    """Expand selected boundary seeds without crossing non-boundary edges."""
    seeds = [e for e in bm.edges if e.select and e.is_boundary and not e.hide]
    edges, todo = set(), seeds[:]
    while todo:
        e = todo.pop()
        if e in edges:
            continue
        edges.add(e)
        todo.extend(x for v in e.verts for x in v.link_edges
                    if x.is_boundary and not x.hide and x not in edges)
    chains = edge_chains(edges)
    if not chains or any(not closed for _, _, closed in chains):
        raise ValueError("Select at least one edge of a closed open border")
    return chains


def grid_spans(verts):
    """Choose four corners with equal opposite edge counts and sharp turns."""
    n = len(verts)
    points = [v.co for v in verts]
    turns = []
    for i, p in enumerate(points):
        a, b = p - points[i - 1], points[(i + 1) % n] - p
        if min(a.length, b.length) < 1e-10:
            raise ValueError("Border has a zero-length edge")
        turns.append(a.angle(b))
    candidates = []
    for width in range(1, n // 4 + 1):
        height = n // 2 - width
        for start in range(n):
            corners = [start, (start + width) % n, (start + width + height) % n,
                       (start + 2 * width + height) % n]
            corner_cost = sum((turns[i] - math.pi / 2) ** 2 for i in corners)
            q = [points[i] for i in corners]
            w = ((q[1] - q[0]).length + (q[2] - q[3]).length) / width
            h = ((q[3] - q[0]).length + (q[2] - q[1]).length) / height
            score = corner_cost + .1 * math.log(max(w, 1e-12) / max(h, 1e-12)) ** 2
            candidates.append((score, start, width, height))
    return sorted(candidates)


def grid_patch(verts, start, width, height):
    """Coons grid with the original boundary vertices kept in place."""
    ring = verts[start:] + verts[:start]
    n = len(ring)
    grid = {}
    for i in range(width + 1):
        grid[i, 0] = ring[i]
        grid[i, height] = ring[(2 * width + height - i) % n]
    for j in range(height + 1):
        grid[width, j] = ring[width + j]
        grid[0, j] = ring[(n - j) % n]
    coords = {key: v.co.copy() for key, v in grid.items()}
    a, b, c, d = (coords[key] for key in ((0, 0), (width, 0), (width, height), (0, height)))
    for i in range(1, width):
        u = i / width
        for j in range(1, height):
            v = j / height
            coords[i, j] = (coords[i, 0] * (1 - v) + coords[i, height] * v
                            + coords[0, j] * (1 - u) + coords[width, j] * u
                            - (a * (1 - u) * (1 - v) + b * u * (1 - v)
                               + c * u * v + d * (1 - u) * v))
    quads = [((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
             for i in range(width) for j in range(height)]
    axis = normal([v.co for v in ring])
    for keys in quads:
        p, q, r, s = [coords[k] for k in keys]
        # Both triangles must face the same way. Do not create folded cells.
        if min((q - p).cross(r - p).dot(axis), (r - p).cross(s - p).dot(axis)) <= 1e-12:
            return None
    return grid, coords, quads


def cap_border(bm, verts, edges):
    # Match the opposite winding of the existing face along the first edge.
    edge = next(e for e in edges if verts[0] in e.verts and verts[1] in e.verts)
    loop = edge.link_loops[0]
    if loop.vert == verts[0] and loop.link_loop_next.vert == verts[1]:
        verts = list(reversed(verts))
    material = edge.link_faces[0].material_index
    smooth = edge.link_faces[0].smooth
    if len(verts) % 2:
        faces = bmesh.ops.triangle_fill(bm, edges=edges, use_beauty=True)["geom"]
        faces = [f for f in faces if isinstance(f, bmesh.types.BMFace)]
        for face in faces:
            face.material_index, face.smooth = material, smooth
        bmesh.ops.join_triangles(bm, faces=faces, angle_face_threshold=math.pi,
                                angle_shape_threshold=math.pi)
        # The caller reports the odd-count fallback. Orient below from the border.
        return True
    patch = None
    for _, start, width, height in grid_spans(verts):
        patch = grid_patch(verts, start, width, height)
        if patch:
            break
    if patch is None:
        raise ValueError("Border is too concave or twisted for an unfolded quad grid")
    grid, coords, quads = patch
    for key, co in coords.items():
        if key not in grid:
            grid[key] = bm.verts.new(co)
    for keys in quads:
        f = bm.faces.new([grid[key] for key in keys])
        f.material_index, f.smooth = material, smooth
        f.select_set(True)
    return False


def _edit_meshes(context):
    return [ob for ob in context.objects_in_mode_unique_data if ob.type == "MESH"]


class MAX_OT_quad_cap(bpy.types.Operator):
    """Close selected borders with a quad grid, expanding even a single border edge"""
    bl_idname = "max.quad_cap"
    bl_label = "Quad Cap"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        count, odd, skipped = 0, 0, []
        for ob in _edit_meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.index_update()
            bm.edges.index_update()
            try:
                borders = selected_borders(bm)
            except ValueError as exc:
                skipped.append(str(exc))
                continue
            original_faces = set(bm.faces)
            for verts, edges, _ in borders:
                try:
                    odd += cap_border(bm, verts, edges)
                    count += 1
                except ValueError as exc:
                    skipped.append(str(exc))
            if set(bm.faces) != original_faces:
                # Propagate winding through new faces without changing old faces.
                new = set(bm.faces) - original_faces
                todo = [f for f in new if any(e.link_faces and any(x in original_faces for x in e.link_faces)
                                            for e in f.edges)]
                oriented = set(original_faces)
                while todo:
                    f = todo.pop()
                    if f in oriented:
                        continue
                    for l in f.loops:
                        other = next((x for x in l.edge.link_loops if x.face in oriented), None)
                        if other:
                            if other.vert == l.vert:
                                f.normal_flip()
                            break
                    else:
                        continue
                    oriented.add(f)
                    todo.extend(x for e in f.edges for x in e.link_faces if x not in oriented)
                for f in new:
                    f.select_set(True)
                bm.normal_update()
                bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=True)
        if odd:
            self.report({"WARNING"}, f"{odd} border(s) have an odd edge count: capped with triangles and quads")
        if skipped:
            self.report({"WARNING"}, ". ".join(sorted(set(skipped))))
        return {"FINISHED"} if count else {"CANCELLED"}


def _resample(points, closed):
    path = points + points[:1] if closed else points
    lengths = [(b - a).length for a, b in zip(path, path[1:])]
    total = sum(lengths)
    if total < 1e-10:
        raise ValueError("Loop has zero length")
    result, edge, distance = [], 0, 0.0
    for i in range(len(points)):
        target = total * i / (len(points) if closed else len(points) - 1)
        while edge < len(lengths) - 1 and distance + lengths[edge] < target:
            distance += lengths[edge]
            edge += 1
        t = (target - distance) / lengths[edge] if lengths[edge] > 1e-12 else 0
        result.append(path[edge].lerp(path[edge + 1], t))
    return result


def _round_loop(points, closed):
    if len(points) < 3:
        return _resample(points, closed)
    center = sum(points, Vector()) / len(points)
    rel = [p - center for p in points]
    # Largest triangle gives a stable plane for open arcs too.
    u = max(rel, key=lambda p: p.length_squared).normalized()
    axis = max((u.cross(p) for p in rel), key=lambda p: p.length_squared)
    if axis.length < 1e-10:
        return _resample(points, closed)
    axis.normalize()
    v = axis.cross(u)
    xy = [(p.dot(u), p.dot(v)) for p in rel]
    xx, yy = sum(x * x for x, y in xy), sum(y * y for x, y in xy)
    cross = sum(x * y for x, y in xy)
    rhs_x = sum(x * (x * x + y * y) / 2 for x, y in xy)
    rhs_y = sum(y * (x * x + y * y) / 2 for x, y in xy)
    det = xx * yy - cross * cross
    if det < 1e-16:
        return _resample(points, closed)
    cx, cy = (rhs_x * yy - rhs_y * cross) / det, (rhs_y * xx - rhs_x * cross) / det
    center += u * cx + v * cy
    angles = [math.atan2(y - cy, x - cx) for x, y in xy]
    deltas = [(b - a + math.pi) % math.tau - math.pi for a, b in zip(angles, angles[1:])]
    direction = 1 if sum(deltas) >= 0 else -1
    sweep = direction * math.tau if closed else sum(deltas)
    radius = sum((p - center).length for p in points) / len(points)
    return [center + radius * (u * math.cos(angles[0] + sweep * i / (len(points) if closed else len(points) - 1))
                              + v * math.sin(angles[0] + sweep * i / (len(points) if closed else len(points) - 1)))
            for i in range(len(points))]


class MAX_OT_loop_regularize(bpy.types.Operator):
    """Make edge loops round, or space vertices evenly along their current path"""
    bl_idname = "max.loop_regularize"
    bl_label = "Edge Loop Regularizer"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(name="Mode", items=[("CIRCLE", "Circle", "Round loops with equally spaced vertices"),
                                           ("SPACE", "Even Spacing", "Resample the current polyline by arc length")],
                       default="CIRCLE")
    strength: FloatProperty(name="Strength", default=1.0, min=0, max=1, subtype="FACTOR")

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        plans = []
        try:
            for ob in _edit_meshes(context):
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.index_update()
                bm.edges.index_update()
                chains = edge_chains([e for e in bm.edges if e.select and not e.hide])
                for verts, _, closed in chains:
                    # Work in world coordinates, including non-uniform object scale.
                    points = [ob.matrix_world @ v.co for v in verts]
                    target = _round_loop(points, closed) if self.mode == "CIRCLE" else _resample(points, closed)
                    inv = ob.matrix_world.inverted_safe()
                    plans.append((ob, bm, verts, [inv @ a.lerp(b, self.strength) for a, b in zip(points, target)]))
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        if not plans:
            self.report({"WARNING"}, "Select one or more edge loops or open chains")
            return {"CANCELLED"}
        for ob, bm, verts, target in plans:
            for vert, co in zip(verts, target):
                vert.co = co
            bm.normal_update()
            bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
        return {"FINISHED"}


def move_pivot(ob, mode):
    """Move a mesh/spline origin in world space without moving its geometry."""
    if ob.type not in {"MESH", "CURVE", "SURFACE", "FONT"} or ob.mode != "OBJECT":
        return False
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = ob.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if not mesh or not mesh.vertices:
            return False
        points = [ob.matrix_world @ v.co for v in mesh.vertices]
        low = Vector([min(p[i] for p in points) for i in range(3)])
        high = Vector([max(p[i] for p in points) for i in range(3)])
    finally:
        evaluated.to_mesh_clear()
    target = (low + high) / 2
    if mode == "BOTTOM":
        target.z = low.z
    delta = ob.matrix_world.inverted_safe() @ target
    children = [(child, child.matrix_world.copy()) for child in ob.children]
    if ob.data.users > 1:
        ob.data = ob.data.copy()
    ob.data.transform(Matrix.Translation(-delta), shape_keys=True)
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(delta)
    if ob.type == "MESH" and ob.max_prim.kind:
        ob[PIVOT_OFFSET] = list(Vector(ob.get(PIVOT_OFFSET, (0, 0, 0))) - delta)
    for child, matrix in children:
        child.matrix_world = matrix
    ob.data.update_tag()
    return True


def auto_pivot_created(ob):
    """Finalize add-on mesh/spline creation using the user's pivot preference."""
    from . import get_prefs
    prefs = get_prefs()
    mode = prefs.auto_pivot_on_create if prefs else "OFF"
    if mode != "OFF":
        bpy.context.view_layer.update()
        move_pivot(ob, mode)


class MAX_OT_pivot_bounds(bpy.types.Operator):
    """Place each selected object's pivot at its world bounding-box bottom or center"""
    bl_idname = "max.pivot_bounds"
    bl_label = "Pivot to Bounds"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(name="Pivot", items=[("BOTTOM", "Bottom", "Bottom center of the world bounding box"),
                                            ("CENTER", "Center", "Center of the world bounding box")], default="BOTTOM")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(ob.type in {"MESH", "CURVE", "SURFACE", "FONT"}
                                                for ob in context.selected_objects)

    def execute(self, context):
        count = 0
        # Parents before children, so selected descendants keep their own pivot edits.
        def depth(ob):
            count = 0
            while ob.parent:
                count += 1
                ob = ob.parent
            return count
        for ob in sorted(context.selected_objects, key=depth):
            if ob.library or (ob.data and ob.data.library):
                self.report({"WARNING"}, f"{ob.name}: linked data cannot be edited")
                continue
            count += move_pivot(ob, self.mode)
        return {"FINISHED"} if count else {"CANCELLED"}


classes = (MAX_OT_quad_cap, MAX_OT_loop_regularize, MAX_OT_pivot_bounds)
