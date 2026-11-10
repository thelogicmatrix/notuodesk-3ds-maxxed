"""Max Target Weld: pick a source, then a valid target, without holding a button."""

import bpy
import bmesh
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector
from bpy.app.handlers import persistent
from types import SimpleNamespace

_active = {}
_resources = {}


def teardown(*args):
    """Release viewport resources before undo, file load or class removal."""
    for key in list(_resources):
        release(key)
    from . import target_weld_cursor
    target_weld_cursor.clear()


def remove_draw_handler(handler):
    bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW")


def release(key):
    state = _resources.pop(key, None)
    operator = _active.pop(key, None)
    if operator is not None:
        from . import snaps
        try:
            snaps.clear_preview(operator.region)
        except (ReferenceError, RuntimeError):
            pass
    if state is None:
        return
    cleanups = [lambda: remove_draw_handler(state.handler)]
    if state.cursor_hidden:
        cleanups.append(lambda: state.window.cursor_modal_restore())
        state.cursor_hidden = False
    cleanups.extend((lambda: state.workspace.status_text_set(None), lambda: state.area.tag_redraw()))
    for cleanup in cleanups:
        try:
            cleanup()
        except (ReferenceError, RuntimeError):
            pass
    if not _resources:
        from . import target_weld_cursor
        target_weld_cursor.clear()


@persistent
def before_restore(*args):
    teardown()
    from . import poly_modal
    poly_modal.teardown(restore=False)


def register_handlers():
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
        if before_restore not in handlers:
            handlers.append(before_restore)


def unregister_handlers():
    teardown()
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
        if before_restore in handlers:
            handlers.remove(before_restore)


def is_active(context):
    return bool(context.window and context.window.as_pointer() in _active)


def edge_mapping(source, target):
    """Pair endpoints by distance, keeping any common endpoint fixed."""
    a, b = source.verts
    c, d = target.verts
    candidates = [dict(zip((a, b), pair)) for pair in ((c, d), (d, c))]
    candidates = [m for m in candidates if all(m[v] == v for v in set(source.verts) & set(target.verts))]
    return min(candidates, key=lambda m: sum((a.co-b.co).length_squared for a,b in m.items()))


def invalid_reason(bm, source, target, level):
    if source is None or target is None or not source.is_valid or not target.is_valid:
        return "Pick a visible vertex" if level == 1 else "Pick a visible border edge"
    if source == target:
        return "Source and target must differ"
    if source.hide or target.hide:
        return "Hidden geometry cannot be welded"
    if level == 1:
        if bm.edges.get((source, target)) is None:
            return "Target must be a neighbouring vertex connected by one edge"
        return ""
    if len(source.link_faces) != 1 or len(target.link_faces) != 1:
        return "Target Weld requires edges with exactly one polygon attached"
    if set(source.link_faces) & set(target.link_faces):
        return "Cannot weld edges of the same polygon"
    mapping = edge_mapping(source, target)
    if any(mapping.get(e.verts[0], e.verts[0]) == mapping.get(e.verts[1], e.verts[1]) for e in bm.edges):
        return "Weld would collapse another edge into a vertex"
    # Validate the resulting topology before changing the live mesh. In
    # particular, opposite sides of a box opening cannot become a welded seam.
    counts, faces = {}, set()
    for face in bm.faces:
        ring = [mapping.get(v, v) for v in face.verts]
        compact = [v for i,v in enumerate(ring) if v != ring[i-1]]
        if len(compact) < 3 or len(set(compact)) != len(compact):
            return "Weld would collapse a polygon or create illegal geometry"
        key = frozenset(compact)
        if key in faces:
            return "Weld would create duplicate polygons"
        faces.add(key)
        for i,v in enumerate(compact):
            key = frozenset((v, compact[i-1]))
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > 2:
                return "Weld would create an edge shared by more than two polygons"
    return ""


def weld(bm, source, target, level):
    reason = invalid_reason(bm, source, target, level)
    if reason:
        raise ValueError(reason)
    mapping = {source: target} if level == 1 else edge_mapping(source, target)
    bmesh.ops.weld_verts(bm, targetmap={a:b for a,b in mapping.items() if a != b})
    for seq in (bm.faces, bm.edges, bm.verts):
        for item in seq:
            item.select_set(False)
    target.select_set(True)
    bm.select_flush_mode()
    bm.normal_update()


class MAX_OT_target_weld(Operator):
    """Weld a vertex to its neighbour or a border edge to a valid border edge. Right-click to finish"""
    bl_idname = "max.target_weld"
    bl_label = "Target Weld"
    # Each committed weld pushes its own undo state. Tool exit must not push one.
    bl_options = set()

    @classmethod
    def poll(cls, context):
        from .operators import current_level
        return context.mode == "EDIT_MESH" and current_level(context) in (1, 2, 3)

    def invoke(self, context, event):
        from .operators import current_level, viewport_override
        key = context.window.as_pointer()
        if key in _active:
            release(key)
            return {"CANCELLED"}
        override = viewport_override(context)
        if override is None or override["region"] is None:
            self.report({"WARNING"}, "Target Weld requires a 3D viewport")
            return {"CANCELLED"}
        self.window, self.area, self.region = context.window, override["area"], override["region"]
        self.workspace = context.workspace
        self.obj = context.edit_object
        self.level = current_level(context)
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        seq = self.bm.verts if self.level == 1 else self.bm.edges
        selected = [v for v in seq if v.select and not v.hide and (self.level == 1 or len(v.link_faces) == 1)]
        self.source = selected[0] if len(selected) == 1 else None
        self.mouse = Vector((event.mouse_x-self.region.x, event.mouse_y-self.region.y))
        self.stop_requested = False
        self.inside = False
        self.hover_valid = False
        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_safe, (), "WINDOW", "POST_PIXEL")
        self.key = key
        _resources[key] = SimpleNamespace(handler=self.handler, window=self.window,
                                         workspace=self.workspace, area=self.area, cursor_hidden=False)
        _active[key] = self
        self.update_pointer(self.pointer_inside(event))
        if self.inside:
            with context.temp_override(area=self.area, region=self.region):
                self.hover_target()
        self.workspace.status_text_set("Target Weld: pick target" if self.source else "Target Weld: pick source. Right-click to finish")
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def project(self, co):
        return view3d_utils.location_3d_to_region_2d(self.region, self.region.data, self.obj.matrix_world @ co)

    def pointer_inside(self, event):
        if not (0 <= self.mouse.x < self.region.width and 0 <= self.mouse.y < self.region.height):
            return False
        return not any(r.type in {"UI", "TOOLS"} and r.width > 1
                       and r.x <= event.mouse_x < r.x+r.width and r.y <= event.mouse_y < r.y+r.height
                       for r in self.area.regions)

    def update_pointer(self, inside):
        state = _resources.get(self.key)
        self.inside = inside
        if not inside:
            self.hover_valid = False
        if state is None or state.cursor_hidden == inside:
            return
        if inside:
            state.window.cursor_modal_set("NONE")
        else:
            state.window.cursor_modal_restore()
        state.cursor_hidden = inside

    def hover_target(self):
        if self.source is not None and not self.source.is_valid:
            self.source = None
        target = self.pick()
        reason = invalid_reason(self.bm, self.source, target, self.level) if self.source else (
            "Pick a visible vertex" if self.level == 1 and target is None else
            "Pick a border edge with exactly one polygon attached" if self.level != 1 and (target is None or len(target.link_faces) != 1) else "")
        self.hover_valid = target is not None and not reason
        return target, reason

    def pick(self):
        from . import snaps
        from .create import construction_frame, ray_plane
        context = bpy.context
        _, _, normal = construction_frame(self.region.data)
        base = self.obj.matrix_world @ (self.source.co if self.source is not None and self.level == 1 else Vector())
        raw = ray_plane(self.region, self.region.data, self.mouse, base, normal)
        mouse = self.mouse
        if raw is not None:
            point = snaps.snap_point(context, self.region, self.region.data, mouse, raw,
                                     (base, normal), base=base if self.source is not None else None)
            projected = view3d_utils.location_3d_to_region_2d(self.region, self.region.data, point)
            if projected is not None:
                mouse = projected
        best, distance = None, 14.0
        seq = self.bm.verts if self.level == 1 else self.bm.edges
        for item in seq:
            if item.hide:
                continue
            if self.level == 1:
                point = self.project(item.co)
                if point is None:
                    continue
            else:
                a, b = [self.project(v.co) for v in item.verts]
                if a is None or b is None:
                    continue
                delta = b-a
                t = max(0, min(1, (mouse-a).dot(delta)/delta.length_squared)) if delta.length_squared else 0
                point = a+delta*t
            d = (point-mouse).length
            if d < distance:
                best, distance = item, d
        return best

    def draw_band(self):
        if self.key not in _resources:
            return
        if bpy.context.area != self.area or bpy.context.region != self.region or not self.source or not self.source.is_valid:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        co = self.source.co if self.level == 1 else sum((v.co for v in self.source.verts), Vector())/2
        start = self.project(co)
        if start is None:
            return
        delta = self.mouse-start
        if delta.length < 1:
            return
        length = delta.length
        unit = delta/length
        points = []
        for i in range(0, int(length), 10):
            points.extend((start+unit*i, start+unit*min(i+5, length)))
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        previous_blend = gpu.state.blend_get()
        previous_width = gpu.state.line_width_get()
        gpu.state.blend_set("ALPHA")
        try:
            gpu.state.line_width_set(1)
            shader.bind()
            shader.uniform_float("color", (1, 1, 1, .95))
            batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)
        finally:
            gpu.state.line_width_set(previous_width)
            gpu.state.blend_set(previous_blend)

    def draw_safe(self):
        try:
            if (self.key not in _resources or not self.inside or bpy.context.window != self.window
                    or bpy.context.area != self.area or bpy.context.region != self.region):
                return
            self.draw_band()
            from . import target_weld_cursor
            target_weld_cursor.draw(self.mouse, self.hover_valid, bpy.context.preferences.system.ui_scale)
        except (ReferenceError, RuntimeError, ValueError):
            release(self.key)

    def finish(self):
        release(self.key)
        return {"CANCELLED"}

    def modal(self, context, event):
        try:
            if _active.get(context.window.as_pointer()) is not self:
                return {"CANCELLED"}
            return self.handle_event(context, event)
        except (ReferenceError, RuntimeError, ValueError):
            key = context.window.as_pointer()
            if _active.get(key) is self:
                release(key)
            return {"CANCELLED"}

    def handle_event(self, context, event):
        from .operators import current_level
        if (self.stop_requested or context.mode != "EDIT_MESH" or context.edit_object != self.obj
                or current_level(context) != self.level or self.area not in context.screen.areas[:]):
            return self.finish()
        self.mouse = Vector((event.mouse_x-self.region.x, event.mouse_y-self.region.y))
        self.update_pointer(self.pointer_inside(event))
        self.area.tag_redraw()
        if event.type == "ESC" and event.value == "PRESS":
            return self.finish()
        if not self.inside:
            return {"PASS_THROUGH"}
        from . import snaps
        if snaps.override_event(self, context, event, dragging=False):
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            return self.finish()
        if event.type not in {"MOUSEMOVE", "LEFTMOUSE"}:
            return {"PASS_THROUGH"}
        target, reason = self.hover_target()
        self.workspace.status_text_set("Target Weld: " + (reason or ("click target. Right-click to finish" if self.source else "click source. Right-click to finish")))
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and target is not None and not reason:
            snaps.consume_override(context)
            snaps.clear_preview(self.region)
            if self.source is None:
                self.source = target
            else:
                weld(self.bm, self.source, target, self.level)
                from .editable_poly import update_mesh
                update_mesh(context)
                self.source = None
                bpy.ops.ed.undo_push(message="Target Weld")
            self.hover_target()
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self.finish()


classes = (MAX_OT_target_weld,)
