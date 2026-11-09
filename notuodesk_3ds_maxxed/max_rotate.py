"""Max Linear Roll rotation. Geometry snaps never enter this transform path."""

import math
import sys
import time

import bmesh
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       PointerProperty)
from mathutils import Euler, Matrix, Vector


REFERENCES = [(k, n, "") for k, n in (("VIEW", "View"), ("SCREEN", "Screen"),
              ("WORLD", "World"), ("LOCAL", "Local"), ("PARENT", "Parent"), ("GRID", "Grid"),
              ("WORKING", "Working"), ("GIMBAL", "Gimbal"), ("LOCAL_ALIGNED", "Local Aligned"), ("PICK", "Pick"))]
CENTERS = [("PIVOT", "Use Pivot Point Center", ""),
           ("SELECTION", "Use Selection Center", ""),
           ("COORDINATE", "Use Transform Coordinate Center", "")]
CONSTRAINTS = [(v, v, "") for v in ("X", "Y", "Z", "XY", "YZ", "ZX", "XYZ")]


def _absolute_changed(self, context):
    _typein_changed(context, True)


def _offset_changed(self, context):
    _typein_changed(context, False)


_reference_busy = False


def _reference_update(self, context, operation):
    global _reference_busy
    if _reference_busy:
        return
    _reference_busy = True
    try:
        if operation != "ROTATE":
            setattr(self,"use_"+operation.lower()+"_reference",True)
        if self.constant:
            value = getattr(self,{"ROTATE":"reference","MOVE":"move_reference","SCALE":"scale_reference"}[operation])
            self.reference = self.move_reference = self.scale_reference = value
            self.use_move_reference = self.use_scale_reference = True
        from .snaps import _redraw
        _redraw(context)
    finally:
        _reference_busy = False


def _reference_changed(self, context):
    _reference_update(self,context,"ROTATE")


def _move_reference(self, context):
    _reference_update(self,context,"MOVE")


def _scale_reference(self, context):
    _reference_update(self,context,"SCALE")


def _move_center(self, context):
    self.use_move_center = True


def _scale_center(self, context):
    self.use_scale_center = True


class MaxRotateSettings(bpy.types.PropertyGroup):
    reference: EnumProperty(name="Reference Coordinate System", items=REFERENCES, default="VIEW", update=_reference_changed)
    move_reference: EnumProperty(name="Reference Coordinate System", items=REFERENCES, default="WORLD", update=_move_reference)
    scale_reference: EnumProperty(name="Reference Coordinate System", items=REFERENCES, default="WORLD", update=_scale_reference)
    use_move_reference: BoolProperty()
    use_scale_reference: BoolProperty()
    move_center: EnumProperty(name="Use Center", items=CENTERS, default="SELECTION", update=_move_center)
    scale_center: EnumProperty(name="Use Center", items=CENTERS, default="SELECTION", update=_scale_center)
    use_move_center: BoolProperty()
    use_scale_center: BoolProperty()
    center: EnumProperty(name="Use Center", items=CENTERS, default="PIVOT")
    pick: PointerProperty(name="Pick", type=bpy.types.Object)
    object_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="Z")
    subobject_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="Z")
    move_object_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="XY")
    move_subobject_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="XY")
    scale_object_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="XYZ")
    scale_subobject_axis: EnumProperty(name="Axis Constraints", items=CONSTRAINTS, default="XYZ")
    scale_mode: EnumProperty(name="Select and Scale", items=[("UNIFORM", "Select and Uniform Scale", ""),
                ("NON_UNIFORM", "Select and Non-Uniform Scale", ""), ("SQUASH", "Select and Squash", "")])
    increment: FloatProperty(name="Rotation Increment", default=.5, min=.001, max=10,
                             description="Degrees per mouse pixel, as in Max Gizmos Preferences")
    size: FloatProperty(name="Gizmo Size", default=1, min=.2, max=4)
    show_labels: BoolProperty(name="Show Axis Labels", default=True)
    multiple_gizmos: BoolProperty(name="Allow Multiple Gizmos")
    move_size: FloatProperty(name="Relative Size (%)", default=100, min=1, max=500)
    rotate_size: FloatProperty(name="Relative Size (%)", default=100, min=1, max=500)
    scale_size: FloatProperty(name="Relative Size (%)", default=100, min=1, max=500)
    plane_handles: BoolProperty(name="Plane Handles", default=True)
    plane_offset: FloatProperty(name="Offset (%)", default=42, min=0, max=100)
    screen_move: BoolProperty(name="Move in Screen Space", default=True)
    uniform_handle: FloatProperty(name="Uniform Handle Size (%)", default=55, min=1, max=90)
    two_axis_handle: FloatProperty(name="2-Axis Handle Size (%)", default=23, min=1, max=100)
    free_rotation: BoolProperty(name="Free Rotation", default=True)
    show_tripod: BoolProperty(name="Show Tripod", default=True)
    screen_handle: BoolProperty(name="Screen Handle", default=True)
    show_pie: BoolProperty(name="Show Pie Slice", default=True)
    angle_data: BoolProperty(name="Angle Data", default=True)
    rotation_method: EnumProperty(name="Rotation Method", items=[("LINEAR", "Linear Roll", ""),
              ("CRANK", "Circular Crank", ""), ("LEGACY", "Legacy R4", "")])
    planar_threshold: FloatProperty(name="Planar Angle Threshold", default=15, min=0, max=90)
    constant: BoolProperty(name="Constant", description="Keep reference coordinates when switching transforms")
    grid: PointerProperty(name="Active Grid", type=bpy.types.Object)
    working_location: FloatVectorProperty(name="Working Pivot Position", subtype="TRANSLATION")
    working_rotation: FloatVectorProperty(name="Working Pivot Rotation", subtype="EULER")
    pick0: PointerProperty(type=bpy.types.Object)
    pick1: PointerProperty(type=bpy.types.Object)
    pick2: PointerProperty(type=bpy.types.Object)
    pick3: PointerProperty(type=bpy.types.Object)
    absolute: FloatVectorProperty(name="Absolute", subtype="EULER", update=_absolute_changed)
    offset: FloatVectorProperty(name="Offset", subtype="EULER", update=_offset_changed)


def settings(context):
    return context.scene.max_rotate


def reference_name(context, operation="ROTATE"):
    s = settings(context)
    return getattr(s,{"ROTATE":"reference","MOVE":"move_reference","SCALE":"scale_reference"}[operation])


def center_mode(context, operation="ROTATE"):
    s = settings(context)
    if operation != "ROTATE" and not getattr(s,"use_"+operation.lower()+"_center"):
        return "SELECTION"
    return getattr(s,{"ROTATE":"center","MOVE":"move_center","SCALE":"scale_center"}[operation])


def _constraint_attr(context, operation):
    from . import max_gizmos
    operation = operation or max_gizmos.kind(context) or "ROTATE"
    prefix = {"ROTATE": "", "MOVE": "move_", "SCALE": "scale_"}[operation]
    return prefix + ("subobject_axis" if context.mode == "EDIT_MESH" else "object_axis")


def constraint(context, operation=None):
    return getattr(settings(context), _constraint_attr(context, operation))


def set_constraint(context, value, operation=None):
    s = settings(context)
    attr = _constraint_attr(context, operation)
    if value == "CYCLE":
        planes = ("XY", "YZ", "ZX")
        value = planes[(planes.index(getattr(s, attr))+1) % 3] if getattr(s, attr) in planes else "XY"
    setattr(s, attr, value)
    return value


def reference_basis(context, ob=None, rv3d=None, operation="ROTATE"):
    s = settings(context)
    ob = ob or context.active_object
    rv3d = rv3d or context.region_data
    ref = reference_name(context,operation)
    if ref == "WORKING":
        return Euler(s.working_rotation, "XYZ").to_matrix()
    if ref == "GRID":
        return s.grid.matrix_world.to_quaternion().to_matrix() if s.grid else Matrix.Identity(3)
    if ref == "GIMBAL" and operation != "ROTATE":
        return ob.parent.matrix_world.to_quaternion().to_matrix() if ob and ob.parent else Matrix.Identity(3)
    if ref == "GIMBAL" and ob:
        if ob.rotation_mode not in {"QUATERNION", "AXIS_ANGLE"}:
            axes = []
            for i in range(3):
                angles = ob.rotation_euler.copy()
                for component in ob.rotation_mode[:ob.rotation_mode.index("XYZ"[i])+1]:
                    angles["XYZ".index(component)] = 0
                axes.append(angles.to_matrix().col[i].copy())
            parent = ob.parent.matrix_world.to_quaternion().to_matrix() if ob.parent else Matrix.Identity(3)
            return parent @ Matrix(axes).transposed()
        return ob.parent.matrix_world.to_quaternion().to_matrix() if ob.parent else Matrix.Identity(3)
    if ref == "SCREEN" or (ref == "VIEW" and rv3d and not rv3d.is_perspective):
        return rv3d.view_rotation.to_matrix() if rv3d else Matrix.Identity(3)
    if ref in {"LOCAL", "LOCAL_ALIGNED"} and ob:
        return ob.matrix_world.to_quaternion().to_matrix()
    if ref == "PARENT" and ob and ob.parent:
        return ob.parent.matrix_world.to_quaternion().to_matrix()
    if ref == "PICK" and s.pick:
        return s.pick.matrix_world.to_quaternion().to_matrix()
    return Matrix.Identity(3)


def rotation_delta(delta, handle, tangent, basis, view_basis, axis_constraint, snap, increment):
    """Return a world rotation and its start-relative, stepped angle data.

    Linear Roll projects mouse distance onto the tangent frozen at mouse-down.
    The view ring uses screen Z. Free rotation steps each reference Euler angle.
    Neither native snap_elements, Ctrl nor the geometry snap picker is involved.
    """
    factor = math.radians(increment)
    frame = view_basis if handle == "VIEW" else basis
    angles = Vector()
    if handle in {"X", "Y", "Z", "VIEW"} or (handle == "OFF" and len(axis_constraint) == 1):
        index = 2 if handle == "VIEW" else "XYZ".index(axis_constraint if handle == "OFF" else handle)
        angles[index] = delta.dot(tangent) * factor
    else:
        world = view_basis.col[0] * -delta.y + view_basis.col[1] * delta.x
        angles = basis.transposed() @ world * factor
        if handle == "OFF":
            for i, key in enumerate("XYZ"):
                if key not in axis_constraint:
                    angles[i] = 0
    if snap.angle_snap:
        step = math.radians(snap.angle)
        for i, angle in enumerate(angles):
            # Half a step rounds away from zero, symmetrically in both directions.
            angles[i] = math.copysign(math.floor(abs(angle)/step + .5 + 1e-7) * step, angle)
    rotation = Matrix.Identity(3)
    for i in range(3):
        rotation = Matrix.Rotation(angles[i],3,frame.col[i]) @ rotation
    return rotation, angles


def _geometric_center(ob):
    if ob.type == "MESH" and len(ob.data.vertices):
        return ob.matrix_world @ (sum((Vector(p) for p in ob.bound_box), Vector()) / 8)
    return ob.matrix_world.translation.copy()


def _coordinate_center(context, ob, operation="ROTATE"):
    s = settings(context)
    ref = reference_name(context,operation)
    if ref == "WORKING":
        return Vector(s.working_location)
    if ref == "GRID" and s.grid:
        return s.grid.matrix_world.translation.copy()
    if ref == "PICK" and s.pick:
        return s.pick.matrix_world.translation.copy()
    if ref == "PARENT" and ob and ob.parent:
        return ob.parent.matrix_world.translation.copy()
    if ref == "LOCAL" and ob:
        return ob.matrix_world.translation.copy()
    return Vector()


def transform_center(context, operation="ROTATE"):
    """Idle drawing and mouse-down use the same centre contract."""
    from .snaps import _selection_center
    s, ob = settings(context), context.active_object
    ref, mode = reference_name(context,operation), center_mode(context,operation)
    local = ref == "LOCAL" and (operation == "ROTATE" or getattr(s,"use_"+operation.lower()+"_reference"))
    if operation != "ROTATE" and not getattr(s,"use_"+operation.lower()+"_center") and not local:
        return _selection_center(context)
    if ref == "LOCAL" or mode == "PIVOT":
        if context.mode == "EDIT_MESH":
            if ob:
                points = [ob.matrix_world @ v.co for v in bmesh.from_edit_mesh(ob.data).verts
                          if v.select and not v.hide]
                if points:
                    return sum(points, Vector()) / len(points)
        return ob.matrix_world.translation.copy() if ob else Vector()
    if mode == "COORDINATE":
        return _coordinate_center(context, ob, operation)
    if context.mode == "EDIT_MESH":
        return _selection_center(context)
    points = [_geometric_center(o) for o in context.selected_objects]
    return sum(points, Vector()) / max(1, len(points))


def trackball_delta(start, end, center, radius, basis, view_basis, snap):
    """Rotate the grabbed sphere point onto the current pointer point."""
    def sphere(point):
        p = (point-center) / max(radius, 1e-6)
        length = p.length_squared
        z = math.sqrt(1-length) if length <= .5 else .5/math.sqrt(length)
        return Vector((p.x, p.y, z)).normalized()
    rotation = view_basis @ sphere(start).rotation_difference(sphere(end)).to_matrix() @ view_basis.transposed()
    angles = Vector((basis.transposed() @ rotation @ basis).to_euler("XYZ"))
    if snap.angle_snap:
        step = math.radians(snap.angle)
        for i, angle in enumerate(angles):
            angles[i] = math.copysign(math.floor(abs(angle)/step+.5+1e-7)*step, angle)
        rotation = basis @ Euler(angles, "XYZ").to_matrix() @ basis.transposed()
    return rotation, angles


def constraint_session(context):
    module = sys.modules.get(__package__+".poly_constraints")
    if context.mode == "EDIT_MESH" and module is not None and module.active(context):
        return module.MoveSession(context)
    return None


def close_constraints(context, session, cancel=False):
    if session is not None:
        module = sys.modules[__package__+".poly_constraints"]
        # The solver owns its geometry snapshot. Keep toolbar toggles the user
        # changed during this drag, rather than restoring an older snap toggle.
        current = module.snap_settings(context.scene.tool_settings)
        session.cancel() if cancel else session.finish()
        for name,value in current.items():
            setattr(context.scene.tool_settings,name,value)


class RotationSession:
    """Apply every preview from a saved state. Cancellation restores that state."""

    def __init__(self, context, rv3d=None):
        self.context = context
        self.closed = False
        self.reference = settings(context).reference
        self.center_mode = settings(context).center
        self.objects = list(context.objects_in_mode_unique_data if context.mode == "EDIT_MESH" else context.selected_objects)
        self.matrices = {ob: ob.matrix_world.copy() for ob in self.objects}
        self.bases = {ob: reference_basis(context, ob, rv3d) for ob in self.objects}
        self.eulers = {ob: ob.rotation_euler.copy() for ob in self.objects}
        self.vertices = {}
        self.constraints = constraint_session(context)
        points = []
        for ob in self.objects:
            if ob.mode == "EDIT":
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.index_update()
                self.vertices[ob] = [(v.index, v.co.copy()) for v in bm.verts if v.select and not v.hide]
                points.extend(ob.matrix_world @ co for _, co in self.vertices[ob])
            else:
                points.append(_geometric_center(ob))
        self.center = sum(points, Vector()) / max(1, len(points))
        self.pivots = {}
        for ob in self.objects:
            if self.center_mode == "COORDINATE" and self.reference != "LOCAL":
                pivot = _coordinate_center(context, ob)
            elif self.center_mode == "PIVOT" or self.reference == "LOCAL":
                verts = self.vertices.get(ob)
                pivot = (sum((ob.matrix_world @ co for _, co in verts), Vector()) / len(verts)
                         if verts else ob.matrix_world.translation.copy())
            else:
                pivot = self.center.copy()
            self.pivots[ob] = pivot
        active = context.active_object
        self.gizmo_center = transform_center(context)

    def apply(self, rotation, angles=None, *, view=False):
        if self.closed:
            return
        # Pivot Point Center accumulates transforms down a selected hierarchy.
        # Shared selection/coordinate centres instead apply one common delta.
        def depth(ob):
            n, parent = 0, ob.parent
            while parent:
                n, parent = n+1, parent.parent
            return n
        targets = {}
        for ob in sorted(self.objects, key=depth):
            saved = self.matrices[ob]
            pivot = self.pivots[ob]
            inherited = False
            if ob not in self.vertices and (self.center_mode == "PIVOT" or self.reference == "LOCAL"):
                ancestor = ob.parent
                while ancestor and ancestor not in self.matrices:
                    ancestor = ancestor.parent
                if ancestor:
                    saved = ancestor.matrix_world @ self.matrices[ancestor].inverted_safe() @ saved
                    pivot = saved.translation.copy()
                    inherited = True
            rot = rotation
            if self.reference == "GIMBAL" and angles is not None and not view and ob not in self.vertices:
                euler = self.eulers[ob].copy()
                for i in range(3):
                    euler[i] += angles[i]
                parent = ob.parent.matrix_world.to_quaternion().to_matrix() if ob.parent else Matrix.Identity(3)
                rot = parent @ euler.to_matrix() @ saved.to_quaternion().to_matrix().inverted_safe()
            if self.reference == "LOCAL" and angles is not None and not view:
                basis = saved.to_quaternion().to_matrix() if inherited else self.bases[ob]
                rot = basis @ Euler(angles, "XYZ").to_matrix() @ basis.transposed()
            matrix = Matrix.Translation(pivot) @ rot.to_4x4() @ Matrix.Translation(-pivot)
            if ob in self.vertices:
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.ensure_lookup_table()
                saved = self.matrices[ob]
                local = saved.inverted_safe() @ matrix @ saved
                targets[ob] = {index:saved @ local @ co for index,co in self.vertices[ob]}
                if self.constraints is None:
                    for index, co in self.vertices[ob]:
                        bm.verts[index].co = local @ co
                bm.normal_update()
                bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
            else:
                ob.matrix_world = matrix @ saved
                self.context.view_layer.update()
        if self.constraints is not None:
            self.constraints.apply_targets(targets)
        self.context.view_layer.update()

    def cancel(self):
        if not self.closed:
            self.apply(Matrix.Identity(3))
            close_constraints(self.context,self.constraints,True)
            self.closed = True

    def finish(self):
        close_constraints(self.context,self.constraints)
        self.closed = True


class MAX_OT_rotate_constraint(bpy.types.Operator):
    bl_idname = "max.rotate_constraint"
    bl_label = "Axis Constraints"
    axis: EnumProperty(items=CONSTRAINTS + [("CYCLE", "Cycle Planes", "")])

    def execute(self, context):
        set_constraint(context, self.axis)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class MAX_OT_rotate_size(bpy.types.Operator):
    bl_idname = "max.rotate_size"
    bl_label = "Transform Gizmo Size"
    grow: BoolProperty(default=True)

    def execute(self, context):
        s = settings(context)
        s.size *= 1.1 if self.grow else 1/1.1
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class MAX_OT_rotate_offset(bpy.types.Operator):
    """Exact rotation type-in. Interactive Angle Snap does not round typed values."""
    bl_idname = "max.rotate_offset"
    bl_label = "Rotate Transform Type-In"
    bl_options = {"REGISTER", "UNDO"}
    angles: FloatVectorProperty(size=3, subtype="EULER")

    def execute(self, context):
        tx = RotationSession(context)
        basis = reference_basis(context)
        # Max View type-in uses World, even in an orthographic viewport.
        if settings(context).reference == "VIEW":
            basis = Matrix.Identity(3)
        rotation = basis @ Euler(self.angles, "XYZ").to_matrix() @ basis.transposed()
        tx.apply(rotation, self.angles)
        tx.finish()
        return {"FINISHED"}


def squash_matrix(factor, flags, basis):
    """Compensate unselected axes to keep volume during Squash scaling."""
    count = sum(flags)
    if count not in {1,2}:
        return Matrix.Scale(factor,3)
    compensation = max(abs(factor),1e-8) ** (-count/(3-count))
    scales = [factor if selected else compensation for selected in flags]
    return basis @ Matrix.Diagonal(scales) @ basis.transposed()


_typein_windows = set()
_typein_origin = None
_typein_busy = False
_typein_edit = None


def typein_basis(context, absolute=False):
    # View always types in World. Screen uses World for Absolute only.
    ref = settings(context).reference
    return Matrix.Identity(3) if ref == "VIEW" or (absolute and ref == "SCREEN") else reference_basis(context)


def typein_values(context):
    ob = context.active_object
    if ob is None:
        return Vector()
    if settings(context).reference == "GIMBAL":
        return Vector(ob.rotation_euler)
    basis = typein_basis(context, True)
    return Vector((basis.inverted_safe() @ ob.matrix_world.to_quaternion().to_matrix()).to_euler("XYZ"))


def typein_apply(context, angles, absolute=False, tx=None):
    tx = tx or RotationSession(context)
    basis = typein_basis(context, absolute)
    rotation = Euler(angles, "XYZ").to_matrix()
    if absolute:
        current = tx.matrices[context.active_object].to_quaternion().to_matrix()
        if settings(context).reference == "GIMBAL":
            parent = context.active_object.parent
            basis = parent.matrix_world.to_quaternion().to_matrix() if parent else Matrix.Identity(3)
        rotation = basis @ rotation @ current.inverted_safe()
        tx.apply(rotation)
    else:
        tx.apply(basis @ rotation @ basis.inverted_safe(), angles)
    return tx


def _typein_changed(context, absolute):
    global _typein_busy, _typein_edit
    if _typein_busy or _typein_origin is None:
        return
    window, area, region = _typein_origin
    with context.temp_override(window=window, area=area, region=region):
        if not context.active_object or not context.selected_objects:
            return
        if _typein_edit is None or _typein_edit[1] != absolute:
            _typein_commit()
            _typein_edit = [RotationSession(context), absolute, time.monotonic()]
        values = settings(context).absolute if absolute else settings(context).offset
        typein_apply(context, values, absolute, _typein_edit[0])
        _typein_edit[2] = time.monotonic()
        area.tag_redraw()
    if not bpy.app.timers.is_registered(_typein_tick):
        bpy.app.timers.register(_typein_tick, first_interval=.05)


def _typein_commit():
    global _typein_edit, _typein_busy
    if _typein_edit is not None:
        tx = _typein_edit[0]
        tx.finish()
        _typein_edit = None
        window, area, region = _typein_origin
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.ed.undo_push(message="Rotate Transform Type-In")
            _typein_busy = True
            try:
                settings(bpy.context).absolute = typein_values(bpy.context)
                settings(bpy.context).offset = (0, 0, 0)
            finally:
                _typein_busy = False


def _typein_tick():
    global _typein_busy
    live = {w.as_pointer() for w in bpy.context.window_manager.windows}
    _typein_windows.intersection_update(live)
    if _typein_edit is not None and time.monotonic()-_typein_edit[2] > .4:
        _typein_commit()
    if not _typein_windows:
        return None
    if _typein_edit is None and _typein_origin:
        window, area, region = _typein_origin
        if window not in tuple(bpy.context.window_manager.windows):
            return None
        with bpy.context.temp_override(window=window, area=area, region=region):
            _typein_busy = True
            try:
                settings(bpy.context).absolute = typein_values(bpy.context)
            finally:
                _typein_busy = False
    return .1


def floating_window(context, registry):
    live = {w.as_pointer() for w in context.window_manager.windows}
    existing = next(((w,a) for w in context.window_manager.windows for a in w.screen.areas
                     if a.type == "PREFERENCES"), None)
    if existing:
        window, area = existing
        with context.temp_override(window=window, area=area, region=next(r for r in area.regions if r.type == "WINDOW")):
            bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
    else:
        bpy.ops.screen.userpref_show("INVOKE_DEFAULT")
    window = next((w for w in context.window_manager.windows if w.as_pointer() not in live), None)
    if window is None:
        return None
    registry.add(window.as_pointer())
    area = window.screen.areas[0]
    area.type = "NODE_EDITOR"
    space = area.spaces.active
    space.tree_type = "CompositorNodeTree"
    space.pin = True
    space.show_region_ui = True
    space.show_region_toolbar = False
    space.show_region_header = False
    if hasattr(space,"show_region_asset_shelf"):
        space.show_region_asset_shelf = False
    def activate():
        try:
            if window in tuple(bpy.context.window_manager.windows):
                area.spaces.active.show_region_ui = True
                area.spaces.active.show_region_toolbar = False
                area.spaces.active.show_region_header = False
                if hasattr(area.spaces.active,"show_region_asset_shelf"):
                    area.spaces.active.show_region_asset_shelf = False
                area.tag_redraw()
        except ReferenceError:
            pass
    bpy.app.timers.register(activate,first_interval=.1)
    return window


class MAX_OT_rotate_typein(bpy.types.Operator):
    bl_idname = "max.rotate_typein"
    bl_label = "Rotate Transform Type-In"
    def invoke(self, context, event):
        global _typein_origin, _typein_busy
        live = {w.as_pointer() for w in context.window_manager.windows}
        _typein_windows.intersection_update(live)
        if _typein_windows:
            _typein_commit()
            for window in list(context.window_manager.windows):
                if window.as_pointer() in _typein_windows:
                    with context.temp_override(window=window):
                        bpy.ops.wm.window_close()
            _typein_windows.clear()
            return {"FINISHED"}
        _typein_origin = (context.window, context.area, context.region)
        _typein_busy = True
        try:
            settings(context).absolute = typein_values(context)
            settings(context).offset = (0, 0, 0)
        finally:
            _typein_busy = False
        if not floating_window(context, _typein_windows):
            return {"CANCELLED"}
        if not bpy.app.timers.is_registered(_typein_tick):
            bpy.app.timers.register(_typein_tick, first_interval=.1)
        return {"FINISHED"}


class MAX_PT_rotate_typein(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Item"
    bl_label = "Rotate Transform Type-In"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return context.window.as_pointer() in _typein_windows

    def draw(self, context):
        s = settings(context)
        row = self.layout.row()
        row.label(text="Rotate Transform Type-In")
        row.operator("max.rotate_typein_close", text="", icon="X")
        row = self.layout.row()
        row.enabled = bool(context.active_object and context.selected_objects)
        col = row.column()
        col.label(text="Absolute: "+("World" if s.reference in {"VIEW", "SCREEN"} else s.reference.title()))
        col.enabled = not (context.mode == "EDIT_MESH" and s.reference == "LOCAL")
        for i, axis in enumerate("XYZ"):
            col.prop(s, "absolute", index=i, text=axis)
        col = row.column()
        name = "World" if s.reference == "VIEW" else s.reference.title()
        col.label(text="Offset: "+name)
        for i, axis in enumerate("XYZ"):
            col.prop(s, "offset", index=i, text=axis)


class MAX_OT_rotate_typein_close(bpy.types.Operator):
    bl_idname = "max.rotate_typein_close"
    bl_label = "Close Rotate Transform Type-In"

    def execute(self, context):
        _typein_commit()
        _typein_windows.discard(context.window.as_pointer())
        bpy.ops.wm.window_close()
        return {"FINISHED"}


def remember_pick(context, ob):
    s = settings(context)
    history = [getattr(s,"pick"+str(i)) for i in range(4)]
    history = [ob]+[item for item in history if item is not None and item != ob]
    for i in range(4):
        setattr(s,"pick"+str(i),history[i] if i<len(history) else None)
    s.pick = ob
    from .max_gizmos import kind
    setattr(s,{"MOVE":"move_reference","SCALE":"scale_reference"}.get(kind(context),"reference"),"PICK")


class MAX_OT_rotate_pick(bpy.types.Operator):
    bl_idname = "max.rotate_pick"
    bl_label = "Pick Reference Coordinate System"
    saved: bpy.props.IntProperty(default=-1)
    name: bpy.props.StringProperty(name="Object")

    def execute(self, context):
        ob = getattr(settings(context),"pick"+str(self.saved)) if self.saved >= 0 else bpy.data.objects.get(self.name)
        if ob:
            remember_pick(context, ob)
            return {"FINISHED"}
        return {"CANCELLED"}

    def invoke(self, context, event):
        if self.saved >= 0:
            return self.execute(context)
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set("Pick Reference Coordinate System. Click an object. H: pick by name. Right-click: cancel")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} or (event.type == "H" and event.value == "PRESS"):
            context.window.cursor_modal_restore()
            context.workspace.status_text_set(None)
            if event.type == "H":
                bpy.ops.max.rotate_pick_name("INVOKE_DEFAULT")
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            from .create import mouse_ray
            origin, direction = mouse_ray(context.region,context.region_data,Vector((event.mouse_region_x,event.mouse_region_y)))
            hit, _, _, _, ob, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(),origin,direction)
            if hit:
                remember_pick(context,ob.original)
                context.window.cursor_modal_restore()
                context.workspace.status_text_set(None)
                context.area.tag_redraw()
                return {"FINISHED"}
        return {"RUNNING_MODAL"}


class MAX_OT_rotate_pick_name(bpy.types.Operator):
    bl_idname = "max.rotate_pick_name"
    bl_label = "Pick Object"
    name: bpy.props.StringProperty(name="Object")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self,width=300)

    def draw(self, context):
        self.layout.prop_search(self,"name",context.scene,"objects")

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if not ob:
            return {"CANCELLED"}
        remember_pick(context,ob)
        return {"FINISHED"}


class MAX_MT_rotate_pick_history(bpy.types.Menu):
    bl_label = "Reference Coordinate Systems"

    def draw(self, context):
        for i in range(4):
            ob = getattr(settings(context),"pick"+str(i))
            if ob:
                self.layout.operator("max.rotate_pick",text=ob.name).saved = i
        self.layout.operator("max.rotate_pick",text="Pick...")


class MAX_MT_transform_center(bpy.types.Menu):
    bl_label = "Use Center"

    def draw(self, context):
        from .max_gizmos import kind
        prop = {"ROTATE":"center","MOVE":"move_center","SCALE":"scale_center"}.get(kind(context),"center")
        self.layout.prop(settings(context),prop,expand=True)


_preference_windows = set()


class MAX_OT_gizmo_preferences(bpy.types.Operator):
    bl_idname = "max.gizmo_preferences"
    bl_label = "Gizmos Preferences"

    def invoke(self, context, event):
        live = {w.as_pointer() for w in context.window_manager.windows}
        _preference_windows.intersection_update(live)
        if not _preference_windows:
            floating_window(context,_preference_windows)
        return {"FINISHED"}


class MAX_PT_gizmo_preferences(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Item"
    bl_label = "Gizmos Preferences"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return context.window.as_pointer() in _preference_windows

    def draw(self, context):
        s = settings(context)
        self.layout.label(text="Gizmos Preferences")
        groups = (("Transform Gizmos",("show_labels","multiple_gizmos","size","constant")),
                  ("Move Gizmo",("move_size","plane_handles","plane_offset","screen_move")),
                  ("Rotate Gizmo",("rotate_size","free_rotation","show_tripod","screen_handle","show_pie","angle_data","rotation_method","planar_threshold","increment")),
                  ("Scale Gizmo",("scale_size","uniform_handle","two_axis_handle")),
                  ("Reference Coordinates",("grid","working_location","working_rotation")))
        for title, fields in groups:
            col = self.layout.box().column(align=True)
            col.label(text=title)
            for field in fields:
                col.prop(s,field)


_clones = {}
_clone_dialogs = {}
_retired = set()


def retained_class(cls):
    return cls in _retired


def _retire_dialogs():
    for cls in list(_retired):
        if cls not in _clone_dialogs.values():
            bpy.utils.unregister_class(cls)
            _retired.remove(cls)
    return .05 if _retired else None


def defer_unregister(cls):
    if cls not in _clone_dialogs.values():
        return False
    _retired.add(cls)
    if not bpy.app.timers.is_registered(_retire_dialogs):
        bpy.app.timers.register(_retire_dialogs,first_interval=.05,persistent=True)
    return True


class _ClonePreview:
    """Standalone branch fallback. Integrated builds reuse shift_clone transactions."""

    def __init__(self, context):
        self.context = context
        self.edit = context.mode == "EDIT_MESH"
        self.originals = list(context.selected_objects)
        self.active = context.active_object
        self.copies = []
        self.meshes = []
        self.closed = False
        if self.edit:
            from .operators import current_level
            self.level = current_level(context)
            for ob in context.objects_in_mode_unique_data:
                bm = bmesh.from_edit_mesh(ob.data)
                snapshot = bm.copy()
                if self.level in {2,3}:
                    selected = [e for e in bm.edges if e.select and not e.hide and (e.is_boundary or e.is_wire)]
                    created = bmesh.ops.extrude_edge_only(bm,edges=selected)["geom"] if selected else []
                else:
                    selection = bm.faces if self.level in {4,5} else bm.verts
                    selected = [e for e in selection if e.select and not e.hide]
                    created = bmesh.ops.duplicate(bm,geom=selected)["geom"] if selected else []
                original_verts = [v for v in bm.verts if v.select and not v.hide]
                for seq in (bm.faces,bm.edges,bm.verts):
                    for e in seq:
                        e.select_set(False)
                verts = [e for e in created if isinstance(e,bmesh.types.BMVert)]
                if self.level in {2,3}:
                    for edge in bm.edges:
                        if all(v in verts for v in edge.verts):
                            edge.select_set(True)
                elif self.level in {4,5}:
                    for face in (e for e in created if isinstance(e,bmesh.types.BMFace)):
                        face.select_set(True)
                else:
                    for v in verts:
                        v.select_set(True)
                bm.verts.index_update()
                self.meshes.append((ob,[v.index for v in verts],snapshot,[v.co.copy() for v in verts]))
                bmesh.update_edit_mesh(ob.data)
        else:
            from .operators import max_name
            for src in self.originals:
                ob = src.copy()
                if src.data:
                    ob.data = src.data.copy()
                ob.name = max_name(src.name.rstrip("0123456789") or "Object")
                for collection in src.users_collection:
                    collection.objects.link(ob)
                self.copies.append(ob)
            mapping = dict(zip(self.originals,self.copies))
            for src, ob in zip(self.originals,self.copies):
                world = src.matrix_world.copy()
                if src.parent in mapping:
                    ob.parent = mapping[src.parent]
                ob.matrix_world = world
                src.select_set(False)
                ob.select_set(True)
            context.view_layer.objects.active = mapping.get(self.active,self.copies[0])
        context.view_layer.update()

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        if self.edit:
            for ob,verts,snapshot,start in self.meshes:
                bm = bmesh.from_edit_mesh(ob.data)
                backup = bpy.data.meshes.new("Clone rollback")
                try:
                    snapshot.to_mesh(backup)
                    bm.clear()
                    bm.from_mesh(backup)
                    bmesh.update_edit_mesh(ob.data)
                finally:
                    snapshot.free()
                    bpy.data.meshes.remove(backup)
        else:
            for ob in self.copies:
                bpy.data.objects.remove(ob,do_unlink=True)
            for ob in self.originals:
                ob.select_set(True)
            self.context.view_layer.objects.active = self.active

    def changed(self):
        if self.closed:
            return False
        if self.edit:
            for ob,indices,snapshot,start in self.meshes:
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.ensure_lookup_table()
                if any((bm.verts[i].co-co).length>1e-6 for i,co in zip(indices,start)):
                    return True
            return False
        return any(any(abs(a-b)>1e-6 for ar,br in zip(src.matrix_world,ob.matrix_world) for a,b in zip(ar,br))
                   for src,ob in zip(self.originals,self.copies))

    def finish(self, mode="COPY", count=1, name="", destination="ELEMENT"):
        if self.edit:
            if destination == "OBJECT":
                before = set(bpy.data.objects)
                bpy.ops.mesh.separate(type="SELECTED")
                for ob in set(bpy.data.objects)-before:
                    if name:
                        ob.name = name
            for ob,indices,snapshot,start in self.meshes:
                snapshot.free()
            self.closed = True
            return
        from .operators import max_name
        if name:
            self.copies[0].name = name
        for source, first in zip(self.originals,self.copies):
            if mode == "INSTANCE":
                first.data = source.data
            elif mode == "REFERENCE" and source.type == "MESH":
                self._reference(first, source)
            step = first.matrix_world @ source.matrix_world.inverted_safe()
            previous = first
            for _ in range(1,count):
                ob = first.copy()
                if mode == "COPY" and first.data:
                    ob.data = first.data.copy()
                ob.name = max_name((name or source.name).rstrip("0123456789") or "Object")
                for collection in first.users_collection:
                    collection.objects.link(ob)
                ob.matrix_world = step @ previous.matrix_world
                if mode == "REFERENCE" and source.type == "MESH":
                    self._reference(ob,source)
                ob.select_set(True)
                previous = ob
        self.closed = True

    @staticmethod
    def _reference(ob, source):
        # The source's evaluated geometry feeds the reference before its own
        # downstream modifiers. Editing the reference cannot edit its source.
        ob.modifiers.clear()
        ob.data = bpy.data.meshes.new(source.name+" Reference")
        group = bpy.data.node_groups.new(source.name+" Reference", "GeometryNodeTree")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        info = group.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "ORIGINAL"
        info.inputs["Object"].default_value = source
        info.inputs["As Instance"].default_value = False
        output = group.nodes.new("NodeGroupOutput")
        group.links.new(info.outputs["Geometry"],output.inputs["Geometry"])
        ob.modifiers.new("Reference", "NODES").node_group = group


def begin_clone(context):
    module = sys.modules.get(__package__+".shift_clone")
    if module is not None:
        tx = module.MeshClones(context) if context.mode == "EDIT_MESH" else module.ObjectClone(context)
        module._active[context.window.as_pointer()] = (tx, context.window_manager, None)
        return tx
    return _ClonePreview(context)


def defer_clone(context, tx):
    module = sys.modules.get(__package__+".shift_clone")
    token = str(id(tx))
    if module is not None and not isinstance(tx,_ClonePreview):
        module.finish_snap_clone(context, tx)
        return
    if not tx.changed():
        tx.cancel()
        return
    if tx.edit and tx.level in {2,3}:
        tx.finish()
        bpy.ops.ed.undo_push(message="Extend Edges")
        return
    _clones[token] = tx
    window, area, region = context.window, context.area, context.region
    def show():
        if token in _clones:
            with bpy.context.temp_override(window=window,area=area,region=region):
                bpy.ops.max.rotate_clone_options("INVOKE_DEFAULT",token=token)
        return None
    bpy.app.timers.register(show,first_interval=.05)


def cancel_clone(context, tx):
    module = sys.modules.get(__package__+".shift_clone")
    if module is not None and not isinstance(tx,_ClonePreview):
        module.finish_snap_clone(context,tx,cancel=True)
    else:
        tx.cancel()


class MAX_OT_rotate_clone_options(bpy.types.Operator):
    bl_idname = "max.rotate_clone_options"
    bl_label = "Clone Options"
    bl_options = {"UNDO"}
    token: bpy.props.StringProperty(options={"SKIP_SAVE"})
    mode: EnumProperty(items=[(v,v.title(),"") for v in ("COPY","INSTANCE","REFERENCE")])
    count: bpy.props.IntProperty(name="Number of Copies",default=1,min=1,max=1000)
    name: bpy.props.StringProperty(name="Name")
    destination: EnumProperty(items=[("ELEMENT","Clone To Element",""),("OBJECT","Clone To Object","")])

    def invoke(self, context, event):
        tx = _clones[self.token]
        self.name = context.active_object.name
        result = context.window_manager.invoke_props_dialog(self,width=290,
                    title="Clone Part of Mesh" if tx.edit else "Clone Options")
        if "RUNNING_MODAL" in result:
            _clone_dialogs[self.token] = type(self)
        return result

    def draw(self, context):
        tx = _clones.get(self.token)
        if not tx:
            return
        lay = self.layout
        lay.prop(self,"destination" if tx.edit else "mode",expand=True)
        if not tx.edit:
            lay.prop(self,"count")
        lay.prop(self,"name")

    def execute(self, context):
        _clone_dialogs.pop(self.token,None)
        tx = _clones.pop(self.token,None)
        if tx:
            tx.finish(self.mode,self.count,self.name,self.destination)
        return {"FINISHED"} if tx else {"CANCELLED"}

    def cancel(self, context):
        _clone_dialogs.pop(self.token,None)
        tx = _clones.pop(self.token,None)
        if tx:
            tx.cancel()


class MAX_OT_rotate(bpy.types.Operator):
    """Linear Roll. Release commits. Right-click or Esc restores the selection."""
    bl_idname = "max.rotate"
    bl_label = "Rotate"
    bl_options = {"REGISTER", "BLOCKING"}
    handle: EnumProperty(items=[(k,k,"") for k in ("AUTO","OFF","X","Y","Z","VIEW","FREE")], default="AUTO")

    @classmethod
    def poll(cls, context):
        return bool(context.area and context.area.type == "VIEW_3D" and context.region_data
                    and context.mode in {"OBJECT", "EDIT_MESH"} and context.active_object)

    def invoke(self, context, event):
        from . import max_gizmos as g, snaps
        self._closed = False
        self.region, self.rv3d = context.region, context.region_data
        self.start_co = Vector((event.mouse_region_x,event.mouse_region_y))
        if event.value == "CLICK_DRAG":
            self.start_co = Vector((event.mouse_prev_press_x-self.region.x,event.mouse_prev_press_y-self.region.y))
        self.cursor = self.start_co.copy()
        self.view_basis = self.rv3d.view_rotation.to_matrix()
        self.orientation = reference_basis(context)
        data = g.pick_geometry(context,self.start_co) if context.space_data.show_gizmo else None
        if self.handle == "AUTO":
            self.handle = g.hit_test(data, self.start_co)
        self.clone = begin_clone(context) if event.shift else None
        self.tx = RotationSession(context)
        self.pivot = self.tx.gizmo_center.copy()
        if data and settings(context).multiple_gizmos:
            self.pivot = data["center"].copy()
        if not self.tx.objects or (context.mode == "EDIT_MESH" and not any(self.tx.vertices.values())):
            self.tx.cancel()
            if self.clone:
                cancel_clone(context,self.clone)
            return {"CANCELLED"}
        self.axis_constraint = constraint(context, "ROTATE")
        if self.handle in {"X","Y","Z"}:
            self.axis_constraint = set_constraint(context, self.handle, "ROTATE")
        self.tangent, self.radial = g.tangent(data, self.handle, self.start_co)
        self.sphere_center = data["xy"].copy() if data else self.start_co.copy()
        self.sphere_radius = data["radius"] if data else 100
        self.angle_data = Vector()
        self._crank_last = 0
        self._crank_total = 0
        self.number = ""
        g.begin(context,self,"ROTATE",self.pivot,self.orientation,self.handle)
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Rotate. A: Angle Snap. F5/F6/F7: X/Y/Z. F8: planes. Right-click: cancel")
        self._update(context,Vector((event.mouse_region_x,event.mouse_region_y)))
        return {"RUNNING_MODAL"}

    def _update(self, context, co):
        from . import snaps
        self.cursor = co.copy()
        if self.handle == "FREE":
            if settings(context).rotation_method == "LEGACY":
                matrix, self.angle_data = rotation_delta(co-self.start_co,"FREE",self.tangent,
                    self.orientation,self.view_basis,self.axis_constraint,snaps.settings(context),settings(context).increment)
            else:
                matrix, self.angle_data = trackball_delta(self.start_co, co, self.sphere_center,
                    self.sphere_radius, self.orientation, self.view_basis, snaps.settings(context))
        else:
            delta, tangent = co-self.start_co, self.tangent
            s = settings(context)
            if self.handle in {"X", "Y", "Z", "VIEW"}:
                axis = self.view_basis.col[2] if self.handle == "VIEW" else self.orientation.col["XYZ".index(self.handle)]
                if s.rotation_method == "CRANK" and abs(axis.dot(self.view_basis.col[2])) > math.sin(math.radians(s.planar_threshold)):
                    from .create import ray_plane
                    point = ray_plane(self.region,self.rv3d,co,self.pivot,axis)
                    if point is not None and (point-self.pivot).length > 1e-6:
                        radial = point-self.pivot
                        angle = math.atan2(axis.dot(self.radial.cross(radial)),self.radial.dot(radial))
                        self._crank_total += (angle-self._crank_last+math.pi) % math.tau-math.pi
                        self._crank_last = angle
                    delta = Vector((math.degrees(self._crank_total)/s.increment, 0))
                    tangent = Vector((1, 0))
                elif s.rotation_method == "LEGACY":
                    tangent = Vector((1, 0)) if abs(self.tangent.x) >= abs(self.tangent.y) else Vector((0, 1))
            matrix, self.angle_data = rotation_delta(delta,self.handle,tangent,
                self.orientation,self.view_basis,self.axis_constraint,snaps.settings(context),settings(context).increment)
        if self.number not in {"","-",".","-."}:
            # Typed values, like Transform Type-In, remain exact with A on.
            self.angle_data = Vector()
            index = "XYZ".index(self.handle) if self.handle in {"X","Y","Z"} else 2
            self.angle_data[index] = math.radians(float(self.number))
            basis = self.view_basis if self.handle == "VIEW" else self.orientation
            matrix = basis @ Euler(self.angle_data,"XYZ").to_matrix() @ basis.transposed()
        self.tx.apply(matrix,self.angle_data,view=self.handle == "VIEW")
        context.area.tag_redraw()

    def _finish(self, context, cancel=False):
        from . import max_gizmos as g
        if self._closed:
            return {"CANCELLED"}
        self._closed = True
        g.finish(self.region)
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        if cancel:
            self.tx.cancel()
            if self.clone:
                cancel_clone(context,self.clone)
            return {"CANCELLED"}
        self.tx.finish()
        if self.clone:
            defer_clone(context,self.clone)
            # The options dialog owns the sole undo step for the completed clone.
            return {"CANCELLED"}
        bpy.ops.ed.undo_push(message="Rotate")
        return {"FINISHED"}

    def modal(self, context, event):
        from . import snaps
        if self._closed:
            return {"CANCELLED"}
        co = Vector((event.mouse_region_x,event.mouse_region_y))
        if event.type in {"ESC","RIGHTMOUSE"} and event.value == "PRESS":
            return self._finish(context,True)
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._update(context,co)
            return self._finish(context)
        if event.type in {"RET","NUMPAD_ENTER"} and event.value == "PRESS":
            return self._finish(context)
        if event.value == "PRESS":
            if event.type == "A" and not event.ctrl and not event.alt:
                snaps.toggle(context,"ANGLE_SNAP")
            elif event.type == "S" and not event.ctrl and not event.alt:
                snaps.toggle(context,"SNAP")
            elif event.type in {"F5","F6","F7","F8"}:
                self.axis_constraint = set_constraint(context,{"F5":"X","F6":"Y","F7":"Z","F8":"CYCLE"}[event.type],"ROTATE")
                self.handle = "OFF"
                self.tangent = Vector((1,0))
            elif event.type == "BACK_SPACE":
                self.number = self.number[:-1]
            elif event.ascii and event.ascii in "0123456789.-":
                candidate = self.number+event.ascii
                try:
                    if candidate not in {"-",".","-."}:
                        float(candidate)
                    self.number = candidate
                except ValueError:
                    pass
        if event.type == "MOUSEMOVE" or event.value == "PRESS":
            self._update(context,co)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._finish(context,True)


class _RotateTool:
    bl_space_type = "VIEW_3D"
    bl_idname = "max.rotate"
    bl_label = "Select and Rotate"
    bl_description = "Linear Roll. A toggles Angle Snap independently of geometry snaps"
    bl_icon = "ops.transform.rotate"
    bl_widget = "MAX_GGT_max_transform"
    bl_keymap = (("max.rotate", {"type":"LEFTMOUSE","value":"CLICK_DRAG"}, {}),
                ("max.rotate", {"type":"LEFTMOUSE","value":"CLICK_DRAG","shift":True}, {}),
                ("view3d.select", {"type":"LEFTMOUSE","value":"CLICK"}, {"properties":[("deselect_all",True)]}))


tools = tuple(type("MAX_WST_rotate_"+mode,(_RotateTool,bpy.types.WorkSpaceTool),
                   {"bl_context_mode":mode}) for mode in ("OBJECT","EDIT_MESH"))


def draw_managers(layout, context):
    s = settings(context)
    from .max_gizmos import kind
    operation = kind(context) or "ROTATE"
    prop = {"ROTATE":"reference","MOVE":"move_reference","SCALE":"scale_reference"}[operation]
    ref = reference_name(context,operation)
    row = layout.row(align=True)
    row.ui_units_x = 4
    row.prop(s,prop,text="")
    if ref == "PICK":
        row.operator("max.rotate_pick",text=s.pick.name if s.pick else "Pick...")
    row.menu("MAX_MT_rotate_pick_history",text="",icon="DOWNARROW_HLT")
    row = layout.row(align=True)
    center = row.row(align=True)
    center.enabled = ref != "LOCAL"
    center.menu("MAX_MT_transform_center",text="",icon={"PIVOT":"PIVOT_INDIVIDUAL", "SELECTION":"PIVOT_MEDIAN", "COORDINATE":"PIVOT_CURSOR"}[center_mode(context,operation)])
    attr = _constraint_attr(context,None)
    row.prop(s,attr,text="")


class MAX_MT_scale_flyout(bpy.types.Menu):
    bl_label = "Select and Scale"

    def draw(self, context):
        self.layout.prop(settings(context),"scale_mode",expand=True)


classes = (MaxRotateSettings, MAX_OT_rotate_constraint, MAX_OT_rotate_size, MAX_OT_rotate_offset,
           MAX_OT_rotate, MAX_MT_scale_flyout, MAX_OT_rotate_clone_options, MAX_OT_rotate_typein,
           MAX_PT_rotate_typein, MAX_OT_rotate_typein_close, MAX_OT_rotate_pick,
           MAX_OT_rotate_pick_name, MAX_MT_rotate_pick_history, MAX_MT_transform_center,
           MAX_OT_gizmo_preferences, MAX_PT_gizmo_preferences)


def register():
    if bpy.app.timers.is_registered(_retire_dialogs):
        bpy.app.timers.unregister(_retire_dialogs)
    _retired.clear()
    bpy.types.Scene.max_rotate = PointerProperty(type=MaxRotateSettings)
    if not bpy.app.background:
        for tool in tools:
            bpy.utils.register_tool(tool,separator=False,group=False)


def unregister():
    _typein_commit()
    for window in list(bpy.context.window_manager.windows):
        if window.as_pointer() in _typein_windows or window.as_pointer() in _preference_windows:
            with bpy.context.temp_override(window=window):
                bpy.ops.wm.window_close()
    _typein_windows.clear()
    _preference_windows.clear()
    if bpy.app.timers.is_registered(_typein_tick):
        bpy.app.timers.unregister(_typein_tick)
    for clone in list(_clones.values()):
        clone.cancel()
    _clones.clear()
    if not bpy.app.background:
        for tool in reversed(tools):
            bpy.utils.unregister_tool(tool)
    if hasattr(bpy.types.Scene, "max_rotate"):
        del bpy.types.Scene.max_rotate
