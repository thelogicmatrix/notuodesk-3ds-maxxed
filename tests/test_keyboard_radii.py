"""Run with isolated BLENDER_USER_* paths:
blender -b --factory-startup --python-exit-code 1 --python tests/test_keyboard_radii.py
"""

import math

import addon_utils
import bmesh
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import keyboard_entry


def check_mesh(ob, closed=True):
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        assert bm.faces, "no faces"
        assert all(math.isfinite(c) for v in bm.verts for c in v.co), "non-finite vertex"
        assert all(f.calc_area() > 1e-9 for f in bm.faces), "zero-area face"
        assert all(e.calc_length() > 1e-7 for e in bm.edges), "collapsed edge"
        if closed:
            assert all(e.is_manifold for e in bm.edges), "open or non-manifold edge"
            assert all(v.is_manifold for v in bm.verts), "non-manifold vertex"
            assert bm.calc_volume(signed=True) > 1e-6, "zero or inverted volume"
    finally:
        bm.free()


failures = []


def run(label, test, *args):
    try:
        test(*args)
        print("RADII PASS", label, flush=True)
    except AssertionError as exc:
        failures.append(label)
        print("RADII FAIL", label, str(exc), flush=True)


def reject(kind, radius1, radius2):
    values = keyboard_entry.settings(bpy.context, kind)
    values.radius1, values.radius2, values.height = radius1, radius2, 4
    objects, meshes = set(bpy.data.objects), set(bpy.data.meshes)
    active = bpy.context.active_object
    selected = set(bpy.context.selected_objects)
    assert bpy.ops.max.keyboard_create(kind=kind) == {"CANCELLED"}, "invalid radii accepted"
    assert set(bpy.data.objects) == objects, "object leaked"
    assert set(bpy.data.meshes) == meshes, "mesh leaked"
    assert bpy.context.active_object == active
    assert set(bpy.context.selected_objects) == selected


def create(kind, radius1, radius2, height=4):
    values = keyboard_entry.settings(bpy.context, kind)
    values.radius1, values.radius2, values.height = radius1, radius2, height
    values.x, values.y, values.z = 2, -3, 4
    assert bpy.ops.max.keyboard_create(kind=kind) == {"FINISHED"}, "valid radii rejected"
    ob = bpy.context.active_object
    assert ob.max_prim.kind == kind
    assert (ob.max_prim.radius1, ob.max_prim.radius2) == (radius1, radius2)
    assert tuple(ob.location) == (2, -3, 4)
    # Horn and spindle tori touch or intersect themselves, as their radii imply.
    check_mesh(ob, closed=kind != "TORUS" or radius1 == 0 or radius1 > radius2)
    if kind == "TUBE":
        outer, inner = max(radius1, radius2), min(radius1, radius2)
        radii = [v.co.xy.length for v in ob.data.vertices]
        assert abs(max(radii) - outer) < 1e-5
        if inner > 0:
            assert abs(min(radii) - inner) < 1e-5
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        expected = ob.max_prim.sides / 2 * math.sin(2 * math.pi / ob.max_prim.sides)
        expected *= (outer ** 2 - inner ** 2) * abs(height)
        assert abs(bm.calc_volume() - expected) < 1e-4
        bm.free()
        assert abs(min(v.co.z for v in ob.data.vertices) - min(0, height)) < 1e-5
        assert abs(max(v.co.z for v in ob.data.vertices) - max(0, height)) < 1e-5
        # Keep Tube parameters when the solid cylinder becomes hollow and back.
        if inner == 0:
            prop = "radius1" if radius1 == 0 else "radius2"
            setattr(ob.max_prim, prop, 0.5)
            check_mesh(ob)
            assert min(v.co.xy.length for v in ob.data.vertices) > 0.49
            setattr(ob.max_prim, prop, 0)
            check_mesh(ob)
    if kind == "TORUS" and radius1 == 0:
        assert all(abs(v.co.length - radius2) < 1e-5 for v in ob.data.vertices)


for kind, r1, r2 in (
        ("TORUS", 2, 0), ("TORUS", 0, 0),
        ("TUBE", 2, 2), ("TUBE", 0, 0), ("CONE", 0, 0),
        # Radius 2 is unused for these types and must not rescue a zero radius.
        ("SPHERE", 0, 2), ("GEOSPHERE", 0, 2), ("CYLINDER", 0, 2)):
    run(f"reject {kind} {r1}/{r2} without side effects", reject, kind, r1, r2)

for kind, r1, r2, height in (
        ("TUBE", 2, 0, 4), ("TUBE", 0, 2, 4),
        ("TUBE", 2, 1, 4), ("TUBE", 1, 2, 4),
        ("TUBE", 2, 0, -4), ("TUBE", 0, 2, -4),
        ("TUBE", 2, 1, -4), ("TUBE", 1, 2, -4),
        ("CONE", 2, 0, 4), ("CONE", 0, 2, 4),
        ("CONE", 2, 2, 4), ("CONE", 1, 2, 4),
        ("TORUS", 2, 1, 4), ("TORUS", 1, 1, 4),
        ("TORUS", 1, 2, 4), ("TORUS", 0, 2, 4),
        ("SPHERE", 2, 0, 4), ("GEOSPHERE", 2, 0, 4), ("CYLINDER", 2, 0, 4)):
    run(f"create {kind} {r1}/{r2} height {height}", create, kind, r1, r2, height)

assert not failures, failures
print("RADII ALL PASS (27 cases)", flush=True)
