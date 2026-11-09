"""3ds Max FBX export, with shared System Units and Z-up coordinates."""

import os
from contextlib import contextmanager

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix

from .max_import import UNITS, UNIT_SCALE

UNIT_ITEMS = [(k, n, d) for k, n, d, _ in UNITS]


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


@contextmanager
def _source_state(context):
    """Restore native FBX's temporary rig/frame changes even if it raises."""
    poses = [(arm, arm.pose_position) for arm in bpy.data.armatures]
    frame, subframe = context.scene.frame_current, context.scene.frame_subframe
    active = context.view_layer.objects.active
    mode = active.mode if active else "OBJECT"
    selection = [(obj, obj.select_get()) for obj in context.view_layer.objects]
    try:
        yield
    finally:
        for arm, position in poses:
            arm.pose_position = position
        if (context.scene.frame_current, context.scene.frame_subframe) != (frame, subframe):
            context.scene.frame_set(frame, subframe=subframe)
        for obj, selected in selection:
            if obj.select_get() != selected:
                obj.select_set(selected)
        context.view_layer.objects.active = active
        if active and active.mode != mode:
            bpy.ops.object.mode_set(mode=mode)
        context.view_layer.update()


@contextmanager
def _baked_meshes(context, objects, roots):
    """Freeze the evaluated pose before native FBX prepares rest-pose skinning."""
    meshes, saved = [], []
    world = {}

    def fbx_world(obj):
        if obj not in world:
            parent = obj.parent if obj.parent in roots and obj.parent_type == "OBJECT" else None
            local = obj.matrix_local if parent else obj.matrix_world
            transform = Matrix.LocRotScale(*local.decompose())
            world[obj] = fbx_world(parent) @ transform if parent else transform
        return world[obj]

    try:
        graph = context.evaluated_depsgraph_get()
        # Evaluate every source before swapping any data, including dependency targets.
        for obj in objects:
            if obj.type != "MESH":
                continue
            evaluated = obj.evaluated_get(graph)
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
            meshes.append((obj, mesh))
            # FBX decomposes object transforms to TRS. Put any lost shear into vertices.
            correction = fbx_world(obj).inverted_safe() @ evaluated.matrix_world
            if max(abs(correction[i][j] - (i == j)) for i in range(4) for j in range(4)) > 1e-6:
                normals = [n.vector.copy() for n in mesh.corner_normals]
                mesh.transform(correction)
                normal_matrix = correction.to_3x3().inverted_safe().transposed()
                mesh.normals_split_custom_set([(normal_matrix @ n).normalized() for n in normals])
        for obj, mesh in meshes:
            modifiers = [(mod, mod.show_viewport, mod.show_render,
                          mod.object if mod.type == "ARMATURE" else None) for mod in obj.modifiers]
            saved.append((obj, obj.data, modifiers))
            obj.data = mesh
            for mod, _viewport, _render, _rig in modifiers:
                mod.show_viewport = mod.show_render = False
                if mod.type == "ARMATURE":
                    mod.object = None
        context.view_layer.update()
        yield
    finally:
        for obj, data, modifiers in reversed(saved):
            obj.data = data
            for mod, viewport, render, rig in modifiers:
                mod.show_viewport, mod.show_render = viewport, render
                if mod.type == "ARMATURE":
                    mod.object = rig
        for _obj, mesh in meshes:
            bpy.data.meshes.remove(mesh)
        context.view_layer.update()


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


def fbx_settings(selected=False, embed=False, animation=True):
    smoothing = bpy.ops.export_scene.fbx.get_rna_type().properties["mesh_smooth_type"].enum_items.keys()
    return dict(use_selection=selected, object_types={"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"},
                axis_forward="Y", axis_up="Z", use_space_transform=True, bake_space_transform=False,
                apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                mesh_smooth_type="SMOOTH_GROUP" if "SMOOTH_GROUP" in smoothing else "FACE",
                use_mesh_modifiers=True, use_subsurf=False, use_mesh_edges=True, use_custom_props=True,
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
    embed_media: BoolProperty(name="Embed Media", default=False,
                             description="Embed image files used by supported FBX materials")
    animation: BoolProperty(name="Animation", default=True,
                            description="Bake transform animation over the scene frame range. Mesh geometry stays at the current frame")

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        for prop in ("units", "embed_media", "animation"):
            lay.prop(self, prop)

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
        units = self.units if self.properties.is_property_set("units") else context.scene.max_system_units
        scene_units = context.scene.unit_settings
        old_system, old_scale = scene_units.system, scene_units.scale_length
        meters = old_scale if old_system != "NONE" else 1.0
        settings = fbx_settings(selected, self.embed_media, self.animation)
        roots = tuple(context.selected_objects if selected else context.view_layer.objects)
        objects = _export_objects(context, roots)
        try:
            # Native FBX writes System Units into UnitScaleFactor, separately from geometry.
            scene_units.system = "METRIC"
            scene_units.scale_length = UNIT_SCALE[units]
            settings["global_scale"] = meters / UNIT_SCALE[units]
            with _source_state(context):
                if context.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                with _export_evaluation(context, objects), _baked_meshes(context, objects, roots):
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
