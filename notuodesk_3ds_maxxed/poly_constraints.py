"""Editable Poly Move constraints, evaluated against the mesh before the drag."""

import sys

import bpy
import bmesh
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, BoolVectorProperty, FloatProperty, FloatVectorProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_sessions = set()


def snap_settings(ts):
    values = {}
    for prop in ts.bl_rna.properties:
        key = prop.identifier
        if not prop.is_readonly and key.startswith(("snap_", "use_snap")):
            value = getattr(ts, key)
            values[key] = set(value) if isinstance(value, set) else tuple(value) if getattr(prop, "is_array", False) else value
    return values


def active(context):
    ob = context.active_object
    return bool(context.mode == "EDIT_MESH" and ob and ob.max_poly.constraints != "NONE")


class MoveSession:
    """Shared geometry hook for free drag, gizmos and the Max snapping tool."""

    def __init__(self, context):
        self.ts = context.scene.tool_settings
        self.snaps = snap_settings(self.ts)
        self.meshes = []
        self.closed = False
        normal_sum, center, count = Vector(), Vector(), 0
        for ob in context.objects_in_mode_unique_data:
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.index_update()
            bm.normal_update()
            world = ob.matrix_world.copy()
            inverse = world.inverted_safe()
            normal_matrix = inverse.transposed().to_3x3()
            points = [world @ v.co for v in bm.verts]
            selected = [v for v in bm.verts if v.select and not v.hide]
            mode = ob.max_poly.constraints
            surface = None
            if mode == "FACE":
                triangles = [tuple(loop.vert.index for loop in tri) for tri in bm.calc_loop_triangles()
                             if not tri[0].face.hide]
                if triangles:
                    surface = BVHTree.FromPolygons(points, triangles, all_triangles=True)
            vertices = []
            for v in selected:
                start = points[v.index]
                # Edge/Border selections slide across their adjoining unselected rails.
                rails = [points[e.other_vert(v).index] - start for e in v.link_edges
                         if not e.hide and (context.tool_settings.mesh_select_mode[0] or not e.select)]
                normal = (normal_matrix @ v.normal).normalized()
                vertices.append((v.index, start, rails, normal))
                center += start
                normal_sum += normal
                count += 1
            self.meshes.append((ob, ob.data, inverse, mode, surface, vertices))
        self.center = center / max(1, count)
        self.normal = normal_sum.normalized()
        _sessions.add(self)

    def apply(self, delta, normal_distance=None):
        if self.closed:
            return
        delta = Vector(delta)
        distance = delta.dot(self.normal) if normal_distance is None else normal_distance
        for ob, me, inverse, mode, surface, vertices in self.meshes:
            if ob.mode != "EDIT" or ob.data != me:
                continue
            bm = bmesh.from_edit_mesh(me)
            bm.verts.ensure_lookup_table()
            for index, start, rails, normal in vertices:
                target = start + delta
                if mode == "EDGE":
                    candidates = [start + rail * max(0, min(1, delta.dot(rail) / rail.length_squared))
                                  for rail in rails if rail.length_squared > 1e-16]
                    target = min(candidates, key=lambda p: (p-target).length_squared) if candidates else start
                elif mode == "FACE":
                    hit = surface.find_nearest(target) if surface else None
                    target = hit[0] if hit and hit[0] is not None else start
                elif mode == "NORMAL":
                    target = start + normal * distance
                bm.verts[index].co = inverse @ target
            bm.normal_update()
            bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)

    def finish(self):
        if not self.closed:
            for key, value in self.snaps.items():
                setattr(self.ts, key, value)
            self.closed = True
            _sessions.discard(self)

    def cancel(self):
        if not self.closed:
            # Restore directly, including when the user changed mode during a drag.
            for ob, me, inverse, mode, surface, vertices in self.meshes:
                if ob.name not in bpy.data.objects or ob.data != me:
                    continue
                if ob.mode == "EDIT":
                    bm = bmesh.from_edit_mesh(me)
                    bm.verts.ensure_lookup_table()
                    for index, start, rails, normal in vertices:
                        bm.verts[index].co = inverse @ start
                    bm.normal_update()
                    bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
                else:
                    for index, start, rails, normal in vertices:
                        me.vertices[index].co = inverse @ start
                    me.update()
            self.finish()


def invoke_move(context, event, **properties):
    """Snaps integration: call first in snap_transform.invoke for kind == MOVE.

    Return this result when non-None. Constraints take priority over target snaps.
    Forward constraint_axis/from_gizmo. Rotate and Scale keep their existing path.
    """
    if active(context):
        return bpy.ops.max.poly_move("INVOKE_DEFAULT", **properties)
    return None


def select_move(context):
    if active(context):
        bpy.ops.wm.tool_set_by_id(name="max.poly_move")
    else:
        snaps = sys.modules.get(__package__ + ".snaps")
        if snaps is not None:
            snaps.select_transform(context, "MOVE")
        else:
            bpy.ops.wm.tool_set_by_id(name="builtin.move")


def constraint_update(self, context):
    if bpy.app.background or not context or context.mode != "EDIT_MESH":
        return
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                with context.temp_override(window=window, area=area):
                    tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
                    if tool and tool.idname in {"builtin.move", "max.poly_move", "max.snap_move"}:
                        select_move(context)
                area.tag_redraw()


def orientation_basis(context):
    snaps = sys.modules.get(__package__ + ".snaps")
    if snaps is not None:
        return snaps.orientation_basis(context)
    slot = context.scene.transform_orientation_slots[0]
    if slot.custom_orientation:
        return slot.custom_orientation.matrix.copy()
    if slot.type in {"LOCAL", "NORMAL", "GIMBAL"} and context.object:
        if slot.type == "NORMAL" and context.mode == "EDIT_MESH":
            bm = bmesh.from_edit_mesh(context.object.data)
            normal = sum((v.normal for v in bm.verts if v.select), Vector())
            normal = context.object.matrix_world.inverted_safe().transposed().to_3x3() @ normal
            if normal.length:
                return normal.to_track_quat("Z", "Y").to_matrix()
        return context.object.matrix_world.to_quaternion().to_matrix()
    if slot.type == "VIEW" and context.region_data:
        return context.region_data.view_rotation.to_matrix()
    return Matrix.Identity(3)


class MAX_OT_poly_move_tool(bpy.types.Operator):
    bl_idname = "max.poly_move_tool"
    bl_label = "Select and Move"

    def execute(self, context):
        select_move(context)
        return {"FINISHED"}


class MAX_OT_poly_move(bpy.types.Operator):
    """Move along the original edges, surface or normals. Right-click cancels"""
    bl_idname = "max.poly_move"
    bl_label = "Move"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}
    value: FloatVectorProperty(size=3, subtype="TRANSLATION")
    normal_distance: FloatProperty(default=0)
    constraint_axis: BoolVectorProperty(size=3, default=(False, False, False), options={"SKIP_SAVE"})
    from_gizmo: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        session = MoveSession(context)
        try:
            distance = self.normal_distance if self.properties.is_property_set("normal_distance") else None
            session.apply(self.value, normal_distance=distance)
            session.finish()
        except Exception:
            session.cancel()
            raise
        return {"FINISHED"}

    def invoke(self, context, event):
        if not active(context):
            bpy.ops.transform.translate("INVOKE_DEFAULT", release_confirm=True,
                                        constraint_axis=self.constraint_axis)
            return {"CANCELLED"}
        if not context.region_data:
            return {"CANCELLED"}
        self.session = MoveSession(context)
        self.region, self.rv3d = context.region, context.region_data
        self.basis = orientation_basis(context)
        self.start = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.value == "CLICK_DRAG":
            self.start = Vector((event.mouse_prev_press_x-self.region.x, event.mouse_prev_press_y-self.region.y))
        self.release_confirm = self.from_gizmo or event.value == "CLICK_DRAG"
        self.number = ""
        self.origin = self._point(self.start)
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Move constrained to " + context.object.max_poly.constraints.title() +
                                          ". X/Y/Z: axis. Right-click or Esc: cancel")
        return {"RUNNING_MODAL"}

    def _point(self, co):
        return view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, co, self.session.center)

    def _update(self, context, event):
        co = Vector((event.mouse_region_x, event.mouse_region_y))
        delta = self._point(co) - self.origin
        axes = [i for i, enabled in enumerate(self.constraint_axis) if enabled]
        if len(axes) == 1:
            from .create import ray_line_height
            axis = self.basis.col[axes[0]]
            distance = ray_line_height(self.region, self.rv3d, co, self.session.center, axis)
            start = ray_line_height(self.region, self.rv3d, self.start, self.session.center, axis)
            delta = axis * (distance-start)
        elif len(axes) == 2:
            normal = self.basis.col[axes[0]].cross(self.basis.col[axes[1]]).normalized()
            delta -= normal * delta.dot(normal)
        distance = delta.dot(self.session.normal)
        view_normal = self.rv3d.view_rotation @ Vector((0,0,1))
        if abs(self.session.normal.dot(view_normal)) > .95:
            # Like Shrink/Fatten, a face-on view still needs a usable mouse direction.
            unit = (self._point(self.start + Vector((1,0))) - self.origin).length
            distance = (co.x-self.start.x) * unit
        if self.number not in {"", "-", ".", "-."}:
            amount = float(self.number)
            direction = self.basis.col[axes[0]] if len(axes) == 1 else delta.normalized()
            delta = direction * amount
            distance = amount
        self.value, self.normal_distance = delta, distance
        self.session.apply(delta, normal_distance=distance)
        context.area.tag_redraw()

    def _finish(self, context, cancel=False):
        self.session.cancel() if cancel else self.session.finish()
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        return {"CANCELLED"} if cancel else {"FINISHED"}

    def modal(self, context, event):
        if self.session.closed or context.mode != "EDIT_MESH":
            return self._finish(context, True)
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            return self._finish(context, True)
        try:
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                self._update(context, event)
                return self._finish(context)
            if event.type == "LEFTMOUSE" and event.value == ("RELEASE" if self.release_confirm else "PRESS"):
                self._update(context, event)
                return self._finish(context)
            if event.value == "PRESS":
                if event.type in {"X", "Y", "Z"}:
                    index = "XYZ".index(event.type)
                    self.constraint_axis = tuple(i != index if event.shift else i == index for i in range(3))
                elif event.type == "BACK_SPACE":
                    self.number = self.number[:-1]
                elif event.ascii and event.ascii in "0123456789.-":
                    candidate = self.number + event.ascii
                    try:
                        if candidate not in {"-", ".", "-."}:
                            float(candidate)
                        self.number = candidate
                    except ValueError:
                        pass
            if event.type == "MOUSEMOVE" or event.value == "PRESS":
                self._update(context, event)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return self._finish(context, True)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if hasattr(self, "session"):
            self._finish(context, True)


class MAX_WST_poly_move(bpy.types.WorkSpaceTool):
    bl_idname = "max.poly_move"
    bl_label = "Select and Move"
    bl_description = "Move with Editable Poly Constraints"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_icon = "ops.transform.translate"
    bl_widget = "MAX_GGT_poly_move"
    bl_keymap = (("max.poly_move", {"type": "LEFTMOUSE", "value": "CLICK_DRAG"}, {}),
                 ("view3d.select", {"type": "LEFTMOUSE", "value": "CLICK"},
                  {"properties": [("deselect_all", True)]}))


class MAX_GGT_poly_move(bpy.types.GizmoGroup):
    bl_idname = "MAX_GGT_poly_move"
    bl_label = "Select and Move"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return bool(tool and tool.idname == "max.poly_move" and context.mode == "EDIT_MESH")

    def setup(self, context):
        self.handles = []
        for i, color in enumerate(((1,.15,.15), (.3,1,.2), (.2,.5,1))):
            for plane in (False, True):
                gizmo = self.gizmos.new("GIZMO_GT_primitive_3d" if plane else "GIZMO_GT_arrow_3d")
                gizmo.draw_style = "PLANE" if plane else "NORMAL"
                gizmo.color, gizmo.alpha = color, .25 if plane else .8
                gizmo.color_highlight, gizmo.alpha_highlight = (1,1,.2), 1
                props = gizmo.target_set_operator("max.poly_move")
                props.from_gizmo = True
                props.constraint_axis = tuple(j != i if plane else j == i for j in range(3))
                if plane:
                    gizmo.scale_basis = .18
                    gizmo.use_draw_offset_scale = True
                self.handles.append((gizmo, i, plane))
        self.center = self.gizmos.new("GIZMO_GT_move_3d")
        self.center.draw_style = "RING_2D"
        self.center.color, self.center.alpha = (1,1,1), .7
        self.center.color_highlight, self.center.alpha_highlight = (1,1,.2), 1
        self.center.scale_basis = .15
        self.center.target_set_operator("max.poly_move").from_gizmo = True

    def draw_prepare(self, context):
        bm = bmesh.from_edit_mesh(context.object.data)
        points = [context.object.matrix_world @ v.co for v in bm.verts if v.select and not v.hide]
        center = sum(points, Vector()) / max(1, len(points))
        basis = orientation_basis(context)
        for gizmo, i, plane in self.handles:
            gizmo.hide = not points
            normal = basis.col[i].normalized()
            matrix = normal.to_track_quat("Z", "Y").to_matrix().to_4x4()
            matrix.translation = center
            gizmo.matrix_basis = matrix
            if plane:
                a, b = [basis.col[j] for j in range(3) if j != i]
                local = matrix.to_3x3().inverted_safe() @ ((a+b) * 1.8)
                gizmo.matrix_offset = Matrix.Translation(local)
        self.center.hide = not points
        self.center.matrix_basis = Matrix.Translation(center)


@persistent
def teardown(_=None):
    for session in list(_sessions):
        session.cancel()


def register_tools():
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre):
        handlers.append(teardown)
    if not bpy.app.background:
        bpy.utils.register_tool(MAX_WST_poly_move, after={"builtin.move"})


def unregister_tools():
    teardown()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre):
        if teardown in handlers:
            handlers.remove(teardown)
    if not bpy.app.background:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    with bpy.context.temp_override(window=window, area=area):
                        tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
                        if tool and tool.idname == "max.poly_move":
                            bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.utils.unregister_tool(MAX_WST_poly_move)


classes = (MAX_OT_poly_move_tool, MAX_OT_poly_move, MAX_GGT_poly_move)
