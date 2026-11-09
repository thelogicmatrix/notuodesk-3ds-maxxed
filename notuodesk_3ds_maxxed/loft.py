"""Live Loft compound objects, with spline picking and Geometry Nodes skinning."""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.geometry import interpolate_bezier

from . import create, gn_mods
from .operators import max_name

GROUP_NAME = gn_mods.PREFIX + 'Loft'
_syncing = False
MODES = (('MOVE', 'Move', 'Hide the source after using it'),
         ('COPY', 'Copy', 'Use an independent copy of the source'),
         ('INSTANCE', 'Instance', 'Keep a live reference to the source'))
FIELDS = (('cap_start', 'Cap Start'), ('cap_end', 'Cap End'),
          ('shape_steps', 'Shape Steps'), ('path_steps', 'Path Steps'),
          ('adaptive', 'Adaptive Path Steps'), ('contour', 'Contour'),
          ('banking', 'Banking'), ('flip_normals', 'Flip Normals'),
          ('smooth_length', 'Smooth Length'), ('smooth_width', 'Smooth Width'),
          ('shape_level', 'Shape Level'), ('scale_start', 'Scale Start'),
          ('scale_end', 'Scale End'), ('twist', 'Twist'))


def valid_spline(ob):
    if ob is None or ob.type != 'CURVE' or len(ob.data.splines) != 1:
        return False
    sp = ob.data.splines[0]
    return sp.type in {'POLY', 'BEZIER'} and len(sp.bezier_points if sp.type == 'BEZIER' else sp.points) >= 2


def modifier(ob):
    if ob is None:
        return None
    return next((m for m in ob.modifiers if m.type == 'NODES' and m.node_group
                 and m.node_group.get('max_loft')), None)


def is_loft(ob):
    return ob is not None and ob.max_loft.enabled and modifier(ob) is not None


def _node(g, kind, **inputs):
    n = g.nodes.new(kind)
    for name, value in inputs.items():
        if isinstance(value, str):
            n.inputs[name].default_value = value
        else:
            g._set(n, name, value)
    return n


def _capture(g, geo, fields):
    n = g.nodes.new('GeometryNodeCaptureAttribute')
    n.domain = 'POINT'
    for name, kind, value in fields:
        n.capture_items.new(kind, name)
        g.links.new(value, n.inputs[name])
    g.links.new(geo, n.inputs['Geometry'])
    return n


def _sample(g, curve, value, kind='FLOAT'):
    n = g.nodes.new('GeometryNodeSampleCurve')
    n.data_type = kind
    g.links.new(curve, n.inputs['Curves'])
    g.links.new(value, n.inputs['Value'])
    return n


def _switch(g, kind, test, a, b):
    n = g.nodes.new('GeometryNodeSwitch')
    n.input_type = kind
    for key, value in (('Switch', test), ('False', a), ('True', b)):
        g._set(n, key, value)
    return n.outputs['Output']


def _scale(g, vector, amount):
    n = g.nodes.new('ShaderNodeVectorMath')
    n.operation = 'SCALE'
    g._set(n, 0, vector)
    g._set(n, 'Scale', amount)
    return n.outputs['Vector']


def _steps(g, curve, steps):
    # Subdivide first, then evaluate once per segment. This keeps POLY corners
    # and Bezier curvature while giving Steps intermediate points per segment.
    sub = _node(g, 'GeometryNodeSubdivideCurve', Curve=curve, Cuts=steps)
    res = _node(g, 'GeometryNodeSetSplineResolution', Curve=sub.outputs[0], Resolution=1)
    poly = g.nodes.new('GeometryNodeResampleCurve')
    if hasattr(poly, 'mode'):
        poly.mode = 'EVALUATED'
    else:
        poly.inputs['Mode'].default_value = 'Evaluated'
    g.links.new(res.outputs[0], poly.inputs['Curve'])
    return poly.outputs[0]


def _adaptive_path(g, curve):
    """Add the single shape's level as a main path division."""
    factor = g.nodes.new('GeometryNodeSplineParameter').outputs['Factor']
    cyclic = g.nodes.new('GeometryNodeInputSplineCyclic').outputs[0]
    cap = _capture(g, curve, [('Level', 'FLOAT', factor)])
    points = g.nodes.new('GeometryNodeCurveToPoints')
    points.mode = 'EVALUATED'
    g.links.new(cap.outputs['Geometry'], points.inputs['Curve'])
    level = g.m('DIVIDE', g.g('Shape Level'), 100.0)
    order = _node(g, 'GeometryNodeStoreNamedAttribute', Geometry=points.outputs['Points'],
                  Name='max_loft_order', Value=cap.outputs['Level'])
    order.data_type = 'FLOAT'
    order.domain = 'POINT'
    sample = _sample(g, curve, factor)
    g.links.new(level, sample.inputs['Factor'])
    extra = _node(g, 'GeometryNodePoints', Count=1, Position=sample.outputs['Position'])
    extra_order = _node(g, 'GeometryNodeStoreNamedAttribute', Geometry=extra.outputs['Points'],
                        Name='max_loft_order', Value=level)
    extra_order.data_type = 'FLOAT'
    extra_order.domain = 'POINT'
    # Replace a coincident point rather than creating a zero-length segment.
    near = g.m('LESS_THAN', g.m('ABSOLUTE', g.m('SUBTRACT', cap.outputs['Level'], level)), 1e-5)
    delete = _node(g, 'GeometryNodeDeleteGeometry', Geometry=order.outputs[0], Selection=near)
    delete.domain = 'POINT'
    join = g.nodes.new('GeometryNodeJoinGeometry')
    g.links.new(delete.outputs[0], join.inputs['Geometry'])
    g.links.new(extra_order.outputs[0], join.inputs['Geometry'])
    attr = _node(g, 'GeometryNodeInputNamedAttribute', Name='max_loft_order')
    attr.data_type = 'FLOAT'
    rebuild = _node(g, 'GeometryNodePointsToCurves', Points=join.outputs[0], Weight=attr.outputs['Attribute'])
    close = _node(g, 'GeometryNodeSetSplineCyclic', Curve=rebuild.outputs[0],
                  Cyclic=_sample(g, curve, cyclic).outputs['Value'])
    interior = g.m('MULTIPLY', g.m('GREATER_THAN', level, 1e-5), g.m('LESS_THAN', level, .99999))
    active = g.m('MULTIPLY', g.g('Adaptive Path Steps'), interior)
    return _switch(g, 'GEOMETRY', active, curve, close.outputs[0])


def build_group():
    g = gn_mods.G('Loft')
    for name in ('Path', 'Shape'):
        g.ng.interface.new_socket(name, in_out='INPUT', socket_type='NodeSocketObject')
    for name in ('Cap Start', 'Cap End', 'Adaptive Path Steps', 'Contour', 'Banking',
                 'Smooth Length', 'Smooth Width'):
        g.inp(name, 'BOOL', True)
    g.inp('Flip Normals', 'BOOL', False)
    g.inp('Shape Steps', 'INT', 6, lo=0, hi=100)
    g.inp('Path Steps', 'INT', 5, lo=0, hi=100)
    g.inp('Shape Level', default=0.0, lo=0.0, hi=100.0)
    g.inp('Scale Start', default=100.0, lo=0.0, hi=10000.0)
    g.inp('Scale End', default=100.0, lo=0.0, hi=10000.0)
    g.inp('Twist', default=0.0)
    path = _node(g, 'GeometryNodeObjectInfo', Object=g.g('Path'))
    # ORIGINAL keeps the source independent of the Loft object's transform.
    path.transform_space = 'ORIGINAL'
    scaled_path = _node(g, 'GeometryNodeTransform', Geometry=path.outputs['Geometry'], Scale=path.outputs['Scale'])
    shape = _node(g, 'GeometryNodeObjectInfo', Object=g.g('Shape'))
    shape.transform_space = 'ORIGINAL'
    # Shape translation and rotation are ignored, as when Max picks a shape.
    scaled = _node(g, 'GeometryNodeTransform', Geometry=shape.outputs['Geometry'], Scale=shape.outputs['Scale'])
    profile = _steps(g, scaled.outputs[0], g.g('Shape Steps'))
    path_geo = _steps(g, scaled_path.outputs[0], g.g('Path Steps'))
    path_geo = _adaptive_path(g, path_geo)
    # These modes use Blender's frame transport. Both are available in 4.2.
    bank = _node(g, 'GeometryNodeSetCurveNormal', Curve=path_geo)
    flat = _node(g, 'GeometryNodeSetCurveNormal', Curve=path_geo)
    if hasattr(flat, 'mode'):
        bank.mode = 'MINIMUM_TWIST'
        flat.mode = 'Z_UP'
    else:
        bank.inputs['Mode'].default_value = 'Minimum Twist'
        flat.inputs['Mode'].default_value = 'Z Up'
    path_geo = _switch(g, 'GEOMETRY', g.g('Banking'), flat.outputs[0], bank.outputs[0])
    factor = g.nodes.new('GeometryNodeSplineParameter').outputs['Factor']
    radius = g.m('DIVIDE', g.m('ADD', g.g('Scale Start'),
                  g.m('MULTIPLY', factor, g.m('SUBTRACT', g.g('Scale End'), g.g('Scale Start')))), 100.0)
    rad = _node(g, 'GeometryNodeSetCurveRadius', Curve=path_geo, Radius=radius)
    tilt = _node(g, 'GeometryNodeSetCurveTilt', Curve=rad.outputs[0],
                 Tilt=g.m('MULTIPLY', factor, g.m('RADIANS', g.g('Twist'))))
    tangent = g.nodes.new('GeometryNodeInputTangent').outputs[0]
    normal = g.nodes.new('GeometryNodeInputNormal').outputs[0]
    # Capture the un-twisted frame. Contour off reorients every cross section
    # into the start frame without losing its Scale or Twist deformation.
    frame = _capture(g, rad.outputs[0], [('Center', 'VECTOR', g.position()),
                     ('Tangent', 'VECTOR', tangent), ('Normal', 'VECTOR', normal),
                     ('Factor', 'FLOAT', factor)])
    g.links.new(frame.outputs['Geometry'], tilt.inputs['Curve'])
    skin = _node(g, 'GeometryNodeCurveToMesh', Curve=tilt.outputs[0],
                 **{'Profile Curve': profile, 'Fill Caps': True})
    if 'Scale' in skin.inputs:
        g.links.new(g.nodes.new('GeometryNodeInputRadius').outputs[0], skin.inputs['Scale'])
    off = g.vm('SUBTRACT', g.position(), frame.outputs['Center'])
    binormal = g.vm('CROSS_PRODUCT', frame.outputs['Tangent'], frame.outputs['Normal'])
    start_t = _sample(g, rad.outputs[0], tangent, 'FLOAT_VECTOR').outputs['Value']
    start_n = _sample(g, rad.outputs[0], normal, 'FLOAT_VECTOR').outputs['Value']
    start_b = g.vm('CROSS_PRODUCT', start_t, start_n)
    fixed = frame.outputs['Center']
    for source_axis, start_axis in ((frame.outputs['Normal'], start_n), (binormal, start_b),
                                    (frame.outputs['Tangent'], start_t)):
        fixed = g.vm('ADD', fixed, _scale(g, start_axis, g.vm('DOT_PRODUCT', off, source_axis, out='Value')))
    geo = g.set_position(skin.outputs[0], position=_switch(g, 'VECTOR', g.g('Contour'), fixed, g.position()))
    start_cap = g.m('MULTIPLY', g.m('LESS_THAN', frame.outputs['Factor'], 1e-6),
                    g.m('SUBTRACT', 1, g.g('Cap Start')))
    end_cap = g.m('MULTIPLY', g.m('GREATER_THAN', frame.outputs['Factor'], .999999),
                  g.m('SUBTRACT', 1, g.g('Cap End')))
    delete = _node(g, 'GeometryNodeDeleteGeometry', Geometry=geo, Selection=g.m('MAXIMUM', start_cap, end_cap))
    delete.domain = 'FACE'
    delete.mode = 'ONLY_FACE'
    flip = _node(g, 'GeometryNodeFlipFaces', Mesh=delete.outputs[0], Selection=g.g('Flip Normals'))
    smooth = _node(g, 'GeometryNodeSetShadeSmooth', Mesh=flip.outputs[0],
                   **{'Shade Smooth': g.m('MAXIMUM', g.g('Smooth Length'), g.g('Smooth Width'))})
    smooth.domain = 'FACE'
    g.ng['max_loft'] = True
    return g.out(smooth.outputs[0])


def _spline_state(data):
    """Editable knots, before render thickness and object modifiers."""
    result = []
    for sp in data.splines:
        points = sp.bezier_points if sp.type == 'BEZIER' else sp.points
        values = []
        for p in points:
            value = (tuple(p.co), p.radius, p.tilt)
            if sp.type == 'BEZIER':
                value += (p.handle_left_type, p.handle_right_type,
                          tuple(p.handle_left), tuple(p.handle_right))
            values.append(value)
        result.append((sp.type, sp.use_cyclic_u, sp.resolution_u, tuple(values)))
    return tuple(result)


def _rna_state(value):
    """Snapshot modifier settings, including nested mappings and node inputs."""
    result = []
    for prop in value.bl_rna.properties:
        if prop.identifier in {'rna_type', 'id_data', 'is_active', 'node_warnings'}:
            continue
        if prop.is_readonly and prop.type not in {'POINTER', 'COLLECTION'}:
            continue
        item = getattr(value, prop.identifier)
        if prop.type == 'POINTER':
            item = item if item is None or isinstance(item, bpy.types.ID) else _rna_state(item)
        elif prop.type == 'COLLECTION':
            item = tuple(_rna_state(child) for child in item)
        elif getattr(prop, 'is_array', False):
            item = tuple(item)
        result.append((prop.identifier, item))
    if isinstance(value, bpy.types.NodesModifier):
        result.append(('inputs', tuple((key, repr(item.to_dict() if hasattr(item, 'to_dict')
                                                else item.to_list() if hasattr(item, 'to_list')
                                                else item)) for key, item in value.items())))
    return value.bl_rna.identifier, tuple(result)


def _spline_modifiers(source):
    # Other Geometry Nodes modifiers can deform the spline. Filter by Line's
    # explicit marker, never by a modifier name or by its node types.
    return [m for m in source.modifiers if not (m.type == 'NODES' and m.node_group
                                               and m.node_group.get('max_spline_render'))]


def _sync_modifiers(source, proxy):
    modifiers = _spline_modifiers(source)
    current = [m for m in proxy.modifiers if not (m.type == 'NODES' and m.node_group
                                                 and m.node_group.get('max_loft_spline'))]
    if tuple(_rna_state(m) for m in modifiers) == tuple(_rna_state(m) for m in current):
        return
    proxy.modifiers.clear()
    # Blender's native copier preserves settings, node inputs and stack order.
    # The context override also works for hidden sources and during Edit Mode.
    with bpy.context.temp_override(object=source, active_object=source,
                                   selected_objects=[proxy], selected_editable_objects=[proxy]):
        for mod in modifiers:
            bpy.ops.object.modifier_copy_to_selected(modifier=mod.name)
    if modifiers:
        # Native curve deformers such as Bend expose their result as wire mesh
        # edges. Recover those curves after the stack, keeping node curves too.
        group = next((g for g in bpy.data.node_groups if g.get('max_loft_spline')), None)
        if group is None:
            g = gn_mods.G('Loft spline')
            parts = _node(g, 'GeometryNodeSeparateComponents', Geometry=g.g('Geometry'))
            edges = _node(g, 'GeometryNodeMeshToCurve', Mesh=parts.outputs['Mesh'])
            join = g.nodes.new('GeometryNodeJoinGeometry')
            g.links.new(parts.outputs['Curve'], join.inputs['Geometry'])
            g.links.new(edges.outputs['Curve'], join.inputs['Geometry'])
            group = g.out(join.outputs[0])
            group['max_loft_spline'] = True
        proxy.modifiers.new('Loft spline', 'NODES').node_group = group


def _curve_source(ob, role):
    """Evaluate the modified spline independently of its render thickness."""
    p = ob.max_loft
    source = getattr(p, role)
    if source is not None and source.mode == 'EDIT':
        source.update_from_editmode()
    if not valid_spline(source):
        return None
    proxy = getattr(p, role + '_curve')
    if proxy is None or proxy.get('max_loft_owner') != ob:
        proxy = bpy.data.objects.new(ob.name + ' ' + role, bpy.data.curves.new('Loft spline', 'CURVE'))
        proxy['max_loft_owner'] = ob
        ob.users_collection[0].objects.link(proxy)
        proxy.hide_set(True)
        proxy.hide_render = True
        proxy.hide_select = True
        setattr(p, role + '_curve', proxy)
    if proxy.parent != source:
        proxy.parent = source
    if _spline_state(proxy.data) != _spline_state(source.data):
        old = proxy.data
        data = source.data.copy()
        # 3D also prevents a closed 2D spline's fill from becoming a mesh.
        data.dimensions = '3D'
        data.bevel_depth = data.extrude = 0
        data.bevel_mode = 'ROUND'
        data.bevel_object = data.taper_object = None
        proxy.data = data
        if old.users == 0:
            bpy.data.curves.remove(old)
    _sync_modifiers(source, proxy)
    return proxy


def _sync_sources(ob):
    global _syncing
    mod = modifier(ob)
    if mod is None or _syncing:
        return
    # Native modifier copying can request another depsgraph update.
    _syncing = True
    try:
        for role in ('path', 'shape'):
            source = _curve_source(ob, role)
            name = role.title()
            for ident, label in gn_mods.inputs(mod):
                if label == name:
                    data, prop = gn_mods.input_ref(mod, ident)
                    current = data.value if prop == 'value' else mod.get(ident)
                    if current != source:
                        gn_mods.set_input(mod, name, source)
                        ob.update_tag()
                    break
    finally:
        _syncing = False


@persistent
def _sync_splines(scene, depsgraph=None):
    # Run before evaluation so viewport and render both see the latest knots.
    for ob in list(scene.objects):
        if ob.max_loft.enabled:
            _sync_sources(ob)
    for proxy in list(scene.objects):
        if 'max_loft_owner' in proxy and proxy.get('max_loft_owner') is None:
            data = proxy.data
            bpy.data.objects.remove(proxy, do_unlink=True)
            if data.users == 0:
                bpy.data.curves.remove(data)


def _update(self, context):
    ob = self.id_data
    mod = modifier(ob)
    if mod is None:
        return
    for attr, name in FIELDS:
        gn_mods.set_input(mod, name, getattr(self, attr))
    _sync_sources(ob)
    ob.update_tag()


def _spline_poll(self, ob):
    return valid_spline(ob)


class MaxLoftParams(PropertyGroup):
    enabled: BoolProperty(default=False)
    path: PointerProperty(name='Path', type=bpy.types.Object, poll=_spline_poll, update=_update)
    shape: PointerProperty(name='Shape', type=bpy.types.Object, poll=_spline_poll, update=_update)
    path_curve: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    shape_curve: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    cap_start: BoolProperty(name='Cap Start', default=True, update=_update)
    cap_end: BoolProperty(name='Cap End', default=True, update=_update)
    shape_steps: IntProperty(name='Shape Steps', default=6, min=0, max=100, update=_update)
    path_steps: IntProperty(name='Path Steps', default=5, min=0, max=100, update=_update)
    adaptive: BoolProperty(name='Adaptive Path Steps', default=True, update=_update,
                           description='Insert a path division at the shape level')
    contour: BoolProperty(name='Contour', default=True, update=_update)
    banking: BoolProperty(name='Banking', default=True, update=_update,
                          description='Minimum-twist frame when on, Z-up frame when off')
    flip_normals: BoolProperty(name='Flip Normals', default=False, update=_update)
    smooth_length: BoolProperty(name='Smooth Length', default=True, update=_update)
    smooth_width: BoolProperty(name='Smooth Width', default=True, update=_update)
    path_percent: FloatProperty(name='Path', default=0.0, min=0, max=100,
                                description='Level for the next Get Shape, as a percentage of path length')
    shape_level: FloatProperty(name='Shape Level', default=0.0, min=0, max=100, update=_update)
    scale_start: FloatProperty(name='Start %', default=100.0, min=0, max=10000, update=_update)
    scale_end: FloatProperty(name='End %', default=100.0, min=0, max=10000, update=_update)
    twist: FloatProperty(name='Twist', default=0.0, update=_update, description='End rotation in degrees')


def _source(context, ob, mode):
    if mode == 'COPY':
        dup = ob.copy()
        dup.data = ob.data.copy()
        context.collection.objects.link(dup)
        dup.hide_set(True)
        dup.hide_render = True
        return dup
    if mode == 'MOVE':
        ob.hide_set(True)
        ob.hide_render = True
    return ob


def make_loft(context, path, shape, mode='INSTANCE', anchor='PATH'):
    """Create a live, single-profile loft from two ordinary spline objects."""
    if not valid_spline(path) or not valid_spline(shape) or path == shape:
        raise ValueError('Choose two different single-spline Poly or Bezier objects')
    if mode not in {item[0] for item in MODES}:
        raise ValueError('Unknown source mode')
    ng = next((g for g in bpy.data.node_groups if g.name == GROUP_NAME and g.get('max_loft')), None)
    if ng is None:
        ng = build_group()
    context.view_layer.update()
    ob = create.new_object(context, max_name('Loft'), bpy.data.meshes.new('Loft'))
    location, rotation, scale = path.matrix_world.decompose()
    ob.matrix_world = Matrix.LocRotScale(location, rotation, Vector((1, 1, 1)))
    if anchor == 'SHAPE':
        sp = path.data.splines[0]
        points = sp.bezier_points if sp.type == 'BEZIER' else sp.points
        first = Vector(points[0].co[:3])
        direction = ((points[0].handle_right - points[0].co) if sp.type == 'BEZIER'
                     else Vector(points[1].co[:3]) - first)
        first = first * scale
        direction = direction * scale
        alignment = direction.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        location, rotation, _ = shape.matrix_world.decompose()
        ob.matrix_world = (Matrix.LocRotScale(location, rotation, Vector((1, 1, 1)))
                           @ alignment.inverted() @ Matrix.Translation(-first))
    mod = ob.modifiers.new('Loft', 'NODES')
    mod.node_group = ng
    p = ob.max_loft
    p.enabled = True
    p.path = _source(context, path, mode)
    p.shape = _source(context, shape, mode)
    _update(p, context)
    return ob


def _polyline(ob):
    """Local sampled edges for spline picking, including unbevelled curves."""
    sp = ob.data.splines[0]
    if sp.type == 'POLY':
        pts = [Vector(p.co[:3]) for p in sp.points]
        return pts + pts[:1] if sp.use_cyclic_u else pts
    pts = sp.bezier_points
    result = []
    for i in range(len(pts) if sp.use_cyclic_u else len(pts) - 1):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        result.extend(interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, 17)[:-1])
    result.append(pts[0].co.copy() if sp.use_cyclic_u else pts[-1].co.copy())
    return result


def pick_spline(context, event, excluded):
    area, region = create.region_under_mouse(context, event.mouse_x, event.mouse_y)
    if region is None:
        return None
    mouse = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
    best, distance = None, 14.0
    for ob in context.visible_objects:
        if ob in excluded or not valid_spline(ob) or ob.hide_select:
            continue
        pts = [view3d_utils.location_3d_to_region_2d(region, region.data, ob.matrix_world @ v)
               for v in _polyline(ob)]
        for a, b in zip(pts, pts[1:]):
            if a is None or b is None:
                continue
            delta = b - a
            t = max(0.0, min(1.0, (mouse - a).dot(delta) / delta.length_squared)) if delta.length_squared else 0
            d = (mouse - (a + t * delta)).length
            if d < distance:
                best, distance = ob, d
    return best


class MAX_OT_loft_start(Operator):
    bl_idname = 'max.loft_start'
    bl_label = 'Loft'
    bl_description = 'Select a spline, then use Get Shape or Get Path'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and (valid_spline(context.active_object) or is_loft(context.active_object))

    def execute(self, context):
        context.window_manager.max_loft_active = True
        context.area.tag_redraw() if context.area else None
        return {'FINISHED'}


class MAX_OT_loft_pick(Operator):
    bl_idname = 'max.loft_pick'
    bl_label = 'Get Loft Spline'
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(items=(('PATH', 'Get Path', ''), ('SHAPE', 'Get Shape', '')))
    object_name: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and (valid_spline(context.active_object) or is_loft(context.active_object))

    def execute(self, context):
        seed = getattr(self, '_seed', None) or context.active_object
        picked = bpy.data.objects.get(self.object_name)
        forbidden = {seed}
        if is_loft(seed):
            forbidden.add(seed.max_loft.shape if self.source == 'PATH' else seed.max_loft.path)
        if not valid_spline(picked) or picked in forbidden:
            self.report({'WARNING'}, 'Choose a different single-spline Poly or Bezier object')
            return {'CANCELLED'}
        mode = context.window_manager.max_loft_mode
        if is_loft(seed):
            setattr(seed.max_loft, self.source.lower(), _source(context, picked, mode))
            if self.source == 'SHAPE':
                seed.max_loft.shape_level = seed.max_loft.path_percent
        else:
            path, shape = (picked, seed) if self.source == 'PATH' else (seed, picked)
            try:
                make_loft(context, path, shape, mode, anchor='SHAPE' if self.source == 'PATH' else 'PATH')
            except ValueError as exc:
                self.report({'WARNING'}, str(exc))
                return {'CANCELLED'}
        context.window_manager.max_loft_active = True
        return {'FINISHED'}

    def invoke(self, context, event):
        self._seed = context.active_object
        self._window = context.window
        self._workspace = context.workspace
        self._window.cursor_modal_set('EYEDROPPER')
        self._workspace.status_text_set('Loft: pick a spline. Right-click or Esc to cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self):
        self._window.cursor_modal_restore()
        self._workspace.status_text_set(None)

    def cancel(self, context):
        self._finish()

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._finish()
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
            excluded = {self._seed}
            if is_loft(self._seed):
                excluded.add(self._seed.max_loft.shape if self.source == 'PATH' else self._seed.max_loft.path)
            picked = pick_spline(context, event, excluded)
            self._window.cursor_modal_set('EYEDROPPER' if picked else 'STOP')
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if picked:
                    self.object_name = picked.name
                    self._finish()
                    return self.execute(context)
                return {'RUNNING_MODAL'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} or event.type.startswith('NDOF'):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


def creation_visible(context):
    wm = context.window_manager
    if wm.max_cmd_tab == 'CREATE':
        return wm.max_create_cat == 'GEOMETRY' and wm.max_create_sub == 'COMPOUND' and wm.max_loft_active
    return is_loft(context.active_object)


def params_visible(context):
    return creation_visible(context) and is_loft(context.active_object)


def draw_creation(layout, context):
    wm = context.window_manager
    row = layout.row(align=True)
    row.alignment = 'CENTER'
    row.emboss = 'NONE'
    for key, label, _ in MODES:
        icon = 'RADIOBUT_ON' if wm.max_loft_mode == key else 'RADIOBUT_OFF'
        row.prop_enum(wm, 'max_loft_mode', key, text=label, icon=icon)
    row = layout.row(align=True)
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('max.loft_pick', text='Get Path').source = 'PATH'
    row.operator('max.loft_pick', text='Get Shape').source = 'SHAPE'
    ob = context.active_object
    if is_loft(ob):
        layout.label(text='Path: ' + (ob.max_loft.path.name if ob.max_loft.path else '(missing)'))
        layout.label(text='Shape: ' + (ob.max_loft.shape.name if ob.max_loft.shape else '(missing)'))


def draw_skin(layout, context):
    p = context.active_object.max_loft
    for attr, name in FIELDS[:8]:
        layout.prop(p, attr, text=name)


def draw_surface(layout, context):
    p = context.active_object.max_loft
    layout.prop(p, 'smooth_length')
    layout.prop(p, 'smooth_width')


def draw_path(layout, context):
    p = context.active_object.max_loft
    layout.prop(p, 'path_percent', text='Path %')
    layout.label(text=f'Shape at {p.shape_level:g}%')
    layout.label(text='Get Shape replaces the single profile')


def draw_deformations(layout, context):
    p = context.active_object.max_loft
    layout.label(text='Scale')
    layout.prop(p, 'scale_start')
    layout.prop(p, 'scale_end')
    layout.prop(p, 'twist', text='Twist (degrees)')


classes = (MaxLoftParams, MAX_OT_loft_start, MAX_OT_loft_pick)


def register_props():
    bpy.types.Object.max_loft = PointerProperty(type=MaxLoftParams)
    bpy.types.WindowManager.max_loft_active = BoolProperty(default=False, options={'SKIP_SAVE'})
    bpy.types.WindowManager.max_loft_mode = EnumProperty(items=MODES, default='INSTANCE')
    bpy.app.handlers.depsgraph_update_pre.append(_sync_splines)
    bpy.app.handlers.render_pre.append(_sync_splines)


def unregister_props():
    bpy.app.handlers.depsgraph_update_pre.remove(_sync_splines)
    bpy.app.handlers.render_pre.remove(_sync_splines)
    del bpy.types.WindowManager.max_loft_mode
    del bpy.types.WindowManager.max_loft_active
    del bpy.types.Object.max_loft
