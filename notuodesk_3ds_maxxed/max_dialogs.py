"""Supported Max dialogs. Scene writes happen only inside explicit transactions."""
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, StringProperty)
from mathutils import Euler, Matrix, Vector
from . import max_layers

REFERENCE_LIMIT = ("Reference shares object data like Instance. Independent downstream "
                   "modifier stacks and Max reference controllers are not supported.")
CLONE_MODES = [("COPY", "Copy", "Independent object data"),
               ("INSTANCE", "Instance", "Shared object data"),
               ("REFERENCE", "Reference", REFERENCE_LIMIT)]
_transactions = set()


def radio(layout, data, name, choices):
    for value, text in choices:
        row = layout.row(align=True)
        row.emboss = "NONE"
        row.prop_enum(data, name, value, text=text,
                      icon="RADIOBUT_ON" if getattr(data, name) == value else "RADIOBUT_OFF")


def _alive(obj):
    try:
        return obj is not None and bpy.data.objects.get(obj.name) == obj
    except ReferenceError:
        return False


def _depth(obj):
    depth = 0
    while obj.parent:
        depth += 1
        obj = obj.parent
    return depth


def _write_matrices(context, matrices):
    for obj in sorted(matrices, key=_depth):
        if _alive(obj):
            obj.matrix_world = matrices[obj]
            context.view_layer.update()


def active_tool(context):
    if context.workspace:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        name = tool.idname if tool else ""
        if "rotate" in name:
            return "ROTATE"
        if "scale" in name or "resize" in name:
            return "SCALE"
    return "MOVE"


def coordinate_basis(context, obj, system):
    """World and Parent have origins. Local uses the object's current axes."""
    if system == "WORLD":
        return Matrix.Identity(4)
    if system == "PARENT":
        return obj.parent.matrix_world.copy() if obj.parent else Matrix.Identity(4)
    if system == "LOCAL":
        return obj.matrix_world.to_quaternion().to_matrix().to_4x4()
    if system in {"VIEW", "SCREEN"}:
        area = next((a for a in context.screen.areas if a.type == "VIEW_3D"), None) if context.screen else None
        if area:
            return area.spaces.active.region_3d.view_rotation.to_matrix().to_4x4()
        raise ValueError("Screen coordinates require a viewport")
    raise ValueError("Unsupported reference coordinate system")


class TransformDraft:
    """Always calculate previews from the starting world matrices."""
    def __init__(self, context, objects=None, system="WORLD"):
        if context.mode != "OBJECT":
            raise ValueError("Type-In supports object transforms. Finish sub-object editing first")
        self.context = context
        self.objects = list(context.selected_objects if objects is None else objects)
        if not self.objects:
            raise ValueError("Select an object first")
        for obj in self.objects:
            max_layers._writable(obj)
            if obj.max_frozen:
                raise ValueError("Unfreeze the selection first")
            if obj.constraints:
                raise ValueError("Constrained objects need their controller edited directly")
        context.view_layer.update()
        self.matrices = {obj: obj.matrix_world.copy() for obj in self.objects}
        self.bases = {obj: coordinate_basis(context, obj, system) for obj in self.objects}
        self.closed = False
        _transactions.add(self)

    def _validate(self):
        if self.closed or not all(_alive(obj) for obj in self.objects):
            raise ValueError("The source selection is no longer available")

    def type_in(self, tool, group, values):
        self._validate()
        if tool not in {"MOVE", "ROTATE", "SCALE"} or group not in {"ABSOLUTE", "OFFSET"}:
            raise ValueError("Unsupported transform")
        matrices = {}
        for obj, original in self.matrices.items():
            basis = self.bases[obj]
            position, rotation, scale = (basis.inverted_safe() @ original).decompose()
            if tool == "MOVE":
                position = Vector(values) if group == "ABSOLUTE" else position + Vector(values)
            elif tool == "ROTATE":
                value = Euler(values, "XYZ").to_quaternion()
                rotation = value if group == "ABSOLUTE" else value @ rotation
            else:
                factor = Vector(values) / 100.0
                scale = factor if group == "ABSOLUTE" else Vector(a*b for a, b in zip(scale, factor))
            matrices[obj] = basis @ Matrix.LocRotScale(position, rotation, scale)
        _write_matrices(self.context, matrices)

    def mirror(self, axis="X", offset=0.0):
        self._validate()
        if axis not in "XYZ" or len(axis) != 1:
            raise ValueError("Choose X, Y or Z")
        index = "XYZ".index(axis)
        reflection = Matrix.Identity(4)
        reflection[index][index] = -1
        reflection[index][3] = 2 * offset
        matrices = {obj: self.bases[obj] @ reflection @ self.bases[obj].inverted_safe() @ matrix
                    for obj, matrix in self.matrices.items()}
        _write_matrices(self.context, matrices)

    def align(self, target, position=(True, True, True), orientation=(False, False, False),
              scale=(False, False, False), current_point="PIVOT", target_point="PIVOT"):
        self._validate()
        if not _alive(target) or target.name not in self.context.scene.objects or target in self.objects:
            raise ValueError("Choose a different live target object")
        target_position = object_point(target, target.matrix_world, target_point)
        _, target_rotation, target_scale = target.matrix_world.decompose()
        matrices = {}
        for obj, original in self.matrices.items():
            location, rotation, size = original.decompose()
            source_euler, target_euler = rotation.to_euler("XYZ"), target_rotation.to_euler("XYZ")
            for i in range(3):
                if orientation[i]:
                    source_euler[i] = target_euler[i]
                if scale[i]:
                    size[i] = target_scale[i]
            matrix = Matrix.LocRotScale(location, source_euler.to_quaternion(), size)
            source_position = object_point(obj, matrix, current_point)
            for i in range(3):
                if position[i]:
                    matrix[i][3] += target_position[i] - source_position[i]
            matrices[obj] = matrix
        _write_matrices(self.context, matrices)

    def accept(self):
        self._validate()
        self.closed = True
        _transactions.discard(self)

    def cancel(self):
        if not self.closed:
            _write_matrices(self.context, {obj: matrix for obj, matrix in self.matrices.items() if _alive(obj)})
            self.closed = True
        _transactions.discard(self)


def object_point(obj, matrix, point):
    if point == "PIVOT":
        return matrix.translation.copy()
    corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    low = Vector(min(c[i] for c in corners) for i in range(3))
    high = Vector(max(c[i] for c in corners) for i in range(3))
    if point == "MIN":
        return low
    if point == "MAX":
        return high
    if point == "CENTER":
        return (low + high) * .5
    raise ValueError("Unsupported alignment point")


def clone(context, mode="COPY", copies=1, name="", transform=None):
    from .shift_clone import ObjectClone
    if context.mode != "OBJECT" or not context.selected_objects:
        raise ValueError("Select objects before cloning")
    if mode not in {item[0] for item in CLONE_MODES} or not 1 <= copies <= 10000:
        raise ValueError("Invalid clone options")
    for obj in context.selected_objects:
        max_layers._writable(obj)
        if obj.max_frozen:
            raise ValueError("Unfreeze the selection first")
    tx = ObjectClone(context)
    try:
        if transform:
            transform(tx)
        return tx.finish(mode, copies, name, "COPY")
    except Exception:
        tx.cancel()
        raise


class MirrorDraft:
    """Own preview clones and their transform until the dialog accepts or closes."""
    def __init__(self, context, system="WORLD"):
        self.context, self.system = context, system
        self.source = list(context.selected_objects)
        if context.mode != "OBJECT" or not self.source:
            raise ValueError("Select objects before mirroring")
        self.tx = self.clones = None
        self.closed = False
        _transactions.add(self)

    def preview(self, axis, offset, mode="NONE"):
        from .shift_clone import ObjectClone
        if self.closed or not all(_alive(obj) for obj in self.source):
            raise ValueError("The mirror selection is no longer available")
        self._restore()
        if mode != "NONE":
            self.clones = ObjectClone(self.context)
        try:
            objects = self.clones.preview if self.clones else self.source
            self.tx = TransformDraft(self.context, objects, self.system)
            self.tx.mirror(axis, offset)
        except Exception:
            self._restore()
            raise
        self.mode = mode

    def _restore(self):
        if self.tx:
            self.tx.cancel()
            self.tx = None
        if self.clones:
            self.clones.cancel()
            self.clones = None

    def accept(self):
        if self.closed or not self.tx:
            raise ValueError("No mirror preview is active")
        try:
            result = self.clones.finish(self.mode, 1, "", "COPY") if self.clones else []
            self.tx.accept()
        except Exception:
            self.cancel()
            raise
        self.closed = True
        _transactions.discard(self)
        return result

    def cancel(self):
        if not self.closed:
            self._restore()
            self.closed = True
        _transactions.discard(self)


class MAX_OT_clone_dialog(bpy.types.Operator):
    """Clone selected objects with independent or shared object data"""
    bl_idname = "max.clone_dialog"
    bl_label = "Clone Options"
    bl_options = {"REGISTER", "UNDO"}
    mode: EnumProperty(items=CLONE_MODES, default="COPY")
    copies: IntProperty(name="Number of Copies", default=1, min=1, max=10000)
    name: StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        radio(self.layout, self, "mode", [(i[0], i[1]) for i in CLONE_MODES])
        self.layout.prop(self, "copies")
        self.layout.prop(self, "name")
        if self.mode == "REFERENCE":
            self.layout.label(text="Shared data. Independent modifier stacks.")
            self.layout.label(text="Max reference controllers are unavailable.")

    def execute(self, context):
        try:
            clone(context, self.mode, self.copies, self.name)
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


SYSTEMS = [(v, n, "") for v, n in (("WORLD", "World"), ("LOCAL", "Local"),
            ("PARENT", "Parent"), ("VIEW", "View"), ("SCREEN", "Screen"))]


class MAX_OT_typein_dialog(bpy.types.Operator):
    """Enter absolute or offset values for the active object transform tool"""
    bl_idname = "max.typein_dialog"
    bl_label = "Transform Type-In"
    bl_options = {"REGISTER", "UNDO"}
    tool: EnumProperty(items=[(v, v.title(), "") for v in ("MOVE", "ROTATE", "SCALE")])
    system: EnumProperty(name="Reference Coordinate System", items=SYSTEMS, default="WORLD")
    group: EnumProperty(items=[("ABSOLUTE", "Absolute", ""), ("OFFSET", "Offset", "")])
    absolute: FloatVectorProperty(name="Absolute", size=3)
    offset: FloatVectorProperty(name="Offset", size=3)
    absolute_angle: FloatVectorProperty(name="Absolute", size=3, subtype="EULER")
    offset_angle: FloatVectorProperty(name="Offset", size=3, subtype="EULER")
    preview: BoolProperty(name="Preview", default=False)

    def invoke(self, context, event):
        self.tool = active_tool(context)
        obj = context.active_object
        if not obj:
            return {"CANCELLED"}
        location, rotation, scale = obj.matrix_world.decompose()
        self.absolute = location if self.tool == "MOVE" else Vector(scale) * 100
        self.absolute_angle = rotation.to_euler("XYZ")
        self.offset = (100, 100, 100) if self.tool == "SCALE" else (0, 0, 0)
        try:
            self._tx = TransformDraft(context, system=self.system)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        self.layout.label(text=self.tool.title() + " Transform Type-In")
        self.layout.prop(self, "system")
        for group, label in (("ABSOLUTE", "Absolute"), ("OFFSET", "Offset")):
            box = self.layout.box()
            radio(box, self, "group", [(group, label + ": " + self.system.title())])
            prop = group.lower() + ("_angle" if self.tool == "ROTATE" else "")
            for i, axis in enumerate("XYZ"):
                box.prop(self, prop, index=i, text=axis + (" (%)" if self.tool == "SCALE" else ""))
        self.layout.prop(self, "preview")

    def check(self, context):
        tx = getattr(self, "_tx", None)
        if tx and not tx.closed:
            try:
                tx.bases = {obj: coordinate_basis(context, obj, self.system) for obj in tx.objects}
                # Local preview axes are always derived from the starting pose.
                if self.system == "LOCAL":
                    tx.bases = {obj: matrix.to_quaternion().to_matrix().to_4x4() for obj, matrix in tx.matrices.items()}
                if self.preview:
                    prop = self.group.lower() + ("_angle" if self.tool == "ROTATE" else "")
                    tx.type_in(self.tool, self.group, getattr(self, prop))
                else:
                    _write_matrices(context, tx.matrices)
            except ValueError as exc:
                self.report({"WARNING"}, str(exc))
        return True

    def cancel(self, context):
        if getattr(self, "_tx", None):
            self._tx.cancel()

    def execute(self, context):
        tx = None
        try:
            tx = getattr(self, "_tx", None) or TransformDraft(context, system=self.system)
            self.check(context)
            prop = self.group.lower() + ("_angle" if self.tool == "ROTATE" else "")
            tx.type_in(self.tool, self.group, getattr(self, prop))
            tx.accept()
        except (ValueError, RuntimeError) as exc:
            if tx:
                tx.cancel()
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class MAX_OT_mirror_dialog(bpy.types.Operator):
    """Mirror objects across a reference plane, with optional cloning"""
    bl_idname = "max.mirror_dialog"
    bl_label = "Mirror"
    bl_options = {"REGISTER", "UNDO"}
    axis: EnumProperty(items=[(a, a, "") for a in "XYZ"], default="X")
    offset: FloatProperty(name="Offset", unit="LENGTH")
    system: EnumProperty(name="Reference Coordinate System", items=SYSTEMS, default="WORLD")
    mode: EnumProperty(items=[("NONE", "No Clone", "")] + CLONE_MODES, default="NONE")
    preview: BoolProperty(name="Preview", default=False)

    def invoke(self, context, event):
        try:
            self._session = MirrorDraft(context, self.system)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        self.layout.label(text="Mirror Axis")
        radio(self.layout, self, "axis", [(a, a) for a in "XYZ"])
        self.layout.prop(self, "offset")
        self.layout.prop(self, "system")
        radio(self.layout.box(), self, "mode", [("NONE", "No Clone")] + [(i[0], i[1]) for i in CLONE_MODES])
        if self.mode == "REFERENCE":
            self.layout.label(text="Reference shares data. No reference stack.")
        self.layout.prop(self, "preview")

    def check(self, context):
        session = getattr(self, "_session", None)
        if session and not session.closed:
            try:
                session.system = self.system
                if self.preview:
                    session.preview(self.axis, self.offset, self.mode)
                else:
                    session._restore()
            except ValueError as exc:
                self.report({"WARNING"}, str(exc))
        return True

    def cancel(self, context):
        if getattr(self, "_session", None):
            self._session.cancel()

    def execute(self, context):
        tx = None
        try:
            tx = getattr(self, "_session", None) or MirrorDraft(context, self.system)
            tx.system = self.system
            tx.preview(self.axis, self.offset, self.mode)
            tx.accept()
        except (ValueError, RuntimeError) as exc:
            if tx:
                tx.cancel()
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


POINTS = [(v, n, "") for v, n in (("MIN", "Minimum"), ("CENTER", "Center"),
                                 ("PIVOT", "Pivot Point"), ("MAX", "Maximum"))]


class MAX_OT_align_dialog(bpy.types.Operator):
    """Align selected objects to a target's position, orientation and scale"""
    bl_idname = "max.align_dialog"
    bl_label = "Align Selection"
    bl_options = {"REGISTER", "UNDO"}
    target: StringProperty(name="Target Object")
    position: BoolVectorProperty(name="Align Position", size=3, default=(True, True, True))
    orientation: BoolVectorProperty(name="Align Orientation", size=3)
    scale: BoolVectorProperty(name="Match Scale", size=3)
    current_point: EnumProperty(name="Current Object", items=POINTS, default="PIVOT")
    target_point: EnumProperty(name="Target Object", items=POINTS, default="PIVOT")
    preview: BoolProperty(name="Preview", default=False)

    def invoke(self, context, event):
        try:
            self._tx = TransformDraft(context)
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        self.layout.prop_search(self, "target", context.scene, "objects")
        for prop, label in (("position", "Align Position"), ("orientation", "Align Orientation"), ("scale", "Match Scale")):
            box = self.layout.box()
            box.label(text=label)
            row = box.row()
            for i, axis in enumerate("XYZ"):
                row.prop(self, prop, index=i, text=axis)
        row = self.layout.row()
        for prop in ("current_point", "target_point"):
            col = row.column()
            col.label(text="Current Object" if prop == "current_point" else "Target Object")
            radio(col, self, prop, [(item[0], item[1]) for item in POINTS])
        self.layout.prop(self, "preview")

    def check(self, context):
        tx = getattr(self, "_tx", None)
        if tx and not tx.closed:
            try:
                _write_matrices(context, tx.matrices)
                if self.preview and context.scene.objects.get(self.target):
                    tx.align(context.scene.objects.get(self.target), self.position, self.orientation, self.scale, self.current_point, self.target_point)
            except ValueError as exc:
                self.report({"WARNING"}, str(exc))
        return True

    def cancel(self, context):
        if getattr(self, "_tx", None):
            self._tx.cancel()

    def execute(self, context):
        tx = None
        try:
            tx = getattr(self, "_tx", None) or TransformDraft(context)
            tx.align(context.scene.objects.get(self.target), self.position, self.orientation, self.scale, self.current_point, self.target_point)
            tx.accept()
        except (ValueError, RuntimeError) as exc:
            if tx:
                tx.cancel()
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class ObjectPropertiesDraft:
    FIELDS = ("name", "display_type", "show_name", "show_wire", "show_in_front", "hide_render", "max_show_frozen_gray")

    def __init__(self, obj):
        self.obj = obj
        self.values = {key: getattr(obj, key) for key in self.FIELDS}
        self.closed = False

    def apply(self):
        if self.closed or not _alive(self.obj):
            return False
        max_layers._writable(self.obj)
        for key, value in self.values.items():
            setattr(self.obj, key, value)
        self.closed = True
        return True

    def cancel(self):
        self.closed = True


class MAX_OT_object_properties_dialog(bpy.types.Operator):
    """Edit supported General, Display and Rendering object properties"""
    bl_idname = "max.object_properties_dialog"
    bl_label = "Object Properties"
    bl_options = {"REGISTER", "UNDO"}
    object_name: StringProperty(options={"HIDDEN"})
    name: StringProperty(name="Name")
    display_type: EnumProperty(name="Display", items=[(v, n, "") for v, n in
        (("TEXTURED", "Shaded"), ("SOLID", "Solid"), ("WIRE", "Wireframe"), ("BOUNDS", "Display as Box"))])
    show_name: BoolProperty(name="Show Name")
    show_wire: BoolProperty(name="Edged Faces")
    show_in_front: BoolProperty(name="Display in Front")
    hide_render: BoolProperty(name="Hide from Rendering")
    max_show_frozen_gray: BoolProperty(name="Show Frozen in Gray", default=True)

    def invoke(self, context, event):
        if not context.active_object:
            return {"CANCELLED"}
        self._source = context.active_object
        self.object_name = self._source.name
        for key in ObjectPropertiesDraft.FIELDS:
            setattr(self, key, getattr(self._source, key))
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        obj = getattr(self, "_source", context.scene.objects.get(self.object_name))
        box = self.layout.box()
        box.label(text="General")
        box.prop(self, "name")
        if _alive(obj):
            box.label(text="Type: " + obj.type.title())
            if obj.type == "MESH":
                box.label(text=f"Vertices: {len(obj.data.vertices)}   Faces: {len(obj.data.polygons)}")
        box = self.layout.box()
        box.label(text="Display")
        for key in ("display_type", "show_name", "show_wire", "show_in_front", "max_show_frozen_gray"):
            box.prop(self, key)
        box = self.layout.box()
        box.label(text="Rendering")
        box.prop(self, "hide_render")

    def execute(self, context):
        obj = getattr(self, "_source", context.scene.objects.get(self.object_name))
        if not _alive(obj):
            return {"CANCELLED"}
        draft = ObjectPropertiesDraft(obj)
        draft.values = {key: getattr(self, key) for key in draft.FIELDS}
        try:
            draft.apply()
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


def resolve_scene_action(decision, save, proceed):
    """A cancelled or failed save never advances to the destructive action."""
    if decision == "CANCEL":
        return False
    if decision == "SAVE":
        if not save():
            return False
    elif decision != "DISCARD":
        raise ValueError("Unknown save decision")
    proceed()
    return True


def native_save(filepath):
    if not filepath or Path(filepath).suffix.lower() != ".blend":
        raise ValueError("Save a Blender scene (.blend). Use Export for interchange formats")
    return bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)), check_existing=True) == {"FINISHED"}


class MAX_OT_scene_file_dialog(bpy.types.Operator):
    """Save native Blender scenes, or open/new after a save, discard or cancel choice"""
    bl_idname = "max.scene_file_dialog"
    bl_label = "Scene File"
    action: EnumProperty(items=[(v, n, "") for v, n in
        (("OPEN", "Open Blender Scene"), ("NEW", "New Scene"), ("SAVE", "Save Blender Scene"), ("SAVE_AS", "Save Blender Scene As"))])
    filepath: StringProperty(name="Scene (.blend)", subtype="FILE_PATH")
    save_path: StringProperty(name="Save current scene as (.blend)", subtype="FILE_PATH")
    decision: EnumProperty(items=[("SAVE", "Save", ""), ("DISCARD", "Discard", ""), ("CANCEL", "Cancel", "")], default="CANCEL")

    def invoke(self, context, event):
        self.save_path = bpy.data.filepath
        if self.action in {"SAVE", "SAVE_AS"}:
            self.filepath = bpy.data.filepath
        self._scene = context.scene
        self._dirty = bpy.data.is_dirty
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        self.layout.label(text=Path(bpy.data.filepath).name if bpy.data.filepath else "Untitled.blend")
        if self.action != "NEW":
            self.layout.prop(self, "filepath")
        if self.action in {"OPEN", "NEW"} and getattr(self, "_dirty", bpy.data.is_dirty):
            self.layout.label(text="Save changes to the current scene?")
            radio(self.layout, self, "decision", [("SAVE", "Save"), ("DISCARD", "Discard"), ("CANCEL", "Cancel")])
            if self.decision == "SAVE":
                self.layout.prop(self, "save_path")
        self.layout.label(text="Native scene format: Blender (.blend). Export is separate.")

    def execute(self, context):
        if getattr(self, "_scene", context.scene) != context.scene:
            return {"CANCELLED"}
        try:
            if self.action in {"SAVE", "SAVE_AS"}:
                return {"FINISHED"} if native_save(self.filepath) else {"CANCELLED"}
            if self.action == "OPEN" and (Path(self.filepath).suffix.lower() != ".blend" or not Path(self.filepath).is_file()):
                raise ValueError("Choose an existing Blender scene (.blend). Use Import for .max and FBX")
            def proceed():
                if self.action == "OPEN":
                    bpy.ops.wm.open_mainfile(filepath=self.filepath)
                else:
                    bpy.ops.wm.read_homefile(use_empty=True)
            decision = self.decision if getattr(self, "_dirty", bpy.data.is_dirty) else "DISCARD"
            return {"FINISHED"} if resolve_scene_action(decision, lambda: native_save(self.save_path), proceed) else {"CANCELLED"}
        except (ValueError, RuntimeError, OSError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


@persistent
def cancel_transactions(*_):
    for tx in list(_transactions):
        tx.cancel()


classes = (MAX_OT_clone_dialog, MAX_OT_typein_dialog, MAX_OT_mirror_dialog, MAX_OT_align_dialog,
           MAX_OT_object_properties_dialog, MAX_OT_scene_file_dialog)
_installed = False


def install():
    global _installed
    if not _installed:
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.app.handlers.load_pre.append(cancel_transactions)
        bpy.app.handlers.save_pre.append(cancel_transactions)
        _installed = True


def uninstall():
    global _installed
    cancel_transactions()
    if _installed:
        bpy.app.handlers.load_pre.remove(cancel_transactions)
        bpy.app.handlers.save_pre.remove(cancel_transactions)
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        _installed = False
