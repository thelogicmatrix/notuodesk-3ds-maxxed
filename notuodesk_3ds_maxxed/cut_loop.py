"""Click-to-cut and SwiftLoop, without Blender's knife/loop-cut modal tools."""

import bmesh
import bpy
import gpu
from bpy.types import Operator, SpaceView3D
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_line

from .create import region_under_mouse


EPS = 1e-6


def _split_edge(edge, co):
    a, b = edge.verts
    factor = (co - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)
    if factor < EPS:
        return a
    if factor > 1 - EPS:
        return b
    return bmesh.utils.edge_split(edge, a, factor)[1]


def resolve_hit(bm, hit):
    """Make a picked surface point a vertex, preserving face corner data."""
    kind, elem, co = hit
    if kind == 'VERT' and elem.is_valid:
        return elem
    if kind == 'EDGE' and elem.is_valid:
        a, b = elem.verts
        t = (co - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)
        if not -EPS <= t <= 1 + EPS:
            for candidate in bm.edges:
                a, b = candidate.verts
                t = (co - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)
                if -EPS <= t <= 1 + EPS and (a.co.lerp(b.co, t) - co).length < EPS:
                    elem = candidate
                    break
        return _split_edge(elem, co)
    if not elem.is_valid:
        bm.faces.ensure_lookup_table()
        nearest = BVHTree.FromBMesh(bm).find_nearest(co)
        if nearest[2] is None or nearest[3] > 1e-4:
            raise ValueError('Cut point is no longer on the surface')
        elem = bm.faces[nearest[2]]
    existing = next((v for v in elem.verts if (v.co - co).length < EPS), None)
    if existing is not None:
        return existing
    # A fan is valid only inside a convex polygon. Triangulate concave polygons
    # first, then add the endpoint to the triangle that contains it.
    if any((l.vert.co - l.link_loop_prev.vert.co).cross(l.link_loop_next.vert.co - l.vert.co).dot(elem.normal) < -EPS
           for l in elem.loops):
        bmesh.ops.triangulate(bm, faces=[elem])
        bm.faces.ensure_lookup_table()
        nearest = BVHTree.FromBMesh(bm).find_nearest(co)
        elem = bm.faces[nearest[2]]
        for edge in elem.edges:
            a, b = edge.verts
            t = (co - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)
            if -EPS <= t <= 1 + EPS and (a.co.lerp(b.co, t) - co).length < EPS:
                return _split_edge(edge, co)
    vert = bm.verts.new(co)
    vert.copy_from_face_interp(elem)
    boundary = list(elem.verts)
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        face = bm.faces.new((a, b, vert))
        face.material_index = elem.material_index
        face.smooth = elem.smooth
        face.select_set(elem.select)
        for loop in face.loops:
            loop.copy_from_face_interp(elem)
    bm.faces.remove(elem)
    return vert


def _cross(a, b):
    return a.x * b.y - a.y * b.x


def _inside(point, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a.y > point.y) != (b.y > point.y):
            x = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < x:
                inside = not inside
    return inside


def cut_segment(bm, start, hit, project, visible=None, edge_position=None):
    """Split every visible face crossed by one screen-space cut segment."""
    start = start if isinstance(start, bmesh.types.BMVert) else resolve_hit(bm, start)
    end = resolve_hit(bm, hit)
    bm.normal_update()
    if start == end:
        return end
    p, q = project(start.co), project(end.co)
    direction = q - p
    if direction.length_squared < EPS:
        return end
    # Save faces before splitting edges, so adjacent faces share each new vertex.
    crossings = {}
    plans = []
    for face in list(bm.faces):
        if face.hide:
            continue
        points = []
        for vert in face.verts:
            screen = project(vert.co)
            if screen is None:
                continue
            t = (screen - p).dot(direction) / direction.length_squared
            if -EPS <= t <= 1 + EPS and abs(_cross(screen - p, direction)) < 1e-4:
                points.append((t, vert))
        for edge in face.edges:
            a, b = (project(v.co) for v in edge.verts)
            if a is None or b is None:
                continue
            delta = b - a
            denom = _cross(direction, delta)
            if abs(denom) < EPS:
                continue
            t = _cross(a - p, delta) / denom
            u = _cross(a - p, direction) / denom
            if EPS < t < 1 - EPS and EPS < u < 1 - EPS:
                co = edge_position(edge, p + direction * t) if edge_position else edge.verts[0].co.lerp(edge.verts[1].co, u)
                crossings[edge] = co
                points.append((t, edge))
        points.sort(key=lambda item: item[0])
        unique = []
        for item in points:
            if not unique or abs(item[0] - unique[-1][0]) > EPS:
                unique.append(item)
        for left, right in zip(unique, unique[1:]):
            mid = p + direction * ((left[0] + right[0]) * .5)
            polygon = [project(v.co) for v in face.verts]
            if all(p is not None for p in polygon) and _inside(mid, polygon) and (visible is None or visible(face, mid)):
                plans.append((face, left[1], right[1]))
    used_edges = {item for _, a, b in plans for item in (a, b) if isinstance(item, bmesh.types.BMEdge)}
    split = {edge: _split_edge(edge, crossings[edge]) for edge in used_edges}
    for face, a, b in plans:
        a, b = split.get(a, a), split.get(b, b)
        if a == b or bm.edges.get((a, b)):
            continue
        common = [f for f in a.link_faces if f in b.link_faces and not f.hide]
        target = face if face.is_valid and face in common else next(iter(common), None)
        if target is not None:
            bmesh.utils.face_split(target, a, b)
    bm.normal_update()
    return end


def ring_plan(edge, factor):
    """Cross opposite edges of quads, carrying the picked edge's orientation."""
    factors = {edge: factor}
    faces = {}
    pending = [edge]
    while pending:
        current = pending.pop()
        if current.hide or len(current.link_faces) > 2:
            continue
        for face in current.link_faces:
            if face.hide or len(face.verts) != 4 or face in faces:
                continue
            loop = next(l for l in face.loops if l.edge == current)
            opposite = loop.link_loop_next.link_loop_next.edge
            a = loop.vert
            d = loop.link_loop_prev.vert
            t = factors[current] if current.verts[0] == a else 1 - factors[current]
            t = t if opposite.verts[0] == d else 1 - t
            faces[face] = (current, opposite)
            if opposite not in factors:
                factors[opposite] = t
                pending.append(opposite)
    return factors, faces


def loop_position(edge, factor, flow=False):
    a, b = edge.verts
    co = a.co.lerp(b.co, factor)
    if flow:
        # Cubic surface interpolation using endpoint tangent planes.
        delta = b.co - a.co
        ta = delta - a.normal * delta.dot(a.normal)
        tb = delta - b.normal * delta.dot(b.normal)
        t = factor
        co = ((2*t**3 - 3*t*t + 1) * a.co + (t**3 - 2*t*t + t) * ta
              + (-2*t**3 + 3*t*t) * b.co + (t**3 - t*t) * tb)
    return co


def insert_loop(bm, edge, factor, flow=False):
    factors, faces = ring_plan(edge, max(.001, min(.999, factor)))
    if not faces:
        return []
    positions = {e: loop_position(e, t, flow) for e, t in factors.items()}
    verts = {e: bmesh.utils.edge_split(e, e.verts[0], t)[1] for e, t in factors.items()}
    for e, v in verts.items():
        v.co = positions[e]
    result = []
    for face, (a, b) in faces.items():
        _, loop = bmesh.utils.face_split(face, verts[a], verts[b])
        result.append(loop.edge)
    bm.normal_update()
    return result


def edge_loop(edge):
    """Walk the opposite edge at regular vertices and open-strip boundaries."""
    found = {edge}
    pending = [(edge, v) for v in edge.verts]
    while pending:
        current, vert = pending.pop()
        if len(vert.link_edges) not in {3, 4}:
            continue
        candidates = [e for e in vert.link_edges if e not in found and not e.hide
                      and not any(f in current.link_faces for f in e.link_faces)]
        if len(candidates) == 1:
            other = candidates[0]
            found.add(other)
            pending.append((other, other.other_vert(vert)))
    return list(found)


def remove_loop(bm, edge):
    edges = edge_loop(edge)
    bmesh.ops.dissolve_edges(bm, edges=edges, use_verts=True, use_face_split=False)
    bm.normal_update()


class _SurfaceTool:
    active = None

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH' and context.mode in {'OBJECT', 'EDIT_MESH'}

    def invoke(self, context, event):
        if _SurfaceTool.active is not None:
            _SurfaceTool.active._finish(context)
        self.object = context.active_object
        self.is_cut = isinstance(self, MAX_OT_cut)
        self.was_object = context.mode == 'OBJECT'
        self.original_sublevel = context.window_manager.max_sublevel
        if self.was_object:
            bpy.ops.object.mode_set(mode='EDIT')
        # Keep the wrapper alive with the stored BMVert/BMEdge references.
        self.bm = bmesh.from_edit_mesh(self.object.data)
        self.bvh = None
        self.start = None
        self.hit = None
        self.lines = []
        self.drag = None
        self.area, self.region = region_under_mouse(context, event.mouse_x, event.mouse_y)
        if self.region is None:
            self.area = context.area if context.area.type == 'VIEW_3D' else None
            self.region = next((r for r in self.area.regions if r.type == 'WINDOW'), None) if self.area else None
        if self.region is None:
            if self.was_object:
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}
        self.rv3d = self.region.data
        self.handle = SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        _SurfaceTool.active = self
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {'RUNNING_MODAL'}

    def _status(self, context):
        text = ('Cut: click a vertex, edge or polygon. Right-click ends chain, again exits.'
                if self.is_cut else
                'SwiftLoop: click inserts, Shift flow, Ctrl selects, Ctrl+Shift removes, Alt drags. Right-click exits.')
        context.workspace.status_text_set(text)

    def _finish(self, context):
        if getattr(self, 'handle', None) is not None:
            SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        if self.was_object and self.object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
            context.window_manager.max_sublevel = self.original_sublevel
        if context.area and context.area.type == 'VIEW_3D':
            current = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
            if current and current.idname == 'builtin.knife':
                bpy.ops.wm.tool_set_by_id(name='builtin.select_box')
        self.area.tag_redraw()
        if _SurfaceTool.active == self:
            _SurfaceTool.active = None
        return {'FINISHED'}

    def cancel(self, context):
        self._finish(context)

    def _draw(self):
        if bpy.context.region != self.region or not self.lines:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {'pos': self.lines})
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2)
        shader.bind()
        shader.uniform_float('color', (0.2, 1.0, 0.25, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1)
        gpu.state.blend_set('NONE')

    def _project(self, co):
        return view3d_utils.location_3d_to_region_2d(self.region, self.rv3d, self.object.matrix_world @ co)

    def _ray(self, mouse):
        inv = self.object.matrix_world.inverted()
        clamp = max(10, self.rv3d.view_distance * 10, self.object.dimensions.length * 10)
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, mouse, clamp=clamp)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, mouse)
        return inv @ origin, (inv.to_3x3() @ direction).normalized()

    def _edge_position(self, edge, mouse):
        origin, direction = self._ray(mouse)
        pair = intersect_line_line(edge.verts[0].co, edge.verts[1].co, origin, origin + direction)
        return pair[0] if pair else edge.verts[0].co.copy()

    def _pick(self, context, event):
        area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
        if region != self.region:
            return None
        bm = self.bm
        if self.bvh is None:
            bm.verts.index_update()
            bm.normal_update()
            self.bvh_faces = [face for face in bm.faces if not face.hide]
            self.bvh = BVHTree.FromPolygons(
                [v.co for v in bm.verts],
                [[v.index for v in face.verts] for face in self.bvh_faces])
        mouse = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
        origin, direction = self._ray(mouse)
        co, normal, index, distance = self.bvh.ray_cast(origin, direction)
        if index is None:
            # Permit picking silhouettes and boundary vertices just outside a face.
            return self._near_boundary(bm, mouse)
        face = self.bvh_faces[index]
        vertices = [(self._project(v.co), v) for v in face.verts]
        vertices = [(p, v) for p, v in vertices if p is not None]
        close = [(p - mouse).length for p, v in vertices]
        if close and min(close) <= 10:
            vert = vertices[close.index(min(close))][1]
            return ('VERT', vert, vert.co.copy())
        edges = []
        for edge in face.edges:
            a, b = (self._project(v.co) for v in edge.verts)
            if a is None or b is None or (b - a).length_squared < EPS:
                continue
            factor = max(0, min(1, (mouse - a).dot(b - a) / (b - a).length_squared))
            edges.append(((mouse - a.lerp(b, factor)).length, edge, a.lerp(b, factor)))
        if edges:
            dist, edge, screen = min(edges, key=lambda item: item[0])
            if dist <= 8 or not self.is_cut:
                return ('EDGE', edge, self._edge_position(edge, screen))
        return ('FACE', face, co)

    def _near_boundary(self, bm, mouse):
        candidates = []
        for vert in bm.verts:
            if vert.hide:
                continue
            pos = self._project(vert.co)
            if pos is not None and (pos - mouse).length <= 10:
                origin, direction = self._ray(pos)
                first = self.bvh.ray_cast(origin, direction)[0]
                if first is None or (first - vert.co).length < 1e-3:
                    candidates.append(((pos - mouse).length, vert))
        if candidates:
            _, vert = min(candidates, key=lambda item: item[0])
            return ('VERT', vert, vert.co.copy())
        edges = []
        for edge in bm.edges:
            if edge.hide:
                continue
            a, b = (self._project(v.co) for v in edge.verts)
            if a is None or b is None or (b - a).length_squared < EPS:
                continue
            t = max(0, min(1, (mouse - a).dot(b - a) / (b - a).length_squared))
            screen = a.lerp(b, t)
            if (screen - mouse).length > 8:
                continue
            co = self._edge_position(edge, screen)
            origin, direction = self._ray(screen)
            first = self.bvh.ray_cast(origin, direction)[0]
            if first is None or (first - co).length < 1e-3:
                edges.append(((screen - mouse).length, edge, co))
        if edges:
            _, edge, co = min(edges, key=lambda item: item[0])
            return ('EDGE', edge, co)
        return None

    def _update(self, context, message):
        self.bvh = None
        bmesh.update_edit_mesh(self.object.data, loop_triangles=True, destructive=True)
        bpy.ops.ed.undo_push(message=message)

    def modal(self, context, event):
        if _SurfaceTool.active != self:
            return {'FINISHED'}
        if context.active_object != self.object or context.mode != 'EDIT_MESH':
            return self._finish(context)
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            if self.drag is not None:
                for vert, co, *_ in self.drag['verts']:
                    vert.co = co
                self.drag = None
                bmesh.update_edit_mesh(self.object.data)
                self.bvh = None
            if event.type == 'RIGHTMOUSE' and self.is_cut and self.start is not None:
                self.start = None
                self.lines = []
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return self._finish(context)
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE' or event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_ALT', 'RIGHT_ALT'}:
            self.hit = self._pick(context, event)
            self._preview(context, event)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                self.hit = self._pick(context, event)
                if self.hit:
                    self._click(context, event)
                self._preview(context, event)
            elif event.value == 'RELEASE' and self.drag is not None:
                self.drag = None
                self._update(context, 'SwiftLoop Slide')
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'Z' and event.ctrl:
            # Leave before native undo invalidates BMesh references.
            self._finish(context)
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class MAX_OT_cut(_SurfaceTool, Operator):
    """Cut connected segments. Right-click ends the chain, again leaves Cut"""
    bl_idname = 'max.cut'
    bl_label = 'Cut'

    def _preview(self, context, event):
        self.lines = []
        context.window.cursor_modal_set({'VERT': 'CROSS', 'EDGE': 'SCROLL_X', 'FACE': 'CROSSHAIR'}[self.hit[0]] if self.hit else 'CROSSHAIR')
        if self.start is not None:
            a = self.start.co if isinstance(self.start, bmesh.types.BMVert) else self.start[2]
            a = self._project(a)
            b = self._project(self.hit[2]) if self.hit else Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))
            if a is not None and b is not None:
                self.lines = [a, b]

    def _click(self, context, event):
        if self.start is None:
            self.start = self.hit
            return
        bm = self.bm
        # Resolving face endpoints changes the BVH. Visibility uses the original
        # surface intersection location rather than stale face indices.
        original = self.bvh
        def visible(face, mouse):
            origin, direction = self._ray(mouse)
            co = original.ray_cast(origin, direction)[0]
            if co is None:
                return False
            return abs((co - face.verts[0].co).dot(face.normal)) < 1e-4
        self.start = cut_segment(bm, self.start, self.hit, self._project, visible, self._edge_position)
        self._update(context, 'Cut Segment')
        self.hit = ('VERT', self.start, self.start.co.copy())


class MAX_OT_swift_loop(_SurfaceTool, Operator):
    """Preview and place loops with one click. Right-click leaves SwiftLoop"""
    bl_idname = 'max.swift_loop'
    bl_label = 'SwiftLoop'

    def _edge(self, selected=False):
        if not self.hit:
            return None
        if self.hit[0] == 'EDGE':
            return self.hit[1]
        if self.hit[0] == 'VERT':
            if selected:
                return next((e for e in self.hit[1].link_edges if e.select and not e.hide), None)
            return next((e for e in self.hit[1].link_edges if not e.hide), None)
        return None

    def _preview(self, context, event):
        self.lines = []
        if self.drag is not None:
            self._slide(event)
            return
        edge = self._edge(event.alt)
        if edge is None:
            return
        if event.ctrl or event.alt:
            segments = [(e.verts[0].co, e.verts[1].co) for e in edge_loop(edge)]
        else:
            a, b = edge.verts
            t = max(.001, min(.999, (self.hit[2] - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)))
            factors, faces = ring_plan(edge, t)
            points = {e: loop_position(e, f, event.shift) for e, f in factors.items()}
            segments = [(points[a], points[b]) for a, b in faces.values()]
        for a, b in segments:
            a, b = self._project(a), self._project(b)
            if a is not None and b is not None:
                self.lines.extend((a, b))

    def _click(self, context, event):
        edge = self._edge(event.alt)
        if edge is None:
            return
        bm = self.bm
        if event.alt:
            self._start_slide(edge, event)
            return
        if event.ctrl and event.shift:
            remove_loop(bm, edge)
            self.hit = None
            self._update(context, 'SwiftLoop Remove')
            return
        if event.ctrl:
            bpy.ops.mesh.select_mode(type='EDGE')
            self.was_object = False
            context.window_manager.max_sublevel = 2
            for v in bm.verts:
                v.select_set(False)
            for e in bm.edges:
                e.select_set(False)
            for f in bm.faces:
                f.select_set(False)
            for e in edge_loop(edge):
                e.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(self.object.data)
            self._update(context, 'SwiftLoop Select')
            return
        a, b = edge.verts
        t = (self.hit[2] - a.co).dot(b.co - a.co) / max((b.co - a.co).length_squared, EPS * EPS)
        inserted = insert_loop(bm, edge, t, event.shift)
        if inserted:
            self.hit = None
            self._update(context, 'SwiftLoop Insert')

    def _start_slide(self, edge, event):
        edges = edge_loop(edge)
        if not any(e.select for e in edges):
            return
        selected = set(edges)
        rails_by_vert = {}
        for v in {v for e in edges for v in e.verts}:
            rails = [e for e in v.link_edges if e not in selected and not e.hide]
            if len(rails) != 2:
                return
            rails_by_vert[v] = rails
        # Carry the side across each loop edge's adjacent faces, rather than
        # assuming that all rails point in the same world-space direction.
        first = edge.verts[0]
        ordered = {first: rails_by_vert[first]}
        pending = [first]
        while pending:
            v = pending.pop()
            for e in v.link_edges:
                if e not in selected:
                    continue
                other = e.other_vert(v)
                if other in ordered:
                    continue
                side_face = next((f for f in e.link_faces if ordered[v][0] in f.edges), None)
                rails = rails_by_vert[other]
                if side_face is not None and rails[1] in side_face.edges:
                    rails = rails[::-1]
                ordered[other] = rails
                pending.append(other)
        verts = [(v, v.co.copy(), *(e.other_vert(v).co.copy() for e in ordered[v])) for v in ordered]
        anchor = min(verts, key=lambda item: (self._project(item[1]) - Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))).length)
        self.drag = {'verts': verts, 'anchor': anchor, 'mouse': Vector((event.mouse_x, event.mouse_y)), 'straight': event.ctrl}
        if event.ctrl:
            self._slide(event)

    def _slide(self, event):
        anchor = self.drag['anchor']
        mouse = Vector((event.mouse_x, event.mouse_y)) - self.drag['mouse']
        a = self._project(anchor[1])
        choices = [(self._project(co) - a, i) for i, co in enumerate(anchor[2:])]
        delta, side = max(choices, key=lambda item: item[0].dot(mouse) / max(item[0].length, EPS))
        t = max(0, min(.999, mouse.dot(delta) / max(delta.length_squared, EPS)))
        distance = (anchor[1] - anchor[2]).length
        distance += t * (anchor[side + 2] - anchor[1]).length * (-1 if side == 0 else 1)
        for vert, original, rail_a, rail_b in self.drag['verts']:
            if self.drag['straight']:
                delta = rail_b - rail_a
                factor = max(.001, min(.999, distance / max(delta.length, EPS)))
                vert.co = rail_a.lerp(rail_b, factor)
            else:
                vert.co = original.lerp((rail_a, rail_b)[side], t)
        bmesh.update_edit_mesh(self.object.data, loop_triangles=False, destructive=False)
        self.bvh = None


classes = (MAX_OT_cut, MAX_OT_swift_loop)


def cancel_active():
    if _SurfaceTool.active is not None:
        _SurfaceTool.active._finish(bpy.context)
