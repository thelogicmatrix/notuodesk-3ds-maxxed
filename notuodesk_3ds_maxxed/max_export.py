"""3ds Max FBX export, with shared System Units and Z-up coordinates."""

import os
from contextlib import contextmanager

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

from .max_import import UNITS, UNIT_SCALE

UNIT_ITEMS = [(k, n, d) for k, n, d, _ in UNITS]
MESH_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def _export_objects(context, roots):
    """Include instance sources even when hiding prevents depsgraph instances."""
    objects = set(roots)
    pending = list(roots)
    while pending:
        obj = pending.pop()
        sources = ()
        if obj.instance_type == "COLLECTION" and obj.instance_collection:
            sources = obj.instance_collection.all_objects
        elif obj.is_instancer:
            sources = obj.children
        for source in sources:
            if source not in objects:
                objects.add(source)
                pending.append(source)
    instancers = {obj for obj in objects if obj.is_instancer}
    if instancers:
        objects.update(instance.instance_object.original
                       for instance in context.evaluated_depsgraph_get().object_instances
                       if instance.is_instance and instance.parent
                       and instance.parent.original in instancers)
    return objects


def _subdivision_export_safe(obj, exported_objects=()):
    """Allow only a control mesh and subdivision settings FBX can reproduce."""
    if obj.type != "MESH" or obj.hide_viewport or obj.hide_render or obj.hide_get():
        return False
    # Instance sources outside the view layer are visible through their instancer.
    if obj.name in bpy.context.view_layer.objects and not obj.visible_get():
        return False
    enabled = [mod for mod in obj.modifiers if mod.show_viewport or mod.show_render]
    # Earlier arbitrary modifiers can create unsupported evaluated crease attributes.
    # Keep the allow-list to one enabled modifier, including only one SUBSURF.
    if len(enabled) != 1 or enabled[0].type != "SUBSURF":
        return False
    sub = enabled[0]
    if not (sub.show_viewport and sub.show_render and sub.subdivision_type == "CATMULL_CLARK"
            and sub.use_limit_surface and sub.quality == 3
            and sub.uv_smooth == "PRESERVE_BOUNDARIES" and sub.boundary_smooth == "ALL"
            and sub.levels == sub.render_levels and not getattr(sub, "use_custom_normals", False)):
        return False
    if obj.animation_data or obj.data.animation_data or obj.data.shape_keys:
        return False
    edge_creases = obj.data.attributes.get("crease_edge")
    vertex_creases = obj.data.attributes.get("crease_vert")
    # FBX carries edge creases, but does not carry vertex creases or use_creases=False.
    if vertex_creases and any(v.value != 0 for v in vertex_creases.data):
        return False
    if not sub.use_creases and edge_creases and any(v.value != 0 for v in edge_creases.data):
        return False
    # Native FBX can share one Geometry record between linked Mesh objects.
    fields = ("subdivision_type", "levels", "render_levels", "show_viewport", "show_render",
              "use_limit_surface", "quality", "uv_smooth", "boundary_smooth", "use_creases")
    signature = tuple(getattr(sub, field) for field in fields)
    for other in exported_objects:
        if other == obj or other.type != "MESH" or other.data != obj.data:
            continue
        other_subs = [mod for mod in other.modifiers if mod.type == "SUBSURF"
                      and (mod.show_viewport or mod.show_render)]
        if len(other_subs) != 1 or tuple(getattr(other_subs[0], field) for field in fields) != signature:
            return False
    return True


@contextmanager
def _export_evaluation(context, objects):
    """Enable exported objects for viewport evaluation, then restore exactly."""
    saved = []

    def enable(owner, prop):
        old = getattr(owner, prop)
        if old:
            saved.append((owner, prop, old))
            setattr(owner, prop, False)

    def enable_layers(layer):
        # Never include excluded objects that native FBX would not export.
        if layer.exclude:
            return
        if any(obj in objects for obj in layer.collection.all_objects):
            enable(layer, "hide_viewport")
            for child in layer.children:
                enable_layers(child)

    hidden = [(obj, obj.hide_get()) for obj in objects if obj.name in context.view_layer.objects]
    try:
        for collection in bpy.data.collections:
            if any(obj in objects for obj in collection.all_objects):
                enable(collection, "hide_viewport")
        enable_layers(context.view_layer.layer_collection)
        for obj in objects:
            enable(obj, "hide_viewport")
        for obj, was_hidden in hidden:
            if was_hidden:
                obj.hide_set(False)
        context.view_layer.update()
        context.evaluated_depsgraph_get().update()
        yield
    finally:
        for obj, was_hidden in hidden:
            if was_hidden:
                obj.hide_set(True)
        for owner, prop, old in reversed(saved):
            setattr(owner, prop, old)
        context.view_layer.update()
        context.evaluated_depsgraph_get().update()


def fbx_settings(selected=False, subdivision="APPLY", embed=False, animation=True):
    smoothing = bpy.ops.export_scene.fbx.get_rna_type().properties["mesh_smooth_type"].enum_items.keys()
    return dict(use_selection=selected, object_types={"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"},
                axis_forward="Y", axis_up="Z", use_space_transform=True, bake_space_transform=False,
                apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                mesh_smooth_type="SMOOTH_GROUP" if "SMOOTH_GROUP" in smoothing else "FACE",
                use_mesh_modifiers=True, use_subsurf=subdivision == "KEEP", use_custom_props=True,
                add_leaf_bones=False, bake_anim=animation, bake_anim_use_all_actions=False,
                bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0.0,
                path_mode="COPY" if embed else "AUTO", embed_textures=embed)


def remember_fbx_units(scene, filepath):
    """FBX stores its own units. Remember recognized units for the next export."""
    from io_scene_fbx import parse_fbx
    try:
        root, _version = parse_fbx.parse(filepath)
        settings = next(e for e in root.elems if e.id == b"GlobalSettings")
        props = next(e for e in settings.elems if e.id == b"Properties70")
        cm = next(p.props[-1] for p in props.elems if p.props[0] == b"UnitScaleFactor")
        scene.max_system_units = next(k for k, _n, _d, scale in UNITS if abs(cm - scale * 100) < 1e-6)
    except (OSError, ValueError, StopIteration):
        pass


class _MaxExportBase(ExportHelper):
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})
    units: EnumProperty(name="System Units", items=UNIT_ITEMS, default="INCHES",
                        description="Match System Unit Setup in 3ds Max. FBX carries this unit scale")
    subdivision: EnumProperty(name="TurboSmooth / Subdivision", items=(
        ("APPLY", "Apply to Mesh", "Export evaluated geometry for a matching shape"),
        ("KEEP", "Keep Editable", "Keep subdivision editable only for meshes passing the FBX settings allow-list. "
         "Any incompatible exported geometry applies subdivision for the entire export")),
        default="APPLY")
    embed_media: BoolProperty(name="Embed Media", default=False,
                             description="Embed image files used by supported FBX materials")
    animation: BoolProperty(name="Animation", default=True, description="Bake the scene frame range")

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        for prop in ("units", "subdivision", "embed_media", "animation"):
            lay.prop(self, prop)
        if self.subdivision == "KEEP":
            lay.label(text="Editable requires supported FBX mesh settings", icon="INFO")
            lay.label(text="Other geometry applies the entire export")

    def invoke(self, context, event):
        if not self.properties.is_property_set("units"):
            self.units = context.scene.max_system_units
        return ExportHelper.invoke(self, context, event)

    def run(self, context, selected):
        if not self.filepath:
            self.report({"ERROR"}, "Choose an FBX filename")
            return {"CANCELLED"}
        if selected and not context.selected_objects:
            self.report({"WARNING"}, "Select objects to export")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        units = self.units if self.properties.is_property_set("units") else context.scene.max_system_units
        scene_units = context.scene.unit_settings
        old_system, old_scale = scene_units.system, scene_units.scale_length
        meters = old_scale if old_system != "NONE" else 1.0
        settings = fbx_settings(selected, self.subdivision, self.embed_media, self.animation)
        roots = tuple(context.selected_objects if selected else context.view_layer.objects)
        objects = _export_objects(context, roots)
        if settings["use_subsurf"]:
            # Cameras, lights and instance carriers have no subdivision geometry.
            unsafe = [obj.name for obj in objects if obj.type in MESH_TYPES
                      and not _subdivision_export_safe(obj, objects)]
            if unsafe:
                # Native FBX has one subdivision switch for the entire export.
                settings["use_subsurf"] = False
                self.report({"WARNING"}, "Applied subdivision for the entire export. "
                            "Objects outside the editable FBX allow-list: " + ", ".join(sorted(unsafe)))
        try:
            # Native FBX writes System Units into UnitScaleFactor, separately from geometry.
            scene_units.system = "METRIC"
            scene_units.scale_length = UNIT_SCALE[units]
            settings["global_scale"] = meters / UNIT_SCALE[units]
            with _export_evaluation(context, objects):
                # Enabling visibility must not expand Export Selected's original scope.
                with context.temp_override(selected_objects=roots):
                    result = bpy.ops.export_scene.fbx(filepath=self.filepath, **settings)
        except (RuntimeError, OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc).splitlines()[-1])
            return {"CANCELLED"}
        finally:
            scene_units.system = old_system
            scene_units.scale_length = old_scale
        if "FINISHED" in result:
            context.scene.max_system_units = units
            self.report({"INFO"}, f"Exported {os.path.basename(self.filepath)} for 3ds Max")
        return result


class MAX_OT_export_max_fbx(Operator, _MaxExportBase):
    """Export the scene for 3ds Max as FBX"""
    bl_idname = "max.export_max_fbx"
    bl_label = "3ds Max Scene (FBX)"

    def execute(self, context):
        return self.run(context, selected=False)


class MAX_OT_export_selected_fbx(Operator, _MaxExportBase):
    """Export selected objects for 3ds Max as FBX"""
    bl_idname = "max.export_selected_fbx"
    bl_label = "Export Selected (3ds Max FBX)"

    def execute(self, context):
        return self.run(context, selected=True)


def menu_export(self, context):
    self.layout.operator("max.export_max_fbx", text="3ds Max Scene (FBX)...")
    self.layout.operator("max.export_selected_fbx", text="Export Selected (3ds Max FBX)...")


def menu_selected(self, context):
    self.layout.separator()
    self.layout.operator_context = "INVOKE_DEFAULT"
    self.layout.operator("max.export_selected_fbx", text="Export Selected (3ds Max FBX)...")


def register_props():
    bpy.types.Scene.max_system_units = EnumProperty(name="System Units", items=UNIT_ITEMS, default="INCHES")


def unregister_props():
    del bpy.types.Scene.max_system_units


def register_menus():
    bpy.types.TOPBAR_MT_file_export.append(menu_export)
    bpy.types.TOPBAR_MT_file.append(menu_selected)
    bpy.types.MAX_MT_customize.append(menu_selected)


def unregister_menus():
    bpy.types.MAX_MT_customize.remove(menu_selected)
    bpy.types.TOPBAR_MT_file.remove(menu_selected)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)


classes = (MAX_OT_export_max_fbx, MAX_OT_export_selected_fbx)
