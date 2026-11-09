"""Max Linear Roll rotation. Geometry snaps never enter this transform path."""

import math
import sys

import bmesh
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       PointerProperty)
from mathutils import Euler, Matrix, Vector


REFERENCES = [(k, n, "") for k, n in (("VIEW", "View"), ("SCREEN", "Screen"),
              ("WORLD", "World"), ("LOCAL", "Local"), ("PARENT", "Parent"), ("PICK", "Pick"))]
CENTERS = [("PIVOT", "Use Pivot Point Center", ""),
           ("SELECTION", "Use Selection Center", ""),
           ("COORDINATE", "Use Transform Coordinate Center", "")]
CONSTRAINTS = [(v, v, "") for v in ("X", "Y", "Z", "XY", "YZ", "ZX", "XYZ")]


class MaxRotateSettings(bpy.types.PropertyGroup):
    reference: EnumProperty(name="Reference Coordinate System", items=REFERENCES, default="VIEW")
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


def settings(context):
    return context.scene.max_rotate


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


def reference_basis(context, ob=None, rv3d=None):
    s = settings(context)
    ob = ob or context.active_object
    rv3d = rv3d or context.region_data
    if s.reference == "SCREEN" or (s.reference == "VIEW" and rv3d and not rv3d.is_perspective):
        return rv3d.view_rotation.to_matrix() if rv3d else Matrix.Identity(3)
    if s.reference == "LOCAL" and ob:
        return ob.matrix_world.to_quaternion().to_matrix()
    if s.reference == "PARENT" and ob and ob.parent:
        return ob.parent.matrix_world.to_quaternion().to_matrix()
    if s.reference == "PICK" and s.pick:
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
    return frame @ Euler(angles, "XYZ").to_matrix() @ frame.transposed(), angles


def _geometric_center(ob):
    if ob.type == "MESH" and len(ob.data.vertices):
        return ob.matrix_world @ (sum((Vector(p) for p in ob.bound_box), Vector()) / 8)
    return ob.matrix_world.translation.copy()


def _coordinate_center(context, ob):
    s = settings(context)
    if s.reference == "PICK" and s.pick:
        return s.pick.matrix_world.translation.copy()
    if s.reference == "PARENT" and ob and ob.parent:
        return ob.parent.matrix_world.translation.copy()
    if s.reference == "LOCAL" and ob:
        return ob.matrix_world.translation.copy()
    return Vector()


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
            if self.center_mode == "COORDINATE":
                pivot = _coordinate_center(context, ob)
            elif self.center_mode == "PIVOT" or self.reference == "LOCAL":
                verts = self.vertices.get(ob)
                pivot = (sum((ob.matrix_world @ co for _, co in verts), Vector()) / len(verts)
                         if verts else ob.matrix_world.translation.copy())
            else:
                pivot = self.center.copy()
            self.pivots[ob] = pivot
        active = context.active_object
        self.gizmo_center = (self.pivots.get(active, self.center).copy() if self.center_mode != "SELECTION"
                             or self.reference == "LOCAL" else self.center.copy())

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


class MAX_OT_rotate_typein(bpy.types.Operator):
    bl_idname = "max.rotate_typein"
    bl_label = "Rotate Transform Type-In"
    angles: FloatVectorProperty(size=3,subtype="EULER",name="Offset")
    absolute: FloatVectorProperty(size=3,subtype="EULER",name="Absolute",
                description="Absolute rotation is read-only in this dialog")

    def invoke(self, context, event):
        self.absolute = context.active_object.matrix_world.to_euler('XYZ')
        return context.window_manager.invoke_popup(self,width=340)

    def draw(self, context):
        row = self.layout.row()
        col = row.column()
        col.label(text="Absolute: World")
        col.enabled = False
        col.prop(self,"absolute",text="")
        col = row.column()
        name = settings(context).reference.title()
        col.label(text="Offset: "+name)
        col.prop(self,"angles",text="")
        col.operator("max.rotate_offset",text="Apply Offset").angles = self.angles

    def execute(self, context):
        return {"FINISHED"}


_clones = {}


class _ClonePreview:
    """Standalone branch fallback. Integrated builds reuse shift_clone transactions."""

    def __init__(self, context):
        self.context = context
        self.edit = context.mode == "EDIT_MESH"
        self.originals = list(context.selected_objects)
        self.active = context.active_object
        self.copies = []
        self.meshes = []
        if self.edit:
            for ob in context.objects_in_mode_unique_data:
                bm = bmesh.from_edit_mesh(ob.data)
                selected = [e for seq in (bm.verts,bm.edges,bm.faces) for e in seq if e.select and not e.hide]
                original_verts = [v for v in bm.verts if v.select and not v.hide]
                created = bmesh.ops.duplicate(bm,geom=selected)["geom"]
                for seq in (bm.verts,bm.edges,bm.faces):
                    for e in seq:
                        e.select = e in created
                verts = [e for e in created if isinstance(e,bmesh.types.BMVert)]
                bm.verts.index_update()
                self.meshes.append((ob,[v.index for v in verts],[v.index for v in original_verts]))
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
        if self.edit:
            for ob,verts,original in self.meshes:
                bm = bmesh.from_edit_mesh(ob.data)
                bm.verts.ensure_lookup_table()
                old = [bm.verts[i] for i in original]
                bmesh.ops.delete(bm,geom=[bm.verts[i] for i in verts],context="VERTS")
                for v in old:
                    v.select = True
                bmesh.update_edit_mesh(ob.data)
        else:
            for ob in self.copies:
                bpy.data.objects.remove(ob,do_unlink=True)
            for ob in self.originals:
                ob.select_set(True)
            self.context.view_layer.objects.active = self.active

    def finish(self, mode="COPY", count=1, name="", destination="ELEMENT"):
        if self.edit:
            if destination == "OBJECT":
                bpy.ops.mesh.separate(type="SELECTED")
            return
        from .operators import max_name
        if name:
            self.copies[0].name = name
        for source, first in zip(self.originals,self.copies):
            if mode in {"INSTANCE","REFERENCE"}:
                first.data = source.data
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
                ob.select_set(True)
                previous = ob


def begin_clone(context):
    module = sys.modules.get(__package__+".shift_clone")
    if module is not None:
        return module.MeshClones(context) if context.mode == "EDIT_MESH" else module.ObjectClone(context)
    return _ClonePreview(context)


def defer_clone(context, tx):
    module = sys.modules.get(__package__+".shift_clone")
    token = str(id(tx))
    if module is not None and not isinstance(tx,_ClonePreview):
        module._pending[token] = tx
        module._defer_dialog(context,token)
        return
    _clones[token] = tx
    window, area, region = context.window, context.area, context.region
    def show():
        if token in _clones:
            with bpy.context.temp_override(window=window,area=area,region=region):
                bpy.ops.max.rotate_clone_options("INVOKE_DEFAULT",token=token)
        return None
    bpy.app.timers.register(show,first_interval=.05)


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
        return context.window_manager.invoke_props_dialog(self,width=290,
                    title="Clone Part of Mesh" if tx.edit else "Clone Options")

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
        tx = _clones.pop(self.token,None)
        if tx:
            tx.finish(self.mode,self.count,self.name,self.destination)
        return {"FINISHED"}

    def cancel(self, context):
        tx = _clones.pop(self.token,None)
        if tx:
            tx.cancel()


class MAX_OT_rotate(bpy.types.Operator):
    """Linear Roll. Release commits. Right-click or Esc restores the selection."""
    bl_idname = "max.rotate"
    bl_label = "Rotate"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}
    handle: EnumProperty(items=[(k,k,"") for k in ("AUTO","OFF","X","Y","Z","VIEW","FREE")], default="AUTO")

    @classmethod
    def poll(cls, context):
        return bool(context.area and context.area.type == "VIEW_3D" and context.region_data
                    and context.mode in {"OBJECT", "EDIT_MESH"} and context.active_object)

    def invoke(self, context, event):
        from . import max_gizmos as g, snaps
        self.region, self.rv3d = context.region, context.region_data
        self.start_co = Vector((event.mouse_region_x,event.mouse_region_y))
        if event.value == "CLICK_DRAG":
            self.start_co = Vector((event.mouse_prev_press_x-self.region.x,event.mouse_prev_press_y-self.region.y))
        self.cursor = self.start_co.copy()
        self.view_basis = self.rv3d.view_rotation.to_matrix()
        self.orientation = reference_basis(context)
        data = g.geometry(context, "ROTATE") if context.space_data.show_gizmo else None
        if self.handle == "AUTO":
            self.handle = g.hit_test(data, self.start_co)
        self.clone = begin_clone(context) if event.shift else None
        self.tx = RotationSession(context)
        self.pivot = self.tx.gizmo_center.copy()
        if not self.tx.objects or (context.mode == "EDIT_MESH" and not any(self.tx.vertices.values())):
            if self.clone:
                self.clone.cancel()
            return {"CANCELLED"}
        self.axis_constraint = constraint(context, "ROTATE")
        if self.handle in {"X","Y","Z"}:
            self.axis_constraint = set_constraint(context, self.handle, "ROTATE")
        self.tangent, self.radial = g.tangent(data, self.handle, self.start_co)
        self.angle_data = Vector()
        self.number = ""
        g.begin(context,self,"ROTATE",self.pivot,self.orientation,self.handle)
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Rotate. A: Angle Snap. F5/F6/F7: X/Y/Z. F8: planes. Right-click: cancel")
        self._update(context,Vector((event.mouse_region_x,event.mouse_region_y)))
        return {"RUNNING_MODAL"}

    def _update(self, context, co):
        from . import snaps
        self.cursor = co.copy()
        matrix, self.angle_data = rotation_delta(co-self.start_co,self.handle,self.tangent,
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
        g.finish(self.region)
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        if cancel:
            self.tx.cancel()
            if self.clone:
                self.clone.cancel()
            return {"CANCELLED"}
        self.tx.finish()
        if self.clone:
            defer_clone(context,self.clone)
            # The options dialog owns the sole undo step for the completed clone.
            return {"CANCELLED"}
        return {"FINISHED"}

    def modal(self, context, event):
        from . import snaps
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
    row = layout.row(align=True)
    row.ui_units_x = 4
    row.prop(s,"reference",text="")
    if s.reference == "PICK":
        row.prop(s,"pick",text="")
    row = layout.row(align=True)
    row.prop(s,"center",text="")
    attr = _constraint_attr(context,None)
    row.prop(s,attr,text="")


class MAX_MT_scale_flyout(bpy.types.Menu):
    bl_label = "Select and Scale"

    def draw(self, context):
        self.layout.prop(settings(context),"scale_mode",expand=True)


classes = (MaxRotateSettings, MAX_OT_rotate_constraint, MAX_OT_rotate_size, MAX_OT_rotate_offset,
           MAX_OT_rotate, MAX_MT_scale_flyout, MAX_OT_rotate_clone_options, MAX_OT_rotate_typein)


def register():
    bpy.types.Scene.max_rotate = PointerProperty(type=MaxRotateSettings)
    if not bpy.app.background:
        for tool in tools:
            bpy.utils.register_tool(tool,separator=False,group=False)


def unregister():
    if not bpy.app.background:
        for tool in reversed(tools):
            bpy.utils.unregister_tool(tool)
    if hasattr(bpy.types.Scene, "max_rotate"):
        del bpy.types.Scene.max_rotate
