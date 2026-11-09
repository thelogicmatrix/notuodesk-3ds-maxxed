"""Max freeze state, including textured reference objects."""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty, StringProperty
from bpy_extras import view3d_utils


def _restore_look(ob):
    source = ob.max_frozen_mesh
    if source:
        temporary = ob.data
        materials = list(temporary.materials)
        ob.data = source
        ob.max_frozen_mesh = None
        for slot, saved in zip(ob.material_slots, ob.max_frozen_slots):
            slot.link = saved.link
            if saved.link == "OBJECT":
                slot.material = saved.material
        ob.max_frozen_slots.clear()
        if temporary.users == 0:
            bpy.data.meshes.remove(temporary)
        for material in materials:
            if material and material.get("max_frozen_display_material") and material.users == 0:
                bpy.data.materials.remove(material)
    if "max_frozen_color" in ob:
        ob.color = ob["max_frozen_color"]
    if "max_frozen_display" in ob:
        ob.display_type = ob["max_frozen_display"]
    if ob.max_prim.kind == "PLANEPLUS":
        p = ob.max_plane_plus
        ob.display_type = "WIRE" if p.image and p.enable_image else "TEXTURED"


def _gray_update(ob, context):
    if not ob.max_frozen:
        return
    _restore_look(ob)
    if ob.max_show_frozen_gray:
        ob.color = (0.55, 0.55, 0.55, 1.0)
        ob.display_type = "SOLID"
        if ob.type == "MESH":
            # A private display mesh leaves shared meshes and materials intact.
            source = ob.data
            original_materials = [slot.material for slot in ob.material_slots] or [None]
            ob.data = source.copy()
            ob.max_frozen_mesh = source
            for slot in ob.material_slots:
                saved = ob.max_frozen_slots.add()
                saved.link, saved.material = slot.link, slot.material
                slot.link = "DATA"
            ob.data.materials.clear()
            for material in original_materials:
                # Keep render shaders intact. Only Workbench's viewport color
                # changes, and SOLID display suppresses its texture display.
                gray = material.copy() if material else bpy.data.materials.new("Frozen Display")
                if not gray.use_nodes:
                    original_color = tuple(gray.diffuse_color)
                    gray.use_nodes = True
                    gray.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = original_color
                gray.diffuse_color = (0.55, 0.55, 0.55, 1.0)
                gray["max_frozen_display_material"] = True
                ob.data.materials.append(gray)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _property_update(self, context):
    _gray_update(self, context)


def freeze(ob, scene):
    if ob.max_frozen:
        return
    legacy = ob.hide_select and "max_frozen_color" in ob
    if "max_frozen_color" not in ob:
        ob["max_frozen_color"] = list(ob.color)
    ob["max_frozen_display"] = ob.display_type
    ob["max_frozen_hide_select"] = False if legacy else ob.hide_select
    ob.max_frozen = True
    ob.select_set(False)
    ob.hide_select = True
    # Blender otherwise permits snapping to objects locked against selection.
    if hasattr(scene.tool_settings, "use_snap_selectable"):
        if "max_freeze_snap_selectable" not in scene:
            scene["max_freeze_snap_selectable"] = scene.tool_settings.use_snap_selectable
        scene.tool_settings.use_snap_selectable = True
    _gray_update(ob, bpy.context)


def unfreeze(ob, scene):
    if not ob.max_frozen:
        # Objects frozen by earlier add-on versions have only this color backup.
        if ob.hide_select and "max_frozen_color" in ob:
            ob.color = ob["max_frozen_color"]
            del ob["max_frozen_color"]
            ob.hide_select = False
        return
    _restore_look(ob)
    ob.hide_select = ob.get("max_frozen_hide_select", False)
    ob.max_frozen = False
    for key in ("max_frozen_color", "max_frozen_display", "max_frozen_hide_select"):
        if key in ob:
            del ob[key]
    if not any(o.max_frozen for o in scene.objects) and "max_freeze_snap_selectable" in scene:
        scene.tool_settings.use_snap_selectable = scene["max_freeze_snap_selectable"]
        del scene["max_freeze_snap_selectable"]


def _frozen_items(self, context):
    items = [(o.name, o.name, "") for o in sorted(context.scene.objects, key=lambda o: o.name.lower())
             if o.max_frozen or (o.hide_select and "max_frozen_color" in o)]
    _frozen_items.cache = items
    return items


class MaxFrozenSlot(bpy.types.PropertyGroup):
    link: StringProperty()
    material: PointerProperty(type=bpy.types.Material)


class MAX_OT_unfreeze_by_name(bpy.types.Operator):
    """Choose a frozen object to unfreeze"""
    bl_idname = "max.unfreeze_by_name"
    bl_label = "Unfreeze by Name"
    bl_property = "obj"
    bl_options = {"REGISTER", "UNDO"}

    obj: EnumProperty(items=_frozen_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        ob = context.scene.objects.get(self.obj)
        if ob is None:
            return {"CANCELLED"}
        unfreeze(ob, context.scene)
        return {"FINISHED"}


def _hit_frozen(context, region, co):
    origin = view3d_utils.region_2d_to_origin_3d(region, region.data, co)
    direction = view3d_utils.region_2d_to_vector_3d(region, region.data, co)
    hit, _, _, _, ob, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
    if hit and (ob.original.max_frozen or "max_frozen_color" in ob.original):
        return ob.original
    # Lights, cameras, helpers and wire-only objects have no raycast surface.
    # Pick near their origin without changing selection or selection locks.
    nearest, distance = None, (12 * context.preferences.system.ui_scale) ** 2
    for ob in context.visible_objects:
        if not (ob.max_frozen or "max_frozen_color" in ob):
            continue
        if ob.type == "MESH" and ob.data.polygons:
            continue
        point = view3d_utils.location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
        if point is None:
            continue
        d = (point.x - co[0]) ** 2 + (point.y - co[1]) ** 2
        if d < distance:
            nearest, distance = ob, d
    return nearest


class MAX_OT_unfreeze_by_hit(bpy.types.Operator):
    """Click a frozen object to unfreeze it. Right-click to leave"""
    bl_idname = "max.unfreeze_by_hit"
    bl_label = "Unfreeze by Hit"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Unfreeze by Hit: click an object. Right-click to finish")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            context.workspace.status_text_set(None)
            return {"FINISHED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            from .create import region_under_mouse
            area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
            if region:
                co = (event.mouse_x - region.x, event.mouse_y - region.y)
                ob = _hit_frozen(context, region, co)
                if ob:
                    unfreeze(ob, context.scene)
                    bpy.ops.ed.undo_push(message="Unfreeze by Hit")
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE":
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


class MAX_OT_object_properties(bpy.types.Operator):
    """Object display properties"""
    bl_idname = "max.object_properties"
    bl_label = "Object Properties"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.label(text=context.active_object.name)
        self.layout.prop(context.active_object, "max_show_frozen_gray")

    def execute(self, context):
        return {"FINISHED"}


classes = (MaxFrozenSlot, MAX_OT_unfreeze_by_name, MAX_OT_unfreeze_by_hit, MAX_OT_object_properties)


def register_props():
    bpy.types.Object.max_frozen = BoolProperty(default=False)
    bpy.types.Object.max_show_frozen_gray = BoolProperty(name="Show Frozen in Gray", default=True,
                                                       update=_property_update)
    bpy.types.Object.max_frozen_mesh = PointerProperty(type=bpy.types.Mesh)
    bpy.types.Object.max_frozen_slots = CollectionProperty(type=MaxFrozenSlot)


def unregister_props():
    # Restore display copies before removing their persistent state.
    for scene in bpy.data.scenes:
        for ob in scene.objects:
            unfreeze(ob, scene)
    for name in ("max_frozen", "max_show_frozen_gray", "max_frozen_mesh", "max_frozen_slots"):
        delattr(bpy.types.Object, name)
