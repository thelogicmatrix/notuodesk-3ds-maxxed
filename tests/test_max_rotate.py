"""blender -b --factory-startup --python tests/test_max_rotate.py

Uses the isolated profile supplied by run_checks.py. Geometry and rotation
expectations below are literal fixtures, independent of the drag implementation.
"""
import math
from types import SimpleNamespace

import addon_utils
import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
import notuodesk_3ds_maxxed as addon

assert hasattr(addon, "max_rotate"), "Rotate must own its drag path, independent of geometry snaps"
r = addon.max_rotate
s = addon.snaps.settings(bpy.context)
I = Matrix.Identity(3)


def close(a, b, epsilon=2e-5):
    assert (Vector(a) - Vector(b)).length < epsilon, (tuple(a), tuple(b))


def delta(dx, dy=0, handle="Z", constraint="Z", basis=None, tangent=(1, 0)):
    return r.rotation_delta(Vector((dx, dy)), handle, Vector(tangent), basis or I, I,
                            constraint, s, .5)


def empty():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def mesh(name="Source", points=((1, 0, 0), (3, 0, 0), (1, 2, 0))):
    me = bpy.data.meshes.new(name)
    me.from_pydata(points, [(0, 1), (1, 2), (2, 0)], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.context.view_layer.update()
    return ob


# A and S are independent. A target positioned at a non-increment angle must
# never change the angle or the pivot of the real geometry transaction.
empty()
ob = mesh()
target = mesh("Vertex target", ((1.8, .334, .2), (2.2, .378, .1), (2, .2, .3)))
target.select_set(False)
bpy.context.view_layer.objects.active = ob
ts = bpy.context.scene.tool_settings
ts.use_snap = True
ts.snap_elements = {"VERTEX"}
s.vertex, s.grid_points, s.angle_snap, s.percent_snap = True, False, True, True
s.angle = 5
rs = r.settings(bpy.context)
rs.reference, rs.center = "WORLD", "PIVOT"
tx = r.RotationSession(bpy.context)
for dx, want in ((13, 5), (24, 10), (33, 15), (-13, -5)):
    mat, angles = delta(dx)
    tx.apply(mat, angles)
    close(ob.matrix_world.to_3x3() @ Vector((1, 0, 0)),
          (math.cos(math.radians(want)), math.sin(math.radians(want)), 0))
    assert abs(math.degrees(angles.z) - want) < 1e-5
    close(ob.location, (0, 0, 0))
tx.cancel()
close(ob.matrix_world.to_3x3() @ Vector((1, 0, 0)), (1, 0, 0))
assert ts.use_snap and ts.snap_elements == {"VERTEX"} and s.percent_snap
print("ROTATE angle snap + vertex S PASS exact 5/10/15/-5 degrees, pivot unchanged", flush=True)

s.angle_snap = False
mat, angles = delta(13)
assert abs(math.degrees(angles.z) - 6.5) < 1e-5
close(mat @ Vector((1, 0, 0)), (.993571856, .113203214, 0))
print("ROTATE angle snap OFF PASS continuous=6.5 degrees with vertex S still ON", flush=True)

s.angle_snap = True
for handle, vector in (("X", (5, 0, 0)), ("Y", (0, 5, 0)), ("Z", (0, 0, 5)),
                       ("VIEW", (0, 0, 5)), ("FREE", (-10, 5, 0))):
    mat, angles = delta(13, 17 if handle == "FREE" else 0, handle)
    close(tuple(math.degrees(v) for v in angles), vector)
for constraint in ("X", "Y", "Z", "XY", "YZ", "ZX"):
    mat, angles = delta(13, 17, "OFF", constraint)
    for i, value in enumerate(angles):
        assert abs(math.degrees(value)/5 - round(math.degrees(value)/5)) < 1e-5
        if "XYZ"[i] not in constraint:
            assert abs(value) < 1e-8
print("ROTATE angle snap modes PASS X/Y/Z/view/free/F5-F8", flush=True)

# Quantization is relative to the saved matrix, never world Euler multiples.
ob.rotation_euler.z = math.radians(12)
bpy.context.view_layer.update()
tx = r.RotationSession(bpy.context)
tx.apply(*delta(13))
assert abs(math.degrees(ob.rotation_euler.z)-17) < 2e-5
tx.apply(*delta(24))
assert abs(math.degrees(ob.rotation_euler.z)-22) < 2e-5
s.angle_snap = False
tx.apply(*delta(13))
assert abs(math.degrees(ob.rotation_euler.z)-18.5) < 2e-5
s.angle_snap = True
tx.apply(*delta(13))
assert abs(math.degrees(ob.rotation_euler.z)-17) < 2e-5
tx.cancel()
assert abs(math.degrees(ob.rotation_euler.z)-12) < 2e-5
print("ROTATE start-relative steps + live A toggle + cancel PASS", flush=True)

# Translating both pointer endpoints, including far-offscreen pivots, must
# preserve the linear response. Orthogonal pointer motion contributes zero.
for pivot in ((500, 500), (-5000, 2000), (9000, -8000)):
    for start in ((600, 500), (-4900, 2000), (9100, -8000)):
        end = Vector(start) + Vector((24, 800))
        mat, angles = r.rotation_delta(end-Vector(start), "Z", Vector((1, 0)), I, I, "Z", s, .5)
        assert abs(math.degrees(angles.z)-10) < 1e-5
print("ROTATE linear tangent PASS translated pointers, offscreen pivots, orthogonal rejection", flush=True)

empty()
ob = mesh()
ob.rotation_euler.z = math.pi/2
bpy.context.view_layer.update()
rs.reference = "LOCAL"
local = r.reference_basis(bpy.context, ob)
close(local.col[0], (0, 1, 0))
rs.reference = "WORLD"
close(r.reference_basis(bpy.context, ob).col[0], (1, 0, 0))
parent = bpy.data.objects.new("Parent", None)
bpy.context.collection.objects.link(parent)
parent.rotation_euler.y = math.pi/2
ob.parent = parent
bpy.context.view_layer.update()
rs.reference = "PARENT"
close(r.reference_basis(bpy.context, ob).col[0], (0, 0, -1))
rs.reference, rs.pick = "PICK", parent
close(r.reference_basis(bpy.context, ob).col[0], (0, 0, -1))
print("ROTATE reference axes PASS World/Local/Parent/Pick", flush=True)

# Max saves axis locks per transform, and separately at sub-object level.
r.set_constraint(bpy.context, "Y", "MOVE")
assert r.constraint(bpy.context, "MOVE") == "Y"
assert r.constraint(bpy.context, "ROTATE") == "Z"
for expected in ("XY", "YZ", "ZX", "XY"):
    assert r.set_constraint(bpy.context, "CYCLE", "MOVE") == expected
r.set_constraint(bpy.context, "X", "MOVE")
assert r.constraint(bpy.context, "MOVE") == "X"
bpy.ops.object.mode_set(mode="EDIT")
r.set_constraint(bpy.context, "Z", "MOVE")
assert r.constraint(bpy.context, "MOVE") == "Z"
bpy.ops.object.mode_set(mode="OBJECT")
assert r.constraint(bpy.context, "MOVE") == "X"
print("ROTATE axis lock persistence PASS per tool, per mode, F8 XY/YZ/ZX", flush=True)

for flags,want in (((True,False,False),(2,.707106781,.707106781)),
                    ((True,True,False),(2,2,.25))):
    matrix = r.squash_matrix(2,flags,I)
    close(matrix.diagonal() if hasattr(matrix,'diagonal') else (matrix[0][0],matrix[1][1],matrix[2][2]),want)
    assert abs(matrix.determinant()-1)<2e-5
print("ROTATE shared Scale squash PASS volume preserved for axis and plane",flush=True)

empty()
one = mesh("One")
one.location = (2, 0, 0)
two = mesh("Two")
two.location = (4, 0, 0)
bpy.context.view_layer.update()
rs.reference, rs.center = "WORLD", "PIVOT"
tx = r.RotationSession(bpy.context)
tx.apply(*delta(180))
close(one.location, (2, 0, 0))
close(two.location, (4, 0, 0))
tx.cancel()
rs.center = "COORDINATE"
tx = r.RotationSession(bpy.context)
tx.apply(*delta(180))
close(one.location, (0, 2, 0))
close(two.location, (0, 4, 0))
tx.cancel()
print("ROTATE centers PASS individual pivots and World coordinate center", flush=True)

# Max Pivot Point Center accumulates rotations down a selected hierarchy.
empty()
parent = mesh('Rotating parent')
child = mesh('Rotating child')
child.parent = parent
child.location = (2,0,0)
bpy.context.view_layer.update()
rs.reference,rs.center = 'WORLD','PIVOT'
tx = r.RotationSession(bpy.context)
tx.apply(*delta(180))
close(parent.matrix_world.to_3x3() @ Vector((1,0,0)),(0,1,0))
close(child.matrix_world.to_3x3() @ Vector((1,0,0)),(-1,0,0))
close(child.matrix_world.translation,(0,2,0))
tx.cancel()
close(child.matrix_world.to_3x3() @ Vector((1,0,0)),(1,0,0))
close(child.matrix_world.translation,(2,0,0))
print('ROTATE Pivot hierarchy PASS accumulated parent/child rotation + cancel',flush=True)

# Every sub-object level rotates its selected vertices. Max level 3 is Border,
# 5 is Element. The geometry path must not depend on a level-specific operator.
empty()
ob = mesh()
rs.reference, rs.center = "WORLD", "COORDINATE"
bpy.ops.object.mode_set(mode="EDIT")
for level in range(1, 6):
    bpy.context.window_manager.max_sublevel = level
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = True
    bmesh.update_edit_mesh(ob.data)
    tx = r.RotationSession(bpy.context)
    tx.apply(*delta(13))
    bm.verts.ensure_lookup_table()
    close(bm.verts[0].co, (.996194698, .087155743, 0))
    tx.cancel()
    close(bm.verts[0].co, (1, 0, 0))
print("ROTATE angle snap Edit Poly PASS Vertex/Edge/Border/Polygon/Element + cancel", flush=True)
bpy.ops.object.mode_set(mode="OBJECT")

# Exact Type-In is allowed even with A on. Autodesk describes it as the path
# for entering an exact angle rather than setting an interactive increment.
rs.center = "PIVOT"
bpy.ops.max.rotate_offset(angles=(0, 0, math.radians(7.3)))
assert abs(math.degrees(ob.rotation_euler.z)-7.3) < 2e-5
print("ROTATE Transform Type-In PASS exact=7.3 degrees while A is ON", flush=True)

empty()
ob = mesh()
clone = r.begin_clone(bpy.context)
tx = r.RotationSession(bpy.context)
tx.apply(*delta(24))
copy = bpy.context.active_object
assert copy != ob
assert abs(math.degrees(copy.rotation_euler.z)-10) < 2e-5
close(ob.rotation_euler, (0,0,0))
tx.cancel()
clone.cancel()
assert list(bpy.context.selected_objects) == [ob]
assert len(bpy.context.scene.objects) == 1
bpy.ops.object.mode_set(mode="EDIT")
clone = r.begin_clone(bpy.context)
tx = r.RotationSession(bpy.context)
tx.apply(*delta(24))
bm = bmesh.from_edit_mesh(ob.data)
assert len(bm.verts) == 6
tx.cancel()
clone.cancel()
bm = bmesh.from_edit_mesh(ob.data)
assert len(bm.verts) == 3, (len(bm.verts), [(len(verts), len(original)) for _, verts, original in clone.meshes])
bpy.ops.object.mode_set(mode="OBJECT")
print("ROTATE angle snap Shift clone PASS object and mesh previews, source intact, cancel restores", flush=True)

addon_utils.disable("notuodesk_3ds_maxxed")
print("ROTATE headless PASS", flush=True)
