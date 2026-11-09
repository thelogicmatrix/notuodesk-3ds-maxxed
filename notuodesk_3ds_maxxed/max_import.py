"""Open / merge 3ds Max scenes.

.max is a closed Autodesk format. Reading it is done by the open-source
"Import Autodesk MAX (.max)" extension (io_scene_max, GPL, on
extensions.blender.org), which reads meshes, UVs and Standard / Physical /
V-Ray / Corona materials. This module wraps it the 3ds Max way:

* File > Open 3ds Max File  -> opens into a new scene (nothing is overwritten)
* File > Import > Merge 3ds Max File -> adds to the current scene
* fixes scale from the scene's system units (the reader ignores units)
* Max-style object colors, VRayMtl panel on imported materials, zoom extents
* one-click install of the reader if it is missing
* FBX from 3ds Max: full-fidelity route (animation, rigs, splines, cameras, lights)
"""

import os
import re
import struct

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

READER_ID = "io_scene_max"
READER_URL = "https://extensions.blender.org/add-ons/io-scene-max/"

# 3ds Max system units -> meters
UNITS = [
    ("INCHES", "Inches", "3ds Max default in the US (1 unit = 1 inch)", 0.0254),
    ("CENTIMETERS", "Centimeters", "Common metric 3ds Max setup", 0.01),
    ("MILLIMETERS", "Millimeters", "Product / engineering scenes", 0.001),
    ("FEET", "Feet", "", 0.3048),
    ("METERS", "Meters", "", 1.0),
    ("GENERIC", "Generic Units (1:1)", "Keep the raw numbers: 1 Max unit = 1 Blender meter", 1.0),
]
UNIT_SCALE = {k: s for k, _, _, s in UNITS}


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".exr", ".hdr", ".dds", ".psd", ".webp")


def reader_available():
    return "max" in dir(bpy.ops.import_scene)


_PATH_SUFFIX = re.compile(r"^(.*?)_((?:[A-Za-z]:[\\/]|\\\\|/).+)$")


def _split_bitmap_name(name):
    """The reader names materials '<max name>_<bitmap path stem>'. On macOS/Linux the
    'stem' of a Windows path is the whole path. Return (max name, bitmap stem)."""
    m = _PATH_SUFFIX.match(name)
    if not m:
        return name, None
    stem = m.group(2).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return m.group(1), (stem or None)


def _max_display_name(name):
    """'04___Default' -> '04 - Default' (how 3ds Max shows it)."""
    if "___" in name:
        return name.replace("___", " - ")
    return name


def _index_images(folders):
    """{lowercase stem: path} for every image under the given folders."""
    found = {}
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, _dirs, files in os.walk(folder):
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() in IMAGE_EXTS:
                    found.setdefault(stem.lower(), os.path.join(root, f))
    return found


def _material_has_image(mat):
    return mat.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in mat.node_tree.nodes)


def _find_image(index, stem):
    path = index.get(stem.lower())
    if path:
        return path
    # Only accept the known renamed-copy suffix, not unrelated fuzzy matches.
    original = re.sub(r" \(\d+\)$", "", stem.lower())
    return next((path for key, path in sorted(index.items())
                 if re.sub(r" \(\d+\)$", "", key) == original), None)


def _missing_images(mat):
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or not node.image or node.image.packed_file:
                continue
            image = node.image
            if image.filepath and not os.path.isfile(bpy.path.abspath(image.filepath, library=image.library)):
                yield image


def relink_textures(materials, folders):
    """Wire missing bitmaps into the materials' base color. Returns (linked, missing)."""
    from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
    index = _index_images(folders)
    linked, missing = [], []
    for mat in materials:
        for image in _missing_images(mat):
            stem = os.path.splitext(image.filepath.replace("\\", "/").rsplit("/", 1)[-1])[0]
            path = _find_image(index, stem)
            if path:
                image.filepath = path
                image.reload()
                linked.append(stem)
            else:
                missing.append(stem)
        stem = mat.get("max_bitmap")
        if not stem or _material_has_image(mat):
            continue
        path = _find_image(index, stem)
        if path is None:
            missing.append(stem)
            continue
        img = bpy.data.images.load(path, check_existing=True)
        shader = PrincipledBSDFWrapper(mat, is_readonly=False)
        shader.base_color_texture.image = img
        linked.append(stem)
    return linked, sorted(set(missing))


def _post_process(context, before_objs, before_mats, label, zoom=True, max_material_names=True):
    """Max-style cleanup of whatever the import just created."""
    from .create import random_color
    new_objs = [o for o in context.scene.objects if o.name not in before_objs]
    new_mats = [m for m in bpy.data.materials if m.name not in before_mats]
    for ob in new_objs:
        if ob.type in {"MESH", "CURVE", "FONT", "SURFACE", "META"} and tuple(ob.color) == (1.0, 1.0, 1.0, 1.0):
            ob.color = random_color()
            ob["max_keep_color"] = 1
    for mat in new_mats:
        if mat.use_nodes and any(n.type == "BSDF_PRINCIPLED" for n in mat.node_tree.nodes):
            mat["max_vray"] = 1          # editable in Modify > Material with V-Ray names
        if max_material_names:
            base, stem = _split_bitmap_name(mat.name)
            if stem:
                mat["max_bitmap"] = stem
            mat.name = _max_display_name(base)
    for o in context.selected_objects:
        o.select_set(False)
    for ob in new_objs:
        try:
            ob.select_set(True)
        except RuntimeError:
            pass
    if new_objs:
        context.view_layer.objects.active = new_objs[0]
    if zoom and new_objs:
        from .operators import viewport_override
        ov = viewport_override(context)
        if ov:
            try:
                with context.temp_override(**ov):
                    bpy.ops.view3d.view_selected(use_all_regions=True)
            except RuntimeError:
                pass
    return new_objs, new_mats


def _report_textures(op, materials, folder):
    linked, missing = relink_textures(materials, [folder])
    if missing:
        op.report({"WARNING"}, f"Missing External Files ({len(missing)}): {', '.join(missing)}. "
                               "Use File > External Data > Relink 3ds Max Textures")
    return linked, missing


def _new_scene(context, name):
    scene = bpy.data.scenes.new(name)
    scene.unit_settings.system = context.scene.unit_settings.system
    scene.unit_settings.scale_length = context.scene.unit_settings.scale_length
    scene.max_system_units = context.scene.max_system_units
    if context.scene.world:
        scene.world = context.scene.world
    context.window.scene = scene
    return scene


EXT_API = "https://extensions.blender.org/api/v1/extensions/"


def _direct_install_reader():
    """Fallback: download io_scene_max straight from extensions.blender.org, verify its
    published SHA-256, and install it into the user repository."""
    import hashlib
    import json
    import tempfile
    import urllib.request
    ua = {"User-Agent": "NotuoDesk-3ds-Maxxed"}
    with urllib.request.urlopen(urllib.request.Request(EXT_API, headers=ua), timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    item = next((e for e in data.get("data", []) if e.get("id") == READER_ID), None)
    if item is None:
        raise RuntimeError("io_scene_max is not listed on extensions.blender.org")
    with urllib.request.urlopen(urllib.request.Request(item["archive_url"], headers=ua), timeout=60) as r:
        payload = r.read()
    expected = (item.get("archive_hash") or "").split(":")[-1].lower()
    if expected and hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError("downloaded file failed its checksum")
    path = os.path.join(tempfile.mkdtemp(prefix="maxxed_reader_"), "io_scene_max.zip")
    with open(path, "wb") as fh:
        fh.write(payload)
    bpy.ops.extensions.package_install_files(filepath=path, repo="user_default",
                                             enable_on_install=True, overwrite=True)


class MAX_OT_install_max_reader(Operator):
    """Install the open-source .max reader (io_scene_max) from extensions.blender.org"""
    bl_idname = "max.install_max_reader"
    bl_label = "Install .max Reader"

    def execute(self, context):
        if not bpy.app.online_access:
            self.report({"WARNING"}, "Turn on Preferences > System > Network > Allow Online Access, then try again")
            try:
                context.preferences.active_section = "SYSTEM"
                bpy.ops.screen.userpref_show("INVOKE_DEFAULT")
            except Exception:
                pass
            return {"CANCELLED"}
        if context.window:
            context.window.cursor_set("WAIT")
        errors = []
        repos = context.preferences.extensions.repos
        idx = next((i for i, r in enumerate(repos)
                    if r.enabled and "extensions.blender.org" in (r.remote_url or "")), -1)
        if idx >= 0:
            try:
                # The package list (index.json) must be downloaded before installing from it;
                # called without INVOKE these run to completion (blocking)
                bpy.ops.extensions.repo_sync(repo_index=idx)
                bpy.ops.extensions.package_install(repo_index=idx, pkg_id=READER_ID, enable_on_install=True)
            except Exception as exc:
                errors.append(str(exc).strip().splitlines()[-1])
        if not reader_available():
            try:
                _direct_install_reader()
            except Exception as exc:
                errors.append(str(exc).strip().splitlines()[-1])
        if context.window:
            context.window.cursor_set("DEFAULT")
        if reader_available():
            self.report({"INFO"}, ".max reader installed: File > Open 3ds Max File is ready")
            return {"FINISHED"}
        bpy.ops.wm.url_open(url=READER_URL)
        self.report({"ERROR"}, "Could not install the .max reader automatically "
                               f"({'; '.join(errors) or 'unknown error'}). Its page is now open: "
                               "click 'Get Add-on' there, or drag the downloaded .zip into Blender")
        return {"CANCELLED"}


class _MaxImportBase(ImportHelper):
    filename_ext = ".max"
    filter_glob: StringProperty(default="*.max", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})

    units: EnumProperty(name="System Units", items=[(k, n, d) for k, n, d, _ in UNITS], default="INCHES",
                        description="The System Unit Setup of the 3ds Max file (Customize > Units Setup in Max)")
    textures: BoolProperty(name="Search for Textures", default=True,
                           description="Look for bitmaps next to the .max file and in its subfolders")
    materials: BoolProperty(name="Materials", default=True)
    uvs: BoolProperty(name="Texture Coordinates", default=True)
    primitives: BoolProperty(name="Primitives / Helpers", default=True)

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        lay.prop(self, "units")
        lay.prop(self, "textures")
        lay.prop(self, "materials")
        lay.prop(self, "uvs")
        lay.prop(self, "primitives")
        if not reader_available():
            box = lay.box()
            box.label(text="The .max reader is not installed", icon="ERROR")
            box.operator("max.install_max_reader", icon="IMPORT")

    def invoke(self, context, event):
        if not self.properties.is_property_set("units"):
            self.units = context.scene.max_system_units
        if self.filepath and os.path.isfile(self.filepath):   # drag & drop
            return context.window_manager.invoke_props_dialog(self, width=320)
        return ImportHelper.invoke(self, context, event)

    def _paths(self):
        if self.files and self.directory:
            return [os.path.join(self.directory, f.name) for f in self.files if f.name.lower().endswith(".max")]
        return [self.filepath]

    def run(self, context, new_scene):
        from . import max_reader
        if not reader_available():
            self.report({"ERROR"}, "Install the .max reader first (File > Import > Install .max Reader)")
            bpy.ops.max.install_max_reader()
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        filters = {"EMPTY", "ARMATURE"}
        if self.materials:
            filters.add("MATERIAL")
        if self.uvs:
            filters.add("UV")
        if self.primitives:
            filters.add("PRIMITIVE")
        total = 0
        units = self.units if self.properties.is_property_set("units") else context.scene.max_system_units
        for path in self._paths():
            name = os.path.splitext(os.path.basename(path))[0]
            if new_scene:
                _new_scene(context, name)
            before_o = {o.name for o in context.scene.objects}
            before_m = {m.name for m in bpy.data.materials}
            try:
                result = bpy.ops.import_scene.max(
                    filepath=path, scale_objects=1.0, use_image_search=self.textures,
                    axis_forward="Y", axis_up="Z",
                    object_filter=filters, use_collection=not new_scene, use_apply_matrix=True)
            except (RuntimeError, TypeError) as exc:
                self.report({"ERROR"}, f"{os.path.basename(path)}: {str(exc).splitlines()[-1]}")
                continue
            if "FINISHED" not in result:
                self.report({"WARNING"}, f"{os.path.basename(path)} could not be read")
                continue
            try:
                max_reader.recover_materials([m for m in bpy.data.materials if m.name not in before_m])
            except (AttributeError, IndexError, TypeError, ValueError) as exc:
                self.report({"WARNING"}, f"Source material names could not be recovered: {exc}")
            objs = [o for o in context.scene.objects if o.name not in before_o]
            meters = context.scene.unit_settings.scale_length if context.scene.unit_settings.system != "NONE" else 1.0
            max_reader.scale_roots(context, objs, UNIT_SCALE[units] / meters)
            try:
                restored = max_reader.recover_smoothing(objs)
                print(f"[3ds Maxxed] Recovered smoothing groups on {restored} meshes")
                missing = max_reader.missing_nodes(objs)
                if missing:
                    self.report({"WARNING"}, f"{len(missing)} source nodes were not imported: {', '.join(missing[:8])}. "
                                             "Use FBX from 3ds Max for unsupported objects")
            except (AttributeError, IndexError, TypeError, ValueError, struct.error) as exc:
                self.report({"WARNING"}, f"Smoothing groups could not be recovered: {exc}")
            objs, mats = _post_process(context, before_o, before_m, name)
            context.scene.max_system_units = units
            _report_textures(self, mats, os.path.dirname(path))
            total += len(objs)
        if total == 0:
            self.report({"WARNING"}, "Nothing was imported. For newer or compressed files, "
                                     "save as FBX from 3ds Max (see tools/max_to_blender.ms)")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {total} objects")
        return {"FINISHED"}


class MAX_OT_load_bitmap(Operator, ImportHelper):
    """Load a bitmap into the active material's Diffuse / Base Color (like a Max Bitmap map)"""
    bl_idname = "max.load_bitmap"
    bl_label = "Load Bitmap"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default="*" + ";*".join(IMAGE_EXTS), options={"HIDDEN"})
    apply_to_object: BoolProperty(name="All materials on this object that use the same bitmap", default=True)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.active_material is not None

    def execute(self, context):
        from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
        ob = context.active_object
        mat = ob.active_material
        mat.use_nodes = True
        img = bpy.data.images.load(self.filepath, check_existing=True)
        targets = [mat]
        stem = mat.get("max_bitmap")
        if self.apply_to_object and stem:
            targets = [m for m in bpy.data.materials if m.get("max_bitmap") == stem]
        for m in targets:
            m.use_nodes = True
            PrincipledBSDFWrapper(m, is_readonly=False).base_color_texture.image = img
            m["max_bitmap"] = m.get("max_bitmap") or os.path.splitext(os.path.basename(self.filepath))[0]
        self.report({"INFO"}, f"{img.name} -> {', '.join(m.name for m in targets)}")
        return {"FINISHED"}


class MAX_OT_relink_textures(Operator):
    """Find missing 3ds Max bitmaps in a folder (searched recursively, any image format)"""
    bl_idname = "max.relink_textures"
    bl_label = "Relink 3ds Max Textures"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        mats = [m for m in bpy.data.materials if m.get("max_bitmap") or any(_missing_images(m))]
        if not mats:
            self.report({"INFO"}, "No missing image files or 3ds Max bitmap references in this file")
            return {"CANCELLED"}
        linked, missing = relink_textures(mats, [self.directory])
        msg = f"Relinked {len(linked)} texture(s)"
        if missing:
            msg += f"; still missing: {', '.join(missing)}"
        self.report({"WARNING" if missing else "INFO"}, msg)
        return {"FINISHED"}


class MAX_OT_open_max(Operator, _MaxImportBase):
    """Open a 3ds Max scene (.max) in a new scene"""
    bl_idname = "max.open_max"
    bl_label = "Open 3ds Max File"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return self.run(context, new_scene=True)


class MAX_OT_merge_max(Operator, _MaxImportBase):
    """Merge objects from a 3ds Max scene (.max) into the current scene"""
    bl_idname = "max.merge_max"
    bl_label = "Merge 3ds Max File"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return self.run(context, new_scene=False)


class MAX_OT_import_max_fbx(Operator, ImportHelper):
    """Import an FBX exported from 3ds Max with Max-friendly settings
    (animation, rigs, cameras, lights, TurboSmooth as subdivision)"""
    bl_idname = "max.import_max_fbx"
    bl_label = "Import FBX from 3ds Max"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})
    new_scene: BoolProperty(name="Open as New Scene", default=False)
    animation: BoolProperty(name="Animation", default=True)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        name = os.path.splitext(os.path.basename(self.filepath))[0]
        if self.new_scene:
            _new_scene(context, name)
        before_o = {o.name for o in context.scene.objects}
        before_m = {m.name for m in bpy.data.materials}
        try:
            bpy.ops.import_scene.fbx(filepath=self.filepath, use_custom_normals=True, use_image_search=True,
                                     use_anim=self.animation, anim_offset=0.0, use_subsurf=True,
                                     use_manual_orientation=False,
                                     automatic_bone_orientation=True, use_custom_props=True)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc).splitlines()[-1])
            return {"CANCELLED"}
        objs, mats = _post_process(context, before_o, before_m, name, max_material_names=False)
        from .max_export import remember_fbx_units
        remember_fbx_units(context.scene, self.filepath)
        self.report({"INFO"}, f"Imported {len(objs)} objects from {os.path.basename(self.filepath)}")
        return {"FINISHED"}


class MAX_FH_max(bpy.types.FileHandler):
    """Drag a .max file onto Blender to open it the 3ds Maxxed way"""
    bl_idname = "MAX_FH_max"
    bl_label = "3ds Maxxed: Merge 3ds Max File"
    bl_import_operator = "max.merge_max"
    bl_file_extensions = ".max"

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type in {"VIEW_3D", "OUTLINER"}


def menu_import(self, context):
    lay = self.layout
    lay.separator()
    lay.operator("max.merge_max", text="Merge 3ds Max File (.max)")
    lay.operator("max.import_max_fbx", text="FBX from 3ds Max (.fbx)")
    if not reader_available():
        lay.operator("max.install_max_reader", text="Install .max Reader...", icon="IMPORT")


def menu_file(self, context):
    self.layout.operator("max.open_max", text="Open 3ds Max File...", icon="FILE_FOLDER")


classes = (MAX_OT_install_max_reader, MAX_OT_open_max, MAX_OT_merge_max, MAX_OT_import_max_fbx,
           MAX_OT_relink_textures, MAX_OT_load_bitmap, MAX_FH_max)


def menu_external(self, context):
    self.layout.operator("max.relink_textures", text="Relink 3ds Max Textures...")


def register_menus():
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file.prepend(menu_file)
    bpy.types.TOPBAR_MT_file_external_data.append(menu_external)


def unregister_menus():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.types.TOPBAR_MT_file.remove(menu_file)
    bpy.types.TOPBAR_MT_file_external_data.remove(menu_external)
