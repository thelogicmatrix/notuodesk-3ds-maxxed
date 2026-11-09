"""TurboSmooth settings belong to each subdivision entry, not to the object."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty
from .gn_mods import G

_targets = {}


def bind_modifier(ob, mod):
    _targets[ob.as_pointer()] = mod


def modifier(ob):
    if ob is None or ob.type != 'MESH':
        return None
    target = _targets.get(ob.as_pointer())
    try:
        if target and target.id_data == ob and ob.modifiers.get(target.name) == target:
            return target
    except ReferenceError:
        _targets.pop(ob.as_pointer(), None)
    chosen = ob.modifiers.get(ob.get('max_ts_active', ''))
    if chosen and chosen.type == 'SUBSURF':
        return chosen
    index = getattr(ob, 'max_stack_index', -1)
    if 0 <= index < len(ob.modifiers) and ob.modifiers[index].type == 'SUBSURF':
        return ob.modifiers[index]
    return next((m for m in reversed(ob.modifiers) if m.type == 'SUBSURF'), None)


def _key(mod):
    # persistent_uid survives save/load. 4.x builds without it use the saved name.
    return str(getattr(mod, 'persistent_uid', 0) or mod.name)


def _state(ob, mod):
    if 'max_ts_states' not in ob:
        ob['max_ts_states'] = {}
    key = _key(mod)
    if key not in ob['max_ts_states']:
        # Old object-level settings are copied once into each adopted entry.
        old = ob.get('max_turbosmooth', {})
        ob['max_ts_states'][key] = dict(render_iters_on=bool(old.get('render_iters_on', False)),
                                      render_iters=int(old.get('render_iters', mod.render_levels)),
                                      smooth_result=bool(old.get('smooth_result', True)),
                                      separate_materials=bool(old.get('separate_materials', False)),
                                      separate_smoothing=bool(old.get('separate_smoothing', False)))
    return ob['max_ts_states'][key]


def select_modifier(ob, mod):
    if mod and mod.id_data == ob and mod.type == 'SUBSURF':
        bind_modifier(ob, mod)
        ob['max_ts_active'] = mod.name
        _state(ob, mod)
        return True
    return False


def _get(settings, key, default):
    ob = settings.id_data
    mod = modifier(ob)
    states = ob.get('max_ts_states', {})
    legacy = ob.get('max_turbosmooth', {})
    return states.get(_key(mod), legacy).get(key, default) if mod else default


def _put(settings, key, value):
    ob = settings.id_data
    mod = modifier(ob)
    if mod:
        _state(ob, mod)[key] = value
        sync(ob)


def _native_get(settings, key, default):
    mod = modifier(settings.id_data)
    return getattr(mod, key, default) if mod else default


def _native_put(settings, key, value):
    ob = settings.id_data
    mod = modifier(ob)
    if mod and hasattr(mod, key):
        setattr(mod, key, value)
        sync(ob)


class MaxTurboSmooth(bpy.types.PropertyGroup):
    iterations: IntProperty(name='Iterations', min=0, max=10,
                            get=lambda s: _native_get(s, 'levels', 1), set=lambda s, v: _native_put(s, 'levels', v))
    render_iters_on: BoolProperty(name='Render Iters', get=lambda s: _get(s, 'render_iters_on', False),
                                  set=lambda s, v: _put(s, 'render_iters_on', v))
    render_iters: IntProperty(name='Render Iterations', min=0, max=10,
                              get=lambda s: _get(s, 'render_iters', 1), set=lambda s, v: _put(s, 'render_iters', v))
    isoline: BoolProperty(name='Isoline Display', get=lambda s: _native_get(s, 'show_only_control_edges', False),
                          set=lambda s, v: _native_put(s, 'show_only_control_edges', v))
    explicit_normals: BoolProperty(name='Explicit Normals', get=lambda s: _native_get(s, 'use_custom_normals', False),
                                   set=lambda s, v: _native_put(s, 'use_custom_normals', v))
    smooth_result: BoolProperty(name='Smooth Result', get=lambda s: _get(s, 'smooth_result', True),
                                set=lambda s, v: _put(s, 'smooth_result', v))
    separate_materials: BoolProperty(name='Materials', get=lambda s: _get(s, 'separate_materials', False),
                                     set=lambda s, v: _put(s, 'separate_materials', v))
    separate_smoothing: BoolProperty(name='Smoothing Groups', get=lambda s: _get(s, 'separate_smoothing', False),
                                     set=lambda s, v: _put(s, 'separate_smoothing', v))
    update_mode: EnumProperty(name='Update', items=(('ALWAYS', 'Always', 'Update in viewports and rendering'),
                                                  ('RENDER', 'When Rendering', 'Refine only for rendering')),
                              get=lambda s: 0 if _native_get(s, 'show_viewport', True) else 1,
                              set=lambda s, v: _native_put(s, 'show_viewport', v == 0))


def _field(g, name, data_type):
    node = g.nodes.new('GeometryNodeInputNamedAttribute')
    node.data_type = data_type
    g._set(node, 'Name', name)
    return node.outputs['Attribute']


def _boundary(g, field):
    node = g.nodes.new('GeometryNodeMeshFaceSetBoundaries')
    g._set(node, 'Face Group ID', field)
    return node.outputs[0]


def _smoothing_boundary(g):
    if not hasattr(bpy.types, 'FunctionNodeBitMath'):
        # Blender 4.2 has no integer bitwise node. sync supplies this edge field.
        return _field(g, '_max_ts_group_boundary', 'BOOLEAN')
    masks = []
    index = g.nodes.new('GeometryNodeInputIndex').outputs[0]
    for order in (0, 1):
        corner = g.nodes.new('GeometryNodeCornersOfEdge')
        g._set(corner, 'Edge Index', index)
        g._set(corner, 'Sort Index', order)
        face = g.nodes.new('GeometryNodeFaceOfCorner')
        g._set(face, 'Corner Index', corner.outputs['Corner Index'])
        sample = g.nodes.new('GeometryNodeSampleIndex')
        sample.data_type = 'INT'
        sample.domain = 'FACE'
        g._set(sample, 'Geometry', g.g('Geometry'))
        g._set(sample, 'Index', face.outputs['Face Index'])
        g._set(sample, 'Value', _field(g, 'max_smoothing_group', 'INT'))
        masks.append(sample.outputs['Value'])
    both = g.nodes.new('FunctionNodeBitMath')
    both.operation = 'AND'
    g._set(both, 'A', masks[0])
    g._set(both, 'B', masks[1])
    return g.m('COMPARE', both.outputs[0], 0, .1)


def _fallback_boundaries(ob):
    if hasattr(bpy.types, 'FunctionNodeBitMath'):
        return
    mesh = ob.data
    masks = mesh.attributes.get('max_smoothing_group')
    if masks is None:
        return
    neighbors = {edge.index: [] for edge in mesh.edges}
    lookup = {tuple(sorted(edge.vertices)): edge.index for edge in mesh.edges}
    for face in mesh.polygons:
        verts = list(face.vertices)
        for a, b in zip(verts, verts[1:]+verts[:1]):
            neighbors[lookup[tuple(sorted((a, b)))]].append(masks.data[face.index].value)
    attribute = mesh.attributes.get('_max_ts_group_boundary')
    if attribute is None:
        attribute = mesh.attributes.new('_max_ts_group_boundary', 'BOOLEAN', 'EDGE')
    for index, values in neighbors.items():
        hard = len(values) != 2 or (values[0] & values[1]) == 0
        if attribute.data[index].value != hard:
            attribute.data[index].value = hard


def _support_group():
    g = G('TurboSmooth surface')
    g.ng['max_ts_support'] = True
    for name, default in (('Smooth Result', True), ('Materials', False), ('Smoothing Groups', False)):
        g.inp(name, 'BOOL', default)
    material = g.nodes.new('GeometryNodeInputMaterialIndex').outputs[0]
    mat_boundary = g.m('MULTIPLY', _boundary(g, material), g.g('Materials'))
    smoothing = _smoothing_boundary(g)
    smoothing = g.m('MULTIPLY', smoothing, g.g('Smoothing Groups'))
    crease = g.m('MAXIMUM', _field(g, 'crease_edge', 'FLOAT'), g.m('MAXIMUM', mat_boundary, smoothing))
    store = g.nodes.new('GeometryNodeStoreNamedAttribute')
    store.domain = 'EDGE'
    store.data_type = 'FLOAT'
    g._set(store, 'Geometry', g.g('Geometry'))
    g._set(store, 'Name', 'crease_edge')
    g._set(store, 'Value', crease)
    shade = g.nodes.new('GeometryNodeSetShadeSmooth')
    shade.domain = 'FACE'
    g._set(shade, 'Mesh', store.outputs['Geometry'])
    # With Smooth Result off, leave incoming per-face intent unchanged.
    g._set(shade, 'Selection', g.g('Smooth Result'))
    g._set(shade, 'Shade Smooth', True)
    return g.out(shade.outputs[0])


def _legacy_smoothing(ob):
    attribute = ob.data.attributes.get('max_ts_orig_smooth')
    if attribute and attribute.domain == 'FACE' and attribute.data_type in {'BOOLEAN', 'INT'}:
        for face, saved in zip(ob.data.polygons, attribute.data):
            face.use_smooth = bool(saved.value)
        ob.data.attributes.remove(attribute)
    if 'max_ts_orig_smooth' not in ob.data and 'max_ts_orig_smooth' not in ob:
        return
    backup = ob.data.get('max_ts_orig_smooth', ob.get('max_ts_orig_smooth'))
    if backup is not None and len(backup) == len(ob.data.polygons):
        for face, saved in zip(ob.data.polygons, backup):
            face.use_smooth = bool(saved)
        for owner in (ob, ob.data):
            if 'max_ts_orig_smooth' in owner:
                del owner['max_ts_orig_smooth']


def sync(ob):
    """Refresh owned helpers, without editing base smoothing or base creases."""
    if not ob or ob.type != 'MESH':
        return
    from .gn_mods import set_input
    _legacy_smoothing(ob)
    _fallback_boundaries(ob)
    states = ob.get('max_ts_states', {})
    live = {str(getattr(m, 'persistent_uid', 0) or m.name): m for m in ob.modifiers if m.type == 'SUBSURF'}
    for helper in list(ob.modifiers):
        if helper.type != 'NODES' or not helper.node_group or not helper.node_group.get('max_ts_support'):
            continue
        owner_key = helper.get('max_ts_owner', '')
        if owner_key not in live:
            ob.modifiers.remove(helper)
    for key in list(states.keys()):
        if key not in live:
            del states[key]
    for key, mod in live.items():
        if key not in states:
            continue
        state = states[key]
        helper = next((h for h in ob.modifiers if h.type == 'NODES' and h.get('max_ts_owner') == key), None)
        if helper is None:
            helper = ob.modifiers.new('_MAX TurboSmooth surface', 'NODES')
            helper.node_group = _support_group()
            helper['max_ts_owner'] = key
        source = ob.modifiers.find(helper.name)
        target = ob.modifiers.find(mod.name)
        if source != target-1:
            ob.modifiers.move(source, target if source > target else target-1)
        for flag in ('show_viewport', 'show_render'):
            if getattr(helper, flag) != getattr(mod, flag):
                setattr(helper, flag, getattr(mod, flag))
        for name, field in (('Smooth Result', 'smooth_result'), ('Materials', 'separate_materials'),
                            ('Smoothing Groups', 'separate_smoothing')):
            target_value = bool(state.get(field, field == 'smooth_result'))
            from .gn_mods import value
            if value(helper, name) != target_value:
                set_input(helper, name, target_value)
        render_levels = int(state.get('render_iters', mod.levels)) if state.get('render_iters_on') else mod.levels
        if mod.render_levels != render_levels:
            mod.render_levels = render_levels


def add(ob, iterations=1):
    if ob is None or ob.type != 'MESH':
        return None
    mod = ob.modifiers.new('TurboSmooth', 'SUBSURF')
    mod.levels = max(0, min(int(iterations), 10))
    mod.render_levels = mod.levels
    mod.show_only_control_edges = False
    select_modifier(ob, mod)
    sync(ob)
    return mod


class MAX_OT_turbosmooth(bpy.types.Operator):
    bl_idname = 'max.turbosmooth'
    bl_label = 'TurboSmooth'
    bl_options = {'REGISTER', 'UNDO'}
    iterations: IntProperty(default=1, min=0, max=10)

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == 'MESH' and context.object.mode == 'OBJECT')

    def execute(self, context):
        for ob in context.selected_objects:
            if ob.type == 'MESH':
                add(ob, self.iterations)
        return {'FINISHED'}


_syncing = False


@persistent
def _refresh(scene, _depsgraph=None):
    global _syncing
    if _syncing:
        return
    _syncing = True
    try:
        for ob in (scene.objects if hasattr(scene, 'objects') else bpy.data.objects):
            if 'max_ts_states' in ob:
                sync(ob)
    finally:
        _syncing = False


def register_props():
    if not hasattr(bpy.types.Object, 'max_turbosmooth'):
        bpy.types.Object.max_turbosmooth = PointerProperty(type=MaxTurboSmooth)
    for handlers in (bpy.app.handlers.depsgraph_update_pre, bpy.app.handlers.load_post):
        if _refresh not in handlers:
            handlers.append(_refresh)


def unregister_props():
    _targets.clear()
    for handlers in (bpy.app.handlers.depsgraph_update_pre, bpy.app.handlers.load_post):
        if _refresh in handlers:
            handlers.remove(_refresh)
    if hasattr(bpy.types.Object, 'max_turbosmooth'):
        del bpy.types.Object.max_turbosmooth


classes = (MaxTurboSmooth, MAX_OT_turbosmooth)
