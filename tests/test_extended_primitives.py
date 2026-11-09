"""Run with isolated profile: blender -b --factory-startup --python tests/test_extended_primitives.py"""

import math
import sys
import traceback

import addon_utils
import bmesh
import bpy


def check_mesh(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    assert bm.faces, ob.name
    assert all(v.link_faces for v in bm.verts), (ob.name, "loose vertices")
    assert all(e.is_manifold for e in bm.edges), (ob.name, "open/nonmanifold edges")
    assert all(f.calc_area() > 1e-12 for f in bm.faces), (ob.name, "degenerate face")
    assert bm.calc_volume() > 0, (ob.name, "inward normals")
    bm.free()
    assert not ob.data.validate(), (ob.name, "invalid mesh")


def run():
    addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
    from notuodesk_3ds_maxxed import prims, extended_primitives as ext
    kinds = {"HEDRA", "CHAMFERBOX", "OILTANK", "SPINDLE", "GENGON", "PRISM",
             "TORUS_KNOT", "CHAMFERCYL", "CAPSULE", "L_EXT", "C_EXT"}
    assert set(ext.PRIMITIVES) == kinds
    # Impossible triangles must not leave displayed lengths unlike the mesh.
    ob = bpy.data.objects.new("PrismLimits", bpy.data.meshes.new("PrismLimits"))
    bpy.context.collection.objects.link(ob)

    def check_prism():
        p = ob.max_prim
        lengths = sorted((p.side1, p.side2, p.side3))
        assert lengths[0] > 0 and lengths[2] < lengths[0]+lengths[1], ("stored triangle", lengths)
        base = [v.co for v in ob.data.vertices if abs(v.co.z) < 1e-8]
        assert len(base) == 3
        actual = sorted((base[i]-base[(i+1) % 3]).length for i in range(3))
        assert all(math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-8)
                   for a, b in zip(actual, lengths)), ("Prism displayed/mesh sides", lengths, actual)
        check_mesh(ob)

    for sides in ((1, 1, 25), (25, 1, 1), (1, 25, 1), (1, 2, 1),
                  (0, 0, 0), (0, 1, 1), (3, 4, 5)):
        prims.set_params(ob, "PRISM", **dict(zip(("side1", "side2", "side3"), sides)))
        check_prism()
        if sides == (3, 4, 5):
            assert (ob.max_prim.side1, ob.max_prim.side2, ob.max_prim.side3) == sides
    for prop in ("side1", "side2", "side3"):
        prims.set_params(ob, "PRISM", side1=3, side2=4, side3=5)
        setattr(ob.max_prim, prop, 100)
        check_prism()
        setattr(ob.max_prim, prop, 0)
        check_prism()
    print("PASS Prism stored/mesh sides: invalid triangles, zero lengths, valid scalene, live edits", flush=True)
    for kind in ext.PRIMITIVES:
        ob = bpy.data.objects.new(kind, bpy.data.meshes.new(kind))
        bpy.context.collection.objects.link(ob)
        for name, values in (("defaults", {}), ("minimum", dict(sides=3, segments=3,
                height_segs=1, cap_segs=1, fillet_segs=1)), ("zero fillet", dict(fillet=0)),
                ("large fillet", dict(fillet=1000, cap_height=1000)),
                ("negative height", dict(height=-3))):
            prims.set_params(ob, kind, **values)
            check_mesh(ob)
            print("PASS mesh", kind, name, len(ob.data.vertices), flush=True)
        prims.set_params(ob, kind)
        p = ob.max_prim
        if kind == "CHAMFERBOX":
            expected = (.1, .1, .1)
        elif kind in {"CHAMFERCYL", "OILTANK", "SPINDLE"}:
            expected = (2, 2, 1)
        elif kind == "CAPSULE":
            expected = (30, 30, 55)
        elif kind == "PRISM":
            expected = (25, math.sqrt(25**2 - 12.5**2), 10)
        elif kind == "GENGON":
            expected = (1+math.cos(math.pi/5),2*math.sin(math.tau/5),1)
        elif kind in {"L_EXT", "C_EXT"}:
            expected = (1, 1, 1)
        else:
            expected = None
        bpy.context.view_layer.update()
        if expected:
            assert all(abs(a-b) < 1e-4 for a, b in zip(ob.dimensions, expected)), (kind, tuple(ob.dimensions), expected)
            print("PASS dimensions", kind, tuple(round(v, 4) for v in ob.dimensions), flush=True)
        if kind == "HEDRA":
            assert abs(max(v.co.length for v in ob.data.vertices)-25)<1e-4
        before = [tuple(v.co) for v in ob.data.vertices]
        p.radius1 *= 1.25 if kind not in {"CHAMFERBOX", "PRISM", "L_EXT", "C_EXT"} else 1
        if kind in {"CHAMFERBOX", "PRISM", "L_EXT", "C_EXT"}:
            p.height += .25
        assert before != [tuple(v.co) for v in ob.data.vertices], kind
        p.smooth = False
        assert not any(face.use_smooth for face in ob.data.polygons)
        p.smooth = True
        assert any(face.use_smooth for face in ob.data.polygons)
        p.generate_mapping = True
        assert ob.data.uv_layers, kind
        p.generate_mapping = False
        assert not ob.data.uv_layers, kind
        prims.collapse(ob)
        assert not p.kind
    # Regression: standard primitive defaults and builders still work.
    for kind in ("BOX", "CONE", "SPHERE", "GEOSPHERE", "CYLINDER", "TUBE", "TORUS", "PYRAMID", "PLANE"):
        ob = bpy.data.objects.new(kind, bpy.data.meshes.new(kind))
        bpy.context.collection.objects.link(ob)
        prims.set_params(ob, kind, radius2=.25)
        assert len(ob.data.polygons)
    cases = [
        ("CHAMFERBOX", dict(length_segs=3,width_segs=4,height_segs=3,fillet=.02)),
        ("CHAMFERCYL", dict(sides=8,cap_segs=4,fillet_segs=4,height_segs=3,fillet=.2)),
        ("L_EXT", dict(side_segs=3,front_segs=4,width_segs=3,height_segs=2)),
        ("C_EXT", dict(back_length=2,back_segs=3,side_segs=4,front_segs=3,width_segs=2,height_segs=3)),
        ("PRISM", dict(side1=3,side2=4,side3=5,side1_segs=3,side2_segs=4,side3_segs=5,height_segs=3)),
        ("GENGON", dict(fillet=.2,fillet_segs=5,side_segs=3,height_segs=4)),
        ("CAPSULE", dict(height_type="OVERALL",height=1,radius1=3)),
        ("OILTANK", dict(height_type="CENTERS",blend=.2,height_segs=3)),
        ("SPINDLE", dict(height_type="CENTERS",blend=.3,height_segs=3)),
        ("TORUS_KNOT", dict(base_curve="CIRCLE",radius1=3,radius2=.2,warp_count=5,
                            warp_height=10,lumps=4,lump_height=20,twist=2,eccentricity=.5)),
        ("TORUS_KNOT", dict(knot_p=4,knot_q=6,radius2=.1)),
    ]
    for family in ("TETRA","CUBE_OCTA","DODEC_ICOS","STAR1","STAR2"):
        for values in ({},dict(hedra_p=.2,hedra_q=.3),dict(hedra_p=1),dict(hedra_q=1),
                       dict(vertices="CENTER"),dict(vertices="CENTER_SIDES",scale_p=90,scale_q=110)):
            cases.append(("HEDRA",dict(family=family,**values)))
    for kind,values in cases:
        ob = bpy.data.objects.new(kind,bpy.data.meshes.new(kind))
        bpy.context.collection.objects.link(ob)
        prims.set_params(ob,kind,**values)
        check_mesh(ob)
        print("PASS variant",kind,values,flush=True)
    ob = bpy.data.objects.new("OilCap",bpy.data.meshes.new("OilCap"))
    bpy.context.collection.objects.link(ob)
    prims.set_params(ob,"OILTANK")
    # OilTank uses spherical sections, not flattened hemispheres.
    sphere_radius = 2.125  # (1**2 + .25**2)/(2*.25)
    for v in ob.data.vertices:
        x,y,z = v.co
        if z <= .25001:
            assert abs(x*x+y*y+(z-sphere_radius)**2-sphere_radius**2)<1e-5, ("oil cap",tuple(v.co))
    prims.set_params(ob,"HEDRA",hedra_p=.8,hedra_q=.9)
    assert ob.max_prim.hedra_p+ob.max_prim.hedra_q <= 1.000001
    for kind in ("CHAMFERBOX","CHAMFERCYL","GENGON"):
        prims.set_params(ob,kind,fillet=1000)
        assert ob.max_prim.fillet < 1, (kind,"unclamped fillet")
    print("PASS spherical OilTank caps and dependent parameter limits",flush=True)
    prims.set_params(ob,"TORUS_KNOT",base_curve="CIRCLE",radius1=3,radius2=.25)
    bpy.context.view_layer.update()
    assert all(abs(a-b)<1e-5 for a,b in zip(ob.dimensions,(6.5,6.5,.5))), tuple(ob.dimensions)
    # A 4/6 winding pair is a two-component link, not one duplicated curve.
    prims.set_params(ob,"TORUS_KNOT",knot_p=4,knot_q=6,radius2=.1)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    remaining, components = set(bm.verts), 0
    while remaining:
        pending = [remaining.pop()]
        components += 1
        while pending:
            v = pending.pop()
            for edge in v.link_edges:
                other = edge.other_vert(v)
                if other in remaining:
                    remaining.remove(other)
                    pending.append(other)
    assert components == 2, components
    bm.free()
    # Editing the topology ends parametric rebuilding, as with Standard Primitives.
    prims.set_params(ob,"CHAMFERBOX")
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.new((5,5,5))
    bm.to_mesh(ob.data)
    bm.free()
    ob.max_prim.height = 2
    assert not ob.max_prim.kind
    assert max(v.co.x for v in ob.data.vertices) == 5
    print("PASS circle bounds, torus link components, edited-mesh preservation",flush=True)
    print("PASS shape variants:",len(cases),flush=True)
    print("PASS standard primitives regression: 9 kinds", flush=True)
    print("PASS extended primitives: 11 kinds, 55 mesh cases, dimensions, rebuild, UVs, collapse", flush=True)


try:
    run()
except Exception:
    traceback.print_exc()
    sys.exit(1)
