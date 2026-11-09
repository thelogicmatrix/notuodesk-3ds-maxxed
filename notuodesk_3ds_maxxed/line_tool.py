"""Interactive Line creation and the shared spline rollouts."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import Operator, PropertyGroup
from bpy_extras import view3d_utils
from mathutils import Vector

from . import create
from .operators import max_name


TYPES = [("CORNER", "Corner", "Straight segments"),
         ("SMOOTH", "Smooth", "Automatic smooth handles"),
         ("BEZIER", "Bezier", "Handles follow the drag")]
RENDER_FIELDS = ("renderer", "viewport", "thickness", "sides", "angle", "steps", "optimize", "adaptive")
RENDER_MARKER = "max_spline_render"


def _update_spline(self, context):
    if isinstance(self.id_data, bpy.types.Curve):
        for ob in bpy.data.objects:
            if ob.type == "CURVE" and ob.data == self.id_data:
                apply_settings(ob)


def _update_interpolation(self, context):
    if isinstance(self.id_data, bpy.types.Curve):
        cu = self.id_data
        cu.resolution_u = 64 if self.adaptive else self.steps + 1
        cu.render_resolution_u = cu.resolution_u
        for ob in bpy.data.objects:
            if ob.type == "CURVE" and ob.data == cu:
                for mod in ob.modifiers:
                    if is_render_modifier(mod):
                        mod.node_group.nodes["Optimize"].inputs["Switch"].default_value = self.optimize or self.adaptive


class MAX_PG_spline(PropertyGroup):
    renderer: BoolProperty(name="Enable In Renderer", default=False, update=_update_spline)
    viewport: BoolProperty(name="Enable In Viewport", default=False, update=_update_spline)
    thickness: FloatProperty(name="Radial Thickness", default=1.0, min=0.0,
                             subtype="DISTANCE", update=_update_spline)
    sides: IntProperty(name="Sides", default=12, min=3, max=256, update=_update_spline)
    angle: FloatProperty(name="Angle", default=0.0, subtype="ANGLE", update=_update_spline)
    steps: IntProperty(name="Steps", default=6, min=0, max=100, update=_update_interpolation)
    optimize: BoolProperty(name="Optimize", default=True, update=_update_interpolation)
    adaptive: BoolProperty(name="Adaptive", default=False, update=_update_interpolation,
                          description="Blender approximation: use 64 subdivisions per curved segment")


class MAX_PG_line(PropertyGroup):
    shape_kind: EnumProperty(name="Shape Creator", default="NONE", items=[
        ("NONE", "None", "No shape creator chosen"),
    ] + [(kind, label, "") for kind, label, icon in create.SHAPES])
    initial_type: EnumProperty(name="Initial Type", items=TYPES[:2], default="CORNER")
    drag_type: EnumProperty(name="Drag Type", items=TYPES, default="BEZIER")
    x: FloatProperty(name="X", subtype="DISTANCE")
    y: FloatProperty(name="Y", subtype="DISTANCE")
    z: FloatProperty(name="Z", subtype="DISTANCE")
    pending: PointerProperty(type=bpy.types.Object, options={"SKIP_SAVE"})
    defaults: PointerProperty(type=MAX_PG_spline)


def _render_group():
    group = bpy.data.node_groups.new("Spline Rendering", "GeometryNodeTree")
    group[RENDER_MARKER] = True
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = group.nodes, group.links
    source = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    circle = nodes.new("GeometryNodeCurvePrimitiveCircle")
    circle.name = "Radial"
    rotate = nodes.new("GeometryNodeTransform")
    rotate.name = "Angle"
    links.new(circle.outputs["Curve"], rotate.inputs["Geometry"])
    handles = nodes.new("GeometryNodeCurveSetHandles")
    handles.handle_type = "FREE"
    handles.mode = {"LEFT", "RIGHT"}
    # Freeing vector handles preserves the shape but samples straight spans too.
    links.new(source.outputs["Geometry"], handles.inputs["Curve"])
    optimize = nodes.new("GeometryNodeSwitch")
    optimize.input_type = "GEOMETRY"
    optimize.name = "Optimize"
    links.new(handles.outputs["Curve"], optimize.inputs["False"])
    links.new(source.outputs["Geometry"], optimize.inputs["True"])
    mesh = nodes.new("GeometryNodeCurveToMesh")
    links.new(optimize.outputs["Output"], mesh.inputs["Curve"])
    links.new(rotate.outputs["Geometry"], mesh.inputs["Profile Curve"])
    mesh.inputs["Fill Caps"].default_value = True
    viewport = nodes.new("GeometryNodeIsViewport")
    enable = nodes.new("GeometryNodeSwitch")
    enable.input_type = "BOOLEAN"
    enable.name = "Enabled"
    links.new(viewport.outputs["Is Viewport"], enable.inputs["Switch"])
    geometry = nodes.new("GeometryNodeSwitch")
    geometry.input_type = "GEOMETRY"
    links.new(enable.outputs["Output"], geometry.inputs["Switch"])
    links.new(optimize.outputs["Output"], geometry.inputs["False"])
    links.new(mesh.outputs["Mesh"], geometry.inputs["True"])
    links.new(geometry.outputs["Output"], out.inputs["Geometry"])
    return group


def is_render_modifier(mod):
    return mod.type == "NODES" and mod.node_group is not None and mod.node_group.get(RENDER_MARKER)


def apply_settings(ob):
    """Keep the editable curve and generate its optional radial mesh in nodes."""
    cu, p = ob.data, ob.data.max_spline
    cu.resolution_u = 64 if p.adaptive else p.steps + 1
    cu.render_resolution_u = cu.resolution_u
    mod = next((m for m in ob.modifiers if is_render_modifier(m)), None)
    if mod is None:
        # Merely viewing the rollouts never changes an existing shape.
        mod = ob.modifiers.new("Rendering", "NODES")
        mod.node_group = _render_group()
        mod.show_expanded = False
        ob.modifiers.active = None
    cu.bevel_depth = 0.0
    nodes = mod.node_group.nodes
    nodes["Radial"].inputs["Resolution"].default_value = p.sides
    nodes["Radial"].inputs["Radius"].default_value = p.thickness / 2
    nodes["Angle"].inputs["Rotation"].default_value = (0, 0, p.angle)
    nodes["Enabled"].inputs["False"].default_value = p.renderer
    nodes["Enabled"].inputs["True"].default_value = p.viewport
    nodes["Optimize"].inputs["Switch"].default_value = p.optimize or p.adaptive


def _knots(ob):
    return [(p.co.copy(), p.handle_left_type, p.handle_left.copy(), p.handle_right.copy())
            for p in ob.data.splines[0].bezier_points]


def _rebuild(ob, knots, cyclic=False):
    cu = ob.data
    cu.splines.clear()
    if not knots:
        return
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(knots) - 1)
    for p, (co, kind, left, right) in zip(sp.bezier_points, knots):
        p.co = co
        p.handle_left_type = p.handle_right_type = kind
        if kind == "FREE":
            p.handle_left, p.handle_right = left, right
    sp.use_cyclic_u = cyclic
    cu.update_tag()


def pending(context):
    ob = context.window_manager.max_line.pending
    if ob is not None and ob.type == "CURVE" and ob.get("max_line_pending"):
        return ob
    return None


def add_point(context, co, kind=None):
    settings = context.window_manager.max_line
    ob = pending(context)
    if ob is None:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        defaults = settings.defaults
        previous = context.active_object
        if previous and previous.type == "CURVE" and previous.get("max_line"):
            defaults = previous.data.max_spline
        values = {field: getattr(defaults, field) for field in RENDER_FIELDS}
        cu = bpy.data.curves.new("Line", "CURVE")
        cu.dimensions = "3D"
        ob = create.new_object(context, max_name("Line"), cu)
        ob["max_line"] = True
        ob["max_line_pending"] = True
        # Write defaults without firing an update for every field.
        for field, value in values.items():
            cu.max_spline[field] = value
        apply_settings(ob)
        settings.pending = ob
        knots = []
    else:
        knots = _knots(ob)
    co = ob.matrix_world.inverted() @ Vector(co)
    handle_type = {"CORNER": "VECTOR", "SMOOTH": "AUTO", "BEZIER": "FREE"}[kind or settings.initial_type]
    knots.append((co, handle_type, co.copy(), co.copy()))
    _rebuild(ob, knots)
    return ob


def finish_line(context, close=False):
    from . import snaps
    snaps.clear_preview()
    ob = pending(context)
    if ob is None or len(ob.data.splines[0].bezier_points) < 2:
        return False
    ob.data.splines[0].use_cyclic_u = close
    from .poly_tools import finalize_new_object
    finalize_new_object(context, ob)
    del ob["max_line_pending"]
    context.window_manager.max_line.pending = None
    return True


def discard_line(context):
    from . import snaps
    snaps.clear_preview()
    ob = pending(context)
    if ob is not None:
        cu = ob.data
        groups = [m.node_group for m in ob.modifiers if is_render_modifier(m)]
        context.window_manager.max_line.pending = None
        bpy.data.objects.remove(ob, do_unlink=True)
        if cu.users == 0:
            bpy.data.curves.remove(cu)
        for group in groups:
            if group.users == 0:
                bpy.data.node_groups.remove(group)


class MAX_OT_line_keyboard(Operator):
    """Add typed world coordinates to the current Line"""
    bl_idname = "max.line_keyboard"
    bl_label = "Line Keyboard Entry"
    bl_options = {"UNDO"}

    action: EnumProperty(items=[("ADD", "Add Point", ""), ("CLOSE", "Close", ""), ("FINISH", "Finish", "")])

    def execute(self, context):
        if self.action == "ADD":
            p = context.window_manager.max_line
            add_point(context, (p.x, p.y, p.z))
        elif not finish_line(context, self.action == "CLOSE"):
            self.report({"WARNING"}, "Line needs at least two points")
            return {"CANCELLED"}
        for area in context.screen.areas if context.screen else []:
            area.tag_redraw()
        return {"FINISHED"}


class MAX_OT_line_close(Operator):
    """Close the current spline, or continue drawing"""
    bl_idname = "max.line_close"
    bl_label = "Close spline?"

    answer: BoolProperty(default=True)

    def invoke(self, context, event):
        tool = MAX_OT_line.active
        if tool is None:
            return {"CANCELLED"}
        tool.prompt = True
        return context.window_manager.invoke_props_dialog(self, width=220, title="Close spline?", confirm_text="Yes")

    def draw(self, context):
        self.layout.label(text="Connect the last point to the first?")
        self.layout.label(text="Cancel continues the current spline.")

    def execute(self, context):
        tool = MAX_OT_line.active
        if tool is not None:
            tool.prompt = False
            if self.answer:
                tool.finish_current(context, close=True)
        return {"FINISHED"}

    def cancel(self, context):
        if MAX_OT_line.active is not None:
            MAX_OT_line.active.prompt = False


class MAX_OT_line(Operator):
    """Click or drag vertices. Right-click finishes a line and keeps creating"""
    bl_idname = "max.line"
    bl_label = "Line"

    active = None

    def invoke(self, context, event):
        if MAX_OT_line.active is not None:
            MAX_OT_line.active.stop(context)
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
            context.window_manager.max_sublevel = 0
        create.MAX_OT_create._session += 1
        self.session = create.MAX_OT_create._session
        create.MAX_OT_create.active_kind = ""
        self.dragging = False
        self.prompt = False
        self.preview = None
        self.region = None
        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_preview, (), "WINDOW", "POST_VIEW")
        MAX_OT_line.active = self
        context.window_manager.max_line.shape_kind = "LINE"
        context.window_manager.max_create_cat = "SHAPES"
        context.window_manager.modal_handler_add(self)
        self.status(context)
        return {"RUNNING_MODAL"}

    def status(self, context):
        context.workspace.status_text_set("Line: click / drag points. RMB: finish / exit. Backspace: undo point. Shift: 90 degrees. S: grid snap")
        for area in context.window.screen.areas:
            area.tag_redraw()

    def stop(self, context):
        from . import snaps
        snaps.clear_preview(self.region)
        if not finish_line(context):
            discard_line(context)
        self.preview = None
        if self.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handler, "WINDOW")
            self.handler = None
        if MAX_OT_line.active == self:
            MAX_OT_line.active = None
            context.workspace.status_text_set(None)
        for area in context.window.screen.areas:
            area.tag_redraw()

    def cancel(self, context):
        self.stop(context)

    def finish_current(self, context, close=False):
        from . import snaps
        snaps.clear_preview(self.region)
        if finish_line(context, close):
            bpy.ops.ed.undo_push(message="Create Line")
        else:
            discard_line(context)
        self.dragging = False
        self.preview = None
        self.region = None
        self.status(context)

    def point(self, context, event, constrain=True):
        area, region = create.region_under_mouse(context, event.mouse_x, event.mouse_y)
        if region is None:
            return None
        if self.region is None or pending(context) is None:
            self.u, self.v, self.normal = create.construction_frame(region.data)
        self.region = region
        co = (event.mouse_x - region.x, event.mouse_y - region.y)
        p = create.ray_plane(region, region.data, co, Vector((0, 0, 0)), self.normal)
        if p is None:
            return None
        from . import snaps
        ob = pending(context)
        anchor = ob.matrix_world @ ob.data.splines[0].bezier_points[-1].co if ob else None
        p = snaps.snap_point(context, region, region.data, co, p,
                             (Vector((0, 0, 0)), self.normal),
                             exclude=(ob,) if ob else (), base=anchor)
        if constrain and event.shift and ob is not None:
            anchor = ob.matrix_world @ ob.data.splines[0].bezier_points[-1].co
            d = p - anchor
            u, v = d.dot(self.u), d.dot(self.v)
            p = anchor + (self.u * u if abs(u) >= abs(v) else self.v * v)
        return p

    def near_first(self, context, event):
        ob = pending(context)
        if ob is None or len(ob.data.splines[0].bezier_points) < 2:
            return False
        p = ob.matrix_world @ ob.data.splines[0].bezier_points[0].co
        xy = view3d_utils.location_3d_to_region_2d(self.region, self.region.data, p)
        return xy is not None and (xy - Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))).length < 10

    def draw_preview(self):
        ob = pending(bpy.context)
        if self.preview is None or ob is None or bpy.context.region != self.region:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        last = ob.matrix_world @ ob.data.splines[0].bezier_points[-1].co
        coords = [last, self.preview]
        if self.dragging:
            p = ob.data.splines[0].bezier_points[-1]
            coords = [ob.matrix_world @ p.handle_left, ob.matrix_world @ p.handle_right]
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("color", (1.0, 0.65, 0.15, 1.0))
        batch_for_shader(shader, "LINES", {"pos": coords}).draw(shader)

    def modal(self, context, event):
        if MAX_OT_line.active != self:
            return {"FINISHED"}
        if self.session != create.MAX_OT_create._session:
            self.stop(context)
            return {"FINISHED"}
        if self.prompt:
            return {"PASS_THROUGH"}
        from . import snaps
        if snaps.override_event(self, context, event, dragging=self.dragging):
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            if pending(context) is not None:
                self.finish_current(context)
                return {"RUNNING_MODAL"}
            self.stop(context)
            return {"FINISHED"}
        if event.type == "S" and event.value == "PRESS":
            ts = context.scene.tool_settings
            ts.use_snap = not ts.use_snap
            return {"RUNNING_MODAL"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            ob = pending(context)
            if ob is not None:
                knots = _knots(ob)[:-1]
                if knots:
                    _rebuild(ob, knots)
                else:
                    discard_line(context)
                    self.region = None
                self.dragging = False
                self.status(context)
            return {"RUNNING_MODAL"}
        if event.type in {"MOUSEMOVE", "LEFTMOUSE", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            p = self.point(context, event, constrain=not self.dragging)
            if p is None:
                return {"PASS_THROUGH"}
            self.preview = p
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                if self.near_first(context, event):
                    bpy.ops.max.line_close("INVOKE_DEFAULT")
                    return {"RUNNING_MODAL"}
                add_point(context, p)
                snaps.consume_override(context)
                snaps.clear_preview(self.region)
                self.press = Vector((event.mouse_x, event.mouse_y))
                self.dragging = True
            elif self.dragging and event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                ob = pending(context)
                if ob is None:
                    self.dragging = False
                    return {"RUNNING_MODAL"}
                if (Vector((event.mouse_x, event.mouse_y)) - self.press).length >= 4:
                    knots = _knots(ob)
                    co = knots[-1][0]
                    kind = context.window_manager.max_line.drag_type
                    handle = {"CORNER": "VECTOR", "SMOOTH": "AUTO", "BEZIER": "FREE"}[kind]
                    d = ob.matrix_world.inverted() @ p - co
                    knots[-1] = (co, handle, co - d, co + d)
                    _rebuild(ob, knots)
                if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                    self.dragging = False
            self.status(context)
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


def spline_poll(context):
    ob = context.active_object
    return bool(ob and ob.type == "CURVE") or (context.window_manager.max_cmd_tab == "CREATE"
                                               and context.window_manager.max_create_cat == "SHAPES")


def line_poll(context):
    wm = context.window_manager
    return (wm.max_cmd_tab == "CREATE" and wm.max_create_cat == "SHAPES"
            and wm.max_line.shape_kind == "LINE")


def spline_settings(context):
    ob = context.active_object
    if ob and ob.type == "CURVE":
        return ob.data.max_spline
    return context.window_manager.max_line.defaults


def draw_rendering(layout, context):
    p = spline_settings(context)
    col = layout.column(align=True)
    col.use_property_split = False
    col.use_property_decorate = False
    col.prop(p, "renderer")
    col.prop(p, "viewport")
    col.separator(factor=0.4)
    for field, label in (("thickness", "Radial Thickness"), ("sides", "Sides"), ("angle", "Angle")):
        _spinner(col, p, field, label)


def _spinner(layout, values, prop, label):
    row = layout.row(align=True)
    row.use_property_split = False
    row.use_property_decorate = False
    row.scale_y = 0.85
    split = row.split(factor=0.48, align=True)
    caption = split.row(align=True)
    caption.alignment = "RIGHT"
    caption.label(text=label + ":")
    field = split.row(align=True)
    field.alignment = "LEFT"
    field.ui_units_x = 5.0
    field.prop(values, prop, text="")


def draw_interpolation(layout, context):
    p = spline_settings(context)
    col = layout.column(align=True)
    col.use_property_split = False
    col.use_property_decorate = False
    col.enabled = not p.adaptive
    _spinner(col, p, "steps", "Steps")
    col.prop(p, "optimize")
    layout.prop(p, "adaptive")
    if p.adaptive:
        layout.label(text="Blender: 64 subdivisions", icon="INFO")


def draw_method(layout, context):
    p = context.window_manager.max_line
    for prop, label, types in (("initial_type", "Initial Type", TYPES[:2]),
                               ("drag_type", "Drag Type", TYPES)):
        layout.label(text=label)
        row = layout.row(align=True)
        row.alignment = "CENTER"
        row.emboss = "NONE"
        for key, name, description in types:
            icon = "RADIOBUT_ON" if getattr(p, prop) == key else "RADIOBUT_OFF"
            row.prop_enum(p, prop, key, text=name, icon=icon)


def draw_keyboard(layout, context):
    p = context.window_manager.max_line
    col = layout.column(align=True)
    for field in ("x", "y", "z"):
        _spinner(col, p, field, field.upper())
    layout.separator(factor=0.4)
    layout.operator("max.line_keyboard", text="Add Point").action = "ADD"
    row = layout.row(align=True)
    row.operator("max.line_keyboard", text="Close").action = "CLOSE"
    row.operator("max.line_keyboard", text="Finish").action = "FINISH"


classes = (MAX_PG_spline, MAX_PG_line, MAX_OT_line_keyboard, MAX_OT_line_close, MAX_OT_line)


def register_props():
    bpy.types.WindowManager.max_line = PointerProperty(type=MAX_PG_line)
    bpy.types.Curve.max_spline = PointerProperty(type=MAX_PG_spline)


def unregister_props():
    if MAX_OT_line.active is not None:
        MAX_OT_line.active.stop(bpy.context)
    del bpy.types.Curve.max_spline
    del bpy.types.WindowManager.max_line
