"""Run with isolated BLENDER_USER_* paths:
blender -b --factory-startup --python tests/test_max_snaps.py
"""
import math
import os
import tempfile
from types import SimpleNamespace

import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
import notuodesk_3ds_maxxed as addon

assert hasattr(addon, "snaps"), "Max snapping module must be registered"
snaps = addon.snaps
s = snaps.settings(bpy.context)
assert s.grid_points and not s.vertex
assert s.snap_radius == 20 and s.preview_radius == 30
assert s.angle == 5 and s.percent == 10
print("SNAPS defaults PASS", flush=True)
before = s.axis_constraints
bpy.ops.max.snap_toggle(kind="AXIS_CONSTRAINTS")
assert s.axis_constraints != before
bpy.ops.max.snap_toggle(kind="AXIS_CONSTRAINTS")
assert s.axis_constraints == before
print("SNAPS axis constraint toggle PASS", flush=True)

# A 1000px view with 5 world units across gives 200px per unit.
# Catch unconditional rounding and zoom-dependent world-space thresholds.
region = SimpleNamespace(width=1000, height=1000)
rv = SimpleNamespace(perspective_matrix=Matrix.Diagonal((.4, .4, .1, 1)),
                     is_perspective=False)
plane = (Vector((0, 0, 0)), Vector((0, 0, 1)))
def screen(p):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    return location_3d_to_region_2d(region, rv, Vector(p))
def snap(p, **kw):
    p = Vector(p)
    return snaps.snap_point(bpy.context, region, rv, screen(p), p, plane, **kw)
def near(a, b):
    assert (Vector(a) - Vector(b)).length < 1e-5, (tuple(a), b)

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.context.view_layer.update()
bpy.context.scene.tool_settings.use_snap = True
s.grid_spacing = 1
near(snap((1.3, 1, 0)), (1.3, 1, 0))
near(snap((1.04, 1, 0)), (1, 1, 0))
near(snap((1.11, 1, 0)), (1.11, 1, 0))
print("SNAPS magnetic grid PASS far=1.300000 near=1.000000 preview=1.110000", flush=True)

# Height snapping uses the same function, including a screen-space metric
# when the creation height axis points straight at the viewer.
near(snap((0, 0, 1.3), axis=Vector((0, 0, 1)), pixels_per_unit=200), (0, 0, 1.3))
near(snap((0, 0, 1.04), axis=Vector((0, 0, 1)), pixels_per_unit=200), (0, 0, 1))
s.mode = "2_5D"
near(snap((0, 0, 1.04), axis=Vector((0, 0, 1)), pixels_per_unit=200), (0, 0, 1))
s.mode = "3D"
print("SNAPS magnetic height PASS", flush=True)

s.grid_points = False
s.vertex = True
me = bpy.data.meshes.new("Target")
me.from_pydata([(1, 1, 3)], [], [])
ob = bpy.data.objects.new("Target", me)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.update()
s.mode = "2D"
near(snap((1.01, 1, 0)), (1.01, 1, 0))
s.mode = "2_5D"
near(snap((1.01, 1, 0)), (1, 1, 0))
s.mode = "3D"
near(snap((1.01, 1, 0)), (1, 1, 3))
print("SNAPS 2D 2.5D 3D PASS", flush=True)
ob.hide_select = True
ob["max_frozen_color"] = [1, 1, 1, 1]
s.snap_frozen = False
near(snap((1.01, 1, 0)), (1.01, 1, 0))
s.snap_frozen = True
near(snap((1.01, 1, 0)), (1, 1, 3))
print("SNAPS frozen filtering PASS", flush=True)

# A one-shot override must supersede Vertex, then restore it.
bpy.ops.max.snap_override(kind="grid_points")
near(snap((1.04, 1, 0)), (1, 1, 0))
snaps.consume_override(bpy.context)
near(snap((1.04, 1, 0)), (1, 1, 3))
bpy.ops.max.snap_override(kind="OFF")
near(snap((1.04, 1, 0)), (1.04, 1, 0))
snaps.consume_override(bpy.context)
assert s.vertex and not s.grid_points
print("SNAPS one-shot override and None PASS", flush=True)

bpy.data.objects.remove(ob, do_unlink=True)
me = bpy.data.meshes.new("Triangle")
me.from_pydata([(.5, .5, 0), (1.5, .5, 0), (.5, 1.5, 0)], [(0, 1), (1, 2), (2, 0)], [(0, 1, 2)])
ob = bpy.data.objects.new("Triangle", me)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.update()
for kind, point, want in (
    ("pivot", (.02, 0, 0), (0, 0, 0)),
    ("bounding_box", (.54, .5, 0), (.5, .5, 0)),
    ("endpoint", (.54, .5, 0), (.5, .5, 0)),
    ("edge", (1, .54, 0), (1, .5, 0)),
    ("midpoint", (1.04, .5, 0), (1, .5, 0)),
    ("perpendicular", (1, .54, 0), (1, .5, 0)),
    ("center_face", (.85, .83, 0), (5/6, 5/6, 0)),
    ("grid_lines", (1.04, 1.3, 0), (1, 1.3, 0)),
):
    for key, _ in snaps.TYPES:
        setattr(s, key, key == kind)
    near(snap(point, base=Vector((1, 1, 0))), want)
print("SNAPS pivot bounding-box endpoint edge midpoint perpendicular center-face grid-lines PASS", flush=True)

s.angle_snap = True
assert abs(snaps.snap_angle(s, math.radians(17)) - math.radians(15)) < 1e-6
s.percent_snap = True
assert abs(snaps.snap_scale(s, 1.23) - 1.2) < 1e-6
print("SNAPS angle=15 percent=120 PASS", flush=True)

s.angle = 7.5
s.grid_spacing = 2.5
path = os.path.join(tempfile.gettempdir(), "max-snaps-settings-test.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
s.angle = 8.5
bpy.ops.wm.open_mainfile(filepath=path)
assert snaps.settings(bpy.context).angle == 8.5
assert snaps.settings(bpy.context).grid_spacing == 2.5
snaps.settings(bpy.context).angle = 7.5
bpy.ops.wm.save_userpref()
snaps.settings(bpy.context).angle = 1
bpy.ops.wm.read_userpref()
addon._prefs_cache[0] = None
assert snaps.settings(bpy.context).angle == 7.5
print("SNAPS preferences persistence and scene independence PASS", flush=True)
print("SNAPS ALL PASS", flush=True)
