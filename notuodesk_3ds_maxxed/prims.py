"""Parametric primitives: objects keep their creation parameters (Length, Width,
Height, Segs ...) and can be edited in the Modify panel until they are collapsed
to an Editable Poly, exactly like 3ds Max."""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Matrix

from . import extended_primitives

# kind: (label, icon, base style for click-drag, has height stage)
PRIMITIVES = {
    "BOX": ("Box", "MESH_CUBE", "RECT", True),
    "CONE": ("Cone", "MESH_CONE", "RADIUS", True),
    "SPHERE": ("Sphere", "MESH_UVSPHERE", "RADIUS", False),
    "GEOSPHERE": ("GeoSphere", "MESH_ICOSPHERE", "RADIUS", False),
    "CYLINDER": ("Cylinder", "MESH_CYLINDER", "RADIUS", True),
    "TUBE": ("Tube", "MESH_CIRCLE", "RADIUS", True),
    "TORUS": ("Torus", "MESH_TORUS", "RADIUS", False),
    "PYRAMID": ("Pyramid", "MARKER", "RECT", True),
    "PLANE": ("Plane", "MESH_PLANE", "RECT", False),
}
PRIMITIVES.update(extended_primitives.PRIMITIVES)

# 3ds Max default segment counts
DEFAULTS = {
    "BOX": dict(length_segs=1, width_segs=1, height_segs=1),
    "CONE": dict(sides=24, height_segs=5),
    "SPHERE": dict(sides=32),
    "GEOSPHERE": dict(sides=4),
    "CYLINDER": dict(sides=18, height_segs=5),
    "TUBE": dict(sides=18, height_segs=5),
    "TORUS": dict(sides=24, height_segs=12),
    "PYRAMID": dict(length_segs=1, width_segs=1, height_segs=1),
    "PLANE": dict(length_segs=4, width_segs=4),
}

# which parameters each kind shows: (property, label)
UI_FIELDS = {
    "BOX": [("length", "Length"), ("width", "Width"), ("height", "Height"), None,
            ("length_segs", "Length Segs"), ("width_segs", "Width Segs"), ("height_segs", "Height Segs")],
    "PLANE": [("length", "Length"), ("width", "Width"), None,
              ("length_segs", "Length Segs"), ("width_segs", "Width Segs")],
    "PYRAMID": [("width", "Width"), ("length", "Depth"), ("height", "Height"), None,
                ("width_segs", "Width Segs"), ("length_segs", "Depth Segs"), ("height_segs", "Height Segs")],
    "SPHERE": [("radius1", "Radius"), ("sides", "Segments"), ("smooth", "Smooth")],
    "GEOSPHERE": [("radius1", "Radius"), ("sides", "Segments"), ("smooth", "Smooth")],
    "CYLINDER": [("radius1", "Radius"), ("height", "Height"), None,
                 ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "CONE": [("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height"), None,
             ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "TUBE": [("radius1", "Radius 1"), ("radius2", "Radius 2"), ("height", "Height"), None,
             ("height_segs", "Height Segments"), ("sides", "Sides"), ("smooth", "Smooth")],
    "TORUS": [("radius1", "Radius 1"), ("radius2", "Radius 2"), None,
              ("sides", "Segments"), ("height_segs", "Sides"), ("smooth", "Smooth")],
}


def _slice(bm, axis, start, size, count):
    """Cut the mesh into `count` equal slices along an axis (Max 'Segs')."""
    no = [0.0, 0.0, 0.0]
    no[axis] = 1.0
    for i in range(1, count):
        co = [0.0, 0.0, 0.0]
        co[axis] = start + size * i / count
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=co, plane_no=no)


def _ring(bm, r, z, segs):
    return [bm.verts.new((r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs), z))
            for i in range(segs)]


def build_bmesh(kind, p):
    if kind in extended_primitives.PRIMITIVES:
        return extended_primitives.build_bmesh(kind, p)
    bm = bmesh.new()
    h = p.height
    ah = abs(h) if abs(h) > 1e-6 else 1e-6
    smooth_all = False
    if kind in {"BOX", "PYRAMID"}:
        if kind == "BOX":
            bmesh.ops.create_cube(bm, size=1.0)
        else:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4,
                                  radius1=math.sqrt(0.5), radius2=0.0, depth=1.0)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 4, 3, "Z"))
        bmesh.ops.scale(bm, verts=bm.verts, vec=(p.width, p.length, ah))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, ah / 2))
        _slice(bm, 0, -p.width / 2, p.width, p.width_segs)
        _slice(bm, 1, -p.length / 2, p.length, p.length_segs)
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "PLANE":
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, verts=bm.verts, vec=(p.width, p.length, 1.0))
        _slice(bm, 0, -p.width / 2, p.width, p.width_segs)
        _slice(bm, 1, -p.length / 2, p.length, p.length_segs)
    elif kind == "SPHERE":
        bmesh.ops.create_uvsphere(bm, u_segments=max(p.sides, 4), v_segments=max(p.sides // 2, 2), radius=p.radius1)
    elif kind == "GEOSPHERE":
        bmesh.ops.create_icosphere(bm, subdivisions=max(1, min(p.sides, 7)), radius=p.radius1)
    elif kind in {"CYLINDER", "CONE"} or (kind == "TUBE" and min(p.radius1, p.radius2) == 0):
        # A Tube with no inner radius is solid, not a collapsed inner wall.
        r1 = max(p.radius1, p.radius2) if kind == "TUBE" else p.radius1
        r2 = p.radius2 if kind == "CONE" else r1
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=max(p.sides, 3),
                              radius1=r1, radius2=r2, depth=ah)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, ah / 2))
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "TUBE":
        segs = max(p.sides, 3)
        rings = [_ring(bm, r, z, segs) for r, z in
                 ((p.radius1, 0), (p.radius1, ah), (p.radius2, ah), (p.radius2, 0))]
        for k in range(4):
            a, b = rings[k], rings[(k + 1) % 4]
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
        _slice(bm, 2, 0.0, ah, p.height_segs)
    elif kind == "TORUS":
        segs, sides = max(p.sides, 3), max(p.height_segs, 3)
        if p.radius1 == 0 and p.radius2 > 0:
            # The ring collapses to a sphere. Avoid tracing its surface twice.
            bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=max(sides // 2, 2), radius=p.radius2)
        else:
            _torus(bm, p.radius1, p.radius2, segs, sides)
        smooth_all = True
    if kind in {"SPHERE", "GEOSPHERE"}:
        smooth_all = True
    if h < 0 and kind in {"BOX", "PYRAMID", "CYLINDER", "CONE", "TUBE"}:
        bmesh.ops.scale(bm, verts=bm.verts, vec=(1, 1, -1))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # Box, Pyramid and Plane have no Smooth option in Max and are always flat-shaded
    if p.smooth and kind not in {"BOX", "PYRAMID", "PLANE"}:
        for f in bm.faces:
            # smooth round surfaces only, keep caps / boxes flat
            f.smooth = smooth_all or abs(f.normal.z) < 0.7
    return bm


def _torus(bm, radius1, radius2, segs, sides):
    """Share axis vertices for horn and spindle torus cross sections."""
    poles = {}
    grid = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        row = []
        for j in range(sides):
            b = 2 * math.pi * j / sides
            r = radius1 + radius2 * math.cos(b)
            if abs(r) <= radius2 * 1e-12:
                if j not in poles:
                    poles[j] = bm.verts.new((0, 0, radius2 * math.sin(b)))
                row.append(poles[j])
            else:
                row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), radius2 * math.sin(b))))
        grid.append(row)
    for i in range(segs):
        for j in range(sides):
            i2, j2 = (i + 1) % segs, (j + 1) % sides
            verts = tuple(dict.fromkeys((grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2])))
            if len(verts) >= 3:
                bm.faces.new(verts)


def rebuild(ob):
    p = ob.max_prim
    if not p.kind or ob.type != "MESH":
        return False
    me = ob.data
    if p.vcount and len(me.vertices) != p.vcount:
        p.kind = ""          # mesh was edited: it is an Editable Poly now
        return False
    if p.kind in extended_primitives.PRIMITIVES:
        guarded = _guard[0]
        _guard[0] = True
        try:
            extended_primitives.constrain(p)
        finally:
            _guard[0] = guarded
    bm = build_bmesh(p.kind, p)
    if "max_pivot_offset" in ob:
        bmesh.ops.translate(bm, verts=bm.verts, vec=ob["max_pivot_offset"])
    bm.to_mesh(me)
    bm.free()
    me.update()
    if p.kind in extended_primitives.PRIMITIVES:
        extended_primitives.mapping(ob)
    p.vcount = len(me.vertices)
    return True


_guard = [False]


def _update(self, context):
    if _guard[0]:
        return
    ob = self.id_data
    _guard[0] = True
    try:
        rebuild(ob)
    finally:
        _guard[0] = False


class MaxPrimParams(bpy.types.PropertyGroup):
    kind: StringProperty(default="")
    vcount: IntProperty(default=0)
    length: FloatProperty(name="Length", default=1.0, min=0.0001, unit="LENGTH", update=_update)
    width: FloatProperty(name="Width", default=1.0, min=0.0001, unit="LENGTH", update=_update)
    height: FloatProperty(name="Height", default=1.0, unit="LENGTH", update=_update)
    radius1: FloatProperty(name="Radius 1", default=1.0, min=0.0, unit="LENGTH", update=_update)
    radius2: FloatProperty(name="Radius 2", default=0.0, min=0.0, unit="LENGTH", update=_update)
    length_segs: IntProperty(name="Length Segs", default=1, min=1, max=200, update=_update)
    width_segs: IntProperty(name="Width Segs", default=1, min=1, max=200, update=_update)
    height_segs: IntProperty(name="Height Segs", default=1, min=1, max=200, update=_update)
    sides: IntProperty(name="Sides", default=18, min=1, max=200, update=_update)
    smooth: BoolProperty(name="Smooth", default=True, update=_update)


MaxPrimParams.__annotations__.update(extended_primitives.property_definitions(_update))


def set_params(ob, kind, **values):
    """Assign parameters without triggering a rebuild for each one, then rebuild once."""
    p = ob.max_prim
    _guard[0] = True
    try:
        p.kind = kind
        p.vcount = 0
        defaults = (extended_primitives.defaults(kind) if kind in extended_primitives.PRIMITIVES
                    else DEFAULTS.get(kind, {}))
        for k, v in {**defaults, **values}.items():
            setattr(p, k, v)
    finally:
        _guard[0] = False
    rebuild(ob)


def collapse(ob):
    if hasattr(ob, "max_prim"):
        ob.max_prim.kind = ""


classes = (MaxPrimParams,)


def register_props():
    bpy.types.Object.max_prim = bpy.props.PointerProperty(type=MaxPrimParams)


def unregister_props():
    del bpy.types.Object.max_prim
