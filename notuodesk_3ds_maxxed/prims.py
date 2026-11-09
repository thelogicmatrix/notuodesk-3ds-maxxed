"""Editable base meshes, built independently from the clean-room contract."""

import hashlib
import math

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Matrix, Vector

from . import extended_primitives

PRIMITIVES = {
    'BOX': ('Box', 'MESH_CUBE', 'RECT', True),
    'CONE': ('Cone', 'MESH_CONE', 'RADIUS', True),
    'SPHERE': ('Sphere', 'MESH_UVSPHERE', 'RADIUS', False),
    'GEOSPHERE': ('GeoSphere', 'MESH_ICOSPHERE', 'RADIUS', False),
    'CYLINDER': ('Cylinder', 'MESH_CYLINDER', 'RADIUS', True),
    'TUBE': ('Tube', 'MESH_CYLINDER', 'RADIUS', True),
    'TORUS': ('Torus', 'MESH_TORUS', 'RADIUS', False),
    'PYRAMID': ('Pyramid', 'MESH_CONE', 'RECT', True),
    'PLANE': ('Plane', 'MESH_PLANE', 'RECT', False),
    'PLANEPLUS': ('PlanePlus', 'MESH_PLANE', 'RECT', False),
    **extended_primitives.PRIMITIVES,
}
DEFAULTS = {
    'BOX': {}, 'PYRAMID': {}, 'CONE': dict(sides=24, height_segs=5),
    'SPHERE': dict(sides=32), 'GEOSPHERE': dict(sides=4),
    'CYLINDER': dict(sides=18, height_segs=5), 'TUBE': dict(sides=18, height_segs=5),
    'TORUS': dict(sides=24, height_segs=12), 'PLANE': dict(length_segs=4, width_segs=4),
}
_busy = set()
_POSITION_KEY = '_max_base_positions'
_TOPOLOGY_KEY = '_max_base_topology'


def _slice(mesh, axis, start, extent, segments):
    """Cut interior section planes, leaving the two end planes unchanged."""
    normal = Vector((int(axis == 0), int(axis == 1), int(axis == 2)))
    for index in range(1, max(1, int(segments))):
        point = normal * (start + extent * index / segments)
        bmesh.ops.bisect_plane(mesh, geom=list(mesh.verts) + list(mesh.edges) + list(mesh.faces),
                               dist=1e-7, plane_co=point, plane_no=normal)


def _lathe(mesh, profile, sides, phase=0):
    rings = []
    for radius, z in profile:
        if abs(radius) < 1e-10:
            rings.append([mesh.verts.new((0, 0, z))])
        else:
            rings.append([mesh.verts.new((radius * math.cos(phase + math.tau * i / sides),
                                          radius * math.sin(phase + math.tau * i / sides), z))
                          for i in range(sides)])
    for lower, upper in zip(rings, rings[1:]):
        if len(lower) == len(upper) == 1:
            continue
        for i in range(sides):
            j = (i + 1) % sides
            vertices = ((lower[0], upper[j], upper[i]) if len(lower) == 1 else
                        (lower[i], lower[j], upper[0]) if len(upper) == 1 else
                        (lower[i], lower[j], upper[j], upper[i]))
            mesh.faces.new(vertices)


def _standard_mesh(p):
    mesh = bmesh.new()
    kind = p.kind
    n, hs = max(3, p.sides), max(1, p.height_segs)
    if kind in {'BOX', 'PYRAMID'}:
        bmesh.ops.create_cube(mesh, size=1)
        for vertex in mesh.verts:
            vertex.co.x *= p.width
            vertex.co.y *= p.length
            vertex.co.z = (vertex.co.z + .5) * p.height
        for axis, size, count in ((0, p.width, p.width_segs), (1, p.length, p.length_segs),
                                  (2, p.height, hs)):
            _slice(mesh, axis, -size / 2 if axis < 2 else 0, size, count)
        if kind == 'PYRAMID':
            for vertex in mesh.verts:
                factor = 1 - vertex.co.z / p.height if p.height else 1
                vertex.co.x *= factor
                vertex.co.y *= factor
            bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-7)
    elif kind == 'PLANE':
        rows = [[mesh.verts.new(((x / p.width_segs - .5) * p.width,
                                 (y / p.length_segs - .5) * p.length, 0))
                 for x in range(p.width_segs + 1)] for y in range(p.length_segs + 1)]
        for y in range(p.length_segs):
            for x in range(p.width_segs):
                mesh.faces.new((rows[y][x], rows[y][x+1], rows[y+1][x+1], rows[y+1][x]))
    elif kind in {'SPHERE', 'GEOSPHERE'} or kind == 'TORUS' and p.radius1 == 0:
        radius = p.radius2 if kind == 'TORUS' else p.radius1
        if kind == 'GEOSPHERE':
            bmesh.ops.create_icosphere(mesh, subdivisions=min(7, max(1, p.sides)), radius=radius)
        else:
            bmesh.ops.create_uvsphere(mesh, u_segments=n, v_segments=max(4, n // 2), radius=radius)
    elif kind in {'CONE', 'CYLINDER', 'TUBE'}:
        low = p.radius1
        high = p.radius2 if kind == 'CONE' else p.radius1
        if kind == 'TUBE':
            low, inner = max(p.radius1, p.radius2), min(p.radius1, p.radius2)
            high = low
        else:
            inner = 0
        profile = [(0, 0)] if inner == 0 else []
        profile.extend((low + (high - low) * i / hs, p.height * i / hs) for i in range(hs + 1))
        if inner == 0:
            if profile[-1][0] > 0:
                profile.append((0, p.height))
        else:
            profile.extend((inner, p.height * i / hs) for i in range(hs, -1, -1))
            profile.append(profile[0])
        # Avoid duplicate poles and repeated seam rings.
        profile = [value for i, value in enumerate(profile) if not i or value != profile[i-1]]
        _lathe(mesh, profile, n, math.pi / 2 if kind == 'CYLINDER' else 0)
        bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-7)
    elif kind == 'TORUS':
        rings = []
        cross = max(3, p.height_segs)
        for i in range(n):
            angle = math.tau * i / n
            rings.append([mesh.verts.new(((p.radius1 + p.radius2 * math.cos(math.tau*j/cross)) * math.cos(angle),
                                          (p.radius1 + p.radius2 * math.cos(math.tau*j/cross)) * math.sin(angle),
                                          p.radius2 * math.sin(math.tau*j/cross))) for j in range(cross)])
        for i in range(n):
            for j in range(cross):
                mesh.faces.new((rings[i][j], rings[(i+1)%n][j], rings[(i+1)%n][(j+1)%cross], rings[i][(j+1)%cross]))
        # Horn tori share a single pole instead of a ring of coincident vertices.
        bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-7)
    else:
        mesh.free()
        raise ValueError('Unsupported primitive kind')
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    for face in mesh.faces:
        face.smooth = p.smooth and (kind in {'SPHERE', 'GEOSPHERE', 'TORUS'} or
                                    kind in {'CYLINDER', 'CONE', 'TUBE'} and abs(face.normal.z) < .9999)
    return mesh


def _topology(mesh):
    values = (tuple(tuple(e.vertices) for e in mesh.edges), tuple(tuple(f.vertices) for f in mesh.polygons))
    return hashlib.sha256(repr(values).encode('ascii')).hexdigest()


def _source(ob):
    return getattr(ob, 'max_frozen_mesh', None) or ob.data


def _remember(ob, mesh):
    offset = Vector(ob.get('max_pivot_offset', (0, 0, 0)))
    mesh[_POSITION_KEY] = [c for vertex in mesh.vertices for c in vertex.co - offset]
    mesh[_TOPOLOGY_KEY] = _topology(mesh)
    ob.max_prim.vcount = len(mesh.vertices)


def _build(ob):
    p = ob.max_prim
    if p.kind in extended_primitives.PRIMITIVES:
        extended_primitives.constrain(p)
        return extended_primitives.build_bmesh(p.kind, p)
    if p.kind == 'PLANEPLUS':
        from . import plane_plus
        return plane_plus.build_bmesh(ob.max_plane_plus)
    return _standard_mesh(p)


def _surface_key(mesh, offset):
    # Vertex order is not a saved interface. Match geometry and face connectivity.
    coords = [tuple(round(v.co[i] - offset[i], 4) for i in range(3)) for v in mesh.vertices]
    return (sorted(coords), sorted(tuple(sorted(coords[i] for i in face.vertices)) for face in mesh.polygons))


def adopt_legacy(ob):
    """Trust a saved base only when its geometry matches its saved parameters."""
    if ob.type != 'MESH' or ob.mode != 'OBJECT' or not ob.max_prim.kind:
        return False
    mesh = _source(ob)
    if _POSITION_KEY in mesh:
        return _untouched(ob, mesh)
    if mesh.shape_keys or ob.max_prim.kind not in PRIMITIVES and ob.max_prim.kind != 'PLANEPLUS':
        return False
    token = ob.as_pointer()
    _busy.add(token)
    generated = None
    temporary = None
    try:
        generated = _build(ob)
        temporary = bpy.data.meshes.new('Base migration comparison')
        generated.to_mesh(temporary)
        if _surface_key(mesh, Vector(ob.get('max_pivot_offset', (0, 0, 0)))) != _surface_key(temporary, Vector()):
            return False
        _remember(ob, mesh)
        return True
    except (ValueError, ZeroDivisionError):
        return False
    finally:
        if generated:
            generated.free()
        if temporary:
            bpy.data.meshes.remove(temporary)
        _busy.discard(token)


@persistent
def _restore_bases(_):
    for ob in bpy.data.objects:
        adopt_legacy(ob)


def _untouched(ob, mesh):
    if not mesh.vertices:
        return True
    points = mesh.get(_POSITION_KEY)
    if points is None or len(points) != 3 * len(mesh.vertices) or mesh.get(_TOPOLOGY_KEY) != _topology(mesh):
        return False
    offset = Vector(ob.get('max_pivot_offset', (0, 0, 0)))
    for i, vertex in enumerate(mesh.vertices):
        if any(abs(vertex.co[j] - offset[j] - points[i*3+j]) > 2e-5 * max(1, abs(points[i*3+j])) for j in range(3)):
            return False
    return True


def collapse(ob):
    """End base-object editing without touching evaluated geometry."""
    key = ob.as_pointer()
    _busy.add(key)
    try:
        if ob.max_prim.kind == 'PLANEPLUS':
            ob.display_type = 'TEXTURED'
        ob.max_prim.kind = ''
        ob.max_prim.vcount = 0
    finally:
        _busy.discard(key)


def rebuild(ob):
    if not ob or ob.type != 'MESH' or ob.mode != 'OBJECT':
        return False
    p = ob.max_prim
    if p.kind not in PRIMITIVES and p.kind != 'PLANEPLUS':
        return False
    mesh = _source(ob)
    if mesh.shape_keys or not _untouched(ob, mesh):
        collapse(ob)
        return False
    if (p.kind == 'TUBE' and p.radius1 == p.radius2 or
            p.kind == 'TORUS' and p.radius2 <= 0 or
            p.kind in {'SPHERE', 'GEOSPHERE', 'CYLINDER'} and p.radius1 <= 0 or
            p.kind == 'CONE' and max(p.radius1, p.radius2) <= 0):
        return False
    token = ob.as_pointer()
    was_busy = token in _busy
    _busy.add(token)
    generated = None
    try:
        generated = _build(ob)
        if not generated.faces or any(not math.isfinite(c) for v in generated.verts for c in v.co):
            return False
        generated.transform(Matrix.Translation(ob.get('max_pivot_offset', (0, 0, 0))))
        if mesh.users > (2 if getattr(ob, 'max_frozen_mesh', None) else 1):
            mesh = mesh.copy()
            if getattr(ob, 'max_frozen_mesh', None):
                ob.max_frozen_mesh = mesh
            else:
                ob.data = mesh
        materials = [face.material_index for face in mesh.polygons]
        generated.to_mesh(mesh)
        if len(materials) == len(mesh.polygons):
            for face, material in zip(mesh.polygons, materials):
                face.material_index = material
        mesh.update()
        if p.kind != 'PLANEPLUS':
            # The retained projection service also supplies the standard mapping toggle.
            display = ob.data
            ob.data = mesh
            extended_primitives.mapping(ob)
            ob.data = display
        _remember(ob, mesh)
        if getattr(ob, 'max_frozen_mesh', None) and ob.data != mesh:
            generated.to_mesh(ob.data)
            ob.data.update()
        return True
    finally:
        if generated:
            generated.free()
        if not was_busy:
            _busy.discard(token)


def _changed(params, context):
    ob = params.id_data
    if ob.as_pointer() in _busy:
        return
    from . import snaps
    token = ob.as_pointer()
    _busy.add(token)
    try:
        snaps.spinner_params(params, context)
        if params.kind != 'PLANEPLUS' and hasattr(ob, 'max_plane_plus'):
            from . import plane_plus
            plane_plus.kind_changed(ob)
            for field in ob.max_plane_plus.bl_rna.properties:
                if field.identifier != 'rna_type' and ob.max_plane_plus.is_property_set(field.identifier):
                    ob.max_plane_plus.property_unset(field.identifier)
    finally:
        _busy.discard(token)
    rebuild(ob)


class MaxPrimParams(bpy.types.PropertyGroup):
    kind: StringProperty(default='', update=_changed)
    vcount: IntProperty(default=0)
    length: FloatProperty(name='Length', default=1, min=.0001, unit='LENGTH', update=_changed)
    width: FloatProperty(name='Width', default=1, min=.0001, unit='LENGTH', update=_changed)
    height: FloatProperty(name='Height', default=1, unit='LENGTH', update=_changed)
    radius1: FloatProperty(name='Radius 1', default=1, min=0, unit='LENGTH', update=_changed)
    radius2: FloatProperty(name='Radius 2', default=0, min=0, unit='LENGTH', update=_changed)
    length_segs: IntProperty(name='Length Segs', default=1, min=1, max=200, update=_changed)
    width_segs: IntProperty(name='Width Segs', default=1, min=1, max=200, update=_changed)
    height_segs: IntProperty(name='Height Segs', default=1, min=1, max=200, update=_changed)
    sides: IntProperty(name='Sides', default=18, min=1, max=200, update=_changed)
    smooth: BoolProperty(name='Smooth', default=True, update=_changed)


MaxPrimParams.__annotations__.update(extended_primitives.property_definitions(_changed))


def set_params(ob, kind, **values):
    if kind not in PRIMITIVES and kind != 'PLANEPLUS':
        return
    p = ob.max_prim
    token = ob.as_pointer()
    _busy.add(token)
    try:
        initial = dict(length=1, width=1, height=1, radius1=1, radius2=0,
                       length_segs=1, width_segs=1, height_segs=1, sides=18, smooth=True)
        initial.update({name: prop.keywords['default'] for name, prop in extended_primitives.property_definitions(None).items()})
        initial.update(extended_primitives.defaults(kind) if kind in extended_primitives.PRIMITIVES else DEFAULTS.get(kind, {}))
        initial.update(values)
        p.kind = kind
        for name, value in initial.items():
            if name in p.bl_rna.properties:
                setattr(p, name, value)
        if kind != 'PLANEPLUS' and hasattr(ob, 'max_plane_plus'):
            ob.max_plane_plus.property_unset('image')
            ob.max_plane_plus.property_unset('material')
        rebuild(ob)
        from . import snaps
        snaps.remember_spinners(p)
    finally:
        _busy.discard(token)


PARAMETERS = {
    'BOX': (('length', 'Length'), ('width', 'Width'), ('height', 'Height'), ('length_segs', 'Length Segs'), ('width_segs', 'Width Segs'), ('height_segs', 'Height Segs')),
    'PYRAMID': (('width', 'Width'), ('length', 'Depth'), ('height', 'Height'), ('width_segs', 'Width Segs'), ('length_segs', 'Depth Segs'), ('height_segs', 'Height Segs')),
    'CONE': (('radius1', 'Radius 1'), ('radius2', 'Radius 2'), ('height', 'Height'), ('height_segs', 'Height Segments'), ('sides', 'Sides'), ('smooth', 'Smooth')),
    'CYLINDER': (('radius1', 'Radius'), ('height', 'Height'), ('height_segs', 'Height Segments'), ('sides', 'Sides'), ('smooth', 'Smooth')),
    'TUBE': (('radius1', 'Radius 1'), ('radius2', 'Radius 2'), ('height', 'Height'), ('height_segs', 'Height Segments'), ('sides', 'Sides'), ('smooth', 'Smooth')),
    'SPHERE': (('radius1', 'Radius'), ('sides', 'Segments'), ('smooth', 'Smooth')),
    'GEOSPHERE': (('radius1', 'Radius'), ('sides', 'Segments'), ('smooth', 'Smooth')),
    'TORUS': (('radius1', 'Radius 1'), ('radius2', 'Radius 2'), ('sides', 'Segments'), ('height_segs', 'Sides'), ('smooth', 'Smooth')),
    'PLANE': (('length', 'Length'), ('width', 'Width'), ('length_segs', 'Length Segs'), ('width_segs', 'Width Segs')),
}
UI_FIELDS = PARAMETERS


def draw(layout, ob):
    """Final Parameters callback for the wave-2 Command Panel host."""
    from . import max_widgets
    kind = ob.max_prim.kind
    if kind == 'PLANEPLUS':
        from . import plane_plus
        return plane_plus.draw(layout, ob)
    fields = ((name, label) for name, label, unit in extended_primitives.FIELDS[kind]) if kind in extended_primitives.FIELDS else PARAMETERS.get(kind, ())
    for name, label in fields:
        prop = ob.max_prim.bl_rna.properties[name]
        if prop.type == 'BOOLEAN':
            max_widgets.checkbox(layout, ob.max_prim, name, label)
        else:
            if prop.type == 'ENUM':
                max_widgets.radios(layout, ob.max_prim, name, [(item.identifier, item.name) for item in prop.enum_items])
            else:
                max_widgets.spinner(layout, ob.max_prim, name, label, step=1 if prop.type == 'INT' else .1)
    if kind in PARAMETERS:
        max_widgets.checkbox(layout, ob.max_prim, 'generate_mapping', 'Generate Mapping Coords')


classes = (MaxPrimParams,)


def register_props():
    bpy.types.Object.max_prim = PointerProperty(type=MaxPrimParams)
    if _restore_bases not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_restore_bases)


def unregister_props():
    if _restore_bases in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restore_bases)
    if hasattr(bpy.types.Object, 'max_prim'):
        del bpy.types.Object.max_prim
