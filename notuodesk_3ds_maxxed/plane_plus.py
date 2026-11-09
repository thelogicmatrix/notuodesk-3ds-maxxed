"""JokerMartini-style parametric image planes."""

import os

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from mathutils import Vector

PIVOTS = (
    ("LEFT", "Left", "Bottom left"), ("CENTER", "Center", "Center of plane"),
    ("RIGHT", "Right", "Bottom right"), ("TOP_LEFT", "Top Left", ""),
    ("TOP", "Top", "Top center"), ("TOP_RIGHT", "Top Right", ""),
    ("LEFT_EDGE", "Left Edge", "Left center"), ("RIGHT_EDGE", "Right Edge", "Right center"),
    ("BOTTOM", "Bottom", "Bottom center"),
)
PIVOT_UV = {"LEFT": (0, 0), "CENTER": (.5, .5), "RIGHT": (1, 0),
            "TOP_LEFT": (0, 1), "TOP": (.5, 1), "TOP_RIGHT": (1, 1),
            "LEFT_EDGE": (0, .5), "RIGHT_EDGE": (1, .5), "BOTTOM": (.5, 0)}
_guard = False
_draw_handle = None
_pick_keymaps = []
_shader = None


def build_bmesh(p):
    bm = bmesh.new()
    px, py = PIVOT_UV[p.pivot]
    uv = bm.loops.layers.uv.new("UVMap")
    coords = ((0, 0), (1, 0), (1, 1), (0, 1))
    verts = []
    for u, v in coords:
        x, y = (u - px) * p.width, (v - py) * p.length
        verts.append(bm.verts.new((x, 0, y) if p.orientation == "VERTICAL" else (x, y, 0)))
    face = bm.faces.new(verts)
    for loop, co in zip(face.loops, coords):
        loop[uv].uv = co
    bm.normal_update()
    return bm


def _material(ob):
    p = ob.max_plane_plus
    mat = p.material
    if mat is None:
        mat = bpy.data.materials.new(ob.name + " Image")
        mat.use_nodes = True
        p.material = mat
        nodes = mat.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        output.name = "PlanePlus Output"
        surface = nodes.new("ShaderNodeEmission")
        surface.name = "PlanePlus Surface"
        texture = nodes.new("ShaderNodeTexImage")
        texture.name = "PlanePlus Image"
        opacity = nodes.new("ShaderNodeValue")
        opacity.name = "PlanePlus Opacity"
        alpha = nodes.new("ShaderNodeMath")
        alpha.operation = "MULTIPLY"
        alpha.name = "PlanePlus Alpha"
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links = mat.node_tree.links
        links.new(texture.outputs["Alpha"], alpha.inputs[0])
        links.new(opacity.outputs[0], alpha.inputs[1])
        links.new(alpha.outputs[0], mix.inputs[0])
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(surface.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs["Surface"])
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes["PlanePlus Image"].image = p.image
    color = nodes["PlanePlus Surface"].inputs[0]
    for link in list(color.links):
        links.remove(link)
    alpha = nodes["PlanePlus Alpha"].inputs[0]
    for link in list(alpha.links):
        links.remove(link)
    if p.image and p.enable_image:
        links.new(nodes["PlanePlus Image"].outputs["Color"], color)
        links.new(nodes["PlanePlus Image"].outputs["Alpha"], alpha)
    else:
        color.default_value = ob.color
        alpha.default_value = 1
    nodes["PlanePlus Opacity"].outputs[0].default_value = p.opacity / 100
    mesh = ob.max_frozen_mesh or ob.data
    if not mesh.materials:
        mesh.materials.append(mat)
    else:
        mesh.materials[0] = mat


def _update(self, context, axis=None):
    global _guard
    ob = self.id_data
    if _guard or ob.max_prim.kind != "PLANEPLUS":
        return
    _guard = True
    try:
        if self.uniform:
            if axis == "LENGTH":
                self.width = self.length * self.aspect
            else:
                self.length = self.width / self.aspect
        from . import prims
        prims.rebuild(ob)
        if ob.max_frozen_mesh:
            bm = build_bmesh(self)
            bm.to_mesh(ob.max_frozen_mesh)
            bm.free()
        _material(ob)
        # Workbench cannot show per-material opacity or unlit textures. Draw the
        # image over a selectable wire plane in Solid, with normal depth testing.
        if ob.max_frozen and ob.max_show_frozen_gray:
            from . import freezing
            freezing._gray_update(ob, context)
        else:
            ob.display_type = "WIRE" if self.image and self.enable_image else "TEXTURED"
    finally:
        _guard = False
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _width(self, context):
    _update(self, context, "WIDTH")


def _length(self, context):
    _update(self, context, "LENGTH")


class MaxPlanePlusParams(bpy.types.PropertyGroup):
    width: FloatProperty(name="Width", default=1, min=.0001, unit="LENGTH", update=_width)
    length: FloatProperty(name="Length", default=1, min=.0001, unit="LENGTH", update=_length)
    uniform: BoolProperty(name="Uniform", default=True, update=_width)
    aspect: FloatProperty(default=1, min=.000001)
    pivot: EnumProperty(name="Pivot", items=PIVOTS, default="LEFT", update=_width)
    orientation: EnumProperty(name="Orientation", items=[("HORIZONTAL", "Horizontal", "XY plane"),
                                                       ("VERTICAL", "Vertical", "XZ plane")],
                              default="HORIZONTAL", update=_width)
    image: PointerProperty(type=bpy.types.Image)
    material: PointerProperty(type=bpy.types.Material)
    enable_image: BoolProperty(name="Enable Image", default=True, update=_width)
    opacity: FloatProperty(name="Opacity", default=100, min=0, max=100, update=_width)


def kind_changed(ob):
    if ob.max_prim.kind != "PLANEPLUS" and hasattr(ob, "max_plane_plus") and ob.max_plane_plus.material:
        ob.display_type = "TEXTURED"
        if "max_frozen_display" in ob:
            ob["max_frozen_display"] = "TEXTURED"


def new_plane(context):
    from .create import new_object
    from .operators import max_name
    from .prims import set_params
    ob = new_object(context, max_name("PlanePlus"), bpy.data.meshes.new("PlanePlus"))
    ob.max_show_frozen_gray = False
    set_params(ob, "PLANEPLUS")
    _update(ob.max_plane_plus, context)
    return ob


class MAX_OT_plane_plus_image(bpy.types.Operator):
    """Choose an image and match the plane's aspect ratio"""
    bl_idname = "max.plane_plus_image"
    bl_label = "Select Image"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.bmp;*.exr;*.hdr;*.webp", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.max_prim.kind == "PLANEPLUS"

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            image = bpy.data.images.load(bpy.path.abspath(self.filepath), check_existing=True)
            if min(image.size) < 1:
                raise ValueError("Image has no pixels")
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, f"Cannot load image: {exc}")
            return {"CANCELLED"}
        p = context.active_object.max_plane_plus
        p.image = image
        p.aspect = image.size[0] / image.size[1]
        # Loading always fits the image, even when Uniform is currently off.
        global _guard
        _guard = True
        try:
            p.length = p.width / p.aspect
        finally:
            _guard = False
        _update(p, context)
        return {"FINISHED"}


class MAX_OT_plane_plus(bpy.types.Operator):
    """Click-drag a PlanePlus. Ctrl: vertical, Shift: square, Alt: origin. Right-click stops"""
    bl_idname = "max.plane_plus"
    bl_label = "PlanePlus"
    bl_options = {"REGISTER", "UNDO"}
    active = False

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        new_plane(context)
        return {"FINISHED"}

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        self.obj = None
        MAX_OT_plane_plus.active = True
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("PlanePlus: click-drag. Ctrl: vertical. Shift: square. Alt: [0,0,0]. Right-click: finish")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from .create import construction_frame, ray_plane, region_under_mouse
        if event.type in {"RIGHTMOUSE", "ESC"}:
            if self.obj:
                mesh = self.obj.data
                bpy.data.objects.remove(self.obj, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            MAX_OT_plane_plus.active = False
            context.workspace.status_text_set(None)
            return {"FINISHED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and self.obj is None:
            area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
            if not region:
                return {"PASS_THROUGH"}
            self.region = region
            # PlanePlus uses the home grid. Ctrl creates an upright plane.
            self.vertical = event.ctrl
            self.u, self.v, self.normal = construction_frame(region.data)
            co = (event.mouse_x - region.x, event.mouse_y - region.y)
            point = ray_plane(region, region.data, co, Vector((0, 0, 0)), self.normal)
            if point is None:
                return {"RUNNING_MODAL"}
            self.start = point
            self.at_origin = event.alt
            self.obj = new_plane(context)
            self.obj.max_plane_plus.orientation = "VERTICAL" if self.vertical else "HORIZONTAL"
            self.obj.max_plane_plus.uniform = False
            self.obj.location = Vector((0, 0, 0)) if self.at_origin else point
            self.obj.max_plane_plus.width = .0001
            self.obj.max_plane_plus.length = .0001
            return {"RUNNING_MODAL"}
        if self.obj and event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
            r = self.region
            point = ray_plane(r, r.data, (event.mouse_x - r.x, event.mouse_y - r.y), self.start, self.normal)
            if point is not None:
                delta = point - self.start
                du, dv = delta.dot(self.u), delta.dot(self.v)
                width, length = abs(du), abs(dv)
                if event.shift:
                    width = length = max(width, length)
                p = self.obj.max_plane_plus
                p.width, p.length = max(width, .0001), max(length, .0001)
                if not self.at_origin:
                    self.obj.location = self.start + Vector((min(du, 0), 0, min(dv, 0)) if self.vertical
                                                           else (min(du, 0), min(dv, 0), 0))
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                p.aspect = p.width / p.length
                p.uniform = True
                self.obj = None
                bpy.ops.ed.undo_push(message="Create PlanePlus")
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"} if self.obj is None else {"RUNNING_MODAL"}


class MAX_OT_plane_plus_pick(bpy.types.Operator):
    """Select the image face as well as the wire border"""
    bl_idname = "max.plane_plus_pick"
    bl_label = "Select PlanePlus"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        from .create import mouse_ray, region_under_mouse
        area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
        if not region:
            return {"PASS_THROUGH"}
        origin, direction = mouse_ray(region, region.data, (event.mouse_x - region.x, event.mouse_y - region.y))
        hit, _, _, _, ob, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
        if not hit:
            return {"PASS_THROUGH"}
        ob = ob.original
        if ob.hide_select or ob.max_prim.kind != "PLANEPLUS":
            return {"PASS_THROUGH"}
        if not (event.ctrl or event.alt or event.shift):
            for other in context.selected_objects:
                other.select_set(False)
        ob.select_set(False if event.alt else not ob.select_get() if event.shift else True)
        if not event.alt:
            context.view_layer.objects.active = ob
        return {"FINISHED"}


def draw(layout, ob):
    p = ob.max_plane_plus
    layout.use_property_split = False
    layout.use_property_decorate = False
    for prop, label in (("width", "Width:"), ("length", "Length:")):
        row = layout.row(align=True)
        row.label(text=label)
        row.prop(p, prop, text="")
    layout.prop(p, "uniform")
    layout.label(text="Pivot:")
    for key in ("LEFT", "CENTER", "RIGHT"):
        row = layout.row()
        row.emboss = "NONE"
        row.prop_enum(p, "pivot", key, text=dict((k, n) for k, n, _ in PIVOTS)[key],
                      icon="RADIOBUT_ON" if p.pivot == key else "RADIOBUT_OFF")
    row = layout.row(align=True)
    row.label(text="More:")
    row.prop(p, "pivot", text="")
    box = layout.box()
    box.label(text="Image:")
    box.operator("max.plane_plus_image", text=os.path.basename(p.image.filepath) if p.image else "Select Image...")
    box.prop(p, "enable_image")
    row = layout.row(align=True)
    row.label(text="Opacity:")
    row.prop(p, "opacity", text="")
    row = layout.row(align=True)
    row.emboss = "NONE"
    for key, label in (("HORIZONTAL", "Horizontal"), ("VERTICAL", "Vertical")):
        row.prop_enum(p, "orientation", key, text=label,
                      icon="RADIOBUT_ON" if p.orientation == key else "RADIOBUT_OFF")
    layout.prop(ob, "max_show_frozen_gray")
    layout.operator("max.object_cmd", text="Freeze").cmd = "FREEZE"
    layout.label(text="Hold 'Ctrl' for vertical plane.")
    layout.label(text="Hold 'Shift' for square plane.")
    layout.label(text="Hold 'Alt' to create at [0,0,0].")


def _image_shader():
    global _shader
    if _shader is None:
        import gpu
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant("MAT4", "viewProjectionMatrix")
        info.push_constant("FLOAT", "opacity")
        info.sampler(0, "FLOAT_2D", "image")
        info.vertex_in(0, "VEC3", "pos")
        info.vertex_in(1, "VEC2", "texCoord")
        interface = gpu.types.GPUStageInterfaceInfo("plane_plus_interface")
        interface.smooth("VEC2", "uv")
        info.vertex_out(interface)
        info.fragment_out(0, "VEC4", "fragColor")
        info.vertex_source("void main() { uv = texCoord; gl_Position = viewProjectionMatrix * vec4(pos, 1.0); }")
        # Reference images bypass scene lights and view transforms.
        info.fragment_source('''void main() {
            vec4 texel = texture(image, uv);
            fragColor = vec4(texel.rgb, texel.a * opacity);
        }''')
        _shader = gpu.shader.create_from_info(info)
    return _shader


def _draw_images():
    context = bpy.context
    if not context.space_data or context.space_data.type != "VIEW_3D" or context.space_data.shading.type == "WIREFRAME":
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = _image_shader()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.depth_mask_set(False)
    try:
        objects = sorted(context.visible_objects,
                         key=lambda ob: (context.region_data.view_matrix @ ob.matrix_world.translation).z)
        for ob in objects:
            if ob.type != "MESH" or ob.max_prim.kind != "PLANEPLUS":
                continue
            p = ob.max_plane_plus
            if not p.image or not p.enable_image or (ob.max_frozen and ob.max_show_frozen_gray):
                continue
            if len(ob.data.vertices) != 4:
                continue
            coords = [ob.matrix_world @ v.co for v in ob.data.vertices]
            batch = batch_for_shader(shader, "TRIS", {"pos": coords, "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))},
                                     indices=((0, 1, 2), (0, 2, 3)))
            shader.bind()
            shader.uniform_sampler("image", gpu.texture.from_image(p.image))
            shader.uniform_float("viewProjectionMatrix", context.region_data.perspective_matrix)
            shader.uniform_float("opacity", p.opacity / 100)
            batch.draw(shader)
    finally:
        gpu.state.depth_mask_set(True)
        gpu.state.depth_test_set("NONE")
        gpu.state.blend_set("NONE")


classes = (MaxPlanePlusParams, MAX_OT_plane_plus_image, MAX_OT_plane_plus, MAX_OT_plane_plus_pick)


@persistent
def _restore_draw_state(_dummy=None):
    for ob in bpy.data.objects:
        if ob.max_prim.kind == "PLANEPLUS" and not (ob.max_frozen and ob.max_show_frozen_gray):
            p = ob.max_plane_plus
            ob.display_type = "WIRE" if p.image and p.enable_image else "TEXTURED"


def register_props():
    global _draw_handle
    bpy.types.Object.max_plane_plus = PointerProperty(type=MaxPlanePlusParams)
    bpy.app.timers.register(_restore_draw_state, first_interval=0.1)
    bpy.app.handlers.load_post.append(_restore_draw_state)
    if not bpy.app.background:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_images, (), "WINDOW", "POST_PIXEL")
        kc = bpy.context.window_manager.keyconfigs.addon
        if kc:
            km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
            for modifiers in ({}, {"ctrl": True}, {"alt": True}, {"shift": True}):
                item = km.keymap_items.new("max.plane_plus_pick", "LEFTMOUSE", "CLICK", head=True, **modifiers)
                _pick_keymaps.append((km, item))


def unregister_props():
    global _draw_handle, _shader
    if _draw_handle:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
    for km, item in _pick_keymaps:
        km.keymap_items.remove(item)
    _pick_keymaps.clear()
    _shader = None
    if bpy.app.timers.is_registered(_restore_draw_state):
        bpy.app.timers.unregister(_restore_draw_state)
    bpy.app.handlers.load_post.remove(_restore_draw_state)
    for ob in bpy.data.objects:
        if ob.max_prim.kind == "PLANEPLUS":
            ob.display_type = "TEXTURED"
    del bpy.types.Object.max_plane_plus
