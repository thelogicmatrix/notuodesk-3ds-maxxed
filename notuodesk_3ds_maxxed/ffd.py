"""Free-form cages with stable owner links and explicit sub-object commands."""
import math
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_targets = {}


def bind_modifier(ob, mod):
    """Choose a UI target in memory. Safe inside Blender's read-only draw phase."""
    _targets[ob.as_pointer()] = mod


def resolve_owner(cage, refresh=True):
    if cage is None or cage.type != 'LATTICE':
        return None
    owner = cage.parent
    if owner and any(m.type == 'LATTICE' and m.object == cage for m in owner.modifiers):
        if refresh and cage.get('max_ffd_owner') != owner.name:
            cage['max_ffd_owner'] = owner.name
        return owner
    for ob in bpy.data.objects:
        if any(m.type == 'LATTICE' and m.object == cage for m in ob.modifiers):
            if refresh and cage.get('max_ffd_owner') != ob.name:
                cage['max_ffd_owner'] = ob.name
            return ob
    return None


def modifier(ob):
    if ob is None:
        return None
    if ob.type == 'LATTICE':
        cage, ob = ob, resolve_owner(ob, refresh=False)
        return next((m for m in ob.modifiers if m.type == 'LATTICE' and m.object == cage), None) if ob else None
    chosen = _targets.get(ob.as_pointer())
    try:
        if chosen and chosen.id_data == ob and ob.modifiers.get(chosen.name) == chosen:
            return chosen
    except ReferenceError:
        _targets.pop(ob.as_pointer(), None)
    name = ob.get('max_ffd_active', '')
    chosen = ob.modifiers.get(name)
    if chosen and chosen.type == 'LATTICE':
        return chosen
    index = getattr(ob, 'max_stack_index', -1)
    if 0 <= index < len(ob.modifiers) and ob.modifiers[index].type == 'LATTICE':
        return ob.modifiers[index]
    return next((m for m in reversed(ob.modifiers) if m.type == 'LATTICE'), None)


def select_modifier(ob, mod):
    if mod and mod.id_data == ob and mod.type == 'LATTICE':
        bind_modifier(ob, mod)
        ob['max_ffd_active'] = mod.name
        return True
    return False


def _cage(settings):
    mod = modifier(settings.id_data)
    return mod.object if mod else None


def _read(settings, key, default):
    cage = _cage(settings)
    if cage and 'max_ffd_' + key not in cage:
        legacy = settings.id_data.get('max_ffd', {})
        if key in legacy:
            saved = legacy[key]
            if key == 'deform_mode' and isinstance(saved, int):
                saved = ('VOLUME', 'ALL')[min(max(saved, 0), 1)]
            return saved
    return cage.get('max_ffd_' + key, default) if cage else default


def _write(settings, key, value):
    cage = _cage(settings)
    if cage:
        cage['max_ffd_' + key] = value
        owner = resolve_owner(cage)
        if owner:
            update_volume(owner, modifier(cage))


def _dimension(axis):
    def get(settings):
        cage = _cage(settings)
        return getattr(cage.data, 'points_' + axis) if cage else 2

    def set(settings, count):
        cage = _cage(settings)
        if cage:
            setattr(cage.data, 'points_' + axis, count)
            reset(resolve_owner(cage), modifier(cage))
            fit(resolve_owner(cage), modifier(cage))
    return IntProperty(name='Points ' + axis.upper(), min=2, max=64, get=get, set=set,
                       description='Changing dimensions resets every control point')


INTERPOLATION = (('KEY_BSPLINE', 'Smooth', 'B-Spline supported equivalent'),
                 ('KEY_CATMULL_ROM', 'Interpolating', 'Catmull-Rom supported equivalent'),
                 ('KEY_CARDINAL', 'Cardinal equivalent', 'Stored Cardinal interpolation'),
                 ('KEY_LINEAR', 'Linear equivalent', 'Stored linear interpolation'))


def _get_interpolation(settings):
    cage = _cage(settings)
    current = cage.data.interpolation_type_u if cage else 'KEY_BSPLINE'
    return next((i for i, item in enumerate(INTERPOLATION) if item[0] == current), 0)


def _set_interpolation(settings, value):
    cage = _cage(settings)
    if cage:
        for axis in 'uvw':
            setattr(cage.data, 'interpolation_type_' + axis, INTERPOLATION[value][0])


class MaxFFD(bpy.types.PropertyGroup):
    points_u: _dimension('u')
    points_v: _dimension('v')
    points_w: _dimension('w')
    interpolation: EnumProperty(items=INTERPOLATION, get=_get_interpolation, set=_set_interpolation)
    show_lattice: BoolProperty(name='Lattice', get=lambda s: not _cage(s).hide_viewport if _cage(s) else False,
                              set=lambda s, v: setattr(_cage(s), 'hide_viewport', not v) if _cage(s) else None)
    in_front: BoolProperty(name='See-Through', get=lambda s: _cage(s).show_in_front if _cage(s) else False,
                          set=lambda s, v: setattr(_cage(s), 'show_in_front', v) if _cage(s) else None)
    deform_mode: EnumProperty(name='Deform', items=(('VOLUME', 'Only In Volume', 'Leave points outside the cage unchanged'),
                                                  ('ALL', 'All Vertices', 'Affect points outside the cage')),
                             get=lambda s: 0 if _read(s, 'deform_mode', 'ALL') == 'VOLUME' else 1,
                             set=lambda s, v: _write(s, 'deform_mode', ('VOLUME', 'ALL')[v]))
    falloff: FloatProperty(name='Falloff', min=0, unit='LENGTH', get=lambda s: _read(s, 'falloff', 0.),
                          set=lambda s, v: _write(s, 'falloff', v))
    conform_inside: BoolProperty(name='Inside Points', get=lambda s: _read(s, 'conform_inside', True),
                                set=lambda s, v: _write(s, 'conform_inside', v))
    conform_outside: BoolProperty(name='Outside Points', get=lambda s: _read(s, 'conform_outside', True),
                                 set=lambda s, v: _write(s, 'conform_outside', v))
    offset: FloatProperty(name='Offset', unit='LENGTH', get=lambda s: _read(s, 'offset', .05),
                          set=lambda s, v: _write(s, 'offset', v))


def _input_shape(ob, mod):
    """Sample this entry's input, with all downstream display flags restored."""
    index = ob.modifiers.find(mod.name)
    later = list(ob.modifiers)[index:]
    visibility = [(entry, entry.show_viewport) for entry in later]
    evaluated = None
    try:
        for entry, visible in visibility:
            if visible:
                entry.show_viewport = False
        bpy.context.view_layer.update()
        evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        if mesh is None:
            return [], []
        return [v.co.copy() for v in mesh.vertices], [tuple(face.vertices) for face in mesh.polygons]
    finally:
        if evaluated:
            evaluated.to_mesh_clear()
        for entry, visible in visibility:
            if entry.show_viewport != visible:
                entry.show_viewport = visible


def _local_bounds(ob, mod):
    coords, _faces = _input_shape(ob, mod)
    if not coords:
        coords = [Vector((-.5, -.5, -.5)), Vector((.5, .5, .5))]
    return (Vector(tuple(min(p[i] for p in coords) for i in range(3))),
            Vector(tuple(max(p[i] for p in coords) for i in range(3))))


def fit(ob, mod=None):
    mod = mod or modifier(ob)
    if not ob or not mod or not mod.object:
        return False
    cage = mod.object
    lo, hi = _local_bounds(ob, mod)
    rest = [p.co for p in cage.data.points]
    scales = []
    for axis in range(3):
        width = max(p[axis] for p in rest) - min(p[axis] for p in rest)
        scales.append(max(hi[axis]-lo[axis], .0001) / max(width, .0001))
    cage.parent = ob
    cage.matrix_parent_inverse = Matrix.Identity(4)
    cage.matrix_basis = Matrix.Translation((lo+hi)*.5) @ Matrix.Diagonal((*scales, 1))
    cage['max_ffd_owner'] = ob.name
    update_volume(ob, mod)
    return True


def reset(ob, mod=None):
    mod = mod or modifier(ob)
    if not mod or not mod.object:
        return False
    for point in mod.object.data.points:
        point.co_deform = point.co
    mod.object.data.update_tag()
    return True


def add(ob, points=4):
    if ob is None or ob.type != 'MESH':
        return None
    count = max(2, min(int(points), 64))
    data = bpy.data.lattices.new('FFD cage')
    data.points_u = data.points_v = data.points_w = count
    for axis in 'uvw':
        setattr(data, 'interpolation_type_' + axis, 'KEY_BSPLINE')
    cage = bpy.data.objects.new('FFD cage', data)
    (ob.users_collection[0] if ob.users_collection else bpy.context.collection).objects.link(cage)
    cage.show_in_front = True
    cage.hide_render = True
    mod = ob.modifiers.new('FFD %dx%dx%d' % (count, count, count), 'LATTICE')
    mod.object = cage
    select_modifier(ob, mod)
    fit(ob, mod)
    return mod


def update_volume(ob, mod=None):
    mod = mod or modifier(ob)
    if not mod or not mod.object or ob.type != 'MESH':
        return False
    cage = mod.object
    mode = cage.get('max_ffd_deform_mode', 'ALL')
    falloff = cage.get('max_ffd_falloff', 0.)
    if mode == 'ALL' and falloff <= 0:
        mod.vertex_group = ''
        return True
    name = cage.get('max_ffd_volume_group', '')
    group = ob.vertex_groups.get(name) if name else None
    if group is None:
        group = ob.vertex_groups.new(name='_MAX FFD volume')
        cage['max_ffd_volume_group'] = group.name
    mod.vertex_group = group.name
    # Parent-relative matrices avoid depending on a pending depsgraph update.
    transform = cage.matrix_basis.inverted_safe()
    bounds = [max(abs(p.co[i]) for p in cage.data.points) for i in range(3)]
    for vertex in ob.data.vertices:
        position = transform @ vertex.co
        distance = Vector(tuple(max(abs(position[i])-bounds[i], 0) * abs(cage.scale[i]) for i in range(3))).length
        weight = (1. if distance <= 1e-7 else 0.) if mode == 'VOLUME' else max(0., 1.-distance/max(falloff, 1e-7))
        group.add([vertex.index], weight, 'REPLACE')
    return True


def conform(ob, mod=None):
    mod = mod or modifier(ob)
    if not ob or ob.type != 'MESH' or not mod or not mod.object or not ob.data.polygons:
        return False
    cage = mod.object
    vertices, faces = _input_shape(ob, mod)
    if not faces:
        return False
    tree = BVHTree.FromPolygons(vertices, faces)
    transform = cage.matrix_basis
    inverse = transform.inverted_safe()
    settings = ob.max_ffd
    for point in cage.data.points:
        position = transform @ point.co_deform
        hit, normal, _, distance = tree.find_nearest(position)
        if hit is None:
            continue
        # Nearest-face sign is a supported approximation for closed surfaces.
        inside = (position-hit).dot(normal) < 0
        if (inside and settings.conform_inside) or (not inside and settings.conform_outside):
            point.co_deform = inverse @ (hit + normal * settings.offset)
    cage.data.update_tag()
    return True


def _command_target(context):
    ob = context.object
    if ob and ob.type == 'LATTICE':
        return resolve_owner(ob), modifier(ob)
    return ob, modifier(ob)


class MAX_OT_ffd_level(bpy.types.Operator):
    bl_idname = 'max.ffd_level'
    bl_label = 'FFD Sub-Object'
    bl_options = {'REGISTER', 'UNDO'}
    level: EnumProperty(items=(('POINTS', 'Control Points', ''), ('LATTICE', 'Lattice', ''), ('OBJECT', 'Object', '')))

    def execute(self, context):
        owner, mod = _command_target(context)
        if not owner or not mod or not mod.object:
            self.report({'WARNING'}, 'Select an FFD with a cage')
            return {'CANCELLED'}
        if context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        target = owner if self.level == 'OBJECT' else mod.object
        target.hide_viewport = False
        target.hide_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target
        select_modifier(owner, mod)
        mod.object['max_ffd_owner'] = owner.name
        if self.level == 'POINTS':
            bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


class _FFDCommand:
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ob, mod = _command_target(context)
        if not ob or not mod or not mod.object:
            return {'CANCELLED'}
        return {'FINISHED'} if self.action(ob, mod) else {'CANCELLED'}


class MAX_OT_ffd_reset(_FFDCommand, bpy.types.Operator):
    bl_idname = 'max.ffd_reset'
    bl_label = 'Reset'
    action = staticmethod(reset)


class MAX_OT_ffd_fit(_FFDCommand, bpy.types.Operator):
    bl_idname = 'max.ffd_fit'
    bl_label = 'Fit to Object'
    action = staticmethod(fit)


class MAX_OT_ffd_conform(_FFDCommand, bpy.types.Operator):
    bl_idname = 'max.ffd_conform'
    bl_label = 'Conform to Shape'
    action = staticmethod(conform)


class MAX_OT_ffd_update_volume(_FFDCommand, bpy.types.Operator):
    bl_idname = 'max.ffd_update_volume'
    bl_label = 'Update Volume'
    action = staticmethod(update_volume)


class MAX_OT_ffd_animate_all(_FFDCommand, bpy.types.Operator):
    bl_idname = 'max.ffd_animate_all'
    bl_label = 'Animate All'

    @staticmethod
    def action(ob, mod):
        for point in mod.object.data.points:
            point.keyframe_insert(data_path='co_deform', frame=bpy.context.scene.frame_current)
        return True


@persistent
def _owners(_scene, _depsgraph=None):
    for cage in bpy.data.objects:
        if cage.type == 'LATTICE' and 'max_ffd_owner' in cage:
            resolve_owner(cage)


def register_props():
    if not hasattr(bpy.types.Object, 'max_ffd'):
        bpy.types.Object.max_ffd = PointerProperty(type=MaxFFD)
    if _owners not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_owners)


def unregister_props():
    _targets.clear()
    if _owners in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_owners)
    if hasattr(bpy.types.Object, 'max_ffd'):
        del bpy.types.Object.max_ffd


classes = (MaxFFD, MAX_OT_ffd_level, MAX_OT_ffd_reset, MAX_OT_ffd_animate_all,
           MAX_OT_ffd_conform, MAX_OT_ffd_fit, MAX_OT_ffd_update_volume)
