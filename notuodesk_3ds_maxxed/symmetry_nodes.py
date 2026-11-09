"""Native, saved Geometry Nodes for cut-aware planar and radial symmetry."""
import math
from .gn_mods import G

MARKER = 'max_symmetry_geometry'
CAP = '.max_symmetry_cap'
CUT = '.max_symmetry_cut'
NEAR = '.max_symmetry_near'
EPS = 1e-5
REVISION = 2


class Builder(G):
    def node(self, kind, **values):
        n = self.nodes.new(kind)
        for key, value in values.items():
            setattr(n, key, value)
        return n

    def switch(self, condition, yes, no, kind='GEOMETRY'):
        n = self.node('GeometryNodeSwitch', input_type=kind)
        for key, value in (('Switch', condition), ('False', no), ('True', yes)):
            self._set(n, key, value)
        return n.outputs[0]

    def attr(self, name, kind='BOOLEAN'):
        n = self.node('GeometryNodeInputNamedAttribute', data_type=kind)
        n.inputs['Name'].default_value = name
        return n.outputs['Attribute']

    def store(self, geo, name, value, domain='POINT'):
        n = self.node('GeometryNodeStoreNamedAttribute', data_type='BOOLEAN', domain=domain)
        n.inputs['Name'].default_value = name
        self._set(n, 'Geometry', geo)
        self._set(n, 'Value', value)
        return n.outputs[0]

    def either(self, a, b):
        n = self.node('FunctionNodeBooleanMath', operation='OR')
        self._set(n, 0, a)
        self._set(n, 1, b)
        return n.outputs[0]

    def transform(self, geo, translation=None, rotation=None, scale=None):
        n = self.node('GeometryNodeTransform')
        for key, val in (('Geometry', geo), ('Translation', translation), ('Rotation', rotation), ('Scale', scale)):
            self._set(n, key, val)
        return n.outputs[0]

    def rotate(self, vec, rotation, invert=False):
        n = self.node('ShaderNodeVectorRotate', rotation_type='EULER_XYZ', invert=invert)
        self._set(n, 'Vector', vec)
        self._set(n, 'Rotation', rotation)
        return n.outputs[0]

    def join(self, *geometries):
        n = self.node('GeometryNodeJoinGeometry')
        for geo in geometries:
            self._set(n, 0, geo)
        return n.outputs[0]

    def reflect(self, geo, scale):
        # A negative transform preserves loop order. Reflection needs its own
        # winding correction so the duplicated faces still point outwards.
        n = self.node('GeometryNodeFlipFaces')
        self._set(n, 'Mesh', self.transform(geo, scale=scale))
        return n.outputs[0]

    def tolerance(self, geo):
        bounds = self.node('GeometryNodeBoundBox')
        self._set(bounds, 'Geometry', geo)
        extent = self.m('MAXIMUM', self.vm('LENGTH', bounds.outputs['Max'], out=1),
                        self.vm('LENGTH', bounds.outputs['Min'], out=1))
        # Float positions and radial rotations lose absolute precision as
        # coordinates grow. Only cut-tagged vertices use this tolerance.
        return self.m('MAXIMUM', EPS, self.m('MULTIPLY', extent, 1e-6))

    def clip(self, geo, normal, distance, open_boundary=True):
        """Half-space cut with an explicit mask of the cut's seam vertices."""
        pos = self.position()
        signed = self.vm('DOT_PRODUCT', pos, normal, out=1)
        tolerance = self.tolerance(geo)
        limits = self.node('GeometryNodeAttributeStatistic', data_type='FLOAT', domain='POINT')
        self._set(limits, 'Geometry', geo)
        self._set(limits, 'Attribute', signed)
        retained = self.m('GREATER_THAN', limits.outputs['Min'], -1e-12)
        near = self.m('LESS_THAN', self.m('ABSOLUTE', signed), distance)
        projected = self.vm('SUBTRACT', pos, self.vm('MULTIPLY', normal, self.combine(signed, signed, signed)))
        snap = self.node('GeometryNodeSetPosition')
        self._set(snap, 'Geometry', geo)
        self._set(snap, 'Selection', near)
        self._set(snap, 'Position', projected)
        # Preserve an existing open seam on the exact cutting plane as well.
        seam = self.either(self.attr(CUT), self.m('LESS_THAN', self.m('ABSOLUTE', signed), tolerance))
        geo = self.store(snap.outputs[0], CUT, seam)
        bounds = self.node('GeometryNodeBoundBox')
        self._set(bounds, 'Geometry', geo)
        diameter = self.vm('LENGTH', self.vm('SUBTRACT', bounds.outputs['Max'], bounds.outputs['Min']), out=1)
        # Also include the distance from the centre to an off-origin mesh.
        radius = self.m('MAXIMUM', self.vm('LENGTH', bounds.outputs['Max'], out=1),
                        self.vm('LENGTH', bounds.outputs['Min'], out=1))
        size = self.m('ADD', self.m('MULTIPLY', self.m('MAXIMUM', diameter, radius), 4), 1)
        cube = self.node('GeometryNodeMeshCube')
        self._set(cube, 'Size', self.combine(size, size, size))
        align = self.node('FunctionNodeAlignEulerToVector', axis='X')
        self._set(align, 'Vector', normal)
        shift = self.vm('MULTIPLY', normal, self.combine(self.m('MULTIPLY', size, .5),
                                                        self.m('MULTIPLY', size, .5),
                                                        self.m('MULTIPLY', size, .5)))
        cutter = self.transform(cube.outputs['Mesh'], translation=shift, rotation=align.outputs[0])
        cutter = self.store(cutter, CAP, True, 'FACE')
        cut = self.node('GeometryNodeMeshBoolean', operation='INTERSECT')
        if hasattr(cut, 'solver'):
            cut.solver = 'EXACT'
        # Intersect uses the multi-input socket for ALL operands. Mesh 1 is
        # only the minuend for Difference, even though Blender displays it.
        self._set(cut, 1, geo)
        self._set(cut, 1, cutter)
        # Tag the boundary on the newly cut result, including an original
        # vertex already on that boundary. Keep this provenance through every
        # later reflection and rotation. Uncut geometry never gets this tag.
        cut_vertices = self.m('LESS_THAN', self.m('ABSOLUTE', signed), tolerance)
        marked = self.store(cut.outputs['Mesh'], CUT, self.either(self.attr(CUT), cut_vertices))
        # Switch evaluates only the chosen geometry input. An open source
        # wholly inside the retained half-space needs no solid intersection.
        marked = self.switch(retained, geo, marked)
        if not open_boundary:
            return marked
        return self.remove_caps(marked)

    def remove_caps(self, geo):
        remove = self.node('GeometryNodeDeleteGeometry', domain='FACE')
        self._set(remove, 'Geometry', geo)
        self._set(remove, 'Selection', self.attr(CAP))
        # Cutter faces are only construction data. Their removal leaves the
        # open cut boundary that the adjacent reflected segment will close.
        return remove.outputs[0]

    def weld(self, geo, proximity_selection):
        n = self.node('GeometryNodeMergeByDistance')
        self._set(n, 'Geometry', geo)
        self._set(n, 'Selection', self.switch(self.g('Proximity'), proximity_selection, self.attr(CUT), 'BOOLEAN'))
        self._set(n, 'Distance', self.switch(self.g('Proximity'), self.g('Weld Threshold'),
                                            self.m('MINIMUM', self.g('Weld Threshold'), self.tolerance(geo)), 'FLOAT'))
        return self.switch(self.g('Weld'), n.outputs[0], geo)


def build(token):
    g = Builder('Symmetry')
    g.ng[MARKER] = token
    g.ng['max_symmetry_revision'] = REVISION
    for name, kind, default in (
            ('Axes', 'VECTOR', (1, 0, 0)), ('Flips', 'VECTOR', (0, 0, 0)),
            ('Slice', 'BOOL', True), ('Slice Threshold', 'FLOAT', .01),
            ('Weld', 'BOOL', True), ('Weld Threshold', 'FLOAT', .01),
            ('Proximity', 'BOOL', False), ('Radial', 'BOOL', False),
            ('Count', 'INT', 2), ('Radial Axis', 'INT', 2),
            ('Mirror Symmetry', 'BOOL', False), ('Radial Flip', 'BOOL', False)):
        g.inp(name, kind, default=default, lo=2 if name == 'Count' else 0,
              hi=1000 if name == 'Count' else None)
    frame = g.node('GeometryNodeObjectInfo', transform_space='RELATIVE')
    frame.name = 'Mirror frame'
    local = g.vm('DIVIDE', g.rotate(g.vm('SUBTRACT', g.position(), frame.outputs['Location']),
                                   frame.outputs['Rotation'], True), frame.outputs['Scale'])
    source = g.set_position(g.g('Geometry'), position=local)
    source = g.store(g.store(source, CAP, False, 'FACE'), CUT, False)
    axes, flips = g.xyz(g.g('Axes')), g.xyz(g.g('Flips'))
    planar = source
    for i in range(3):
        normal = g.combine(*(g.m('SUBTRACT', 1, g.m('MULTIPLY', 2, flips[i])) if i == j else 0 for j in range(3)))
        sliced = g.clip(planar, normal, g.g('Slice Threshold'))
        half = g.switch(g.g('Slice'), sliced, planar)
        reflected = g.reflect(half, tuple(-1 if j == i else 1 for j in range(3)))
        band = g.m('LESS_THAN', g.m('ABSOLUTE', g.xyz(g.position())[i]), g.g('Weld Threshold'))
        planar = g.switch(axes[i], g.weld(g.join(half, reflected), band), planar)
    # Work around Z in a cyclic coordinate frame, preserving handedness.
    x, y, z = g.xyz(g.position())
    axis_x = g.m('LESS_THAN', g.g('Radial Axis'), .5)
    axis_y = g.m('LESS_THAN', g.g('Radial Axis'), 1.5)
    canonical = g.switch(axis_x, g.combine(y, z, x),
                         g.switch(axis_y, g.combine(z, x, y), g.combine(x, y, z), 'VECTOR'), 'VECTOR')
    radial = g.set_position(source, position=canonical)
    mirror, flip = g.g('Mirror Symmetry'), g.g('Radial Flip')
    radial = g.switch(mirror, g.switch(flip, g.reflect(radial, (1, -1, 1)), radial), radial)
    angle = g.m('DIVIDE', math.tau, g.m('MAXIMUM', g.g('Count'), 2))
    width = g.switch(mirror, g.m('MULTIPLY', angle, .5), angle, 'FLOAT')
    # Keep the first construction cap until the second Boolean has finished.
    # The exact solver needs a closed volume to classify a subsequent cut.
    lower = g.clip(radial, (0, 1, 0), g.g('Slice Threshold'), open_boundary=False)
    normal = g.combine(g.m('SINE', width), g.m('MULTIPLY', -1, g.m('COSINE', width)), 0)
    sector = g.clip(lower, normal, g.g('Slice Threshold'))
    # A second Boolean can interpolate a point attribute from the cutter's
    # face at the first boundary. Reassert both exact cut boundaries before
    # making any copies, rather than proximity-welding the entire segment.
    tolerance = g.tolerance(source)
    boundary = g.either(g.m('LESS_THAN', g.m('ABSOLUTE', g.xyz(g.position())[1]), tolerance),
                        g.m('LESS_THAN', g.m('ABSOLUTE', g.vm('DOT_PRODUCT', g.position(), normal, out=1)), tolerance))
    sector = g.store(sector, CUT, g.either(g.attr(CUT), boundary))
    radial = g.switch(g.g('Slice'), sector, radial)
    band = g.either(g.m('LESS_THAN', g.m('ABSOLUTE', g.xyz(g.position())[1]), g.g('Weld Threshold')),
                    g.m('LESS_THAN', g.m('ABSOLUTE', g.vm('DOT_PRODUCT', g.position(), normal, out=1)), g.g('Weld Threshold')))
    radial = g.store(radial, NEAR, band)
    radial = g.switch(mirror, g.join(radial, g.reflect(radial, (1, -1, 1))), radial)
    points = g.node('GeometryNodeMeshLine')
    g._set(points, 'Count', g.g('Count'))
    points.inputs['Offset'].default_value = (0, 0, 0)
    index = g.node('GeometryNodeInputIndex').outputs[0]
    instance = g.node('GeometryNodeInstanceOnPoints')
    g._set(instance, 'Points', points.outputs['Mesh'])
    g._set(instance, 'Instance', radial)
    g._set(instance, 'Rotation', g.combine(0, 0, g.m('MULTIPLY', index, angle)))
    realize = g.node('GeometryNodeRealizeInstances')
    g._set(realize, 'Geometry', instance.outputs[0])
    radial = g.weld(realize.outputs[0], g.attr(NEAR))
    x, y, z = g.xyz(g.position())
    restored = g.switch(axis_x, g.combine(z, x, y),
                        g.switch(axis_y, g.combine(y, z, x), g.combine(x, y, z), 'VECTOR'), 'VECTOR')
    radial = g.set_position(radial, position=restored)
    result = g.switch(g.g('Radial'), radial, planar)
    world = g.vm('ADD', g.rotate(g.vm('MULTIPLY', g.position(), frame.outputs['Scale']),
                                frame.outputs['Rotation']), frame.outputs['Location'])
    result = g.set_position(result, position=world)
    # Do not leak our intermediate named attributes into an applied mesh.
    for name in (CAP, CUT, NEAR):
        remove = g.node('GeometryNodeRemoveAttribute')
        g._set(remove, 'Geometry', result)
        remove.inputs['Name'].default_value = name
        result = remove.outputs[0]
    return g.out(result)
