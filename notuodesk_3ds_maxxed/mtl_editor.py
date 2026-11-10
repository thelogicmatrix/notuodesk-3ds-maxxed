"""Compact samples and material controls over Blender's rendered materials."""
import math
from types import SimpleNamespace

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import max_icons

NUM_SLOTS = 24
MAX_DEFAULT_DIFFUSE = (150/255, 150/255, 150/255)
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
PHYSICAL_MAP_INFO = {
    'PHYSICAL_ROUGHNESS': ('Roughness', 'Roughness', False),
    'PHYSICAL_COATING': ('Coating', 'Coat Weight', False),
    'PHYSICAL_COAT_ROUGHNESS': ('Coating Roughness', 'Coat Roughness', False),
}
_all_map_info = {**MAP_INFO, **PHYSICAL_MAP_INFO}
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
_preview_requested = set()
_preview_hosts = set()
_pickers = []
_generation = 0
_props_installed = []
_fonts = {}


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


def bsdf(mat):
    return shader(mat)


def ensure_nodes(mat):
    return shader(mat, create=True)


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


def _field_owner(material, path):
    if path.startswith('std.'):
        return material.max_std, path[4:]
    if path.startswith('physical.'):
        return material.max_physical, path[9:]
    return material, path


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


MATERIAL_PROPS = {
    'max_diffuse': FloatVectorProperty(name='Diffuse', size=3, subtype='COLOR', min=0, max=1,
        get=_diffuse_get, set=_diffuse_set),
    'max_specular': FloatVectorProperty(name='Specular', size=3, subtype='COLOR', min=0, max=1,
        get=_specular_get, set=_specular_set),
    'max_spec_level': IntProperty(name='Specular Level', min=0, max=999, soft_max=100,
        get=_level_get, set=_level_set),
    'max_glossiness': IntProperty(name='Glossiness', min=0, max=100, get=_gloss_get, set=_gloss_set),
    'max_opacity': IntProperty(name='Opacity', min=0, max=100, subtype='PERCENTAGE',
        get=_opacity_get, set=_opacity_set),
    'max_ior': FloatProperty(name='Index of Refraction', min=1, max=10, get=_ior_get, set=_ior_set),
    'max_two_sided': BoolProperty(name='2-Sided', get=_two_sided_get, set=_two_sided_set),
}


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


def _physical_socket(name, fallback=0.):
    def get(self):
        return _socket_read(self.id_data, name, fallback)
    def set(self, value):
        _socket_write(self.id_data, name, value)
    return get, set


def _base_color_get(self):
    return tuple(self.get('base_color', _diffuse_get(self.id_data)))


def _base_color_set(self, value):
    self['base_color'] = tuple(value)
    _diffuse_set(self.id_data, tuple(v * self.base_weight for v in value))


def _base_weight_set(self, value):
    color = _base_color_get(self)
    self['base_weight'] = value
    _base_color_set(self, color)


class MaxPhysicalMaterial(bpy.types.PropertyGroup):
    base_weight: FloatProperty(name='Base Weight', min=0, max=1,
        get=lambda self: self.get('base_weight', 1.), set=_base_weight_set)
    base_color: FloatVectorProperty(name='Base Color', size=3, subtype='COLOR', min=0, max=1,
        get=_base_color_get, set=_base_color_set)
    roughness: FloatProperty(name='Roughness', min=0, max=1,
        get=_physical_socket('Roughness')[0], set=_physical_socket('Roughness')[1])
    glossiness: FloatProperty(name='Glossiness', min=0, max=1,
        get=lambda self: 1-self.roughness, set=lambda self, value: setattr(self, 'roughness', 1-value))
    use_glossiness: BoolProperty(name='Glossiness')
    metalness: FloatProperty(name='Metalness', min=0, max=1,
        get=_physical_socket('Metallic')[0], set=_physical_socket('Metallic')[1])
    transparency: FloatProperty(name='Transparency', min=0, max=1,
        get=_physical_socket('Transmission Weight')[0], set=_physical_socket('Transmission Weight')[1])
    coating: FloatProperty(name='Coating Weight', min=0, max=1,
        get=_physical_socket('Coat Weight')[0], set=_physical_socket('Coat Weight')[1])
    coat_roughness: FloatProperty(name='Coating Roughness', min=0, max=1,
        get=_physical_socket('Coat Roughness')[0], set=_physical_socket('Coat Roughness')[1])
    coat_ior: FloatProperty(name='Coating IOR', min=1, max=10,
        get=_physical_socket('Coat IOR', 1.5)[0], set=_physical_socket('Coat IOR', 1.5)[1])
    coat_color: FloatVectorProperty(name='Coating Color', size=4, subtype='COLOR', min=0, max=1,
        get=_physical_socket('Coat Tint', (1, 1, 1, 1))[0],
        set=_physical_socket('Coat Tint', (1, 1, 1, 1))[1])


class MaxMtlEditorState(bpy.types.PropertyGroup):
    slots: CollectionProperty(type=MaxMtlSlot)
    active: IntProperty(default=0, min=0)
    visible: EnumProperty(name='Sample Slots', items=[('6', '3 x 2', ''), ('15', '5 x 3', ''),
        ('24', '6 x 4', ''), ('ALL', 'All (Extension)', '')], default='6')


def new_default_material(index, kind='PHYSICAL'):
    material = bpy.data.materials.new(f'{index+1:02d} - Default')
    material.use_nodes = True
    material['max_type'] = kind
    material.max_diffuse = MAX_DEFAULT_DIFFUSE if kind == 'STANDARD' else (.5, .5, .5)
    material.max_specular = (1, 1, 1)
    material.max_spec_level = 0
    material.max_glossiness = 10
    material.max_opacity = 100
    material.max_two_sided = False
    material.max_std.shader = 'BLINN'
    if kind == 'PHYSICAL':
        material.max_physical.roughness = 0
        material.max_physical.coating = 0
        material.max_ior = 1.52
        material.max_spec_level = 50
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


def map_node(mat, channel):
    material = mat
    if channel not in _all_map_info or not material or not material.node_tree:
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
    socket = _all_map_info.get(channel, ('', None, False))[1]
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


def set_map(mat, channel, image):
    material = mat
    if channel not in _all_map_info:
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
        texture.label = _all_map_info[channel][0]
    texture.image = image
    socket_name = _all_map_info[channel][1]
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


def clear_map(mat, channel):
    material = mat
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
            _request_preview(material)
    else:
        _preview_textures.clear()
        _preview_signatures.clear()
        _preview_requested.clear()


def _request_preview(material):
    pointer = material.as_pointer()
    _preview_requested.add(pointer)
    _preview_requests.add(pointer)
    if not bpy.app.timers.is_registered(_render_previews):
        bpy.app.timers.register(_render_previews, first_interval=.2)


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
        for key in _all_map_info:
            clear_map(material, key)
        material.max_diffuse = MAX_DEFAULT_DIFFUSE if material_kind(material) == 'STANDARD' else (.5, .5, .5)
        material.max_specular = (1, 1, 1)
        material.max_spec_level, material.max_glossiness, material.max_opacity = 0, 10, 100
        material.max_ior, material.max_two_sided = 1.5, False
        for field in material.max_std.bl_rna.properties:
            if field.identifier != 'rna_type' and not field.is_readonly:
                material.max_std.property_unset(field.identifier)
        _standard_update(material.max_std, context)
        _shader_update(material.max_std, context)
        if material_kind(material) == 'PHYSICAL':
            material.max_physical.base_weight = 1
            material.max_physical.base_color = (.5, .5, .5)
            material.max_physical.roughness = 0
            material.max_physical.coating = 0
            material.max_physical.transparency = 0
            material.max_ior = 1.52
            material.max_spec_level = 50
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


class MAX_OT_mtl_sample_options(bpy.types.Operator):
    bl_idname = 'max.mtl_sample_options'
    bl_label = 'Sample Type'
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        _capture_target(self, context)
        return context.window_manager.invoke_popup(self, width=190)

    def draw(self, context):
        material = _resolve_target(self, context)
        if material:
            self.layout.prop(material, 'preview_render_type', text='')

    def execute(self, context):
        return {'FINISHED'}


class MAX_OT_mtl_id_channel(bpy.types.Operator):
    bl_idname = 'max.mtl_id_channel'
    bl_label = 'Material ID Channel'
    bl_options = {'UNDO', 'INTERNAL'}
    channel: IntProperty(name='Material ID Channel', min=0, max=32767)

    def invoke(self, context, event):
        _capture_target(self, context)
        material = _resolve_target(self, context)
        if not material or material.library:
            return {'CANCELLED'}
        self.channel = material.pass_index
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        material = _resolve_target(self, context)
        if not material or material.library:
            return {'CANCELLED'}
        material.pass_index = self.channel
        return {'FINISHED'}


class MAX_OT_mtl_refresh_sample(bpy.types.Operator):
    bl_idname = 'max.mtl_refresh_sample'
    bl_label = 'Make Preview'

    def execute(self, context):
        material = active_material(context)
        if not material:
            return {'CANCELLED'}
        invalidate_preview(material)
        _request_preview(material)
        return {'FINISHED'}


class MAX_OT_mtl_set_type(bpy.types.Operator):
    bl_idname = 'max.mtl_set_type'
    bl_label = 'Material Type'
    bl_options = {'UNDO'}
    kind: EnumProperty(items=[('STANDARD', 'Standard (Legacy)', ''), ('VRAY', 'VRayMtl (Principled equivalent)', ''),
                             ('PHYSICAL', 'Physical Material (Principled equivalent)', '')], default='PHYSICAL')

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
            material = editor.slots[index].material = new_default_material(index, kind=self.kind)
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
        if material is None or self.channel not in _all_map_info:
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
        if material is None or material.library or self.channel not in _all_map_info:
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


def _end_pointer(session):
    if session._done:
        return
    session._done = True
    for window in bpy.context.window_manager.windows:
        if window.as_pointer() in session._windows:
            window.cursor_modal_restore()
            window.workspace.status_text_set(None)
    if session in _pickers:
        _pickers.remove(session)


def _pointer_event(session, context, event):
    if (session._done or session._generation != _generation or session._scene != context.scene
            or session._owner not in {w.as_pointer() for w in context.window_manager.windows}):
        _end_pointer(session)
        return {'CANCELLED'}
    if event.type in {'ESC', 'RIGHTMOUSE'}:
        _end_pointer(session)
        return {'CANCELLED'}
    if event.type == 'LEFTMOUSE' and event.value == session.commit_event:
        obj = object_at_event(context, event)
        applied = False
        if obj:
            try:
                if session.kind == 'DRAG':
                    applied = assign_material(obj, session.material)
                elif obj.active_material:
                    editor = state(context)
                    if session.slot < len(editor.slots):
                        editor.slots[session.slot].material = obj.active_material
                        applied = True
            except ReferenceError:
                pass
        if applied:
            _end_pointer(session)
            bpy.ops.ed.undo_push(message=session.label)
            return {'FINISHED'}
        if session.commit_event == 'RELEASE':
            _end_pointer(session)
            return {'CANCELLED'}
    return {'RUNNING_MODAL'}


class _MaterialPointer:
    def _begin(self, context):
        # A relay can outlive the initiating operator's RNA. Keep its shared
        # state in Python, with no reference back to that operator.
        self._session = session = SimpleNamespace(_generation=_generation, _scene=context.scene,
            _windows=tuple(w.as_pointer() for w in context.window_manager.windows),
            _owner=context.window.as_pointer(), _token=str(id(self)), _done=False,
            kind='DRAG' if self._commit_event == 'RELEASE' else 'PICK',
            material=getattr(self, '_material', None), slot=state(context).active,
            commit_event=self._commit_event, label=self.bl_label)
        for window in context.window_manager.windows:
            window.cursor_modal_set('EYEDROPPER')
        _pickers.append(session)
        for window in context.window_manager.windows:
            if window != context.window:
                area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
                if area:
                    with context.temp_override(window=window, area=area):
                        bpy.ops.max.mtl_pointer_relay('INVOKE_DEFAULT', token=session._token)
        context.workspace.status_text_set('Pick an object. Right-click or Esc cancels.')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        return _pointer_event(self._session, context, event)


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
        return _pointer_event(self._picker, context, event)


class MAX_OT_mtl_pick(_MaterialPointer, bpy.types.Operator):
    bl_idname = 'max.mtl_pick'
    bl_label = 'Pick Material from Object'
    bl_options = {'INTERNAL'}
    _commit_event = 'PRESS'

    def invoke(self, context, event):
        ensure_slots(context.scene)
        return self._begin(context)

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

class MAX_OT_mtl_value(bpy.types.Operator):
    bl_idname = 'max.mtl_value'
    bl_label = 'Material Parameter'
    bl_options = {'UNDO', 'INTERNAL'}
    material: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    field: StringProperty(options={'HIDDEN'})
    color: FloatVectorProperty(name='Color', size=3, subtype='COLOR', min=0, max=1)
    choice: EnumProperty(name='Shader', items=SHADERS)

    def invoke(self, context, event):
        material = bpy.data.materials.get(self.material) if self.material else active_material(context)
        if material is None:
            return {'CANCELLED'}
        self._source_scene = context.scene
        self._target_id = material.as_pointer()
        data, key = _field_owner(material, self.field)
        value = getattr(data, key)
        if key == 'shader':
            self.choice = value
        else:
            self.color = value[:3]
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        self.layout.prop(self, 'choice' if self.field == 'std.shader' else 'color', text='')

    def execute(self, context):
        material = (_resolve_target(self, context) if hasattr(self, '_target_id') else
                    bpy.data.materials.get(self.material) if self.material else active_material(context))
        if material is None or material.library:
            return {'CANCELLED'}
        data, key = _field_owner(material, self.field)
        value = self.choice if self.field == 'std.shader' else self.color
        if key != 'shader' and len(getattr(data, key)) == 4:
            value = (*value, 1)
        setattr(data, key, value)
        invalidate_preview(material)
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
    bl_parent_id = 'MAX_PT_mtl_editor'

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
    bl_parent_id = 'MAX_PT_mtl_editor'

    def draw(self, context):
        material = active_material(context)
        for key, label in (('max_diffuse', 'Diffuse'), ('max_specular', 'Specular'),
                           ('max_spec_level', 'Specular Level'), ('max_glossiness', 'Glossiness'), ('max_opacity', 'Opacity')):
            self.layout.prop(material, key, text=label)
        self.layout.label(text='Principled shading equivalent')


class MAX_PT_mtl_vray(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Basic Parameters (VRayMtl)'
    bl_parent_id = 'MAX_PT_mtl_editor'

    def draw(self, context):
        MAX_PT_mtl_blinn.draw(self, context)

    @classmethod
    def poll(cls, context):
        return super().poll(context) and material_kind(active_material(context)) == 'VRAY'


class MAX_PT_mtl_extended(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Extended Parameters'
    bl_parent_id = 'MAX_PT_mtl_editor'

    def draw(self, context):
        self.layout.prop(active_material(context), 'max_ior', text='Index of Refraction')


class MAX_PT_mtl_maps(_MaterialPanel, bpy.types.Panel):
    bl_label = 'Maps'
    bl_parent_id = 'MAX_PT_mtl_editor'

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

# The Compact rows follow the supplied 2026 screenshot. None means that the
# corresponding Max operation has no implemented Blender equivalent.
COMPACT_TOOLS = (
    ('get', 'Get Material', 'max.mtl_get'),
    ('put_scene', 'Put to Scene', None),
    ('assign', 'Assign to Selection', 'max.mtl_assign'),
    ('reset', 'Reset', 'max.mtl_reset'),
    ('copy', 'Make Copy', 'max.mtl_make_unique'),
    ('unique', 'Make Unique', 'max.mtl_make_unique'),
    ('library', 'Put to Library', 'max.mtl_put_library'),
    ('id', 'Material ID Channel', 'max.mtl_id_channel'),
    ('viewport', 'Show Shaded Material in Viewport', 'max.mtl_show_in_viewport'),
    ('end', 'Show End Result', None),
    ('parent', 'Go to Parent', None),
    ('sibling', 'Go Forward to Sibling', None),
)
SAMPLE_TOOLS = (
    ('sample', 'Sample Type', 'max.mtl_sample_options'),
    ('backlight', 'Backlight', None),
    ('background', 'Background', None),
    ('tiling', 'Sample UV Tiling', None),
    ('video', 'Video Color Check', None),
    ('preview', 'Make Preview', 'max.mtl_refresh_sample'),
    ('options', 'Options', 'wm.call_menu'),
    ('select', 'Select by Material', 'max.mtl_select_by'),
    ('navigator', 'Material/Map Navigator', None),
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
    import blf
    import os
    if 'normal' not in _fonts:
        for key, filename in [('normal', 'segoeui.ttf'), ('bold', 'segoeuib.ttf')]:
            path = os.path.join(os.environ.get('WINDIR', ''), 'Fonts', filename)
            _fonts[key] = blf.load(path) if os.path.isfile(path) else 0
    font = _fonts['normal']
    blf.size(font, size)
    blf.color(font, *color)
    blf.position(font, x, y, 0)
    blf.draw(font, str(text))


def _bold(x, y, text, size):
    import blf
    _label(x, y, '', size)
    font = _fonts['bold']
    blf.size(font, size)
    blf.color(font, .94, .94, .94, 1)
    blf.position(font, x, y, 0)
    blf.draw(font, text)


def _box(x, y, width, height, color=(.27, .27, .27, 1)):
    from .max_editor_windows import _rect
    _rect(x, y, width, height, color)


def _polygon(points, color):
    import gpu
    from gpu_extras.batch import batch_for_shader
    program = gpu.shader.from_builtin('UNIFORM_COLOR')
    program.bind()
    program.uniform_float('color', color)
    positions = [p for i in range(1, len(points)-1) for p in (points[0], points[i], points[i+1])]
    batch_for_shader(program, 'TRIS', {'pos': positions}).draw(program)


def _triangle(x, y, scale, direction='DOWN', color=(.8, .8, .8, 1)):
    points = {'DOWN': [(0, 5), (8, 5), (4, 0)], 'UP': [(0, 0), (8, 0), (4, 5)],
              'RIGHT': [(0, 0), (0, 8), (5, 4)], 'LEFT': [(5, 0), (5, 8), (0, 4)]}[direction]
    _polygon([(x+a*scale, y+b*scale) for a, b in points], color)


def _tool_icon(key, x, y, s, enabled=True):
    """Independent strokes measured against the Compact toolbar reference."""
    from .max_editor_windows import _line
    ink = (.76, .78, .78, 1) if enabled else (.20, .21, .21, 1)
    dark = (.12, .16, .16, 1)
    aqua = (.49, .83, .84, 1) if enabled else (.24, .27, .27, 1)
    def line(a, b, color=ink):
        _line((x+a[0]*s, y+a[1]*s), (x+b[0]*s, y+b[1]*s), color)
    def box(a, b, w, h, color=ink):
        _box(x+a*s, y+b*s, w*s, h*s, color)
    def circle(cx, cy, radius, color=ink, filled=False):
        points = [(x+(cx+radius*math.cos(i*math.tau/24))*s,
                   y+(cy+radius*math.sin(i*math.tau/24))*s) for i in range(24)]
        if filled:
            _polygon(points, color)
        else:
            for i, point in enumerate(points):
                _line(point, points[(i+1) % len(points)], color)
    def arrow(cx, cy, direction='DOWN', color=aqua):
        _triangle(x+cx*s, y+cy*s, .6*s, direction, color)
    def checker(cx, cy, radius=6):
        circle(cx, cy, radius, aqua, True)
        for row in range(-2, 3):
            for col in range(-2, 3):
                if (row+col) % 2 and col*col+row*row < 6:
                    box(cx+col*2-1, cy+row*2-1, 2, 2, dark)
        circle(cx, cy, radius, ink)
    if key in {'sample', 'viewport', 'background'}:
        if key != 'sample':
            box(3, 3, 16, 16, dark)
        if key in {'viewport', 'background'}:
            checker(11, 11, 7)
        else:
            circle(11, 11, 8, ink, True)
            for i in range(5):
                box(2+i*4, 1, 2, 1)
                box(2+i*4, 21, 2, 1)
            for i in range(4):
                box(1, 4+i*4, 1, 2)
                box(21, 4+i*4, 1, 2)
            arrow(18, 0, color=ink)
    elif key == 'backlight':
        circle(14, 13, 7, ink, True)
        circle(14, 13, 6, dark, True)
        circle(8, 8, 6, aqua, True)
        circle(8, 8, 6, ink)
    elif key == 'tiling':
        box(3, 3, 17, 17)
        arrow(17, 0, color=ink)
    elif key == 'video':
        for i, color in enumerate([(.87, .25, .22, 1), (.26, .76, .27, 1), (.94, .72, .27, 1), (.39, .63, .70, 1)]):
            box(3+i*4, 5, 3, 14, color if enabled else ink)
        line((3, 2), (20, 2))
    elif key == 'preview':
        box(3, 3, 17, 16, dark)
        for i in range(4):
            box(4+i*4, 16, 2, 2)
            box(4+i*4, 4, 2, 2)
        line((5, 8), (5, 14))
        line((5, 14), (18, 14))
        line((18, 14), (18, 8))
        arrow(10, 7, color=(.95, .72, .26, 1) if enabled else ink)
    elif key == 'options':
        for cx, cy, radius in [(8, 13, 5), (15, 7, 4)]:
            circle(cx, cy, radius, ink if cx == 8 else (.88, .67, .18, 1))
            for i in range(8):
                angle = i*math.tau/8
                line((cx+(radius-1)*math.cos(angle), cy+(radius-1)*math.sin(angle)),
                     (cx+(radius+2)*math.cos(angle), cy+(radius+2)*math.sin(angle)))
    elif key == 'navigator':
        for row in range(2):
            cy = 6+row*9
            line((5, cy-2), (9, cy+2))
            line((5, cy+2), (9, cy-2))
            line((12, cy), (20, cy))
    elif key == 'select':
        circle(7, 14, 5)
        circle(15, 10, 5)
        _polygon([(x+12*s, y+4*s), (x+11*s, y+14*s), (x+20*s, y+7*s)], ink)
    elif key == 'get':
        for row in range(2):
            for col in range(2):
                box(3+col*7, 4+row*7, 6, 6, dark)
                box(4+col*7, 5+row*7, 4, 4, aqua)
        checker(15, 9, 5)
    elif key in {'put_scene', 'assign'}:
        line((3, 4), (20, 4))
        line((3, 4), (6, 11))
        line((20, 4), (18, 10))
        box(4, 12, 5, 4)
        box(11, 14, 5, 4)
        if key == 'assign':
            box(14, 4, 6, 7, aqua)
            arrow(14, 12)
        else:
            arrow(11, 7, 'UP')
    elif key == 'reset':
        line((5, 16), (18, 16))
        line((8, 19), (15, 19))
        for a, b in [((7, 15), (7, 3)), ((17, 15), (17, 3)), ((7, 3), (17, 3)),
                     ((10, 13), (10, 5)), ((14, 13), (14, 5))]:
            line(a, b)
    elif key in {'copy', 'unique', 'parent', 'sibling'}:
        circle(8, 7, 4)
        circle(15, 14, 4)
        line((3, 17), (8, 12))
        line((3, 17), (12, 17))
        if key in {'copy', 'unique'}:
            line((17, 2), (21, 2))
            line((19, 0), (19, 4))
        elif key == 'parent':
            arrow(2, 12, 'UP', ink)
        else:
            arrow(16, 2, 'RIGHT', ink)
    elif key == 'library':
        box(3, 3, 17, 17, dark)
        box(4, 4, 15, 15)
        box(6, 11, 11, 7, dark)
        box(7, 12, 9, 5)
        box(6, 5, 10, 4, dark)
        arrow(15, 0)
    elif key == 'id':
        box(2, 2, 18, 18)
        _label(x+6*s, y+3*s, '0', round(18*s), dark)
        arrow(18, 0, color=ink)
    elif key == 'end':
        for a, b in [((4, 3), (4, 18)), ((4, 18), (12, 18)), ((12, 18), (12, 3)),
                     ((12, 3), (8, 3)), ((8, 3), (8, 15)), ((8, 15), (4, 15))]:
            line(a, b)
        line((17, 3), (17, 17))
        arrow(14, 17, 'UP', ink)
    elif key == 'pick':
        line((4, 3), (17, 16))
        line((6, 2), (19, 15))
        line((4, 3), (6, 2))
        line((11, 15), (15, 11))
        line((13, 17), (17, 13))
        circle(18, 18, 3, ink, True)


def _toolbar_button(host, key, label, x, y, s, action=None, selected=False):
    bounds = (x, y, x+27*s, y+27*s)
    if selected:
        _rounded(x, y, 27*s, 27*s, 3*s, (.28, .45, .62, 1))
        _rounded(x+s, y+s, 25*s, 25*s, 2*s, (.36, .48, .60, 1))
    _tool_icon(key, x+2*s, y+2*s, s, action is not None)
    host.material_tools.append(dict(key=key, label=label, bounds=bounds, enabled=action is not None))
    if action:
        _hit(host, bounds, action)


def _number(host, material, path, x, y, width, s, enabled=True):
    enabled = enabled and shader(material) is not None
    data, key = _field_owner(material, path)
    value = getattr(data, key)
    edit = getattr(host, 'material_edit', None)
    text = edit['text']+'|' if edit and edit['path'] == path else str(round(value, 3))
    action = ('FIELD', material, path, 'number') if enabled and not material.library else None
    _control(host, x, y, width, 25*s, text, action, s, color=(.35, .35, .35, 1) if enabled else (.30, .30, .30, 1))
    _triangle(x+width-9*s, y+14*s, .5*s, 'UP', (.72, .72, .72, 1) if enabled else (.4, .4, .4, 1))
    _triangle(x+width-9*s, y+6*s, .5*s, 'DOWN', (.72, .72, .72, 1) if enabled else (.4, .4, .4, 1))
    if action:
        for sign in (-1, 1):
            def step(context, event, sign=sign):
                increment = 1 if isinstance(value, int) else .01
                setattr(data, key, getattr(data, key)+sign*increment)
                invalidate_preview(material)
            bottom = y if sign == -1 else y+12.5*s
            _hit(host, (x+width-12*s, bottom, x+width, bottom+12.5*s), step)


def _color(host, material, path, x, y, width, s, enabled=True):
    enabled = enabled and shader(material) is not None
    data, key = _field_owner(material, path)
    value = getattr(data, key)
    display = tuple(12.92*v if v <= .0031308 else 1.055*v**(1/2.4)-.055 for v in value[:3])
    _control(host, x, y, width, 25*s, '',
        _invoke('max.mtl_value', material=material.name, field=path) if enabled and not material.library else None,
        s, color=(*display, 1))
    from .max_editor_windows import _line
    _line((x+s, y+s), (x+width-s, y+s), (.7, .7, .7, 1))


def _physical_map(host, material, channel, x, y, s):
    enabled = channel is not None and map_supported(material, channel) and not material.library
    _control(host, x, y, 26*s, 25*s, map_badge(material, channel) if channel else '',
        _invoke('max.mtl_load_map', channel=channel) if enabled else None, s, color=(.38, .38, .38, 1))


def _combo(host, x, y, width, text, s, action=None):
    _control(host, x, y, width, 25*s, text, action, s)
    _triangle(x+width-17*s, y+10*s, s)


def _draw_physical(host, context, material, width, top, s):
    # Coordinate measurements use the 477px reference client. Only the right
    # column grows when the user resizes the window.
    unit = min(s, width/477)
    u = unit
    right = width-22*u
    opened, y = _rollout(host, 'Presets', 2*u, top, width-18*u, u)
    if opened:
        _box(2*u, y-142*u, width-18*u, 148*u, (.31, .31, .31, 1))
        _combo(host, 13*u, y-27*u, 236*u, '{Finishes}', u)
        # The reference's title tile is independent artwork, not a texture
        # copied out of an Autodesk screenshot.
        tx, ty = 13*u, y-99*u
        _box(tx, ty, 186*u, 66*u, (.15, .19, .16, 1))
        for band in range(33):
            tint = .12+.08*math.sin(band/32*math.pi)
            _box(tx, ty+band*2*u, 186*u, 2*u, (tint, tint+.04, tint+.01, 1))
        _bold(tx+13*u, ty+30*u, 'Physical', round(30*u))
        _bold(tx+30*u, ty+7*u, 'Material', round(28*u))
        _box(253*u, y-101*u, max(20*u, right-257*u), 98*u, (.37, .37, .37, 1))
        _label(163*u, y-123*u, 'Material Mode:', round(13*u))
        _combo(host, 253*u, y-132*u, max(30*u, right-257*u), 'Simple', u)
        y -= 147*u
    opened, y = _rollout(host, 'Coating Parameters', 2*u, y, width-18*u, u)
    if opened:
        _box(2*u, y-97*u, width-18*u, 103*u, (.31, .31, .31, 1))
        _frame_group(9*u, y-7*u, width-32*u, 87*u, 'Coating', u)
        _number(host, material, 'physical.coating', 17*u, y-43*u, 79*u, u)
        _physical_map(host, material, 'PHYSICAL_COATING', 98*u, y-43*u, u)
        _color(host, material, 'physical.coat_color', 127*u, y-43*u, 76*u, u)
        _physical_map(host, material, None, 205*u, y-43*u, u)
        _label(237*u, y-34*u, 'Roughness:', round(13*u))
        _number(host, material, 'physical.coat_roughness', 343*u, y-43*u, 78*u, u)
        _physical_map(host, material, 'PHYSICAL_COAT_ROUGHNESS', 423*u, y-43*u, u)
        _label(290*u, y-69*u, 'IOR:', round(13*u))
        _number(host, material, 'physical.coat_ior', 343*u, y-78*u, 78*u, u)
        y -= 103*u
    else:
        y += 2*u
    opened, y = _rollout(host, 'Basic Parameters', 2*u, y, width-18*u, u)
    if opened:
        _box(2*u, y-176*u, width-18*u, 182*u, (.31, .31, .31, 1))
        _frame_group(9*u, y-6*u, width-32*u, 74*u, 'Base Color and Reflections', u)
        row = y-44*u
        _number(host, material, 'physical.base_weight', 17*u, row, 79*u, u)
        _physical_map(host, material, None, 98*u, row, u)
        _color(host, material, 'physical.base_color', 127*u, row, 76*u, u)
        _physical_map(host, material, 'DIFFUSE', 205*u, row, u)
        def gloss_mode(context, event):
            material.max_physical.use_glossiness = not material.max_physical.use_glossiness
        mode = material.max_physical.use_glossiness
        _combo(host, 234*u, row, 105*u, 'Glossiness' if mode else 'Roughness', u, gloss_mode)
        _number(host, material, 'physical.glossiness' if mode else 'physical.roughness', 343*u, row, 78*u, u)
        _physical_map(host, material, 'GLOSSINESS' if mode else 'PHYSICAL_ROUGHNESS', 423*u, row, u)
        row -= 29*u
        _label(59*u, row+8*u, 'Metalness:', round(13*u))
        _number(host, material, 'physical.metalness', 127*u, row, 76*u, u)
        _physical_map(host, material, 'REFLECTION', 205*u, row, u)
        _label(288*u, row+8*u, 'IOR:', round(13*u))
        _number(host, material, 'max_ior', 343*u, row, 78*u, u)
        _physical_map(host, material, None, 423*u, row, u)
        y -= 92*u
        _frame_group(9*u, y-1*u, width-32*u, 74*u, 'Transparency', u)
        row = y-37*u
        _number(host, material, 'physical.transparency', 17*u, row, 79*u, u)
        _physical_map(host, material, 'REFRACTION', 98*u, row, u)
        _control(host, 127*u, row, 76*u, 25*u, '', None, u, color=(1, 1, 1, 1))
        _physical_map(host, material, None, 205*u, row, u)
        _combo(host, 234*u, row, 105*u, 'Roughness', u)
        _number(host, material, 'physical.roughness', 343*u, row, 78*u, u, enabled=False)
        _physical_map(host, material, None, 423*u, row, u)
        row -= 29*u
        _label(84*u, row+8*u, 'Depth:', round(13*u))
        _control(host, 127*u, row, 104*u, 25*u, '0.0', None, u)
        _triangle(219*u, row+14*u, .5*u, 'UP', (.4, .4, .4, 1))
        _triangle(219*u, row+6*u, .5*u, 'DOWN', (.4, .4, .4, 1))
        _toggle(host, 236*u, row+6*u, 'Thin-walled', False, None, u, False)
        _rounded(423*u, row, 26*u, 25*u, 3*u, (.32, .48, .64, 1))
        _lock(431*u, row+5*u, u)
        y -= 91*u
    return y


def _lock(x, y, s):
    from .max_editor_windows import _line
    color = (.85, .85, .85, 1)
    _rounded(x, y, 10*s, 11*s, 2*s, color)
    for i in range(12):
        a, b = math.pi*i/12, math.pi*(i+1)/12
        _line((x+(5+4*math.cos(a))*s, y+(11+4*math.sin(a))*s),
              (x+(5+4*math.cos(b))*s, y+(11+4*math.sin(b))*s), color)
    _box(x+4*s, y+3*s, 2*s, 5*s, (.2, .2, .2, 1))


def _rounded(x, y, width, height, radius, color):
    points = []
    for cx, cy, angle in [(x+radius, y+radius, 180), (x+width-radius, y+radius, 270),
                          (x+width-radius, y+height-radius, 0), (x+radius, y+height-radius, 90)]:
        for step in range(5):
            theta = math.radians(angle+step*22.5)
            points.append((cx+radius*math.cos(theta), cy+radius*math.sin(theta)))
    _polygon(points, color)


def _control(host, x, y, width, height, text, action, scale, selected=False, color=None):
    _rounded(x, y, width, height, 3*scale, (.65, .65, .65, 1) if selected else (.255, .255, .255, 1))
    _rounded(x+scale, y+scale, width-2*scale, height-2*scale, 2*scale, color or (.365, .365, .365, 1))
    if text:
        import blf
        _label(0, 0, '', round(13*scale))
        font = _fonts['normal']
        blf.size(font, round(13*scale))
        clipped = str(text)
        while clipped and blf.dimensions(font, clipped)[0] > width-8*scale:
            clipped = clipped[:-1]
        _label(x+6*scale, y+height*.3, clipped, round(13*scale))
    if action:
        _hit(host, (x, y, x+width, y+height), action)


def _field(host, context, material, path, x, y, width, label, scale, kind='number', enabled=True):
    data, key = _field_owner(material, path)
    value = getattr(data, key)
    _label(x, y+6*scale, label, round(12*scale), (.89, .89, .89, 1) if enabled else (.55, .55, .55, 1))
    start = x + width*.54
    edit = getattr(host, 'material_edit', None)
    text = edit['text'] + '|' if edit and edit['path'] == path else str(round(value, 3)) if isinstance(value, float) else str(value)
    action = ('FIELD', material, path, kind) if enabled and not material.library else None
    if kind in {'color', 'shader'}:
        action = _invoke('max.mtl_value', material=material.name, field=path) if enabled and not material.library else None
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
        closed = host.material_closed = {'Extended Parameters', 'Maps', 'Coating Parameters'}
    def toggle(context, event):
        if title in closed:
            closed.remove(title)
        else:
            closed.add(title)
    toggle.rollout = title
    _rounded(x, y-23*scale, width, 23*scale, 3*scale, (.31, .31, .31, 1))
    _triangle(x+7*scale, y-15*scale, .8*scale, 'RIGHT' if title in closed else 'DOWN')
    _bold(x+23*scale, y-16*scale, title, round(13*scale))
    for row in range(4):
        for column in range(3):
            _box(x+width-(10-column*2)*scale, y-(8+row*2)*scale, scale, scale, (.55, .55, .55, 1))
    _hit(host, (x, y-23*scale, x+width, y), toggle)
    return title not in closed, y-29*scale


def _sample(host, material, index, bounds, active, context, scale):
    x, y, right, top = bounds
    _box(x, y, right-x, top-y, (.95, .95, .95, 1) if active else (.12, .12, .12, 1))
    _box(x+scale, y+scale, right-x-2*scale, top-y-2*scale, (.48, .48, .48, 1))
    if material:
        if material.as_pointer() not in _preview_requested and not bpy.app.background:
            _request_preview(material)
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
            gpu.state.blend_set('ALPHA')
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
        _box(x+5*scale, top-7*scale, (len(title)*6.5+7)*scale, 15*scale, (.31, .31, .31, 1))
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
    update_window_title(host, context)
    host.material_tools = []
    host.material_elements = {}
    _box(0, 0, width, height-(0 if host.native_handle else 38*s), (.286, .286, .286, 1))
    y = height-(31 if host.native_handle else 69)*s
    _box(0, y, width, 31*s, (1, 1, 1, 1))
    x = 6*s
    for name in ('Modes', 'Material', 'Navigation', 'Options', 'Utilities'):
        button_width = {'Modes': 58, 'Material': 69, 'Navigation': 86, 'Options': 67, 'Utilities': 66}[name]*s
        _label(x, y+8*s, name, round(15*s), (.02, .02, .02, 1))
        _hit(host, (x, y, x+button_width, y+31*s), _invoke('wm.call_menu', name='MAX_MT_mtl_'+name.lower()))
        x += button_width
    # Keep samples full-width at every grid size. Extra saved slots stay reachable.
    available_width = max(100*s, width-65*s)
    cell_width = available_width/columns
    cell_height = cell_width*.905
    start = min(getattr(host, 'sample_start', 0), max(0, len(editor.slots)-columns*rows))
    host.sample_bounds = []
    top = y-4*s
    host.material_elements['samples'] = (5*s, top-rows*cell_height, 5*s+available_width, top)
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
    sample_bottom = top-rows*cell_height
    sx = width-60*s
    _box(sx, sample_bottom, 22*s, rows*cell_height, (.286, .286, .286, 1))
    for bottom, direction, delta in [(top-21*s, 'UP', -1), (sample_bottom, 'DOWN', 1)]:
        _box(sx, bottom, 22*s, 21*s, (.95, .95, .95, 1))
        _triangle(sx+7*s, bottom+8*s, s, direction, (.36, .36, .36, 1))
        _hit(host, (sx, bottom, sx+22*s, bottom+21*s), scroll_samples(delta))
    track = max(0, rows*cell_height-44*s)
    thumb = min(track, max(21*s, track*columns*rows/len(editor.slots)))
    fraction = start/max(1, len(editor.slots)-columns*rows)
    _box(sx, top-22*s-thumb-fraction*(track-thumb), 22*s, thumb, (.78, .78, .78, 1))
    hy = sample_bottom-22*s
    _box(5*s, hy, available_width, 20*s, (.286, .286, .286, 1))
    for hx, direction, delta in [(5*s, 'LEFT', -1), (width-81*s, 'RIGHT', 1)]:
        _box(hx, hy, 21*s, 20*s, (.95, .95, .95, 1))
        _triangle(hx+8*s, hy+6*s, s, direction, (.36, .36, .36, 1))
        _hit(host, (hx, hy, hx+21*s, hy+20*s), scroll_samples(delta))
    _box(26*s, hy, 21*s, 20*s, (.78, .78, .78, 1))
    for index, (key, label, operator) in enumerate(SAMPLE_TOOLS):
        action = _invoke(operator, name='MAX_MT_mtl_options') if key == 'options' else _invoke(operator) if operator else None
        _toolbar_button(host, key, label, width-34*s, top-(27+30*index)*s, s, action)
    y = hy-38*s
    positions = (7, 35, 75, 111, 148, 185, 225, 265, 302, 341, 370, 398)
    for position, (key, label, operator) in zip(positions, COMPACT_TOOLS):
        action = _invoke(operator) if operator else None
        if key == 'unique' and (not material or material.users < 2):
            action = None
        if key == 'assign' and not context.selected_objects:
            action = None
        _toolbar_button(host, key, label, position*s, y, s, action, selected=key in {'viewport', 'end'})
    from .max_editor_windows import _line
    for position in (69, 140, 218, 294, 333):
        _line((position*s, y+3*s), (position*s, y+23*s), (.20, .20, .20, 1))
    host.material_elements['horizontal-toolbar'] = (5*s, y, width-37*s, y+27*s)
    host.material_elements['vertical-toolbar'] = (width-34*s, top-267*s, width-7*s, top)
    y -= 31*s
    _toolbar_button(host, 'pick', 'Pick Material from Object', 104*s, y-2*s, s, _invoke('max.mtl_pick'))
    if material:
        _control(host, 137*s, y, max(30*s, width-276*s), 24*s, material.name,
                 ('FIELD', material, 'name', 'text'), s)
        _triangle(width-156*s, y+10*s, s)
        _hit(host, (width-164*s, y, width-139*s, y+24*s), _invoke('max.mtl_get'))
    _control(host, max(70*s, width-134*s), y, 117*s, 24*s,
             {'STANDARD': 'Standard (Legacy)', 'VRAY': 'VRayMtl', 'PHYSICAL': 'Physical Material'}.get(material_kind(material), 'Material'),
             _invoke('max.mtl_set_type'), s)
    host.material_elements['name-type'] = (104*s, y, width-17*s, y+25*s)
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
        if material_kind(material) == 'PHYSICAL':
            host.material_elements['physical'] = (2*s, 0, width-16*s, y)
            y = _draw_physical(host, context, material, width, y, s)
        else:
            opened, y = _rollout(host, 'Shader Basic Parameters', 5*s, y, width-10*s, s)
            if opened:
                shader_label = dict((key, label) for key, label, description in SHADERS)[material.max_std.shader]
                _combo(host, 14*s, y-30*s, width*.43, shader_label, s,
                    _invoke('max.mtl_value', material=material.name, field='std.shader'))
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
        _box(width-9*s, 0, 7*s, rollout_clip, (.23, .23, .23, 1))
        thumb = max(24*s, rollout_clip/(host.material_scroll_max+1))
        _rounded(width-8*s, max(0, rollout_clip-thumb-host.scroll*6*s), 5*s, thumb, 2*s, (.39, .39, .39, 1))
    finally:
        gpu.state.scissor_test_set(False)
    # Discard invisible hit regions so a scrolled rollout cannot cover the toolbar.
    host.hits[fixed_hits:] = [(bounds, action) for bounds, action in host.hits[fixed_hits:]
                            if bounds[1] >= 0 and bounds[3] <= rollout_clip]


def window_title(context):
    material = active_material(context)
    return 'Material Editor - '+(material.name if material else 'None')


def update_window_title(host, context):
    title = window_title(context)
    if getattr(host, 'material_title', None) == title:
        return
    host.material_title = title
    if host.native_handle:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.SetWindowTextW(wintypes.HWND(host.native_handle), title)


def _write_edit(edit, value):
    material = edit['material']
    if edit['kind'] == 'amount':
        set_map_amount(material, edit['path'], float(value))
    else:
        data, key = _field_owner(material, edit['path'])
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
                    data, key = _field_owner(material, path)
                    value = (material.max_std.bump_amount if kind == 'amount' and path == 'BUMP' else
                             map_node(material, path).get('max_amount', 100.) if kind == 'amount' else
                             getattr(data, key))
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


def close_host(host):
    _preview_hosts.discard(host.area_pointer)
    for session in list(_pickers):
        _end_pointer(session)
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
        _end_pointer(picker)
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
        (bpy.types.Material, 'max_physical', PointerProperty(type=MaxPhysicalMaterial)),
        (bpy.types.Scene, 'max_mtl_editor', PointerProperty(type=MaxMtlEditorState))]
    definitions.extend((bpy.types.Material, key, definition) for key, definition in MATERIAL_PROPS.items())
    for owner, key, definition in definitions:
        if not hasattr(owner, key):
            setattr(owner, key, definition)
            _props_installed.append((owner, key))
    if clear_runtime not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(clear_runtime)
    from . import max_editor_windows
    max_editor_windows.register_material_adapter(open_editor)


def unregister_props():
    clear_runtime()
    from . import max_editor_windows
    if max_editor_windows._material_adapter == open_editor:
        max_editor_windows.register_material_adapter(None)
    if clear_runtime in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_runtime)
    for owner, key in reversed(_props_installed):
        if hasattr(owner, key):
            delattr(owner, key)
    _props_installed.clear()


classes = (MaxStdMaterial, MaxPhysicalMaterial, MaxMtlSlot, MaxMtlEditorState,
    MAX_OT_mtl_slot, MAX_OT_mtl_get, MAX_OT_mtl_assign, MAX_OT_mtl_reset, MAX_OT_mtl_make_unique,
    MAX_OT_mtl_put_library, MAX_OT_mtl_select_by, MAX_OT_mtl_show_in_viewport, MAX_OT_mtl_set_type,
    MAX_OT_mtl_sample_options, MAX_OT_mtl_id_channel, MAX_OT_mtl_refresh_sample,
    MAX_OT_mtl_load_map, MAX_OT_mtl_clear_map, MAX_OT_mtl_map_actions, MAX_OT_mtl_pick, MAX_OT_mtl_reset_slots,
    MAX_OT_mtl_add_slot, MAX_OT_mtl_get_scene, MAX_OT_mtl_drop, MAX_OT_mtl_drag, MAX_OT_mtl_pointer_relay, MAX_OT_mtl_value,
    MAX_MT_mtl_material, MAX_MT_mtl_modes, MAX_MT_mtl_navigation, MAX_MT_mtl_options, MAX_MT_mtl_utilities, MAX_MT_mtl_extensions,
    MAX_PT_mtl_editor, MAX_PT_mtl_shader_basic, MAX_PT_mtl_blinn, MAX_PT_mtl_vray,
    MAX_PT_mtl_extended, MAX_PT_mtl_maps)
