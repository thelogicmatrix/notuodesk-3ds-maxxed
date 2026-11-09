"""3ds Max FBX export, with shared System Units and Z-up coordinates."""

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

from .max_import import UNITS, UNIT_SCALE

UNIT_ITEMS = [(k, n, d) for k, n, d, _ in UNITS]


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
        ("KEEP", "Keep Editable", "Export the last Catmull-Clark modifier as FBX subdivision attributes")),
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
            lay.label(text="Last Catmull-Clark modifier only", icon="INFO")

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
        try:
            # Native FBX writes System Units into UnitScaleFactor, separately from geometry.
            scene_units.system = "METRIC"
            scene_units.scale_length = UNIT_SCALE[units]
            settings["global_scale"] = meters / UNIT_SCALE[units]
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
