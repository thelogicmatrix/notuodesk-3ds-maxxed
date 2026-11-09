"""Renderer-labelled saved routes backed by explicitly named Blender equivalents."""
import math
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Menu, Operator, PropertyGroup
from bpy_extras.io_utils import ImportHelper

MATERIAL_PRESETS = (
    ('DEFAULT', 'Standard material', 'Principled material'),
    ('GLOSSY', 'Glossy material', 'Principled material with glossy reflections'),
    ('METAL', 'Metal', 'Metallic Principled material'),
    ('CHROME', 'Chrome', 'Polished metallic Principled material'),
    ('GLASS', 'Glass', 'Principled transmission material'),
    ('CAR_PAINT', 'Car paint', 'Principled coated paint approximation'),
    ('EMISSIVE', 'Self-illuminated material', 'Principled emission material'),
)
LIGHT_KINDS = (
    ('PLANE', 'Plane area light', 'Rectangular backend area light'),
    ('DISC', 'Disc area light', 'Disc-shaped backend area light'),
    ('SPHERE', 'Sphere light equivalent', 'Backend point light with a finite radius'),
    ('DOME', 'Image environment', 'World environment texture, not VRaySky'),
    ('SUN', 'Sun light', 'Backend directional sun light'),
    ('IES', 'IES light (unavailable)', 'Photometric IES creation is not supplied by this adapter'),
)
# Maxxed conveniences, not Autodesk or V-Ray defaults. Values are samples, max bounces.
QUALITY = {'DRAFT': (32, 4), 'MEDIUM': (128, 8), 'HIGH': (512, 12), 'VERY_HIGH': (1024, 16)}
_EXPOSURE_BASE = 'max_vray_exposure_base'


def available_renderers():
    """Read registered engine names without changing data during UI drawing."""
    engines = {item.identifier: item.name for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    # Workbench is built into supported Blender versions but is absent from RNA's static enum.
    engines['BLENDER_WORKBENCH'] = 'Workbench'
    def visit(base):
        for cls in base.__subclasses__():
            ident = getattr(cls, 'bl_idname', '')
            if ident:
                engines[ident] = getattr(cls, 'bl_label', ident)
            visit(cls)
    visit(bpy.types.RenderEngine)
    return tuple(engines.items())


def _shader(mat):
    if mat and mat.node_tree:
        return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    return None


def _glossiness(mat):
    shader = _shader(mat)
    return 1 - shader.inputs['Roughness'].default_value if shader else 0


def _set_glossiness(mat, value):
    shader = _shader(mat)
    if shader:
        shader.inputs['Roughness'].default_value = 1 - value


def camera_exposure(camera):
    """Exposure stops relative to f/8, 1/200 second, ISO 100."""
    settings = camera.max_vray
    if not settings.enabled or not settings.exposure:
        return 0.0
    ev100 = math.log2(settings.f_number ** 2 * settings.shutter_speed * 100 / settings.iso)
    return math.log2(8 ** 2 * 200) - ev100


@persistent
def sync_camera_exposure(*_args):
    for scene in bpy.data.scenes:
        camera = scene.camera.data if scene.camera and scene.camera.type == 'CAMERA' else None
        if camera and hasattr(camera, 'max_vray') and camera.max_vray.enabled and camera.max_vray.exposure:
            if _EXPOSURE_BASE not in scene:
                scene[_EXPOSURE_BASE] = scene.view_settings.exposure
            value = scene[_EXPOSURE_BASE] + camera_exposure(camera)
            if abs(scene.view_settings.exposure - value) > 1e-6:
                scene.view_settings.exposure = value
        elif _EXPOSURE_BASE in scene:
            scene.view_settings.exposure = scene[_EXPOSURE_BASE]
            del scene[_EXPOSURE_BASE]


def _camera_update(self, context):
    sync_camera_exposure()


class MaxVRayCamera(PropertyGroup):
    enabled: BoolProperty(name='Physical Camera Controls', default=False, update=_camera_update)
    exposure: BoolProperty(name='Exposure', default=True, update=_camera_update)
    f_number: FloatProperty(name='f-number', default=8, min=.5, max=64, update=_camera_update)
    shutter_speed: FloatProperty(name='Shutter speed (1/s)', default=200, min=.01, max=100000, update=_camera_update)
    iso: FloatProperty(name='ISO', default=100, min=1, max=100000, update=_camera_update)


def draw_camera(layout, context):
    obj = context.object
    if obj is None or obj.type != 'CAMERA':
        layout.label(text='Select a camera')
        return
    draw_vray_camera(layout, obj.data)


def draw_vray_camera(layout, camera):
    settings = camera.max_vray
    layout.prop(settings, 'enabled')
    column = layout.column(align=True)
    column.enabled = settings.enabled
    column.prop(settings, 'exposure')
    for field in ('f_number', 'shutter_speed', 'iso'):
        row = column.row(align=True)
        row.enabled = settings.exposure
        row.prop(settings, field)
    layout.label(text='Backend exposure equivalent. No native V-Ray camera model.')


def draw_vraymtl(layout, material):
    shader = _shader(material)
    if shader is None:
        layout.label(text='No Principled material equivalent')
        return
    layout.label(text='Principled material equivalent')
    for field in ('Base Color', 'Metallic', 'Roughness', 'IOR', 'Transmission Weight'):
        layout.prop(shader.inputs[field], 'default_value', text=field)
    layout.prop(material, 'max_vray_glossiness', text='Reflection Glossiness')


def draw_capabilities(layout, context):
    engines = dict(available_renderers())
    layout.label(text='Renderer: ' + engines.get(context.scene.render.engine, context.scene.render.engine))
    layout.label(text='Materials use Principled shading. Lights use the selected backend.')
    layout.label(text='No native VRayMtl, VRaySky, infinite plane or IES creation.')


def _activate(context, obj):
    for selected in context.selected_objects:
        selected.select_set(False)
    context.collection.objects.link(obj)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _new_name(base):
    for number in range(1, 1000000):
        name = f'{base}{number:03d}'
        if name not in bpy.data.objects:
            return name
    return base


class MAX_OT_vray_material(Operator):
    """Create a Principled material equivalent, not native VRayMtl shading"""
    bl_idname = 'max.vray_material'
    bl_label = 'Material Preset (Principled Equivalent)'
    bl_options = {'REGISTER', 'UNDO'}
    preset: EnumProperty(name='Preset', items=MATERIAL_PRESETS)

    def execute(self, context):
        obj = context.object
        if obj is None or not hasattr(obj.data, 'materials'):
            self.report({'WARNING'}, 'Select an object that supports materials')
            return {'CANCELLED'}
        mat = bpy.data.materials.new('Maxxed ' + dict((k, n) for k, n, _ in MATERIAL_PRESETS)[self.preset])
        mat.use_nodes = True
        shader = _shader(mat)
        shader.inputs['Roughness'].default_value = .5
        if self.preset in {'METAL', 'CHROME'}:
            shader.inputs['Metallic'].default_value = 1
            shader.inputs['Roughness'].default_value = .02 if self.preset == 'CHROME' else .25
        elif self.preset == 'GLOSSY':
            shader.inputs['Roughness'].default_value = .1
        elif self.preset == 'GLASS':
            shader.inputs['Transmission Weight'].default_value = 1
            shader.inputs['Roughness'].default_value = .02
            shader.inputs['IOR'].default_value = 1.5
        elif self.preset == 'CAR_PAINT':
            shader.inputs['Base Color'].default_value = (.3, .015, .015, 1)
            shader.inputs['Coat Weight'].default_value = 1
            shader.inputs['Coat Roughness'].default_value = .08
        elif self.preset == 'EMISSIVE':
            shader.inputs['Emission Color'].default_value = (1, 1, 1, 1)
            shader.inputs['Emission Strength'].default_value = 5
        mat['max_vray'] = True
        mat['max_type'] = 'VRAY'
        if obj.material_slots:
            obj.material_slots[obj.active_material_index].material = mat
        else:
            obj.data.materials.append(mat)
        return {'FINISHED'}


class MAX_OT_vray_light(Operator, ImportHelper):
    """Create a supported backend light or image environment equivalent"""
    bl_idname = 'max.vray_light'
    bl_label = 'Light Equivalent'
    bl_options = {'REGISTER', 'UNDO'}
    kind: EnumProperty(name='Type', items=LIGHT_KINDS)
    filepath: StringProperty(name='Environment Image', subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.hdr;*.exr;*.hdri;*.png;*.jpg', options={'HIDDEN'})

    def draw(self, context):
        self.layout.prop(self, 'kind')
        self.layout.label(text=dict((k, d) for k, _n, d in LIGHT_KINDS)[self.kind])

    def invoke(self, context, event):
        if self.kind == 'DOME' and not self.filepath:
            return ImportHelper.invoke(self, context, event)
        return self.execute(context)

    def execute(self, context):
        if self.kind == 'IES':
            self.report({'WARNING'}, 'IES photometric creation is unavailable. No substitute light was created')
            return {'CANCELLED'}
        if self.kind == 'DOME':
            if not self.filepath or not Path(self.filepath).is_file():
                self.report({'WARNING'}, 'Choose an existing environment image')
                return {'CANCELLED'}
            try:
                image = bpy.data.images.load(self.filepath, check_existing=True)
            except RuntimeError as exc:
                self.report({'WARNING'}, str(exc))
                return {'CANCELLED'}
            # A new world avoids changing worlds shared by other scenes.
            world = bpy.data.worlds.new('Maxxed Image Environment')
            world.use_nodes = True
            texture = world.node_tree.nodes.new('ShaderNodeTexEnvironment')
            texture.image = image
            background = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
            world.node_tree.links.new(texture.outputs['Color'], background.inputs['Color'])
            world['max_vray_dome'] = True
            context.scene.world = world
            return {'FINISHED'}
        backend = {'PLANE': 'AREA', 'DISC': 'AREA', 'SPHERE': 'POINT', 'SUN': 'SUN'}[self.kind]
        name = _new_name('Sun' if self.kind == 'SUN' else 'Light')
        data = bpy.data.lights.new(name, backend)
        if backend == 'AREA':
            data.shape = 'DISK' if self.kind == 'DISC' else 'RECTANGLE'
            data.size = 1
            if self.kind == 'PLANE':
                data.size_y = 1
        data.energy = 3 if backend == 'SUN' else 100
        if backend == 'POINT':
            data.shadow_soft_size = .5
        obj = bpy.data.objects.new(name, data)
        obj['max_vray_light'] = self.kind
        _activate(context, obj)
        return {'FINISHED'}


class MAX_OT_vray_camera(Operator):
    """Create a backend camera with independent physical exposure controls"""
    bl_idname = 'max.vray_camera'
    bl_label = 'Physical Camera (Backend Equivalent)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        name = _new_name('Camera')
        data = bpy.data.cameras.new(name)
        data.max_vray.enabled = True
        obj = bpy.data.objects.new(name, data)
        _activate(context, obj)
        context.scene.camera = obj
        sync_camera_exposure()
        return {'FINISHED'}


class MAX_OT_vray_plane(Operator):
    """Create a finite 200 metre ground plane, not an infinite VRayPlane"""
    bl_idname = 'max.vray_plane'
    bl_label = 'Large Ground Plane (Finite)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        units = context.scene.unit_settings
        meter = units.scale_length if units.system != 'NONE' else 1
        half = 100 / meter
        mesh = bpy.data.meshes.new('Ground Plane')
        mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
        obj = bpy.data.objects.new(_new_name('Ground'), mesh)
        _activate(context, obj)
        return {'FINISHED'}


class MAX_OT_set_renderer(Operator):
    """Select an installed production renderer by its real engine name"""
    bl_idname = 'max.set_renderer'
    bl_label = 'Production Renderer'
    engine: StringProperty()

    def execute(self, context):
        if self.engine not in dict(available_renderers()):
            self.report({'WARNING'}, 'Renderer is not installed: ' + self.engine)
            return {'CANCELLED'}
        try:
            context.scene.render.engine = self.engine
        except (TypeError, RuntimeError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_vray_render_preset(Operator):
    """Apply a Maxxed sample/bounce preset to the current supported renderer"""
    bl_idname = 'max.vray_render_preset'
    bl_label = 'Render Quality'
    quality: EnumProperty(name='Quality', items=[(k, k.replace('_', ' ').title(), f'{s} samples, {b} maximum bounces in Cycles')
                                                for k, (s, b) in QUALITY.items()])

    def execute(self, context):
        samples, bounces = QUALITY[self.quality]
        if context.scene.render.engine == 'CYCLES' and hasattr(context.scene, 'cycles'):
            context.scene.cycles.samples = samples
            context.scene.cycles.preview_samples = min(samples, 128)
            context.scene.cycles.max_bounces = bounces
        elif context.scene.render.engine in {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'} and hasattr(context.scene, 'eevee'):
            settings = context.scene.eevee
            field = 'taa_render_samples' if hasattr(settings, 'taa_render_samples') else 'taa_samples'
            if not hasattr(settings, field):
                self.report({'WARNING'}, 'Sample presets are unavailable for this Eevee version')
                return {'CANCELLED'}
            setattr(settings, field, samples)
        else:
            self.report({'WARNING'}, 'This renderer has no supported Maxxed quality adapter')
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_MT_vray(Menu):
    bl_label = 'Rendering Equivalents'

    def draw(self, context):
        layout = self.layout
        draw_capabilities(layout, context)
        layout.separator()
        for ident, label in available_renderers():
            layout.operator('max.set_renderer', text=label).engine = ident
        layout.separator()
        for kind, label, _description in LIGHT_KINDS:
            row = layout.row()
            row.enabled = kind != 'IES'
            row.operator('max.vray_light', text=label).kind = kind
        layout.operator('max.vray_camera')
        layout.operator('max.vray_plane')
        layout.separator()
        for preset, label, _description in MATERIAL_PRESETS:
            row = layout.row()
            row.enabled = context.object is not None and hasattr(context.object.data, 'materials')
            row.operator('max.vray_material', text=label + ' (Principled)').preset = preset
        for quality in QUALITY:
            layout.operator('max.vray_render_preset', text=quality.replace('_', ' ').title()).quality = quality


def register_props():
    if not hasattr(bpy.types.Camera, 'max_vray'):
        bpy.types.Camera.max_vray = PointerProperty(type=MaxVRayCamera)
    if not hasattr(bpy.types.Material, 'max_vray_glossiness'):
        bpy.types.Material.max_vray_glossiness = FloatProperty(name='Reflection Glossiness', min=0, max=1,
                                                              get=_glossiness, set=_set_glossiness)
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post,
                     bpy.app.handlers.render_pre, bpy.app.handlers.load_post):
        if sync_camera_exposure not in handlers:
            handlers.append(sync_camera_exposure)


def unregister_props():
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post,
                     bpy.app.handlers.render_pre, bpy.app.handlers.load_post):
        if sync_camera_exposure in handlers:
            handlers.remove(sync_camera_exposure)
    for scene in bpy.data.scenes:
        if _EXPOSURE_BASE in scene:
            scene.view_settings.exposure = scene[_EXPOSURE_BASE]
            del scene[_EXPOSURE_BASE]
    for owner, name in ((bpy.types.Camera, 'max_vray'), (bpy.types.Material, 'max_vray_glossiness')):
        if hasattr(owner, name):
            delattr(owner, name)


classes = (MaxVRayCamera, MAX_OT_vray_material, MAX_OT_vray_light, MAX_OT_vray_camera,
           MAX_OT_vray_plane, MAX_OT_set_renderer, MAX_OT_vray_render_preset, MAX_MT_vray)
