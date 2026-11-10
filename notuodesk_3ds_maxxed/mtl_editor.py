"""Compact samples and material controls over Blender's rendered materials."""
import math

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import max_icons

NUM_SLOTS = 24
MAP_PREFIX = 'MaxMap_'
MAP_CHANNELS = (
    ('AMBIENT', 'Ambient Color', None, True),
    ('DIFFUSE', 'Diffuse Color', 'Base Color', True),
    ('SPECULAR_COLOR', 'Specular Color', 'Specular Tint', True),
    ('SPECULAR_LEVEL', 'Specular Level', 'Specular IOR Level', False),
    ('GLOSSINESS', 'Glossiness', 'Roughness', False),
    ('SELF_ILLUM', 'Self-Illumination', 'Emission Color', True),
    ('OPACITY', 'Opacity', 'Alpha', False),
    ('FILTER', 'Filter Color', 'Specular Tint', True),
    ('BUMP', 'Bump', 'Normal', False),
    ('REFLECTION', 'Reflection', 'Metallic', False),
    ('REFRACTION', 'Refraction', 'Transmission Weight', False),
    ('DISPLACEMENT', 'Displacement', None, False),
)
MAP_INFO = {key: (label, socket, color) for key, label, socket, color in MAP_CHANNELS}
SHADERS = [('BLINN', 'Blinn', ''), ('PHONG', 'Phong', ''), ('METAL', 'Metal', ''),
           ('ANISOTROPIC', 'Anisotropic', ''), ('OREN_NAYAR', 'Oren-Nayar-Blinn', ''),
           ('TRANSLUCENT', 'Translucent Shader', ''), ('MULTI_LAYER', 'Multi-Layer', '')]
ICON_FALLBACKS = {'material_editor': 'MATERIAL', 'sphere': 'SPHERE', 'mtl_drag': 'FORWARD',
    'mtl_select': 'RESTRICT_SELECT_OFF', 'settings': 'PREFERENCES', 'mtl_get': 'MATERIAL',
    'mtl_assign': 'CHECKMARK', 'mtl_reset': 'TRASH', 'make_unique': 'DUPLICATE',
    'mtl_library': 'FILE_TICK', 'mtl_viewport': 'SHADING_TEXTURE', 'create': 'ADD',
    'mtl_pick': 'EYEDROPPER', 'close': 'X'}
_catalogue = []
_preview_textures = {}
_preview_signatures = {}
_preview_requests = set()
_preview_hosts = set()
_pickers = []
_generation = 0
_props_installed = []


def shader(material, create=False):
    if material is None:
        return None
    if create and not material.use_nodes:
        material.use_nodes = True
    tree = material.node_tree
    if tree is None:
        return None
    # Prefer the surface actually rendered, rather than an unused Principled node.
    for output in tree.nodes:
        if output.type == 'OUTPUT_MATERIAL' and output.is_active_output:
            links = output.inputs['Surface'].links
            if links:
                node = links[0].from_node
                return node if node.type == 'BSDF_PRINCIPLED' else None
    return next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def _socket_read(material, name, fallback):
    node = shader(material)
    return node.inputs[name].default_value if node and name in node.inputs else fallback


def _socket_write(material, name, value):
    if material.library:
        return
    node = shader(material, create=True)
    if node and name in node.inputs:
        node.inputs[name].default_value = value
        material.update_tag()
        invalidate_preview(material)


def _diffuse_get(material):
    return tuple(_socket_read(material, 'Base Color', material.diffuse_color)[:3])


def _diffuse_set(material, value):
    material.diffuse_color = (*value, material.diffuse_color[3])
    _socket_write(material, 'Base Color', (*value, 1))


def _specular_get(material):
    value = _socket_read(material, 'Specular Tint', (1, 1, 1, 1))
    return (value, value, value) if isinstance(value, (float, int)) else tuple(value[:3])


def _specular_set(material, value):
    node = shader(material, create=True)
    if node:
        socket = node.inputs.get('Specular Tint')
        _socket_write(material, 'Specular Tint', (*value, 1) if socket and socket.type == 'RGBA' else sum(value)/3)


def _level_get(material):
    return round(100 * _socket_read(material, 'Specular IOR Level', .5))


def _level_set(material, value):
    _socket_write(material, 'Specular IOR Level', value / 100)


def _gloss_get(material):
    return round(100 * (1 - _socket_read(material, 'Roughness', .5)))


def _gloss_set(material, value):
    _socket_write(material, 'Roughness', 1 - value / 100)


def _opacity_get(material):
    return round(100 * _socket_read(material, 'Alpha', material.diffuse_color[3]))


def _opacity_set(material, value):
    _socket_write(material, 'Alpha', value / 100)
    color = material.diffuse_color[:]
    material.diffuse_color = (*color[:3], value / 100)


def _ior_get(material):
    return _socket_read(material, 'IOR', 1.5)


def _ior_set(material, value):
    _socket_write(material, 'IOR', value)


def _two_sided_get(material):
    return not material.use_backface_culling


def _two_sided_set(material, value):
    material.use_backface_culling = not value


def _standard_update(self, context):
    material = self.id_data
    color = self.self_illum_color if self.self_illum_color_on else _diffuse_get(material)
    _socket_write(material, 'Emission Color', (*color, 1))
    _socket_write(material, 'Emission Strength', self.self_illum_amount / 100)
    bump = material.node_tree.nodes.get(MAP_PREFIX + 'BUMP_Bump') if material.node_tree else None
    if bump:
        bump.inputs['Distance'].default_value = self.bump_amount / 100


def _shader_update(self, context):
    material = self.id_data
    _socket_write(material, 'Metallic', 1 if self.shader == 'METAL' else 0)
    _socket_write(material, 'Anisotropic IOR Level', .5 if self.shader == 'ANISOTROPIC' else 0)
    _socket_write(material, 'Transmission Weight', .5 if self.shader == 'TRANSLUCENT' else 0)


class MaxStdMaterial(bpy.types.PropertyGroup):
    shader: EnumProperty(name='Shader', items=SHADERS, default='BLINN', update=_shader_update)
    wire: BoolProperty(name='Wire')
    faceted: BoolProperty(name='Faceted')
    soften: FloatProperty(name='Soften', default=.1, min=0, max=1)
    self_illum_color_on: BoolProperty(name='Color', update=_standard_update)
    self_illum_color: FloatVectorProperty(name='Self-Illumination', subtype='COLOR', size=3,
        default=(1, 1, 1), min=0, max=1, update=_standard_update)
    self_illum_amount: FloatProperty(name='Self-Illumination', default=0, min=0, max=100, update=_standard_update)
    bump_amount: FloatProperty(name='Bump', default=30, min=0, max=999, update=_standard_update)


class MaxMtlSlot(bpy.types.PropertyGroup):
    material: PointerProperty(type=bpy.types.Material)


class MaxMtlEditorState(bpy.types.PropertyGroup):
    slots: CollectionProperty(type=MaxMtlSlot)
    active: IntProperty(default=0, min=0)
    visible: EnumProperty(name='Sample Slots', items=[('6', '3 x 2', ''), ('15', '5 x 3', ''),
        ('24', '6 x 4', ''), ('ALL', 'All (Extension)', '')], default='6')


def new_default_material(index):
    material = bpy.data.materials.new(f'{index+1:02d} - Default')
    material.use_nodes = True
    material['max_type'] = 'STANDARD'
    material.max_diffuse = (.5, .5, .5)
    material.max_specular = (1, 1, 1)
    material.max_spec_level = 50
    material.max_glossiness = 30
    material.max_opacity = 100
    material.max_std.shader = 'BLINN'
    return material


def ensure_slots(scene):
    editor = scene.max_mtl_editor
    while len(editor.slots) < NUM_SLOTS:
        index = len(editor.slots)
        editor.slots.add().material = new_default_material(index)
    editor.active = min(editor.active, len(editor.slots)-1)
    return editor


def state(context):
    return context.scene.max_mtl_editor


def active_material(context):
    editor = state(context)
    if 0 <= editor.active < len(editor.slots):
        return editor.slots[editor.active].material
    return None


def _capture_target(operator, context):
    material = active_material(context)
    operator._target_id = material.as_pointer() if material else 0
    operator._source_scene = context.scene
    operator._source_slot = state(context).active


def _resolve_target(operator, context):
    if not hasattr(operator, '_target_id'):
        return active_material(context)
    if operator._source_scene != context.scene:
        return None
    return next((m for m in bpy.data.materials if m.as_pointer() == operator._target_id), None)


def grid_shape(editor):
    return {'6': (3, 2), '15': (5, 3), '24': (6, 4)}.get(editor.visible,
        (6, max(1, math.ceil(len(editor.slots)/6))))


def material_kind(material):
    return material.get('max_type', 'VRAY' if material.get('max_vray') else 'STANDARD') if material else 'STANDARD'


def map_node(material, channel):
    if channel not in MAP_INFO or not material or not material.node_tree:
        return None
    return material.node_tree.nodes.get(MAP_PREFIX + channel)


def map_enabled(material, channel):
    node = map_node(material, channel)
    return bool(node and node.image and node.get('max_enabled', not node.mute))


def map_badge(material, channel):
    node = map_node(material, channel)
    return ('M' if map_enabled(material, channel) else 'm') if node and node.image else ''


def map_supported(material, channel):
    node = shader(material)
    socket = MAP_INFO.get(channel, ('', None, False))[1]
    return bool(node and socket and socket in node.inputs)


def _map_mix(material, channel):
    tree = material.node_tree
    return tree.nodes.get(MAP_PREFIX + channel + '_Amount') if tree else None


def set_map_enabled(material, channel, enabled):
    texture = map_node(material, channel)
    if texture is None or material.library:
        return False
    mix = _map_mix(material, channel)
    if mix is None and texture.image and map_supported(material, channel):
        # Upgrade direct saved MaxMap links only when the user edits map state.
        set_map(material, channel, texture.image)
        mix = _map_mix(material, channel)
    texture['max_enabled'] = bool(enabled)
    texture.mute = not enabled
    if mix:
        mix.inputs[0].default_value = float(texture.get('max_amount', 100)) / 100 if enabled else 0
    invalidate_preview(material)
    return True


def set_map_amount(material, channel, amount):
    if material.library:
        return
    texture = map_node(material, channel)
    if texture:
        if channel == 'BUMP':
            material.max_std.bump_amount = amount
        else:
            texture['max_amount'] = max(0., min(100., amount))
        set_map_enabled(material, channel, map_enabled(material, channel))


def set_map(material, channel, image):
    if channel not in MAP_INFO:
        raise ValueError('Unknown material map channel')
    if material.library:
        raise ValueError('Linked materials are read-only')
    node = shader(material, create=True)
    tree = material.node_tree
    if tree is None:
        raise ValueError('This material has no editable node tree')
    texture = map_node(material, channel)
    if texture is None:
        texture = tree.nodes.new('ShaderNodeTexImage')
        texture.name = MAP_PREFIX + channel
        texture.label = MAP_INFO[channel][0]
    texture.image = image
    socket_name = MAP_INFO[channel][1]
    if node and socket_name and socket_name in node.inputs:
        destination = node.inputs[socket_name]
        mix = _map_mix(material, channel)
        if mix is None:
            mix = tree.nodes.new('ShaderNodeMixRGB')
            mix.name = MAP_PREFIX + channel + '_Amount'
            original = destination.links[0].from_socket if destination.is_linked else None
            if original and original.node == texture:
                original = None
            value = destination.default_value
            if isinstance(value, (int, float)):
                value = (value, value, value, 1)
            elif len(value) == 3:
                value = (*value, 1)
            mix.inputs[1].default_value = value
            if original:
                tree.links.new(original, mix.inputs[1])
            tree.links.new(mix.outputs[0], destination)
        mapped = texture.outputs['Color']
        if channel == 'GLOSSINESS':
            invert = tree.nodes.get(MAP_PREFIX + channel + '_Invert')
            if invert is None:
                invert = tree.nodes.new('ShaderNodeInvert')
                invert.name = MAP_PREFIX + channel + '_Invert'
            tree.links.new(mapped, invert.inputs['Color'])
            mapped = invert.outputs['Color']
        elif channel == 'BUMP':
            bump = tree.nodes.get(MAP_PREFIX + channel + '_Bump')
            if bump is None:
                bump = tree.nodes.new('ShaderNodeBump')
                bump.name = MAP_PREFIX + channel + '_Bump'
            bump.inputs['Distance'].default_value = material.max_std.bump_amount / 100
            tree.links.new(mapped, bump.inputs['Height'])
            mapped = bump.outputs['Normal']
        tree.links.new(mapped, mix.inputs[2])
    texture['max_amount'] = texture.get('max_amount', 100.)
    set_map_enabled(material, channel, True)
    return texture


def clear_map(material, channel):
    if material.library:
        raise ValueError('Linked materials are read-only')
    texture = map_node(material, channel)
    if texture is None:
        return
    tree = material.node_tree
    mix = _map_mix(material, channel)
    if mix:
        original = mix.inputs[1].links[0].from_socket if mix.inputs[1].is_linked else None
        for link in list(mix.outputs[0].links):
            if original:
                tree.links.new(original, link.to_socket)
        tree.nodes.remove(mix)
    for suffix in ('', '_Bump', '_Invert'):
        node = tree.nodes.get(MAP_PREFIX + channel + suffix)
        if node:
            tree.nodes.remove(node)
    invalidate_preview(material)


def assign_material(obj, material):
    if obj is None or material is None or not hasattr(obj.data, 'materials') or obj.library or obj.data.library:
        return False
    if obj.material_slots:
        obj.active_material = material
    else:
        obj.data.materials.append(material)
    return True


def invalidate_preview(material=None):
    if material:
        pointer = material.as_pointer()
        _preview_textures.pop(pointer, None)
        _preview_signatures.pop(pointer, None)
        material.update_tag()
        if _preview_hosts and not bpy.app.background:
            _preview_requests.add(pointer)
            if not bpy.app.timers.is_registered(_render_previews):
                bpy.app.timers.register(_render_previews, first_interval=.2)
    else:
        _preview_textures.clear()
        _preview_signatures.clear()


def _render_previews():
    pending = set(_preview_requests)
    _preview_requests.clear()
    if _preview_hosts:
        for material in bpy.data.materials:
            if material.as_pointer() in pending:
                material.preview_ensure()
                material.asset_generate_preview()
    return None


def _material_items(self, context):
    items = [(m.name, m.name, 'Use this material in the active sample') for m in bpy.data.materials]
    if not items:
        items = [('__NONE__', 'No materials', '')]
    if items != _catalogue:
        _catalogue[:] = items
    return _catalogue


class MAX_OT_mtl_slot(bpy.types.Operator):
    bl_idname = 'max.mtl_slot'
    bl_label = 'Sample Slot'
    index: IntProperty()

    def execute(self, context):
        editor = ensure_slots(context.scene)
        if not 0 <= self.index < len(editor.slots):
            return {'CANCELLED'}
        editor.active = self.index
        return {'FINISHED'}


class MAX_OT_mtl_get(bpy.types.Operator):
    bl_idname = 'max.mtl_get'
    bl_label = 'Get Material'
    bl_property = 'material'
    bl_options = {'UNDO'}
    material: EnumProperty(items=_material_items)

    def invoke(self, context, event):
        self._source_scene = context.scene
        self._source_slot = state(context).active
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

    def execute(self, context):
        if getattr(self, '_source_scene', context.scene) != context.scene:
            return {'CANCELLED'}
        material = bpy.data.materials.get(self.material)
        if material is None:
            return {'CANCELLED'}
        editor = ensure_slots(context.scene)
        index = getattr(self, '_source_slot', editor.active)
        if index >= len(editor.slots):
            return {'CANCELLED'}
        editor.slots[index].material = material
        return {'FINISHED'}


class MAX_OT_mtl_assign(bpy.types.Operator):
    bl_idname = 'max.mtl_assign'
    bl_label = 'Assign Material to Selection'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(active_material(context) and context.selected_objects)

    def execute(self, context):
        material = active_material(context)
        count = sum(assign_material(obj, material) for obj in context.selected_objects)
        return {'FINISHED'} if count else {'CANCELLED'}


class MAX_OT_mtl_reset(bpy.types.Operator):
    bl_idname = 'max.mtl_reset'
    bl_label = 'Reset Map/Mtl to Default Settings'
    bl_description = 'Reset this material, including its assigned scene users'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        _capture_target(self, context)
        return context.window_manager.invoke_confirm(self, event, message='Reset the active material and its scene users?')

    def execute(self, context):
        material = _resolve_target(self, context)
        if material is None or material.library:
            return {'CANCELLED'}
        for key in MAP_INFO:
            clear_map(material, key)
        material.max_diffuse = (.5, .5, .5)
        material.max_specular = (1, 1, 1)
        material.max_spec_level, material.max_glossiness, material.max_opacity = 50, 30, 100
        material.max_ior, material.max_two_sided = 1.5, True
        for field in material.max_std.bl_rna.properties:
            if field.identifier != 'rna_type' and not field.is_readonly:
                material.max_std.property_unset(field.identifier)
        _standard_update(material.max_std, context)
        _shader_update(material.max_std, context)
        return {'FINISHED'}


class MAX_OT_mtl_make_unique(bpy.types.Operator):
    bl_idname = 'max.mtl_make_unique'
    bl_label = 'Make Material Copy'
    bl_options = {'UNDO'}

    def execute(self, context):
        material = active_material(context)
        if not material:
            return {'CANCELLED'}
        editor = state(context)
        editor.slots[editor.active].material = material.copy()
        return {'FINISHED'}


class MAX_OT_mtl_put_library(bpy.types.Operator, ExportHelper):
    bl_idname = 'max.mtl_put_library'
    bl_label = 'Put to Library'
    filename_ext = '.blend'
    filter_glob: StringProperty(default='*.blend', options={'HIDDEN'})

    def invoke(self, context, event):
        _capture_target(self, context)
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        material = _resolve_target(self, context)
        if material is None:
            return {'CANCELLED'}
        try:
            bpy.data.libraries.write(self.filepath, {material}, fake_user=True)
        except (OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_mtl_select_by(bpy.types.Operator):
    bl_idname = 'max.mtl_select_by'
    bl_label = 'Select by Material'
    bl_options = {'UNDO'}

    def execute(self, context):
        from . import scene_explorer
        material = active_material(context)
        if not material:
            return {'CANCELLED'}
        scene_explorer.select_objects(context, [obj for obj in context.scene.objects
            if any(slot.material == material for slot in obj.material_slots)])
        return {'FINISHED'}


class MAX_OT_mtl_show_in_viewport(bpy.types.Operator):
    bl_idname = 'max.mtl_show_in_viewport'
    bl_label = 'Show Shaded Material in Viewport'

    def execute(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.shading.color_type = 'MATERIAL'
                    area.tag_redraw()
        return {'FINISHED'}


class MAX_OT_mtl_set_type(bpy.types.Operator):
    bl_idname = 'max.mtl_set_type'
    bl_label = 'Material Type'
    bl_options = {'UNDO'}
    kind: EnumProperty(items=[('STANDARD', 'Standard', ''), ('VRAY', 'VRayMtl (Principled equivalent)', ''),
                             ('PHYSICAL', 'Physical Material (Principled equivalent)', '')])

    def invoke(self, context, event):
        _capture_target(self, context)
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        self.layout.prop(self, 'kind', text='')
        self.layout.label(text='Rendered with Blender Principled shading.')

    def execute(self, context):
        if getattr(self, '_source_scene', context.scene) != context.scene:
            return {'CANCELLED'}
        material = _resolve_target(self, context)
        if material is None:
            if getattr(self, '_target_id', 0):
                return {'CANCELLED'}
            editor = ensure_slots(context.scene)
            index = getattr(self, '_source_slot', editor.active)
            if index >= len(editor.slots):
                return {'CANCELLED'}
            material = editor.slots[index].material = new_default_material(index)
        if material.library or shader(material, create=True) is None:
            return {'CANCELLED'}
        material['max_type'] = self.kind
        material['max_vray'] = self.kind == 'VRAY'
        return {'FINISHED'}


class MAX_OT_mtl_load_map(bpy.types.Operator, ImportHelper):
    bl_idname = 'max.mtl_load_map'
    bl_label = 'Bitmap'
    bl_options = {'UNDO'}
    channel: StringProperty()
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.bmp;*.exr;*.hdr;*.psd;*.webp', options={'HIDDEN'})

    def invoke(self, context, event):
        _capture_target(self, context)
        if not self._target_id:
            return {'CANCELLED'}
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        material = _resolve_target(self, context)
        if material is None or self.channel not in MAP_INFO:
            return {'CANCELLED'}
        try:
            image = bpy.data.images.load(bpy.path.abspath(self.filepath), check_existing=True)
            set_map(material, self.channel, image)
        except (RuntimeError, ValueError, OSError) as exc:
            self.report({'WARNING'}, 'Bitmap was not loaded: ' + str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_mtl_clear_map(bpy.types.Operator):
    bl_idname = 'max.mtl_clear_map'
    bl_label = 'Clear Map'
    bl_options = {'UNDO'}
    channel: StringProperty()

    def execute(self, context):
        material = active_material(context)
        if material is None or material.library or self.channel not in MAP_INFO:
            return {'CANCELLED'}
        clear_map(material, self.channel)
        return {'FINISHED'}


class MAX_OT_mtl_map_actions(bpy.types.Operator):
    bl_idname = 'max.mtl_map_actions'
    bl_label = 'Map'
    bl_options = {'INTERNAL'}
    channel: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=190)

    def draw(self, context):
        self.layout.operator('max.mtl_load_map', text='Bitmap...').channel = self.channel
        self.layout.operator('max.mtl_clear_map', text='Clear Map').channel = self.channel

    def execute(self, context):
        return {'FINISHED'}


class MAX_OT_mtl_reset_slots(bpy.types.Operator):
    bl_idname = 'max.mtl_reset_slots'
    bl_label = 'Reset Material Editor Slots'
    bl_description = 'Replace sample references. Materials assigned to objects stay unchanged'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        self._source_scene = context.scene
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if getattr(self, '_source_scene', context.scene) != context.scene:
            return {'CANCELLED'}
        editor = ensure_slots(context.scene)
        for index, slot in enumerate(editor.slots):
            slot.material = new_default_material(index)
        invalidate_preview()
        return {'FINISHED'}


class MAX_OT_mtl_add_slot(bpy.types.Operator):
    bl_idname = 'max.mtl_add_slot'
    bl_label = 'New Sample Slot'
    bl_options = {'UNDO'}

    def execute(self, context):
        editor = ensure_slots(context.scene)
        editor.slots.add().material = new_default_material(len(editor.slots)-1)
        editor.active = len(editor.slots)-1
        editor.visible = 'ALL'
        return {'FINISHED'}


class MAX_OT_mtl_get_scene(bpy.types.Operator):
    bl_idname = 'max.mtl_get_scene'
    bl_label = 'Get All Scene Materials'
    bl_options = {'UNDO'}

    def execute(self, context):
        editor = ensure_slots(context.scene)
        materials = {}
        for obj in context.scene.objects:
            for slot in obj.material_slots:
                if slot.material:
                    materials[slot.material.as_pointer()] = slot.material
        for index, material in enumerate(materials.values()):
            if index == len(editor.slots):
                editor.slots.add()
            editor.slots[index].material = material
        return {'FINISHED'}


class MAX_OT_mtl_drop(bpy.types.Operator):
    bl_idname = 'max.mtl_drop'
    bl_label = 'Drop Material'
    bl_options = {'UNDO'}
    material: StringProperty()

    def execute(self, context):
        material = bpy.data.materials.get(self.material)
        return {'FINISHED'} if assign_material(context.active_object, material) else {'CANCELLED'}


def object_at_event(context, event):
    from .create import region_under_mouse
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
    from . import max_editor_windows
    area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
    if area is None or max_editor_windows.is_host_area(area):
        return None
    rv = area.spaces.active.region_3d
    point = (event.mouse_x-region.x, event.mouse_y-region.y)
    origin = region_2d_to_origin_3d(region, rv, point)
    direction = region_2d_to_vector_3d(region, rv, point)
    hit, _, _, _, obj, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
    return obj.original if hit else None


class _MaterialPointer:
    def _begin(self, context):
        self._generation = _generation
        self._scene = context.scene
        self._windows = tuple(context.window_manager.windows)
        self._owner = context.window.as_pointer()
        self._token = str(id(self))
        self._done = False
        for window in self._windows:
            window.cursor_modal_set('EYEDROPPER')
        _pickers.append(self)
        for window in self._windows:
            if window != context.window:
                area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
                if area:
                    with context.temp_override(window=window, area=area):
                        bpy.ops.max.mtl_pointer_relay('INVOKE_DEFAULT', token=self._token)
        context.workspace.status_text_set('Pick an object. Right-click or Esc cancels.')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context=None):
        if self._done:
            return
        self._done = True
        live = tuple(bpy.context.window_manager.windows)
        for window in self._windows:
            if window in live:
                window.cursor_modal_restore()
                window.workspace.status_text_set(None)
        if self in _pickers:
            _pickers.remove(self)

    def modal(self, context, event):
        if (self._done or self._generation != _generation or self._scene != context.scene
                or self._owner not in {w.as_pointer() for w in context.window_manager.windows}):
            self._end(context)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == self._commit_event:
            obj = object_at_event(context, event)
            if obj and self._apply(context, obj):
                self._end(context)
                bpy.ops.ed.undo_push(message=self.bl_label)
                return {'FINISHED'}
            if self._commit_event == 'RELEASE':
                self._end(context)
                return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class MAX_OT_mtl_pointer_relay(bpy.types.Operator):
    """Carry one Compact drag or pick into another owned application window."""
    bl_idname = 'max.mtl_pointer_relay'
    bl_label = 'Material Pointer'
    bl_options = {'INTERNAL'}
    token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        self._picker = next((p for p in _pickers if p._token == self.token), None)
        if self._picker is None:
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if self._picker._done:
            return {'FINISHED', 'PASS_THROUGH'}
        result = self._picker.modal(context, event)
        # The initiating operator owns the undo entry. Relays never add one.
        return result


class MAX_OT_mtl_pick(_MaterialPointer, bpy.types.Operator):
    bl_idname = 'max.mtl_pick'
    bl_label = 'Pick Material from Object'
    bl_options = {'INTERNAL'}
    _commit_event = 'PRESS'

    def invoke(self, context, event):
        ensure_slots(context.scene)
        return self._begin(context)

    def _apply(self, context, obj):
        material = obj.active_material
        if material:
            editor = state(context)
            editor.slots[editor.active].material = material
        return bool(material)


class MAX_OT_mtl_drag(_MaterialPointer, bpy.types.Operator):
    bl_idname = 'max.mtl_drag'
    bl_label = 'Drag Material to Object'
    bl_options = {'INTERNAL'}
    index: IntProperty()
    _commit_event = 'RELEASE'

    def invoke(self, context, event):
        editor = ensure_slots(context.scene)
        if not 0 <= self.index < len(editor.slots):
            return {'CANCELLED'}
        self._material = editor.slots[self.index].material
        if self._material is None:
            return {'CANCELLED'}
        return self._begin(context)

    def _apply(self, context, obj):
        try:
            return assign_material(obj, self._material)
        except ReferenceError:
            return False


class MAX_OT_mtl_value(bpy.types.Operator):
    bl_idname = 'max.mtl_value'
    bl_label = 'Material Parameter'
    bl_options = {'UNDO', 'INTERNAL'}
    material: PointerProperty(type=bpy.types.Material, options={'HIDDEN', 'SKIP_SAVE'})
    field: StringProperty(options={'HIDDEN'})
    color: FloatVectorProperty(name='Color', size=3, subtype='COLOR', min=0, max=1)
    choice: EnumProperty(name='Shader', items=SHADERS)

    def invoke(self, context, event):
        self.material = self.material or active_material(context)
        if not self.material:
            return {'CANCELLED'}
        self._scene = context.scene
        data = self.material.max_std if self.field.startswith('std.') else self.material
        key = self.field.removeprefix('std.')
        value = getattr(data, key)
        if key == 'shader':
            self.choice = value
        else:
            self.color = value
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        self.layout.prop(self, 'choice' if self.field == 'std.shader' else 'color', text='')

    def execute(self, context):
        if self.material is None or self.material.library or getattr(self, '_scene', context.scene) != context.scene:
            return {'CANCELLED'}
        data = self.material.max_std if self.field.startswith('std.') else self.material
        setattr(data, self.field.removeprefix('std.'), self.choice if self.field == 'std.shader' else self.color)
        invalidate_preview(self.material)
        return {'FINISHED'}


def _icon_button(layout, op, key, fallback):
    return layout.operator(op, text='', **max_icons.ui(key, fallback))


class MAX_MT_mtl_material(bpy.types.Menu):
    bl_label = 'Material'

    def draw(self, context):
        for command in ('get', 'assign', 'make_unique', 'put_library', 'select_by', 'reset'):
            self.layout.operator('max.mtl_' + command)


class MAX_MT_mtl_modes(bpy.types.Menu):
    bl_label = 'Modes'

    def draw(self, context):
        self.layout.label(text='Compact Material Editor', icon='CHECKMARK')
        row = self.layout.row()
        row.enabled = False
        row.label(text='Slate Material Editor (unavailable)')


class MAX_MT_mtl_navigation(bpy.types.Menu):
    bl_label = 'Navigation'

    def draw(self, context):
        row = self.layout.row()
        row.enabled = False
        row.label(text='Go to Parent (no nested map editor)')
        self.layout.operator('max.mtl_get')


class MAX_MT_mtl_options(bpy.types.Menu):
    bl_label = 'Options'

    def draw(self, context):
        self.layout.prop_enum(state(context), 'visible', '6', text='3 x 2 Sample Windows')
        self.layout.prop_enum(state(context), 'visible', '15', text='5 x 3 Sample Windows')
        self.layout.prop_enum(state(context), 'visible', '24', text='6 x 4 Sample Windows')
        self.layout.operator('max.mtl_show_in_viewport')


class MAX_MT_mtl_utilities(bpy.types.Menu):
    bl_label = 'Utilities'

    def draw(self, context):
        self.layout.operator('max.mtl_reset_slots')
        self.layout.operator('max.mtl_get_scene')
        self.layout.separator()
        self.layout.menu('MAX_MT_mtl_extensions')


class MAX_MT_mtl_extensions(bpy.types.Menu):
    bl_label = 'Extensions'

    def draw(self, context):
        self.layout.operator('max.mtl_add_slot', **max_icons.ui('create', ICON_FALLBACKS['create']))
        self.layout.prop_enum(state(context), 'visible', 'ALL', text='Show All Saved Slots')
        op = self.layout.operator('max.mtl_drag', **max_icons.ui('mtl_drag', ICON_FALLBACKS['mtl_drag']))
        op.index = state(context).active


class _MaterialPanel:
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Material'

    @classmethod
    def poll(cls, context):
        # Compatibility panels are available to Advanced Shader Editor users.
        return context.area and context.area.type == 'NODE_EDITOR' and bool(active_material(context))


class MAX_PT_mtl_editor(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Material Editor'

    def draw(self, context):
        row = self.layout.row(align=True)
        for name in ('material', 'options', 'utilities'):
            row.menu('MAX_MT_mtl_' + name)
        row = self.layout.row(align=True)
        for op, key, fallback in TOOLBAR:
            _icon_button(row, op, key, fallback)
        material = active_material(context)
        if material:
            self.layout.prop(material, 'name', text='')
        self.layout.operator('max.open_editor', text='Compact Material Editor', **max_icons.ui('material_editor', 'MATERIAL')).editor = 'MATERIAL'


class MAX_PT_mtl_shader_basic(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Shader Basic Parameters'

    def draw(self, context):
        material = active_material(context)
        self.layout.prop(material.max_std, 'shader', text='')
        self.layout.prop(material, 'max_two_sided', text='2-Sided')
        row = self.layout.row()
        row.enabled = False
        row.prop(material.max_std, 'wire')
        row.prop(material.max_std, 'faceted')
        row.label(text='Face Map (unavailable)')


class MAX_PT_mtl_blinn(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Blinn Basic Parameters'

    def draw(self, context):
        material = active_material(context)
        for key, label in (('max_diffuse', 'Diffuse'), ('max_specular', 'Specular'),
                           ('max_spec_level', 'Specular Level'), ('max_glossiness', 'Glossiness'), ('max_opacity', 'Opacity')):
            self.layout.prop(material, key, text=label)
        self.layout.label(text='Principled shading equivalent')


class MAX_PT_mtl_vray(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Basic Parameters (VRayMtl)'

    def draw(self, context):
        MAX_PT_mtl_blinn.draw(self, context)

    @classmethod
    def poll(cls, context):
        return super().poll(context) and material_kind(active_material(context)) == 'VRAY'


class MAX_PT_mtl_extended(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Extended Parameters'

    def draw(self, context):
        self.layout.prop(active_material(context), 'max_ior', text='Index of Refraction')


class MAX_PT_mtl_maps(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Maps'

    def draw(self, context):
        material = active_material(context)
        for key, label, socket, color in MAP_CHANNELS:
            row = self.layout.row(align=True)
            row.label(text=label)
            row.operator('max.mtl_load_map', text=map_badge(material, key) or 'None').channel = key
            row.operator('max.mtl_clear_map', text='', icon='X').channel = key
            if not map_supported(material, key):
                row.label(text='Stored only')


TOOLBAR = (
    ('max.mtl_get', 'mtl_get', 'MATERIAL'),
    ('max.mtl_assign', 'mtl_assign', 'CHECKMARK'),
    ('max.mtl_reset', 'mtl_reset', 'TRASH'),
    ('max.mtl_make_unique', 'make_unique', 'DUPLICATE'),
    ('max.mtl_put_library', 'mtl_library', 'FILE_TICK'),
    ('max.mtl_select_by', 'mtl_select', 'RESTRICT_SELECT_OFF'),
    ('max.mtl_show_in_viewport', 'mtl_viewport', 'SHADING_TEXTURE'),
)


def _invoke(idname, **properties):
    def call(context, event):
        category, name = idname.split('.')
        return getattr(getattr(bpy.ops, category), name)('INVOKE_DEFAULT', **properties)
    call.operator = idname
    call.properties = properties
    return call


def _hit(host, bounds, action):
    host.hits.append((bounds, action))


def _label(x, y, text, size, color=(.89, .89, .89, 1)):
    from .max_editor_windows import _text
    _text(x, y, text, size, color)


def _box(x, y, width, height, color=(.27, .27, .27, 1)):
    from .max_editor_windows import _rect
    _rect(x, y, width, height, color)


def _control(host, x, y, width, height, text, action, scale, selected=False, color=None):
    _box(x, y, width, height, (.7, .7, .7, 1) if selected else (.16, .16, .16, 1))
    _box(x+scale, y+scale, width-2*scale, height-2*scale, color or (.35, .35, .35, 1))
    if text:
        import blf
        blf.size(0, round(12*scale))
        clipped = str(text)
        while clipped and blf.dimensions(0, clipped)[0] > width-8*scale:
            clipped = clipped[:-1]
        _label(x+4*scale, y+height*.3, clipped, round(12*scale))
    if action:
        _hit(host, (x, y, x+width, y+height), action)


def _field(host, context, material, path, x, y, width, label, scale, kind='number', enabled=True):
    data = material.max_std if path.startswith('std.') else material
    key = path.removeprefix('std.')
    value = getattr(data, key)
    _label(x, y+6*scale, label, round(12*scale), (.89, .89, .89, 1) if enabled else (.55, .55, .55, 1))
    start = x + width*.54
    edit = getattr(host, 'material_edit', None)
    text = edit['text'] + '|' if edit and edit['path'] == path else str(round(value, 3)) if isinstance(value, float) else str(value)
    action = ('FIELD', material, path, kind) if enabled and not material.library else None
    if kind in {'color', 'shader'}:
        action = _invoke('max.mtl_value', material=material, field=path) if enabled and not material.library else None
        if kind == 'color':
            text = ''
    _control(host, start, y, width*.46, 22*scale, text, action, scale,
             color=(*value[:3], 1) if kind == 'color' else None)


def _toggle(host, x, y, text, value, callback, scale, enabled=True):
    _control(host, x, y, 12*scale, 12*scale, '', callback if enabled else None, scale)
    if value:
        _label(x+scale, y, 'x', round(13*scale))
    _label(x+17*scale, y, text, round(12*scale), (.89, .89, .89, 1) if enabled else (.55, .55, .55, 1))
    if enabled:
        _hit(host, (x, y-3*scale, x+(18+len(text)*7)*scale, y+16*scale), callback)


def _rollout(host, title, x, y, width, scale):
    closed = getattr(host, 'material_closed', None)
    if closed is None:
        closed = host.material_closed = {'Extended Parameters', 'Maps'}
    def toggle(context, event):
        if title in closed:
            closed.remove(title)
        else:
            closed.add(title)
    toggle.rollout = title
    _control(host, x, y-23*scale, width, 23*scale,
             ('> ' if title in closed else 'v ') + title, toggle, scale, color=(.31, .31, .31, 1))
    return title not in closed, y-29*scale


def _sample(host, material, index, bounds, active, context, scale):
    x, y, right, top = bounds
    _box(x, y, right-x, top-y, (.95, .95, .95, 1) if active else (.12, .12, .12, 1))
    _box(x+scale, y+scale, right-x-2*scale, top-y-2*scale, (.48, .48, .48, 1))
    if material:
        preview = material.preview
        if preview and preview.image_size[0] and preview.image_size[1]:
            import gpu
            from gpu_extras.presets import draw_texture_2d
            pointer = material.as_pointer()
            pixels = preview.image_pixels_float
            # Native preview jobs finish asynchronously. Retire a copied GPU image
            # when their pixels change, including an update after a property edit.
            pw, ph = preview.image_size
            signature = ((pw, ph), tuple(pixels[4*((ph*y//8)*pw+pw*x//8)+channel]
                         for y in range(1, 8) for x in range(1, 8) for channel in range(3)))
            texture = _preview_textures.get(pointer)
            if texture is None or _preview_signatures.get(pointer) != signature:
                size = tuple(preview.image_size)
                texture = gpu.types.GPUTexture(size, format='RGBA16F',
                    data=gpu.types.Buffer('FLOAT', len(preview.image_pixels_float), preview.image_pixels_float[:]))
                _preview_textures[pointer] = texture
                _preview_signatures[pointer] = signature
            draw_texture_2d(texture, (x+2*scale, y+2*scale), right-x-4*scale, top-y-4*scale)
        else:
            _label(x+8*scale, y+(top-y)/2, 'Preview...', round(11*scale))
        users = [obj for obj in context.scene.objects if any(s.material == material for s in obj.material_slots)]
        first_slot = next(i for i, slot in enumerate(state(context).slots) if slot.material == material)
        if users and index == first_slot:
            _sample_corners(bounds, any(o.select_get() for o in users), scale)
    _hit(host, bounds, ('SLOT', index))


def _sample_corners(bounds, filled, scale):
    import gpu
    from gpu_extras.batch import batch_for_shader
    x, y, right, top = bounds
    inset, length = 2*scale, 7*scale
    positions = []
    for cx, cy, dx, dy in [(x+inset, y+inset, 1, 1), (x+inset, top-inset, 1, -1),
                           (right-inset, y+inset, -1, 1), (right-inset, top-inset, -1, -1)]:
        a, b, c = (cx, cy), (cx+dx*length, cy), (cx, cy+dy*length)
        positions.extend((a, b, c) if filled else (a, b, b, c, c, a))
    program = gpu.shader.from_builtin('UNIFORM_COLOR')
    program.bind()
    program.uniform_float('color', (1, 1, 1, 1))
    batch_for_shader(program, 'TRIS' if filled else 'LINES', {'pos': positions}).draw(program)


def _map_shortcut(host, material, channel, x, y, scale):
    _control(host, x, y, 19*scale, 20*scale, map_badge(material, channel),
             _invoke('max.mtl_load_map', channel=channel), scale)


def _frame_group(x, top, width, height, title, scale):
    from .max_editor_windows import _line
    color = (.43, .43, .43, 1)
    for a, b in [((x, top-height), (x+width, top-height)), ((x, top-height), (x, top)),
                 ((x+width, top-height), (x+width, top)), ((x, top), (x+width, top))]:
        _line(a, b, color)
    if title:
        _box(x+5*scale, top-7*scale, (len(title)*6.5+7)*scale, 15*scale, (.18, .18, .18, 1))
        _label(x+8*scale, top-3*scale, title, round(11*scale))


def _highlight_plot(material, x, y, width, height):
    import gpu
    from gpu_extras.batch import batch_for_shader
    _box(x, y, width, height, (.12, .12, .12, 1))
    _box(x+1, y+1, width-2, height-2, (.43, .43, .43, 1))
    # A profile of the chosen equivalent, not a second stored highlight setting.
    exponent = 2 ** (material.max_glossiness/10)
    level = material.max_spec_level/100
    points = []
    for i in range(80):
        left, right = i/80, (i+1)/80
        a = y+2 + (height-4)*level*math.cos(math.pi*(left-.5))**exponent
        b = y+2 + (height-4)*level*math.cos(math.pi*(right-.5))**exponent
        points.extend([(x+left*width, y+1), (x+left*width, a), (x+right*width, b),
                       (x+left*width, y+1), (x+right*width, b), (x+right*width, y+1)])
    program = gpu.shader.from_builtin('UNIFORM_COLOR')
    program.bind()
    program.uniform_float('color', (.85, .85, .85, 1))
    batch_for_shader(program, 'TRIS', {'pos': points}).draw(program)


def _draw_basic(host, context, material, width, top, scale):
    s = scale
    left, right = 10*s, width*.53
    half = width*.48
    _frame_group(left, top-4*s, half, 91*s, '', s)
    for index, (path, label, channel) in enumerate([('max_diffuse', 'Ambient:', 'AMBIENT'),
            ('max_diffuse', 'Diffuse:', 'DIFFUSE'), ('max_specular', 'Specular:', 'SPECULAR_COLOR')]):
        y = top-(30+26*index)*s
        _field(host, context, material, path, left+6*s, y, half-36*s, label, s, 'color',
               enabled=channel != 'AMBIENT' and shader(material) is not None)
        _map_shortcut(host, material, channel, left+half-24*s, y, s)
    _frame_group(right, top-4*s, width-right-10*s, 48*s, 'Self-Illumination', s)
    def color_mode(context, event):
        material.max_std.self_illum_color_on = not material.max_std.self_illum_color_on
    _toggle(host, right+6*s, top-33*s, 'Color', material.max_std.self_illum_color_on, color_mode, s,
            enabled=not material.library and shader(material) is not None)
    key = 'std.self_illum_color' if material.max_std.self_illum_color_on else 'std.self_illum_amount'
    _field(host, context, material, key, right+5*s, top-35*s, width-right-38*s, '', s,
           'color' if material.max_std.self_illum_color_on else 'number')
    _map_shortcut(host, material, 'SELF_ILLUM', width-33*s, top-35*s, s)
    _frame_group(right, top-64*s, width-right-10*s, 31*s, '', s)
    _field(host, context, material, 'max_opacity', right+5*s, top-90*s, width-right-38*s, 'Opacity:', s)
    _map_shortcut(host, material, 'OPACITY', width-33*s, top-90*s, s)
    _frame_group(left, top-111*s, width-20*s, 91*s, 'Specular Highlights', s)
    for index, (path, label, channel) in enumerate([('max_spec_level', 'Specular Level:', 'SPECULAR_LEVEL'),
            ('max_glossiness', 'Glossiness:', 'GLOSSINESS'), ('std.soften', 'Soften:', None)]):
        y = top-(140+25*index)*s
        _field(host, context, material, path, left+5*s, y, width*.56-20*s, label, s,
               enabled=path != 'std.soften' and shader(material) is not None)
        if channel:
            _map_shortcut(host, material, channel, width*.56-10*s, y, s)
    _highlight_plot(material, width*.69, top-192*s, width*.26, 73*s)
    _label(12*s, top-220*s, 'Principled shading equivalent', round(10*s), (.65, .65, .65, 1))
    return top-232*s


def draw_host(host, context, width, height, scale):
    """Draw the full Compact window. Hit regions share the same coordinates."""
    s = scale
    editor = state(context)
    if not editor.slots:
        return
    material = active_material(context)
    columns, rows = grid_shape(editor)
    y = height-(25 if host.native_handle else 62)*s
    _box(0, y, width, 25*s, (.95, .95, .95, 1))
    x = 5*s
    for name in ('Modes', 'Material', 'Navigation', 'Options', 'Utilities'):
        button_width = (len(name)*7+12)*s
        _label(x, y+7*s, name, round(12*s), (.05, .05, .05, 1))
        _hit(host, (x, y, x+button_width, y+25*s), _invoke('wm.call_menu', name='MAX_MT_mtl_'+name.lower()))
        x += button_width
    # Keep samples full-width at every grid size. Extra saved slots stay reachable.
    available_width = max(100*s, width-34*s)
    cell_width = available_width/columns
    cell_height = cell_width*.91
    start = min(getattr(host, 'sample_start', 0), max(0, len(editor.slots)-columns*rows))
    start -= start % columns
    host.sample_bounds = []
    top = y-5*s
    for cell in range(min(columns*rows, len(editor.slots)-start)):
        row, col = divmod(cell, columns)
        bounds = (5*s+col*cell_width, top-(row+1)*cell_height,
                  5*s+(col+1)*cell_width-s, top-row*cell_height-s)
        index = start+cell
        host.sample_bounds.append((index, bounds))
        _sample(host, editor.slots[index].material, index, bounds, index == editor.active, context, s)
    def scroll_samples(delta):
        def call(context, event):
            host.sample_start = max(0, min(len(editor.slots)-columns*rows, start+delta*columns))
        return call
    for offset, text, delta in ((0, '^', -1), (1, 'v', 1)):
        _control(host, width-25*s, top-23*s-offset*25*s, 21*s, 22*s, text, scroll_samples(delta), s)
    y = top-rows*cell_height-29*s
    for i, (idname, key, fallback) in enumerate(TOOLBAR):
        x = (5+27*i)*s
        _control(host, x, y, 24*s, 24*s, '', _invoke(idname), s)
        if not max_icons.draw(key, x+12*s, y+12*s, 21*s):
            _label(x+5*s, y+6*s, str(i+1), round(11*s))
    y -= 29*s
    _control(host, 5*s, y, 24*s, 24*s, '', _invoke('max.mtl_pick'), s)
    max_icons.draw('mtl_pick', 17*s, y+12*s, 21*s)
    if material:
        _control(host, 34*s, y, max(30*s, width-170*s), 24*s, material.name,
                 ('FIELD', material, 'name', 'text'), s)
    _control(host, max(70*s, width-131*s), y, 126*s, 24*s,
             {'STANDARD': 'Standard', 'VRAY': 'VRayMtl', 'PHYSICAL': 'Physical Material'}.get(material_kind(material), 'Material'),
             _invoke('max.mtl_set_type'), s)
    y -= 8*s
    if material is None:
        _label(10*s, y-35*s, 'Get Material or choose a material type.', round(13*s))
        return
    # Only the rollout area scrolls. Menus, samples and the name stay in place.
    import gpu
    fixed_hits = len(host.hits)
    rollout_clip = y
    gpu.state.scissor_test_set(True)
    gpu.state.scissor_set(0, 0, int(width), max(0, int(y)))
    try:
        y += host.scroll*26*s
        opened, y = _rollout(host, 'Shader Basic Parameters', 5*s, y, width-10*s, s)
        if opened:
            shader_label = dict((key, label) for key, label, description in SHADERS)[material.max_std.shader]
            _control(host, 14*s, y-30*s, width*.43, 22*s, shader_label+' v',
                     _invoke('max.mtl_value', material=material, field='std.shader'), s)
            def sided(context, event):
                material.max_two_sided = not material.max_two_sided
            _toggle(host, width*.51, y-13*s, 'Wire', material.max_std.wire, None, s, False)
            _toggle(host, width*.76, y-13*s, '2-Sided', material.max_two_sided, sided, s, enabled=not material.library)
            _toggle(host, width*.51, y-37*s, 'Face Map', False, None, s, False)
            _toggle(host, width*.76, y-37*s, 'Faceted', material.max_std.faceted, None, s, False)
            y -= 53*s
        title = 'Blinn Basic Parameters' if material_kind(material) == 'STANDARD' else 'Basic Parameters'
        opened, y = _rollout(host, title, 5*s, y, width-10*s, s)
        if opened:
            y = _draw_basic(host, context, material, width, y, s)
        opened, y = _rollout(host, 'Extended Parameters', 5*s, y, width-10*s, s)
        if opened:
            _field(host, context, material, 'max_ior', 14*s, y-23*s, width-28*s, 'Index of Refraction:', s)
            y -= 54*s
        opened, y = _rollout(host, 'Maps', 5*s, y, width-10*s, s)
        if opened:
            _label(width*.39, y-13*s, 'Amount', round(11*s))
            _label(width*.72, y-13*s, 'Map', round(11*s))
            y -= 18*s
            for channel, label, socket, color in MAP_CHANNELS:
                y -= 25*s
                texture = map_node(material, channel)
                def toggle(context, event, channel=channel):
                    set_map_enabled(material, channel, not map_enabled(material, channel))
                _toggle(host, 12*s, y+5*s, '', map_enabled(material, channel), toggle, s, bool(texture and texture.image))
                _label(32*s, y+6*s, label, round(11*s))
                amount = (material.max_std.bump_amount if channel == 'BUMP' else
                          texture.get('max_amount', 100.) if texture else 100.)
                _control(host, width*.39, y, width*.14, 22*s, str(round(amount, 2)),
                         ('AMOUNT', material, channel) if texture and map_supported(material, channel) else None, s)
                text = texture.image.name if texture and texture.image else 'None'
                if not map_supported(material, channel):
                    text = 'Stored only: ' + text
                _control(host, width*.55, y, width*.45-12*s, 22*s, text,
                         _invoke('max.mtl_load_map', channel=channel), s)
            y -= 12*s
        host.material_scroll_max = max(0, math.ceil((host.scroll*26*s-y)/max(1, 26*s)))
    finally:
        gpu.state.scissor_test_set(False)
    # Discard invisible hit regions so a scrolled rollout cannot cover the toolbar.
    host.hits[fixed_hits:] = [(bounds, action) for bounds, action in host.hits[fixed_hits:]
                            if bounds[1] >= 0 and bounds[3] <= rollout_clip]


def _write_edit(edit, value):
    material = edit['material']
    if edit['kind'] == 'amount':
        set_map_amount(material, edit['path'], float(value))
    else:
        data = material.max_std if edit['path'].startswith('std.') else material
        key = edit['path'].removeprefix('std.')
        setattr(data, key, str(value) if edit['kind'] == 'text' else int(round(float(value)))
                if isinstance(edit['original'], int) else float(value))
    invalidate_preview(material)


def host_event(host, context, event):
    """Handle slot drag origins and inline fields before the host's generic buttons."""
    if getattr(host, 'material_scene', None) != context.scene:
        close_host(host)
        host.sample_press = None
        host.scroll = 0
        prepare_host(host, context)
    edit = getattr(host, 'material_edit', None)
    if edit:
        try:
            edit['material'].name
        except ReferenceError:
            host.material_edit = None
            edit = None
    if edit:
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            _write_edit(edit, edit['original'])
            host.material_edit = None
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            try:
                _write_edit(edit, edit['text'])
                host.material_edit = None
                bpy.ops.ed.undo_push(message='Material Parameter')
            except ValueError:
                pass
        elif event.type == 'BACK_SPACE' and event.value == 'PRESS':
            edit['text'] = '' if edit['replace'] else edit['text'][:-1]
            edit['replace'] = False
        elif event.type == 'A' and event.ctrl and event.value == 'PRESS':
            edit['replace'] = True
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and edit.get('dragged'):
            host.material_edit = None
            bpy.ops.ed.undo_push(message='Material Parameter')
        elif event.type == 'MOUSEMOVE' and edit.get('dragging') and edit['kind'] != 'text':
            delta = event.mouse_y-edit['start_y']
            if abs(delta) > 3:
                value = float(edit['original']) + delta*(.01 if event.shift else 1)
                _write_edit(edit, value)
                edit['text'], edit['dragged'] = str(value), True
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            edit['dragging'] = False
        elif event.value == 'PRESS' and event.unicode and event.unicode.isprintable():
            edit['text'] = event.unicode if edit['replace'] else edit['text']+event.unicode
            edit['replace'] = False
        host.area.tag_redraw()
        return True
    press = getattr(host, 'sample_press', None)
    if press and event.type == 'MOUSEMOVE':
        if math.hypot(event.mouse_x-press[1], event.mouse_y-press[2]) > 5:
            host.sample_press = None
            bpy.ops.max.mtl_drag('INVOKE_DEFAULT', index=press[0])
        return True
    if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
        host.sample_press = None
    if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
        for bounds, action in reversed(host.hits):
            x1, y1, x2, y2 = bounds
            if (x1 <= event.mouse_region_x <= x2 and y1 <= event.mouse_region_y <= y2
                    and getattr(action, 'operator', '') == 'max.mtl_load_map'):
                bpy.ops.max.mtl_map_actions('INVOKE_DEFAULT', channel=action.properties['channel'])
                return True
    if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
        for bounds, action in reversed(host.hits):
            x1, y1, x2, y2 = bounds
            if x1 <= event.mouse_region_x <= x2 and y1 <= event.mouse_region_y <= y2:
                if not isinstance(action, tuple):
                    return False
                if action[0] == 'SLOT':
                    state(context).active = action[1]
                    host.sample_press = (action[1], event.mouse_x, event.mouse_y)
                elif action[0] in {'FIELD', 'AMOUNT'}:
                    material, path = action[1:3]
                    kind = 'amount' if action[0] == 'AMOUNT' else action[3]
                    data = material.max_std if path.startswith('std.') else material
                    value = (material.max_std.bump_amount if kind == 'amount' and path == 'BUMP' else
                             map_node(material, path).get('max_amount', 100.) if kind == 'amount' else
                             getattr(data, path.removeprefix('std.')))
                    host.material_edit = dict(material=material, path=path, kind=kind, original=value,
                        text=str(value), replace=True, start_y=event.mouse_y, dragging=True)
                host.area.tag_redraw()
                return True
    if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
        host.scroll = max(0, min(getattr(host, 'material_scroll_max', 100),
            host.scroll + (-1 if event.type == 'WHEELUPMOUSE' else 1)))
        host.area.tag_redraw()
        return True
    return False


def prepare_host(host, context):
    host.material_scene = context.scene
    ensure_slots(context.scene)
    _preview_hosts.add(host.area_pointer)
    for slot in state(context).slots:
        if slot.material:
            slot.material.preview_ensure()
            if not bpy.app.background:
                invalidate_preview(slot.material)


def close_host(host):
    _preview_hosts.discard(host.area_pointer)
    edit = getattr(host, 'material_edit', None)
    if edit:
        try:
            _write_edit(edit, edit['original'])
        except (ReferenceError, RuntimeError):
            pass
        host.material_edit = None
    invalidate_preview()
    if not _preview_hosts:
        _preview_requests.clear()
        if bpy.app.timers.is_registered(_render_previews):
            bpy.app.timers.unregister(_render_previews)


@persistent
def clear_runtime(*_):
    global _generation
    _generation += 1
    for picker in list(_pickers):
        picker._end()
    _preview_hosts.clear()
    _preview_requests.clear()
    if bpy.app.timers.is_registered(_render_previews):
        bpy.app.timers.unregister(_render_previews)
    invalidate_preview()


def open_editor(context):
    from . import max_editor_windows
    return max_editor_windows.open_host(context, 'MATERIAL')


def register_props():
    definitions = [(bpy.types.Material, 'max_std', PointerProperty(type=MaxStdMaterial)),
        (bpy.types.Scene, 'max_mtl_editor', PointerProperty(type=MaxMtlEditorState)),
        (bpy.types.Material, 'max_diffuse', FloatVectorProperty(name='Diffuse', size=3, subtype='COLOR', min=0, max=1, get=_diffuse_get, set=_diffuse_set)),
        (bpy.types.Material, 'max_specular', FloatVectorProperty(name='Specular', size=3, subtype='COLOR', min=0, max=1, get=_specular_get, set=_specular_set)),
        (bpy.types.Material, 'max_spec_level', IntProperty(name='Specular Level', min=0, max=100, get=_level_get, set=_level_set)),
        (bpy.types.Material, 'max_glossiness', IntProperty(name='Glossiness', min=0, max=100, get=_gloss_get, set=_gloss_set)),
        (bpy.types.Material, 'max_opacity', IntProperty(name='Opacity', min=0, max=100, get=_opacity_get, set=_opacity_set)),
        (bpy.types.Material, 'max_ior', FloatProperty(name='Index of Refraction', min=1, max=100, get=_ior_get, set=_ior_set)),
        (bpy.types.Material, 'max_two_sided', BoolProperty(name='2-Sided', get=_two_sided_get, set=_two_sided_set))]
    for owner, key, definition in definitions:
        if not hasattr(owner, key):
            setattr(owner, key, definition)
            _props_installed.append((owner, key))
    if clear_runtime not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(clear_runtime)


def unregister_props():
    clear_runtime()
    if clear_runtime in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_runtime)
    for owner, key in reversed(_props_installed):
        if hasattr(owner, key):
            delattr(owner, key)
    _props_installed.clear()


classes = (MaxStdMaterial, MaxMtlSlot, MaxMtlEditorState,
    MAX_OT_mtl_slot, MAX_OT_mtl_get, MAX_OT_mtl_assign, MAX_OT_mtl_reset, MAX_OT_mtl_make_unique,
    MAX_OT_mtl_put_library, MAX_OT_mtl_select_by, MAX_OT_mtl_show_in_viewport, MAX_OT_mtl_set_type,
    MAX_OT_mtl_load_map, MAX_OT_mtl_clear_map, MAX_OT_mtl_map_actions, MAX_OT_mtl_pick, MAX_OT_mtl_reset_slots,
    MAX_OT_mtl_add_slot, MAX_OT_mtl_get_scene, MAX_OT_mtl_drop, MAX_OT_mtl_drag, MAX_OT_mtl_pointer_relay, MAX_OT_mtl_value,
    MAX_MT_mtl_material, MAX_MT_mtl_modes, MAX_MT_mtl_navigation, MAX_MT_mtl_options, MAX_MT_mtl_utilities, MAX_MT_mtl_extensions,
    MAX_PT_mtl_editor, MAX_PT_mtl_shader_basic, MAX_PT_mtl_blinn, MAX_PT_mtl_vray,
    MAX_PT_mtl_extended, MAX_PT_mtl_maps)
