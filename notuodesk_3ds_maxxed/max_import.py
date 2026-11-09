"""Scene interchange commands with a separate, versioned Max reader dependency."""
import importlib
from pathlib import Path
import re

import addon_utils
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty
from bpy.types import FileHandler, Operator, OperatorFileListElement
from bpy_extras.io_utils import ImportHelper

from . import max_reader

UNITS = (
    ('INCHES', 'Inches', 'One source unit is one inch', .0254),
    ('CENTIMETERS', 'Centimeters', 'One source unit is one centimeter', .01),
    ('MILLIMETERS', 'Millimeters', 'One source unit is one millimeter', .001),
    ('FEET', 'Feet', 'One source unit is one foot', .3048),
    ('METERS', 'Meters', 'One source unit is one meter', 1.0),
    ('GENERIC', 'Generic Units (1:1)', 'Keep raw source numbers', 1.0),
)
UNIT_SCALE = {key: scale for key, _label, _description, scale in UNITS}
UNIT_ITEMS = [(key, label, description) for key, label, description, _scale in UNITS]
REPLACE_ACTIONS = [('CANCEL', 'Cancel', 'Keep the current scene'),
                   ('SAVE', 'Save', 'Save the current native .blend scene first'),
                   ('DISCARD', "Don't Save", 'Replace without saving the current scene')]


def _reader_package():
    cls = bpy.types.Operator.bl_rna_get_subclass_py('IMPORT_SCENE_OT_max')
    if cls is not None:
        return importlib.import_module(cls.__module__)
    # Some separately packaged reader releases have a manifest instead of bl_info.
    if importlib.util.find_spec('io_scene_max') is not None:
        addon_utils.enable('io_scene_max', default_set=False)
        cls = bpy.types.Operator.bl_rna_get_subclass_py('IMPORT_SCENE_OT_max')
        if cls is not None:
            return importlib.import_module(cls.__module__)
    # Locate the separately installed legacy or extension package by its module name.
    for module in addon_utils.modules():
        if module.__name__.split('.')[-1] == 'io_scene_max':
            addon_utils.enable(module.__name__, default_set=False)
            cls = bpy.types.Operator.bl_rna_get_subclass_py('IMPORT_SCENE_OT_max')
            if cls is not None:
                return importlib.import_module(cls.__module__)
    return None


def require_reader():
    package = _reader_package()
    if package is None:
        raise RuntimeError('Install the separate io_scene_max reader 1.9.2 to read .max files')
    version = getattr(package, '__version__', None)
    if version != '1.9.2':
        raise RuntimeError(f'Unsupported .max reader {version!r}. This adapter supports io_scene_max 1.9.2')
    required = {'filepath', 'scale_objects', 'object_filter', 'use_apply_matrix'}
    if not required.issubset(bpy.ops.import_scene.max.get_rna_type().properties.keys()):
        raise RuntimeError('Unsupported .max reader capabilities. Use io_scene_max 1.9.2')
    return package


def _read_max(path, *, materials=True, textures=True, uvs=True, primitives=True):
    flags = {'EMPTY', 'ARMATURE'}
    flags.update(key for key, enabled in (('MATERIAL', materials), ('UV', uvs),
                                         ('PRIMITIVE', primitives)) if enabled)
    return bpy.ops.import_scene.max(filepath=str(path), scale_objects=1,
                                    object_filter=flags, use_image_search=textures,
                                    use_apply_matrix=True, axis_forward='Y', axis_up='Z')


def _read_fbx(path, *, animation=True):
    try:
        bpy.ops.import_scene.fbx.get_rna_type()
    except (AttributeError, RuntimeError, KeyError) as exc:
        raise RuntimeError('FBX import is unavailable in this Blender installation') from exc
    return bpy.ops.import_scene.fbx(filepath=str(path), use_anim=animation, anim_offset=0,
                                    use_custom_normals=True, use_image_search=True)


def _validate_file(path, extension):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f'File not found: {path}')
    if path.suffix.lower() != extension:
        raise RuntimeError(f'Choose a {extension} file: {path.name}')
    return path


def _stage(context, load, *, replace=False, before_commit=None):
    """Commit links only after the reader and retained-data adapters succeed."""
    target = context.scene
    previous = {kind: set(getattr(bpy.data, kind)) for kind in
                ('objects', 'collections', 'meshes', 'curves', 'materials', 'images', 'cameras', 'lights', 'actions')}
    selected = tuple(context.selected_objects)
    active = context.view_layer.objects.active
    if before_commit:
        before_commit()
    staging = bpy.data.scenes.new('Maxxed import staging')
    staging.unit_settings.system = target.unit_settings.system
    staging.unit_settings.scale_length = target.unit_settings.scale_length
    staging.max_system_units = target.max_system_units
    staging.frame_start, staging.frame_end = target.frame_start, target.frame_end
    window = context.window
    old_window_scene = window.scene if window else None
    committed = False
    try:
        if window:
            window.scene = staging
        with context.temp_override(scene=staging, view_layer=staging.view_layers[0], collection=staging.collection):
            result = load(staging)
            if not result or 'FINISHED' not in result:
                raise RuntimeError('Import cancelled by the reader')
        objects = tuple(staging.objects)
        if not objects:
            raise RuntimeError('The reader returned no supported scene objects')
        if window:
            window.scene = target
        if replace:
            # Unlink only this scene. Objects used by another scene remain intact.
            for collection in tuple(target.collection.children):
                target.collection.children.unlink(collection)
            for obj in tuple(target.collection.objects):
                target.collection.objects.unlink(obj)
        for collection in tuple(staging.collection.children):
            target.collection.children.link(collection)
        for obj in tuple(staging.collection.objects):
            target.collection.objects.link(obj)
        target.max_system_units = staging.max_system_units
        if replace:
            target.frame_start, target.frame_end = staging.frame_start, staging.frame_end
            target.camera = staging.camera or next((obj for obj in objects if obj.type == 'CAMERA'), None)
        context.view_layer.update()
        for obj in context.view_layer.objects:
            obj.select_set(obj in objects)
        context.view_layer.objects.active = next((o for o in objects if o.name in context.view_layer.objects), None)
        committed = True
        return objects
    finally:
        if window:
            window.scene = old_window_scene
        bpy.data.scenes.remove(staging)
        if not committed:
            # Remove only datablocks made during this attempt, never pre-existing data.
            for kind, old in previous.items():
                data = getattr(bpy.data, kind)
                for block in set(data) - old:
                    data.remove(block, do_unlink=True)
            for obj in context.view_layer.objects:
                obj.select_set(obj in selected)
            context.view_layer.objects.active = active


def import_paths(context, paths, *, replace=False, units='INCHES', materials=True,
                 textures=True, uvs=True, primitives=True, before_commit=None):
    require_reader()
    paths = list(paths)
    if not paths:
        raise RuntimeError('Choose at least one .max file')
    if replace and len(paths) != 1:
        raise RuntimeError('Open accepts one .max file. Use Merge for multiple files')
    report = dict(imported=[], errors=[], warnings=[])
    for path in paths:
        try:
            path = _validate_file(path, '.max')
            warnings = []
            def load(scene):
                old_materials = set(bpy.data.materials)
                result = _read_max(path, materials=materials, textures=textures, uvs=uvs, primitives=primitives)
                if 'FINISHED' not in result:
                    return result
                objects = tuple(scene.objects)
                factor = UNIT_SCALE[units]
                if units != 'GENERIC':
                    length = scene.unit_settings.scale_length if scene.unit_settings.system != 'NONE' else 1
                    factor /= length
                max_reader.scale_roots(bpy.context, objects, factor)
                max_reader.recover_smoothing(objects)
                imported_materials = set(bpy.data.materials) - old_materials
                max_reader.recover_materials(imported_materials)
                if max_reader._reader_data() is None:
                    warnings.append('Reader supplied no retained mesh or material records. Conversion may be incomplete')
                missing = max_reader.missing_nodes(objects)
                if missing:
                    warnings.append(f'{len(missing)} source nodes were not imported: ' + ', '.join(missing))
                if textures and materials:
                    _linked, unresolved = relink_textures(imported_materials, [path.parent])
                    if unresolved:
                        warnings.append('Unresolved textures: ' + ', '.join(unresolved))
                scene.max_system_units = units
                return result
            objects = _stage(context, load, replace=replace, before_commit=before_commit)
            report['imported'].append((str(path), objects))
            report['warnings'].extend(warnings)
        except Exception as exc:
            if replace:
                raise
            report['errors'].append(f'{path}: {exc}')
    return report


def import_fbx(context, filepath, *, replace=False, animation=True, before_commit=None):
    path = _validate_file(filepath, '.fbx')
    def load(scene):
        result = _read_fbx(path, animation=animation)
        if 'FINISHED' in result:
            from .max_export import remember_fbx_units
            remember_fbx_units(scene, str(path))
        return result
    return _stage(context, load, replace=replace, before_commit=before_commit)


def _basename(value):
    return re.split(r'[/\\]', str(value))[-1]


def texture_index(folders):
    index = {}
    for folder in folders:
        root = Path(folder)
        if root.is_dir():
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.tga', '.exr', '.hdr', '.dds'}:
                    index.setdefault(path.name.casefold(), set()).add(str(path.resolve()))
    return index


def _find_image(index, name):
    """Match exact filenames or stems, including Windows' numbered copy suffix."""
    wanted = _basename(name).casefold()
    exact, fallback = set(), set()
    for key, values in index.items():
        values = {values} if isinstance(values, (str, Path)) else set(values)
        key = key.casefold()
        stem = Path(key).stem
        if key == wanted or (not Path(wanted).suffix and stem == wanted):
            exact.update(values)
        if (re.sub(r' \(\d+\)$', '', stem) == Path(wanted).stem
                and (not Path(wanted).suffix or Path(wanted).suffix == Path(key).suffix)):
            fallback.update(values)
    choices = exact or fallback
    return str(next(iter(choices))) if len(choices) == 1 else None


def _color_socket(material):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if shader is None:
        shader = nodes.new('ShaderNodeBsdfPrincipled')
        output = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None)
        output = output or nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    return shader.inputs['Base Color']


def relink_textures(materials, folders):
    index = texture_index(folders)
    linked, unresolved = [], []
    for mat in materials:
        image_nodes = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'] if mat.node_tree else []
        requests = [(node, _basename(node.image.filepath) or node.image.name) for node in image_nodes
                    if node.image and node.image.source == 'FILE' and not node.image.packed_file
                    and not Path(bpy.path.abspath(node.image.filepath)).is_file()]
        bitmap = mat.get('max_bitmap')
        if bitmap and not requests and not any(n.image for n in image_nodes):
            requests.append((None, bitmap))
        # Generated images with an imported bitmap identity can also represent missing files.
        if bitmap and not requests:
            requests.extend((n, bitmap) for n in image_nodes if n.image
                            and not Path(bpy.path.abspath(n.image.filepath)).is_file())
        for node, name in requests:
            path = _find_image(index, name) or (_find_image(index, bitmap) if bitmap else None)
            if path is None:
                unresolved.append(str(bitmap or name))
                continue
            try:
                image = bpy.data.images.load(path, check_existing=True)
                if node is None:
                    socket = _color_socket(mat)
                    node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    mat.node_tree.links.new(node.outputs['Color'], socket)
                node.image = image
                linked.append(str(bitmap or name))
            except RuntimeError:
                unresolved.append(str(bitmap or name))
    return linked, unresolved


def _replacement_guard(operator):
    def confirm():
        if not bpy.data.is_dirty:
            return
        if operator.scene_action == 'CANCEL':
            raise RuntimeError('Open cancelled. Choose Save or Don\'t Save to replace this scene')
        if operator.scene_action == 'SAVE':
            if not bpy.data.filepath:
                raise RuntimeError('Save the current scene as a .blend file before Open')
            if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath):
                raise RuntimeError('Scene save cancelled')
    return confirm


class MAX_OT_install_max_reader(Operator, ImportHelper):
    """Locate the independent reader, or install a reader ZIP chosen by the user"""
    bl_idname = 'max.install_max_reader'
    bl_label = 'Install .max Reader'
    filename_ext = '.zip'
    filter_glob: StringProperty(default='*.zip', options={'HIDDEN'})

    def invoke(self, context, event):
        if _reader_package() is not None:
            return self.execute(context)
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            if self.filepath:
                _validate_file(self.filepath, '.zip')
                bpy.ops.preferences.addon_install(filepath=self.filepath)
            require_reader()
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Separate io_scene_max 1.9.2 reader is ready')
        return {'FINISHED'}


class _MaxFileOptions(ImportHelper):
    filename_ext = '.max'
    filter_glob: StringProperty(default='*.max', options={'HIDDEN'})
    files: CollectionProperty(type=OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')
    units: EnumProperty(name='System Units', items=UNIT_ITEMS, default='INCHES')
    textures: BoolProperty(name='Textures', default=True)
    materials: BoolProperty(name='Materials', default=True)
    uvs: BoolProperty(name='UV Maps', default=True)
    primitives: BoolProperty(name='Primitives', default=True)
    scene_action: EnumProperty(name='Save changes to current scene?', items=REPLACE_ACTIONS, default='CANCEL')

    def draw(self, context):
        self.layout.prop(self, 'units')
        for name in ('materials', 'textures', 'uvs', 'primitives'):
            self.layout.prop(self, name)
        self.layout.label(text='Supported reader data only. Some Max materials and objects cannot be converted.')
        if self.bl_idname == 'max.open_max' and bpy.data.is_dirty:
            self.layout.label(text=Path(bpy.data.filepath).name or 'Untitled.blend')
            self.layout.prop(self, 'scene_action', expand=True)

    def invoke(self, context, event):
        if not self.properties.is_property_set('units'):
            self.units = context.scene.max_system_units
        return ImportHelper.invoke(self, context, event)

    def run(self, context, replace):
        paths = [Path(self.directory)/item.name for item in self.files] or ([Path(self.filepath)] if self.filepath else [])
        try:
            report = import_paths(context, paths, replace=replace, units=self.units,
                                  materials=self.materials, textures=self.textures, uvs=self.uvs,
                                  primitives=self.primitives,
                                  before_commit=_replacement_guard(self) if replace else None)
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        for warning in report['errors'] + report['warnings']:
            self.report({'WARNING'}, warning)
        self.report({'INFO'}, f"Imported {len(report['imported'])} file(s), {len(report['errors'])} failed")
        return {'FINISHED'} if report['imported'] else {'CANCELLED'}


class MAX_OT_open_max(Operator, _MaxFileOptions):
    """Open a supported .max scene after saving or discarding current changes"""
    bl_idname = 'max.open_max'
    bl_label = 'Open 3ds Max File'
    bl_options = {'UNDO'}

    def execute(self, context):
        return self.run(context, True)


class MAX_OT_merge_max(Operator, _MaxFileOptions):
    """Merge supported .max objects into the current scene"""
    bl_idname = 'max.merge_max'
    bl_label = 'Merge 3ds Max File'
    bl_options = {'UNDO'}

    def execute(self, context):
        return self.run(context, False)


class MAX_OT_import_max_fbx(Operator, ImportHelper):
    """Import FBX interchange data with optional animation"""
    bl_idname = 'max.import_max_fbx'
    bl_label = 'Import FBX from 3ds Max'
    bl_options = {'UNDO'}
    filename_ext = '.fbx'
    filter_glob: StringProperty(default='*.fbx', options={'HIDDEN'})
    new_scene: BoolProperty(name='New Scene', default=False)
    animation: BoolProperty(name='Animation', default=True)
    scene_action: EnumProperty(name='Save changes to current scene?', items=REPLACE_ACTIONS, default='CANCEL')

    def draw(self, context):
        self.layout.prop(self, 'animation')
        self.layout.prop(self, 'new_scene')
        if self.new_scene and bpy.data.is_dirty:
            self.layout.prop(self, 'scene_action', expand=True)

    def execute(self, context):
        try:
            import_fbx(context, self.filepath, replace=self.new_scene, animation=self.animation,
                       before_commit=_replacement_guard(self) if self.new_scene else None)
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_load_bitmap(Operator, ImportHelper):
    """Load an image and optionally assign it to the active object's material"""
    bl_idname = 'max.load_bitmap'
    bl_label = 'Load Bitmap'
    bl_options = {'UNDO'}
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.tga;*.exr;*.hdr;*.dds', options={'HIDDEN'})
    apply_to_object: BoolProperty(name='Apply to Object', default=True)

    def execute(self, context):
        try:
            if not Path(self.filepath).is_file():
                raise RuntimeError('Bitmap file not found')
            obj = context.object
            if self.apply_to_object and (obj is None or not hasattr(obj.data, 'materials')):
                raise RuntimeError('Select an object that supports materials')
            image = bpy.data.images.load(self.filepath, check_existing=True)
            mat = obj.active_material if self.apply_to_object else None
            if mat is None:
                mat = bpy.data.materials.new(Path(self.filepath).stem)
                if self.apply_to_object:
                    if obj.material_slots:
                        obj.material_slots[obj.active_material_index].material = mat
                    else:
                        obj.data.materials.append(mat)
            socket = _color_socket(mat)
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.image = image
            mat.node_tree.links.new(node.outputs['Color'], socket)
            mat['max_bitmap'] = Path(self.filepath).name
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_relink_textures(Operator):
    """Find missing bitmaps by exact filename in a folder and its subfolders"""
    bl_idname = 'max.relink_textures'
    bl_label = 'Relink 3ds Max Textures'
    bl_options = {'UNDO'}
    directory: StringProperty(name='Search Folder', subtype='DIR_PATH')

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not Path(self.directory).is_dir():
            self.report({'WARNING'}, 'Choose an existing texture folder')
            return {'CANCELLED'}
        linked, missing = relink_textures(bpy.data.materials, [self.directory])
        self.report({'WARNING'} if missing else {'INFO'},
                    f'Relinked {len(linked)} texture(s), {len(missing)} unresolved' +
                    (': ' + ', '.join(missing) if missing else ''))
        return {'FINISHED'}


class MAX_FH_max(FileHandler):
    bl_idname = 'MAX_FH_max'
    bl_label = '3ds Maxxed: Merge 3ds Max File'
    bl_import_operator = 'max.merge_max'
    bl_file_extensions = '.max'

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'


def menu_import(self, context):
    self.layout.operator('max.open_max', text='Open 3ds Max (.max)...')
    self.layout.operator('max.merge_max', text='Merge 3ds Max (.max)...')
    self.layout.operator('max.import_max_fbx', text='3ds Max Interchange (FBX)...')


_menus_installed = False


def register_menus():
    """Transitional native host hook. The curated File host may call menu_import directly."""
    global _menus_installed
    if not _menus_installed:
        bpy.types.TOPBAR_MT_file_import.append(menu_import)
        _menus_installed = True


def unregister_menus():
    global _menus_installed
    if _menus_installed:
        bpy.types.TOPBAR_MT_file_import.remove(menu_import)
        _menus_installed = False


classes = (MAX_OT_install_max_reader, MAX_OT_load_bitmap, MAX_OT_relink_textures,
           MAX_OT_open_max, MAX_OT_merge_max, MAX_OT_import_max_fbx, MAX_FH_max)
