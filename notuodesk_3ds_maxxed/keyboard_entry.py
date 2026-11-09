"""Keyboard Entry and Creation Method for parametric primitives."""

import bpy
from bpy.props import CollectionProperty, EnumProperty, FloatProperty, StringProperty
from mathutils import Matrix, Vector

from . import prims

# Autodesk 3ds Max 2026 help, Creating Primitives from the Keyboard:
# https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Modeling/files/GUID-97C903B3-A972-45BA-A6E4-1DE9A6343BAF.htm
# Extended primitives can add field and method rows here.
FIELDS = {
    "BOX": (("length", "Length"), ("width", "Width"), ("height", "Height")),
    "CONE": (("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height")),
    "SPHERE": (("radius1", "Radius"),),
    "GEOSPHERE": (("radius1", "Radius"),),
    "CYLINDER": (("radius1", "Radius"), ("height", "Height")),
    "TUBE": (("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height")),
    "TORUS": (("radius1", "Radius 1"), ("radius2", "Radius 2")),
    "PYRAMID": (("width", "Width"), ("length", "Depth"), ("height", "Height")),
    "PLANE": (("length", "Length"), ("width", "Width")),
}

METHODS = {
    "BOX": (("CUBE", "Cube"), ("BOX", "Box")),
    "CONE": (("EDGE", "Edge"), ("CENTER", "Center")),
    "SPHERE": (("EDGE", "Edge"), ("CENTER", "Center")),
    "GEOSPHERE": (("DIAMETER", "Diameter"), ("CENTER", "Center")),
    "CYLINDER": (("EDGE", "Edge"), ("CENTER", "Center")),
    "TUBE": (("EDGE", "Edge"), ("CENTER", "Center")),
    "TORUS": (("EDGE", "Edge"), ("CENTER", "Center")),
    "PYRAMID": (("BASE_APEX", "Base/Apex"), ("CENTER", "Center")),
    "PLANE": (("RECTANGLE", "Rectangle"), ("SQUARE", "Square")),
}

DEFAULT_METHODS = {k: "CENTER" for k in METHODS}
DEFAULT_METHODS.update(BOX="BOX", PYRAMID="BASE_APEX", PLANE="RECTANGLE")


class MaxKeyboardValues(bpy.types.PropertyGroup):
    x: FloatProperty(name="X", unit="LENGTH", precision=1)
    y: FloatProperty(name="Y", unit="LENGTH", precision=1)
    z: FloatProperty(name="Z", unit="LENGTH", precision=1)
    length: FloatProperty(name="Length", default=0.0, min=0.0, unit="LENGTH", precision=1)
    width: FloatProperty(name="Width", default=0.0, min=0.0, unit="LENGTH", precision=1)
    height: FloatProperty(name="Height", default=0.0, unit="LENGTH", precision=1)
    radius1: FloatProperty(name="Radius 1", default=0.0, min=0.0, unit="LENGTH", precision=1)
    radius2: FloatProperty(name="Radius 2", default=0.0, min=0.0, unit="LENGTH", precision=1)
    method: EnumProperty(items=[
        ("CENTER", "Center", "Drag from the center"),
        ("EDGE", "Edge", "Drag the diameter"),
        ("DIAMETER", "Diameter", "Drag the diameter"),
        ("BOX", "Box", "Drag opposite base corners, then set height"),
        ("CUBE", "Cube", "Drag from the center to set equal dimensions"),
        ("BASE_APEX", "Base/Apex", "Drag opposite base corners, then set height"),
        ("RECTANGLE", "Rectangle", "Drag opposite corners"),
        ("SQUARE", "Square", "Drag opposite corners with equal sides"),
    ])


def settings(context, kind):
    """Get a type's independent, scene-persistent creation values."""
    entries = context.scene.max_keyboard_entries
    values = entries.get(kind)
    if values is None:
        values = entries.add()
        values.name = kind
        values.method = DEFAULT_METHODS.get(kind, "CENTER")
    return values


def remember_kind(context, kind):
    settings(context, kind)
    context.scene.max_keyboard_kind = kind


def current_kind(context):
    from .create import MAX_OT_create
    return MAX_OT_create.active_kind or context.scene.max_keyboard_kind


def visible(context):
    wm = context.window_manager
    kind = current_kind(context)
    return (wm.max_create_cat == "GEOMETRY" and wm.max_create_sub == "STANDARD"
            and kind in FIELDS and context.scene.max_keyboard_entries.get(kind) is not None)


def method(context, kind):
    values = context.scene.max_keyboard_entries.get(kind)
    return values.method if values else DEFAULT_METHODS.get(kind, "CENTER")


def has_height(kind, creation_method):
    return prims.PRIMITIVES[kind][3] and creation_method != "CUBE"


def base_size(kind, creation_method, start, point, u, v, height):
    """Return grid-space placement and unit-mesh scale for a mouse drag."""
    _, _, style, has_h = prims.PRIMITIVES[kind]
    h = max(abs(height), 1e-4) if has_h else 1.0
    delta = point - start
    if style == "RECT":
        du, dv = delta.dot(u), delta.dot(v)
        center = start + (u * du + v * dv) * 0.5
        if creation_method == "CUBE":
            side = max(abs(du), abs(dv)) * 2
            return start, Vector((side, side, side))
        if creation_method == "CENTER":
            return start, Vector((max(abs(du) * 2, 1e-4), max(abs(dv) * 2, 1e-4), h))
        if creation_method == "SQUARE":
            side = max(abs(du), abs(dv))
            du = -side if du < 0 else side
            dv = -side if dv < 0 else side
            center = start + (u * du + v * dv) * 0.5
        return center, Vector((max(abs(du), 1e-4), max(abs(dv), 1e-4), h))
    radius = delta.length
    center = start
    if creation_method in {"EDGE", "DIAMETER"}:
        radius *= 0.5
        center = (start + point) * 0.5
    radius = max(radius, 1e-4)
    return center, Vector((radius, radius, h if has_h else radius))


def active_frame(context):
    from .create import construction_frame
    rv3d = context.region_data
    if rv3d is None and context.area and context.area.type == "VIEW_3D":
        rv3d = context.space_data.region_3d
    if rv3d is None:
        return Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    return construction_frame(rv3d)


class MAX_OT_keyboard_create(bpy.types.Operator):
    """Create a primitive from its Keyboard Entry values on the active grid"""
    bl_idname = "max.keyboard_create"
    bl_label = "Create"
    bl_options = {"REGISTER", "UNDO"}

    kind: StringProperty(default="")

    def execute(self, context):
        from .create import new_object
        from .operators import max_name
        kind = self.kind or current_kind(context)
        if kind not in FIELDS or kind not in prims.PRIMITIVES:
            self.report({"WARNING"}, "Pick a primitive type first")
            return {"CANCELLED"}
        values = settings(context, kind)
        params = {prop: getattr(values, prop) for prop, label in FIELDS[kind]}
        if any(params.get(p, 1.0) <= 0 for p in ("length", "width")) or (
                "radius1" in params and max(params.get("radius1", 0), params.get("radius2", 0)) <= 0):
            self.report({"WARNING"}, "Enter a non-zero size before creating")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
            context.window_manager.max_sublevel = 0
        remember_kind(context, kind)
        label = prims.PRIMITIVES[kind][0]
        ob = new_object(context, max_name(label), bpy.data.meshes.new(label))
        prims.set_params(ob, kind, **params)
        u, v, n = active_frame(context)
        position = u * values.x + v * values.y + n * values.z
        ob.matrix_world = Matrix.Translation(position) @ Matrix((u, v, n)).transposed().to_4x4()
        return {"FINISHED"}


def draw_method(layout, context):
    kind = current_kind(context)
    values = context.scene.max_keyboard_entries[kind]
    row = layout.row(align=True)
    row.alignment = "CENTER"
    row.emboss = "NONE"
    for key, label in METHODS.get(kind, ()):
        icon = "RADIOBUT_ON" if values.method == key else "RADIOBUT_OFF"
        row.prop_enum(values, "method", key, text=label, icon=icon)


def draw_keyboard(layout, context):
    kind = current_kind(context)
    values = context.scene.max_keyboard_entries[kind]
    col = layout.column(align=True)
    col.use_property_split = False
    col.use_property_decorate = False
    for prop, label in (("x", "X"), ("y", "Y"), ("z", "Z")) + FIELDS[kind]:
        if prop == FIELDS[kind][0][0]:
            col.separator(factor=0.4)
        row = col.row(align=True)
        row.scale_y = 0.85
        split = row.split(factor=0.48, align=True)
        caption = split.row(align=True)
        caption.alignment = "RIGHT"
        caption.label(text=label + ":")
        field = split.row(align=True)
        field.alignment = "LEFT"
        field.ui_units_x = 5.0
        field.prop(values, prop, text="")
    layout.separator(factor=0.4)
    layout.operator("max.keyboard_create", text="Create").kind = kind


classes = (MaxKeyboardValues, MAX_OT_keyboard_create)


def register_props():
    bpy.types.Scene.max_keyboard_entries = CollectionProperty(type=MaxKeyboardValues)
    bpy.types.Scene.max_keyboard_kind = StringProperty(default="")


def unregister_props():
    del bpy.types.Scene.max_keyboard_kind
    del bpy.types.Scene.max_keyboard_entries
