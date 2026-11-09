"""Extended primitive meshes and shared parameter metadata.

Autodesk reference: https://help.autodesk.com/cloudhelp/2015/ENU/3DSMax/files/
GUID-BF868DCF-12E3-431C-A73B-C16C0FD67C98.htm
Dimensions with zero Max constructor defaults start at one Blender unit.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

PRIMITIVES = {
    "HEDRA": ("Hedra", "MESH_ICOSPHERE", "RADIUS", False),
    "CHAMFERBOX": ("ChamferBox", "MESH_CUBE", "RECT", True),
    "OILTANK": ("OilTank", "MESH_CYLINDER", "RADIUS", True),
    "SPINDLE": ("Spindle", "MESH_CONE", "RADIUS", True),
    "GENGON": ("Gengon", "MESH_CIRCLE", "RADIUS", True),
    "PRISM": ("Prism", "MESH_CONE", "RECT", True),
    "TORUS_KNOT": ("Torus Knot", "MESH_TORUS", "RADIUS", True),
    "CHAMFERCYL": ("ChamferCyl", "MESH_CYLINDER", "RADIUS", True),
    "CAPSULE": ("Capsule", "MESH_UVSPHERE", "RADIUS", True),
    "L_EXT": ("L-Ext", "MESH_CUBE", "RECT", True),
    "C_EXT": ("C-Ext", "MESH_CUBE", "RECT", True),
}

# Property, Max label, unit. Keyboard Entry can reuse this table.
def field(prop, label, unit="NONE"):
    return (prop, label, unit)


R = field("radius1", "Radius", "LENGTH")
H = field("height", "Height", "LENGTH")
F = field("fillet", "Fillet", "LENGTH")
HS = field("height_segs", "Height Segs")
FS = field("fillet_segs", "Fillet Segs")
SIDES = field("sides", "Sides")
SMOOTH = field("smooth", "Smooth")
MAP = field("generate_mapping", "Generate Mapping Coords")
HEIGHT_TYPE = field("height_type", "Height Type")
FIELDS = {
    "HEDRA": [field("family", "Family"), field("hedra_p", "P"), field("hedra_q", "Q"),
              field("scale_p", "Axis Scaling P", "PERCENTAGE"), field("scale_q", "Axis Scaling Q", "PERCENTAGE"),
              field("scale_r", "Axis Scaling R", "PERCENTAGE"), field("vertices", "Vertices"), R],
    "CHAMFERBOX": [field("length", "Length", "LENGTH"), field("width", "Width", "LENGTH"), H, F,
                   field("length_segs", "Length Segs"), field("width_segs", "Width Segs"), HS, FS],
    "OILTANK": [R, H, field("cap_height", "Cap Height", "LENGTH"), HEIGHT_TYPE,
                field("blend", "Blend", "LENGTH"), SIDES, HS],
    "SPINDLE": [R, H, field("cap_height", "Cap Height", "LENGTH"), HEIGHT_TYPE,
                field("blend", "Blend", "LENGTH"), SIDES, field("cap_segs", "Cap Segs"), HS],
    "GENGON": [SIDES, R, F, H, field("side_segs", "Side Segs"), FS, HS],
    "PRISM": [field("side1", "Side 1 Length", "LENGTH"), field("side2", "Side 2 Length", "LENGTH"),
              field("side3", "Side 3 Length", "LENGTH"), H, field("side1_segs", "Side 1 Segs"),
              field("side2_segs", "Side 2 Segs"), field("side3_segs", "Side 3 Segs"), HS],
    "TORUS_KNOT": [field("base_curve", "Base Curve"), R, field("segments", "Segments"),
                   field("knot_p", "P"), field("knot_q", "Q"), field("warp_count", "Warp Count"),
                   field("warp_height", "Warp Height", "PERCENTAGE"),
                   field("radius2", "Cross Section Radius", "LENGTH"), SIDES,
                   field("eccentricity", "Eccentricity"), field("twist", "Twist"),
                   field("lumps", "Lumps"), field("lump_height", "Lump Height", "PERCENTAGE"),
                   field("lump_offset", "Lump Offset", "ROTATION")],
    "CHAMFERCYL": [R, H, F, HS, FS, SIDES, field("cap_segs", "Cap Segs")],
    "CAPSULE": [R, H, HEIGHT_TYPE, SIDES, HS],
    "L_EXT": [field("side_length", "Side Length", "LENGTH"), field("front_length", "Front Length", "LENGTH"),
              field("side_width", "Side Width", "LENGTH"), field("front_width", "Front Width", "LENGTH"), H,
              field("side_segs", "Side Segs"), field("front_segs", "Front Segs"),
              field("width_segs", "Width Segs"), HS],
    "C_EXT": [field("back_length", "Back Length", "LENGTH"), field("side_length", "Side Length", "LENGTH"),
              field("front_length", "Front Length", "LENGTH"), field("back_width", "Back Width", "LENGTH"),
              field("side_width", "Side Width", "LENGTH"), field("front_width", "Front Width", "LENGTH"), H,
              field("back_segs", "Back Segs"), field("side_segs", "Side Segs"),
              field("front_segs", "Front Segs"), field("width_segs", "Width Segs"), HS],
}
for _fields in FIELDS.values():
    _fields.extend((SMOOTH, MAP))

# Segment and shape defaults from Autodesk's MAXScript GeometryClass reference.
DEFAULTS = {
    "HEDRA": dict(radius1=25, smooth=False, family="TETRA", hedra_p=0, hedra_q=0,
                  scale_p=100, scale_q=100, scale_r=100, vertices="BASIC"),
    "CHAMFERBOX": dict(length=.1, width=.1, height=.1, fillet=.01, fillet_segs=3),
    "OILTANK": dict(sides=12, cap_height=.25, height_type="OVERALL", blend=0),
    "SPINDLE": dict(sides=12, cap_height=.25, cap_segs=5, height_type="OVERALL", blend=0),
    "GENGON": dict(sides=5, fillet=0, fillet_segs=1, smooth=False),
    "PRISM": dict(side1=25, side2=25, side3=25, height=10, generate_mapping=False, smooth=False),
    "TORUS_KNOT": dict(radius2=10, sides=12, segments=120, knot_p=2, knot_q=3,
                       base_curve="KNOT", eccentricity=1, twist=0, lumps=0,
                       lump_height=0, lump_offset=0, warp_count=0, warp_height=0),
    "CHAMFERCYL": dict(sides=12, fillet=0, fillet_segs=1, cap_segs=1),
    "CAPSULE": dict(radius1=15, height=25, height_type="CENTERS", sides=24),
    "L_EXT": {}, "C_EXT": {},
}

# Stages after the initial footprint drag. More stages require no modal changes.
STAGES = {
    "HEDRA": (), "CHAMFERBOX": ("height", "fillet"), "OILTANK": ("height", "cap_height"),
    "SPINDLE": ("height", "cap_height"), "GENGON": ("height", "fillet"),
    "PRISM": ("height",), "TORUS_KNOT": ("radius2",), "CHAMFERCYL": ("height", "fillet"),
    "CAPSULE": ("height",), "L_EXT": ("height", "wall_width"), "C_EXT": ("height", "wall_width"),
}


def property_definitions(update):
    """Additional fields on max_prim, without a second parametric object system."""
    props = {}
    for name in ("fillet_segs", "cap_segs", "side_segs", "front_segs", "back_segs",
                 "side1_segs", "side2_segs", "side3_segs"):
        props[name] = bpy.props.IntProperty(default=1, min=1, max=200, update=update)
    props["segments"] = bpy.props.IntProperty(default=120, min=3, max=1000, update=update)
    lengths = dict(fillet=0, cap_height=.25, blend=0, side1=25, side2=25, side3=25,
                   side_length=1, front_length=1, back_length=1,
                   side_width=.2, front_width=.2, back_width=.2)
    for name, default in lengths.items():
        props[name] = bpy.props.FloatProperty(default=default, min=0, unit="LENGTH", update=update)
    for name in ("hedra_p", "hedra_q"):
        props[name] = bpy.props.FloatProperty(default=0, min=0, max=1, update=update)
    for name in ("scale_p", "scale_q", "scale_r"):
        props[name] = bpy.props.FloatProperty(default=100, min=.01, max=1000, update=update)
    for name, default, minimum in (("knot_p", 2, 1), ("knot_q", 3, 1), ("eccentricity", 1, .001),
                                    ("twist", 0, -100), ("lumps", 0, 0), ("lump_height", 0, 0),
                                    ("warp_count", 0, 0), ("warp_height", 0, 0)):
        props[name] = bpy.props.FloatProperty(default=default, min=minimum, max=1000, update=update)
    props["lump_offset"] = bpy.props.FloatProperty(default=0, unit="ROTATION", update=update)
    for name, labels, default in (
            ("height_type", ("OVERALL", "CENTERS"), "OVERALL"),
            ("family", ("TETRA", "CUBE_OCTA", "DODEC_ICOS", "STAR1", "STAR2"), "TETRA"),
            ("vertices", ("BASIC", "CENTER", "CENTER_SIDES"), "BASIC"),
            ("base_curve", ("KNOT", "CIRCLE"), "KNOT")):
        names = {"CUBE_OCTA": "Cube/Octa", "DODEC_ICOS": "Dodec/Icos", "STAR1": "Star1",
                 "STAR2": "Star2", "CENTER_SIDES": "Center & Sides"}
        props[name] = bpy.props.EnumProperty(items=[(v, names.get(v, v.title()), "") for v in labels],
                                             default=default, update=update)
    props["generate_mapping"] = bpy.props.BoolProperty(default=True, update=update)
    return props


def defaults(kind):
    values = dict(length=1, width=1, height=1, radius1=1, radius2=0, length_segs=1,
                  width_segs=1, height_segs=1, smooth=True)
    # Reset every extended field when reusing an object or beginning a fresh creation.
    for name, prop in property_definitions(None).items():
        values[name] = prop.keywords["default"]
    values.update(DEFAULTS[kind])
    return values


def constrain(p):
    """Keep coupled limits visible in Parameters as well as in the mesh."""
    kind = p.kind
    h, r = max(abs(p.height),1e-4), max(p.radius1,1e-4)
    if kind == "HEDRA":
        p.hedra_q = min(p.hedra_q,1-p.hedra_p)
    elif kind == "CHAMFERBOX":
        p.fillet = min(p.fillet,.499*min(p.width,p.length,h))
    elif kind == "CHAMFERCYL":
        p.fillet = min(p.fillet,.999*r,.499*h)
    elif kind == "GENGON":
        p.fillet = min(p.fillet,.998*r*math.cos(math.pi/max(p.sides,3)))
    elif kind in {"OILTANK","SPINDLE"}:
        cap = max(p.cap_height,r*.025 if kind == "OILTANK" else min(.1,h*.499))
        cap = min(cap,r*.99) if kind == "OILTANK" else cap
        p.cap_height = min(cap,h*.499) if p.height_type == "OVERALL" else cap
    elif kind in {"L_EXT","C_EXT"}:
        p.side_length = max(p.side_length,1e-4)
        p.front_length = max(p.front_length,1e-4)
        p.back_length = max(p.back_length,1e-4)
        w = min(p.front_length,p.back_length) if kind == "C_EXT" else p.front_length
        p.side_width = min(max(p.side_width,1e-5),w*.999)
        limit = p.side_length*(.499 if kind == "C_EXT" else .999)
        p.front_width = min(max(p.front_width,1e-5),limit)
        p.back_width = min(max(p.back_width,1e-5),limit)


def _lathe(bm, profile, sides):
    """Revolve an ordered (radius, z) profile, welding poles by construction."""
    rings = []
    previous = None
    for r, z in profile:
        if previous and abs(r-previous[0]) < 1e-9 and abs(z-previous[1]) < 1e-9:
            continue
        previous = (r,z)
        if r < 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r*math.cos(math.tau*i/sides), r*math.sin(math.tau*i/sides), z))
                          for i in range(sides)])
    for a, b in zip(rings, rings[1:]):
        for i in range(sides):
            j = (i+1) % sides
            face = ([a[0], b[j], b[i]] if len(a) == 1 else
                    [a[i], a[j], b[0]] if len(b) == 1 else [a[i], a[j], b[j], b[i]])
            bm.faces.new(face)


def _extrude(bm, points, height, height_segs, edge_segs=None):
    outline = []
    for i, a in enumerate(points):
        b = points[(i+1) % len(points)]
        for j in range(edge_segs[i] if edge_segs else 1):
            t = j / (edge_segs[i] if edge_segs else 1)
            outline.append((a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t))
    rings = [[bm.verts.new((x, y, height*k/height_segs)) for x, y in outline]
             for k in range(height_segs+1)]
    n = len(outline)
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i+1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    caps = [bm.faces.new(list(reversed(rings[0]))), bm.faces.new(rings[-1])]
    bmesh.ops.triangulate(bm, faces=caps)


def _round_polygon(points, radius, segs, side_segs):
    if radius <= 1e-8:
        return [tuple(Vector(a).lerp(Vector(points[(i+1) % len(points)]), j/side_segs))
                for i, a in enumerate(points) for j in range(side_segs)]
    arcs = []
    for i, point in enumerate(points):
        v = Vector(point)
        prev, nxt = Vector(points[i-1])-v, Vector(points[(i+1) % len(points)])-v
        u, w = prev.normalized(), nxt.normalized()
        half = u.angle(w)/2
        distance = min(radius/math.tan(half), .499*min(prev.length, nxt.length))
        actual = distance*math.tan(half)
        center = v + (u+w).normalized()*(actual/math.sin(half))
        start = v+u*distance-center
        end = v+w*distance-center
        a0 = math.atan2(start.y, start.x)
        angle = (math.atan2(end.y, end.x)-a0) % math.tau
        arcs.append([tuple(center+Vector((actual*math.cos(a0+angle*j/segs),
                                         actual*math.sin(a0+angle*j/segs)))) for j in range(segs+1)])
    result = []
    for i, arc in enumerate(arcs):
        result.extend(arc)
        for j in range(1, side_segs):
            result.append(tuple(Vector(arc[-1]).lerp(Vector(arcs[(i+1) % len(arcs)][0]), j/side_segs)))
    return result


def _knot(bm, p, component=0):
    n, m = max(3, p.segments), max(3, p.sides)
    # Integer winding numbers close the curve. Non-coprime pairs form a link.
    a, b = max(1, round(p.knot_p)), max(1, round(p.knot_q))
    divisor = math.gcd(a, b)
    if component == 0 and p.base_curve == "KNOT":
        for index in range(1,divisor):
            _knot(bm,p,index)
    phase = math.tau*component/a
    a, b = a//divisor, b//divisor
    def center(t):
        if p.base_curve == "CIRCLE":
            r = p.radius1*(1 + p.warp_height*.01*math.cos(round(p.warp_count)*t))
            return Vector((r*math.cos(t), r*math.sin(t), 0))
        r = p.radius1*(2+math.cos(b*t+phase))/3
        return Vector((r*math.cos(a*t), r*math.sin(a*t), p.radius1*math.sin(b*t+phase)/3))
    grid = []
    for i in range(n):
        t = math.tau*i/n
        c = center(t)
        tangent = (center(t+1e-4)-center(t-1e-4)).normalized()
        # Analytic radial reference returns to the same frame at the seam.
        ref = Vector((math.cos(a*t if p.base_curve == "KNOT" else t),
                      math.sin(a*t if p.base_curve == "KNOT" else t), 0))
        normal = (ref-tangent*ref.dot(tangent)).normalized()
        binormal = tangent.cross(normal).normalized()
        radius = max(p.radius2, 1e-4)*(1+p.lump_height*.01*math.cos(round(p.lumps)*t+p.lump_offset))
        row = []
        for j in range(m):
            angle = math.tau*j/m+round(p.twist)*t
            row.append(bm.verts.new(c+radius*(math.cos(angle)*normal+
                                   p.eccentricity*math.sin(angle)*binormal)))
        grid.append(row)
    for i in range(n):
        for j in range(m):
            bm.faces.new((grid[i][j], grid[(i+1)%n][j], grid[(i+1)%n][(j+1)%m], grid[i][(j+1)%m]))


def _hedra(bm, p):
    # Wythoff reflection orbit of a point inside the spherical fundamental triangle.
    order = 3 if p.family == "TETRA" else 4 if p.family == "CUBE_OCTA" else 5
    c = math.cos(math.pi/order)
    normals = [Vector((1, 0, 0)), Vector((-c, math.sqrt(1-c*c), 0))]
    y = -.5/normals[1].y
    normals.append(Vector((0, y, math.sqrt(1-y*y))))
    matrix = Matrix(normals)
    corners = [matrix.inverted() @ Vector(axis) for axis in ((1,0,0), (0,1,0), (0,0,1))]
    corners = [v.normalized() for v in corners]
    q = min(p.hedra_q, 1-p.hedra_p)
    seed = (p.hedra_p*corners[0]+q*corners[1]+(1-p.hedra_p-q)*corners[2]).normalized()
    pending, points = [seed], []
    while pending:
        v = pending.pop()
        v.normalize()
        # mathutils stores float32. Rounded hash keys split near-identical orbit
        # points across bins after many reflections, so compare distance instead.
        if any((v-other).length_squared < 1e-8 for other in points):
            continue
        points.append(v)
        for normal in normals:
            other = v-2*v.dot(normal)*normal
            if not any((other-existing).length_squared < 1e-8 for existing in points):
                pending.append(other)
    verts = [bm.verts.new(v*p.radius1) for v in points]
    bmesh.ops.convex_hull(bm, input=verts, use_existing_faces=False)
    bmesh.ops.dissolve_limit(bm, angle_limit=1e-5, verts=list(bm.verts), edges=list(bm.edges), delimit=set())
    for v in list(bm.verts):
        if not v.link_faces:
            bm.verts.remove(v)
    if p.vertices == "CENTER_SIDES":
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, use_grid_fill=False)
    if p.vertices != "BASIC" or p.family in {"STAR1", "STAR2"} or (p.scale_p,p.scale_q,p.scale_r) != (100,100,100):
        bm.normal_update()
        for f in list(bm.faces):
            corners = list(f.verts)
            scale = (p.scale_p,p.scale_q,p.scale_r)[len(corners)%3]*.01
            if p.family in {"STAR1", "STAR2"}:
                scale *= 1.6 if p.family == "STAR1" else 2.2
            center = bm.verts.new(f.calc_center_median()*scale)
            bm.faces.remove(f)
            for i, v in enumerate(corners):
                bm.faces.new((v, corners[(i+1)%len(corners)], center))


def build_bmesh(kind, p):
    from .prims import _slice
    bm = bmesh.new()
    h, r = max(abs(p.height), 1e-4), max(p.radius1, 1e-4)
    n, hs = max(3, p.sides), max(1, p.height_segs)
    if kind == "CHAMFERBOX":
        bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, verts=list(bm.verts), vec=(p.width,p.length,h))
        bmesh.ops.translate(bm, verts=list(bm.verts), vec=(0,0,h/2))
        amount = min(p.fillet, .499*min(p.width,p.length,h))
        if amount > 1e-8:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=amount, segments=p.fillet_segs,
                            affect="EDGES", clamp_overlap=True)
        for axis, size, count in ((0,p.width,p.width_segs),(1,p.length,p.length_segs),(2,h,hs)):
            _slice(bm,axis,0 if axis == 2 else -size/2,size,count)
    elif kind in {"OILTANK", "SPINDLE", "CHAMFERCYL", "CAPSULE"}:
        if kind == "CAPSULE":
            cap = r if p.height_type == "CENTERS" else min(r,h/2*.999)
        elif kind == "CHAMFERCYL":
            cap = min(p.fillet,r*.999,h*.499)
        else:
            cap = min(max(p.cap_height,r*.025),r*.99 if kind == "OILTANK" else h*.499)
            if p.height_type == "OVERALL":
                cap = min(cap,h*.499)
        total = h+2*cap if kind in {"CAPSULE", "OILTANK", "SPINDLE"} and p.height_type == "CENTERS" else h
        profile = [(0,0)]
        cap_steps = max(1,p.cap_segs) if kind == "SPINDLE" else max(1,n//4) if kind in {"OILTANK","CAPSULE"} else p.fillet_segs
        if kind == "CHAMFERCYL":
            for j in range(1,p.cap_segs+1):
                profile.append(((r-cap)*j/p.cap_segs,0))
            if cap > 1e-8:
                profile.extend((r-cap+cap*math.sin(math.pi/2*j/cap_steps),
                                cap*(1-math.cos(math.pi/2*j/cap_steps))) for j in range(1,cap_steps+1))
        else:
            for j in range(1,cap_steps+1):
                t = j/cap_steps
                if kind == "SPINDLE":
                    profile.append((r*t,cap*t))
                elif kind == "OILTANK":
                    sphere = (r*r+cap*cap)/(2*cap)
                    angle = math.acos(1-cap/sphere)*t
                    profile.append((sphere*math.sin(angle),sphere*(1-math.cos(angle))))
                else:
                    # Capsule caps reach radius r at the cylinder seam.
                    angle = math.pi/2*t
                    rr = r*math.sin(angle)
                    zz = cap*(1-math.cos(angle))
                    profile.append((rr,zz))
        profile.extend((r,cap+(total-2*cap)*j/hs) for j in range(1,hs+1))
        bottom = profile[:len(profile)-hs]
        profile.extend((rr,total-z) for rr,z in reversed(bottom[:-1]))
        _lathe(bm,profile,n)
        if kind in {"OILTANK","SPINDLE"} and p.blend > 1e-8:
            edges = [e for e in bm.edges if all(abs(v.co.z-cap)<1e-6 for v in e.verts)
                     or all(abs(v.co.z-(total-cap))<1e-6 for v in e.verts)]
            bmesh.ops.bevel(bm,geom=edges,offset=min(p.blend,cap*.49,(total-2*cap)*.49),
                            segments=3,affect="EDGES",clamp_overlap=True)
    elif kind == "GENGON":
        points = [(r*math.cos(math.tau*i/n),r*math.sin(math.tau*i/n)) for i in range(n)]
        points = _round_polygon(points,p.fillet,p.fillet_segs,p.side_segs)
        _extrude(bm,points,h,hs)
    elif kind == "PRISM":
        a, b = max(p.side1,1e-4), max(p.side2,1e-4)
        c = min(max(p.side3,abs(a-b)+1e-4),a+b-1e-4)
        x = (a*a+c*c-b*b)/(2*a)
        y = math.sqrt(max(c*c-x*x,1e-8))
        _extrude(bm,[(-a/2,0),(a/2,0),(x-a/2,y)],h,hs,
                 (p.side1_segs,p.side2_segs,p.side3_segs))
    elif kind in {"L_EXT","C_EXT"}:
        w, l = max(p.front_length,1e-4), max(p.side_length,1e-4)
        sw, fw = min(p.side_width,w*.999), min(p.front_width,l*(.499 if kind == "C_EXT" else .999))
        sw, fw = max(sw,1e-5), max(fw,1e-5)
        if kind == "L_EXT":
            points = [(0,0),(w,0),(w,fw),(sw,fw),(sw,l),(0,l)]
        else:
            back = max(p.back_length,1e-4)
            sw = min(sw,min(w,back)*.999)
            bw = max(1e-5,min(p.back_width,l*.499))
            points = [(0,0),(w,0),(w,fw),(sw,fw),(sw,l-bw),(back,l-bw),(back,l),(0,l)]
        _extrude(bm,points,h,hs)
        _slice(bm,0,0,w,p.front_segs)
        _slice(bm,1,0,l,p.side_segs)
        if kind == "C_EXT":
            _slice(bm,0,0,back,p.back_segs)
        _slice(bm,0,0,sw,p.width_segs)
    elif kind == "TORUS_KNOT":
        _knot(bm,p)
    elif kind == "HEDRA":
        _hedra(bm,p)
    if p.height < 0 and kind not in {"HEDRA","TORUS_KNOT"}:
        bmesh.ops.scale(bm,verts=list(bm.verts),vec=(1,1,-1))
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    for f in bm.faces:
        f.smooth = p.smooth and (kind in {"HEDRA","TORUS_KNOT"} or abs(f.normal.z) < .9999)
    return bm


def mapping(ob):
    """Stable box projection, without operators or viewport context."""
    me = ob.data
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    if not ob.max_prim.generate_mapping:
        return
    uv = me.uv_layers.new(name="UVMap")
    for face in me.polygons:
        axis = max(range(3),key=lambda i:abs(face.normal[i]))
        axes = [i for i in range(3) if i != axis]
        for index in face.loop_indices:
            co = me.vertices[me.loops[index].vertex_index].co
            uv.data[index].uv = (co[axes[0]],co[axes[1]])


def draw(layout, ob):
    col = layout.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    for prop, label, unit in FIELDS[ob.max_prim.kind]:
        col.prop(ob.max_prim,prop,text=label)
