"""Two-click QuickSlice and the standalone native Cut integration fallback."""
from types import SimpleNamespace

import bpy
import bmesh
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector

_sessions = {}


def release(key, restore=True):
    state = _sessions.pop(key, None)
    if state is None:
        return
    if state.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(state.handler, "WINDOW")
    if state.timer is not None:
        bpy.context.window_manager.event_timer_remove(state.timer)
    try:
        state.window.cursor_modal_restore()
        state.workspace.status_text_set(None)
        state.area.tag_redraw()
        if restore and state.was_object and state.obj == bpy.context.active_object and state.obj.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.window_manager.max_sublevel = state.level
    except (ReferenceError, RuntimeError):
        pass


def teardown(restore=True):
    for key in list(_sessions):
        release(key, restore=restore)


def begin(operator, context):
    key = context.window.as_pointer()
    if key in _sessions:
        release(key)
        return None
    state = SimpleNamespace(key=key, owner=operator, window=context.window, area=context.area, region=context.region,
                            workspace=context.workspace, obj=context.active_object,
                            was_object=context.mode == "OBJECT", level=context.window_manager.max_sublevel,
                            handler=None, timer=None, start=None, mouse=Vector((0, 0)))
    if state.was_object:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
    operator.state = state
    _sessions[key] = state
    context.window_manager.modal_handler_add(operator)
    return state


def slice_mesh(context, point, normal, whole=False):
    """Use the same selection, visibility and Split rules as stored-plane Slice."""
    from .editable_poly import settings, update_mesh
    from .operators import current_level
    bm = bmesh.from_edit_mesh(context.edit_object.data)
    faces = [f for f in bm.faces if not f.hide and (whole or current_level(context) < 4 or f.select)]
    edges = {e for f in faces for e in f.edges if not e.hide}
    verts = {v for e in edges for v in e.verts if not v.hide}
    previous_faces = set(bm.faces)
    result = bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces,
                                  dist=.00001, plane_co=point, plane_no=normal)
    if settings(context, "SLICE_PLANE").split:
        bmesh.ops.split_edges(bm, edges=[e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)])
    if not whole and current_level(context) >= 4:
        for face in set(bm.faces) - previous_faces:
            face.select_set(True)
        bm.select_flush_mode()
    update_mesh(context)


class MAX_OT_poly_quick_slice(Operator):
    """Click a start point, move, click the endpoint. Right-click leaves QuickSlice"""
    bl_idname = "max.poly_quick_slice"
    bl_label = "QuickSlice"

    def invoke(self, context, event):
        state = begin(self, context)
        if state is None:
            return {"CANCELLED"}
        state.mouse = Vector((event.mouse_x-state.region.x, event.mouse_y-state.region.y))
        state.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_preview, (), "WINDOW", "POST_PIXEL")
        state.window.cursor_modal_set("CROSSHAIR")
        state.workspace.status_text_set("QuickSlice: click start, then endpoint. Right-click to finish")
        return {"RUNNING_MODAL"}

    def draw_preview(self):
        s = self.state
        if _sessions.get(s.key) is not s or s.start is None or bpy.context.region != s.region:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("color", (1, 1, 1, 1))
        batch_for_shader(shader, "LINES", {"pos": [s.start, s.mouse]}).draw(shader)

    def modal(self, context, event):
        state = _sessions.get(context.window.as_pointer())
        if state is None or state.owner is not self:
            return {"CANCELLED"}
        try:
            s = self.state
            if _sessions.get(s.key) is not s:
                return {"CANCELLED"}
            if context.edit_object != s.obj or context.mode != "EDIT_MESH":
                release(s.key)
                return {"CANCELLED"}
            if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
                release(s.key)
                return {"CANCELLED"}
            if event.type == "Z" and event.ctrl:
                release(s.key)
                return {"PASS_THROUGH"}
            s.mouse = Vector((event.mouse_x-s.region.x, event.mouse_y-s.region.y))
            inside = 0 <= s.mouse.x < s.region.width and 0 <= s.mouse.y < s.region.height
            if any(r.type in {"UI", "TOOLS"} and r.width > 1 and r.x <= event.mouse_x < r.x+r.width and r.y <= event.mouse_y < r.y+r.height for r in s.area.regions):
                inside = False
            if not inside or event.type not in {"MOUSEMOVE", "LEFTMOUSE"}:
                return {"PASS_THROUGH"}
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                if s.start is None:
                    s.start = s.mouse.copy()
                elif (s.mouse-s.start).length > 1:
                    rv = s.region.data
                    depth = s.obj.matrix_world.translation
                    a = view3d_utils.region_2d_to_location_3d(s.region, rv, s.start, depth)
                    b = view3d_utils.region_2d_to_location_3d(s.region, rv, s.mouse, depth)
                    direction = view3d_utils.region_2d_to_vector_3d(s.region, rv, (s.start+s.mouse)/2)
                    normal = (b-a).cross(direction)
                    if normal.length > 1e-8:
                        slice_mesh(context, s.obj.matrix_world.inverted() @ a,
                                   s.obj.matrix_world.to_3x3().transposed() @ normal.normalized(), s.was_object)
                        bpy.ops.ed.undo_push(message="QuickSlice")
                        s.start = None
            s.area.tag_redraw()
            return {"RUNNING_MODAL"}
        except (ReferenceError, RuntimeError, ValueError):
            release(context.window.as_pointer())
            return {"CANCELLED"}

    def cancel(self, context):
        release(context.window.as_pointer())


class MAX_OT_poly_native_cut(Operator):
    """Standalone fallback. The integrated add-on routes Cut to max.cut instead"""
    bl_idname = "max.poly_native_cut"
    bl_label = "Cut"

    def invoke(self, context, event):
        if not hasattr(context.window, "modal_operators"):
            self.report({"WARNING"}, "Cut requires the companion max.cut operator on this Blender version")
            return {"CANCELLED"}
        state = begin(self, context)
        if state is None:
            return {"CANCELLED"}
        state.pending = True
        state.timer = context.window_manager.event_timer_add(.1, window=context.window)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        state = _sessions.get(context.window.as_pointer())
        if state is None or state.owner is not self:
            return {"CANCELLED"}
        try:
            s = self.state
            if _sessions.get(s.key) is not s:
                return {"CANCELLED"}
            if event.type != "TIMER":
                return {"PASS_THROUGH"}
            if s.pending:
                s.pending = False
                with context.temp_override(window=s.window, area=s.area, region=s.region):
                    result = bpy.ops.mesh.knife_tool("INVOKE_DEFAULT")
                if result == {"RUNNING_MODAL"}:
                    return {"PASS_THROUGH"}
            elif any(op.bl_idname == "MESH_OT_knife_tool" for op in s.window.modal_operators):
                return {"PASS_THROUGH"}
            release(s.key)
            return {"FINISHED"}
        except (ReferenceError, RuntimeError):
            release(context.window.as_pointer())
            return {"CANCELLED"}

    def cancel(self, context):
        release(context.window.as_pointer())


classes = (MAX_OT_poly_quick_slice, MAX_OT_poly_native_cut)
