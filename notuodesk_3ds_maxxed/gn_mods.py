"""Editable deformation groups and the retained geometry construction contract."""
import bpy

PREFIX = '3dsMaxxed '
classes = ()


class G:
    """Build a geometry group without coupling consumers to a modifier UI."""

    def __init__(self, name):
        self.ng = bpy.data.node_groups.new(PREFIX + name, 'GeometryNodeTree')
        self.nodes, self.links = self.ng.nodes, self.ng.links
        self.ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
        self.ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        self.source = self.nodes.new('NodeGroupInput')
        self.sink = self.nodes.new('NodeGroupOutput')

    def inp(self, name, kind='FLOAT', default=0, lo=None, hi=None, subtype=None, description=''):
        socket = self.ng.interface.new_socket(name, in_out='INPUT', socket_type={
            'FLOAT': 'NodeSocketFloat', 'INT': 'NodeSocketInt',
            'BOOL': 'NodeSocketBool', 'VECTOR': 'NodeSocketVector'}[kind])
        socket.default_value = default
        if lo is not None:
            socket.min_value = lo
        if hi is not None:
            socket.max_value = hi
        if subtype is not None:
            socket.subtype = subtype
        socket.description = description
        return name

    def g(self, name):
        return self.source.outputs[name]

    def _set(self, node, name, value):
        if value is None:
            return
        target = node.inputs[name]
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, target)
        else:
            target.default_value = value

    def m(self, operation, a, b=None, c=None):
        node = self.nodes.new('ShaderNodeMath')
        node.operation = operation
        for index, value in enumerate((a, b, c)):
            self._set(node, index, value)
        return node.outputs[0]

    def vm(self, operation, a, b=None, out=0, *, output=None):
        node = self.nodes.new('ShaderNodeVectorMath')
        node.operation = operation
        self._set(node, 0, a)
        self._set(node, 'Scale' if operation == 'SCALE' else 1, b)
        return node.outputs[out if output is None else output]

    def xyz(self, value):
        node = self.nodes.new('ShaderNodeSeparateXYZ')
        self._set(node, 0, value)
        return tuple(node.outputs[i] for i in range(3))

    def combine(self, x, y, z):
        node = self.nodes.new('ShaderNodeCombineXYZ')
        for index, value in enumerate((x, y, z)):
            self._set(node, index, value)
        return node.outputs[0]

    def position(self):
        return self.nodes.new('GeometryNodeInputPosition').outputs[0]

    def set_position(self, geometry, position=None, offset=None):
        node = self.nodes.new('GeometryNodeSetPosition')
        for key, value in (('Geometry', geometry), ('Position', position), ('Offset', offset)):
            self._set(node, key, value)
        return node.outputs['Geometry']

    def out(self, geometry):
        self.links.new(geometry, self.sink.inputs['Geometry'])
        return self.ng


def _sockets(modifier):
    group = getattr(modifier, 'node_group', None)
    if group is None:
        return ()
    return tuple(s for s in group.interface.items_tree
                 if s.item_type == 'SOCKET' and s.in_out == 'INPUT'
                 and s.socket_type != 'NodeSocketGeometry')


def inputs(modifier):
    return [(socket.identifier, socket.name) for socket in _sockets(modifier)]


def input_ref(modifier, identifier):
    """Return an RNA owner/path pair that also accepts keyframe_insert."""
    # ID-property access remains valid in 4.2 and 5.0, including animation paths.
    socket = next((s for s in _sockets(modifier) if s.identifier == identifier), None)
    if socket is None:
        raise KeyError(identifier)
    if identifier not in modifier:
        modifier[identifier] = socket.default_value
    return modifier, '["' + bpy.utils.escape_identifier(identifier) + '"]'


def set_input(modifier, name, value):
    socket = next((s for s in _sockets(modifier) if s.name == name), None)
    if socket is None:
        return False
    data, path = input_ref(modifier, socket.identifier)
    if path == 'value':
        data.value = value
    else:
        data[socket.identifier] = value
    modifier.id_data.update_tag()
    return True


def value(modifier, name, default=None):
    socket = next((s for s in _sockets(modifier) if s.name == name), None)
    if socket is None:
        return default
    data, path = input_ref(modifier, socket.identifier)
    return data.path_resolve(path)


PARAMETERS = {
    'Melt': (('Amount', 'FLOAT', .5), ('% of Melt Spread', 'FLOAT', .19),
             ('Solidity', 'FLOAT', 2.), ('Irregularity', 'FLOAT', .35),
             ('Drip Size', 'FLOAT', 1.), ('Seed', 'FLOAT', 0.), ('Flip Axis', 'BOOL', False)),
    'Skew': (('Amount', 'FLOAT', .5), ('Direction', 'FLOAT', 0.)),
    'Squeeze': (('Axial Bulge', 'FLOAT', .5), ('Curve', 'FLOAT', 2.), ('Radial Squeeze', 'FLOAT', 0.)),
    'Slice': (('Slice Height', 'FLOAT', .5), ('Remove Bottom', 'BOOL', False)),
    'Noise': (('Seed', 'FLOAT', 0.), ('Scale', 'FLOAT', 1.), ('Strength X', 'FLOAT', 0.),
              ('Strength Y', 'FLOAT', 0.), ('Strength Z', 'FLOAT', .3), ('Fractal Detail', 'FLOAT', 2.)),
    'Push': (('Push Value', 'FLOAT', .1),),
    'Spherify': (('Percent', 'FLOAT', 1.),),
}
GROUP_NAMES = {kind: PREFIX + ('Melt 2' if kind == 'Melt' else kind) for kind in PARAMETERS}


def identify(modifier):
    group = getattr(modifier, 'node_group', None)
    if group is None:
        return None
    tagged = group.get('max_deformer')
    if tagged in PARAMETERS:
        return tagged
    for kind, name in GROUP_NAMES.items():
        if group.name == name or group.name.startswith(name + '.'):
            return kind
    return None


def _bounds(g):
    node = g.nodes.new('GeometryNodeBoundBox')
    g._set(node, 'Geometry', g.g('Geometry'))
    low, high = node.outputs['Min'], node.outputs['Max']
    return low, high, g.vm('SUBTRACT', high, low)


def _noise(g, position, scale, seed, detail=2):
    texture = g.nodes.new('ShaderNodeTexNoise')
    texture.noise_dimensions = '4D'
    g._set(texture, 'Vector', position)
    g._set(texture, 'Scale', scale)
    g._set(texture, 'W', seed)
    g._set(texture, 'Detail', detail)
    return texture.outputs['Color']


def _slice(g, low, high, span):
    """Intersect with two finite half spaces, preserving a real plane boundary."""
    lx, ly, lz = g.xyz(low)
    hx, hy, hz = g.xyz(high)
    sx, sy, sz = g.xyz(span)
    height = g.m('ADD', lz, g.m('MULTIPLY', sz, g.g('Slice Height')))
    margin = g.m('ADD', g.vm('LENGTH', span, output=1), 1)
    top = g.m('ADD', hz, margin)
    bottom = g.m('SUBTRACT', lz, margin)
    cx = g.m('MULTIPLY', g.m('ADD', lx, hx), .5)
    cy = g.m('MULTIPLY', g.m('ADD', ly, hy), .5)
    halves = []
    for a, b in ((height, top), (bottom, height)):
        cube = g.nodes.new('GeometryNodeMeshCube')
        size = g.combine(g.m('ADD', sx, margin), g.m('ADD', sy, margin),
                         g.m('MAXIMUM', g.m('SUBTRACT', b, a), .00001))
        g._set(cube, 'Size', size)
        move = g.nodes.new('GeometryNodeTransform')
        g._set(move, 'Geometry', cube.outputs['Mesh'])
        g._set(move, 'Translation', g.combine(cx, cy, g.m('MULTIPLY', g.m('ADD', a, b), .5)))
        boolean = g.nodes.new('GeometryNodeMeshBoolean')
        boolean.operation = 'INTERSECT'
        # Intersect takes all operands through the multi-input mesh socket.
        g.links.new(g.g('Geometry'), boolean.inputs[1])
        g.links.new(move.outputs['Geometry'], boolean.inputs[1])
        halves.append(boolean.outputs['Mesh'])
    choice = g.nodes.new('GeometryNodeSwitch')
    choice.input_type = 'GEOMETRY'
    g._set(choice, 'Switch', g.g('Remove Bottom'))
    g._set(choice, 'False', halves[1])
    g._set(choice, 'True', halves[0])
    return choice.outputs['Output']


def build(kind):
    if kind not in PARAMETERS:
        raise ValueError('Unsupported deformer: ' + kind)
    g = G('Melt 2' if kind == 'Melt' else kind)
    g.ng['max_deformer'] = kind
    g.ng['max_deformer_version'] = 1
    for name, category, default in PARAMETERS[kind]:
        g.inp(name, category, default, subtype='ANGLE' if name == 'Direction' else None)
    p = g.position()
    x, y, z = g.xyz(p)
    low, high, span = _bounds(g)
    if kind == 'Slice':
        return g.out(_slice(g, low, high, span))
    if kind == 'Skew':
        distance = g.m('MULTIPLY', z, g.g('Amount'))
        offset = g.combine(g.m('MULTIPLY', distance, g.m('COSINE', g.g('Direction'))),
                           g.m('MULTIPLY', distance, g.m('SINE', g.g('Direction'))), 0)
        return g.out(g.set_position(g.g('Geometry'), offset=offset))
    if kind == 'Push':
        normal = g.nodes.new('GeometryNodeInputNormal').outputs[0]
        return g.out(g.set_position(g.g('Geometry'), offset=g.vm('SCALE', normal, g.g('Push Value'))))
    if kind == 'Noise':
        strength = g.combine(*(g.g('Strength ' + axis) for axis in 'XYZ'))
        noise = _noise(g, p, g.m('DIVIDE', 1, g.m('MAXIMUM', g.g('Scale'), .000001)),
                       g.g('Seed'), g.g('Fractal Detail'))
        offset = g.vm('MULTIPLY', g.vm('SUBTRACT', noise, (.5, .5, .5)), strength)
        return g.out(g.set_position(g.g('Geometry'), offset=offset))
    center = g.vm('SCALE', g.vm('ADD', low, high), .5)
    relative = g.vm('SUBTRACT', p, center)
    if kind == 'Spherify':
        sx, sy, sz = g.xyz(span)
        radius = g.m('MULTIPLY', g.m('MAXIMUM', sx, g.m('MAXIMUM', sy, sz)), .5)
        sphere = g.vm('SCALE', g.vm('NORMALIZE', relative), radius)
        delta = g.vm('SCALE', g.vm('SUBTRACT', sphere, relative), g.g('Percent'))
        return g.out(g.set_position(g.g('Geometry'), offset=delta))
    lower_z = g.xyz(low)[2]
    height = g.m('MAXIMUM', g.xyz(span)[2], .000001)
    t = g.m('DIVIDE', g.m('SUBTRACT', z, lower_z), height)
    t = g.m('MINIMUM', g.m('MAXIMUM', t, 0), 1)
    if kind == 'Squeeze':
        mid = g.m('SUBTRACT', g.m('MULTIPLY', t, 2), 1)
        bell = g.m('POWER', g.m('MAXIMUM', g.m('SUBTRACT', 1, g.m('MULTIPLY', mid, mid)), 0),
                   g.m('MAXIMUM', g.g('Curve'), .000001))
        radial = g.m('ADD', g.m('SUBTRACT', 1, g.g('Radial Squeeze')), g.m('MULTIPLY', bell, g.g('Axial Bulge')))
        rx, ry, rz = g.xyz(relative)
        position = g.vm('ADD', center, g.combine(g.m('MULTIPLY', rx, radial), g.m('MULTIPLY', ry, radial), rz))
    else:
        # Solidity shapes the height profile. Extras modulate it continuously.
        flip = g.g('Flip Axis')
        direction = g.m('SUBTRACT', 1, g.m('MULTIPLY', flip, 2))
        along = g.m('ADD', g.m('MULTIPLY', t, direction), flip)
        profile = g.m('POWER', along, g.m('MAXIMUM', g.m('MULTIPLY', g.g('Solidity'), .5), .25))
        irregular = g.xyz(_noise(g, p, g.m('DIVIDE', 1, g.m('MAXIMUM', g.g('Drip Size'), .000001)), g.g('Seed')))[0]
        irregular = g.m('MULTIPLY', g.m('SUBTRACT', irregular, .5), g.g('Irregularity'))
        amount = g.m('MINIMUM', g.m('MAXIMUM', g.g('Amount'), 0), 1)
        drop = g.m('MULTIPLY', amount, g.m('MINIMUM', g.m('MAXIMUM', g.m('ADD', profile, irregular), 0), along))
        new_z = g.m('SUBTRACT', z, g.m('MULTIPLY', direction, g.m('MULTIPLY', height, drop)))
        spread = g.m('ADD', 1, g.m('MULTIPLY', g.g('% of Melt Spread'), g.m('MULTIPLY', amount, g.m('SUBTRACT', 1, along))))
        rx, ry, _ = g.xyz(relative)
        cx, cy, _ = g.xyz(center)
        position = g.combine(g.m('ADD', cx, g.m('MULTIPLY', rx, spread)),
                             g.m('ADD', cy, g.m('MULTIPLY', ry, spread)), new_z)
    return g.out(g.set_position(g.g('Geometry'), position=position))


def add(ob, kind):
    mod = ob.modifiers.new(kind, 'NODES')
    mod.node_group = build(kind)
    for socket in _sockets(mod):
        input_ref(mod, socket.identifier)
    return mod


def get(kind):
    """Create the independently authored version without replacing loaded groups."""
    return build(kind)


BUILDERS = {kind.upper(): (lambda kind=kind: build(kind)) for kind in PARAMETERS}
