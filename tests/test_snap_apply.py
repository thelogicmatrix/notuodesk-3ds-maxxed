"""Preview acceptance must differ from free motion. Run with run_checks.py."""
from types import SimpleNamespace
import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import snaps, max_status

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
s = snaps.settings(bpy.context)
for key, _ in snaps.TYPES:
    setattr(s, key, key == 'vertex')
s.mode = '3D'
s.snap_radius, s.preview_radius = 20, 30
bpy.context.scene.tool_settings.use_snap = True
mesh = bpy.data.meshes.new('Target')
mesh.from_pydata([(1, 1, 2)], [], [])
ob = bpy.data.objects.new('Target', mesh)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.update()
region = SimpleNamespace(width=1000, height=1000)
rv = SimpleNamespace(perspective_matrix=Matrix.Diagonal((.4, .4, .1, 1)), is_perspective=False)
plane = (Vector(), Vector((0, 0, 1)))
raw = Vector((1.12, 1, 0))
co = Vector((724, 700))
free = snaps.snap_point(bpy.context, region, rv, co, raw, plane)
assert (free-raw).length < 1e-6, free
accepted = snaps.snap_point(bpy.context, region, rv, co, raw, plane, commit=True)
assert (accepted-Vector((1, 1, 2))).length < 1e-6, accepted
print('SNAP_APPLY preview remains free at24px, release accepts exact vertex PASS', flush=True)
assert max_status._message == 'Vertex snap on Target at [1.0, 1.0, 2.0]', max_status._message
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = .01
bpy.context.scene.unit_settings.length_unit = 'MILLIMETERS'
snaps.snap_point(bpy.context, region, rv, co, raw, plane)
assert max_status._message == 'Vertex snap on Target at [10.0, 10.0, 20.0]', max_status._message
snaps.clear_preview(region)
assert not max_status._message, max_status._message
print('SNAP_APPLY live target prompt converts world coordinates to scene millimeters and clears PASS', flush=True)
far = snaps.snap_point(bpy.context, region, rv, (740, 700), raw, plane, commit=True)
assert (far-raw).length < 1e-6, far
print('SNAP_APPLY release outside preview radius stays free PASS', flush=True)
for override in ('OFF', 'NONE'):
    s.override = override
    bpy.context.scene.tool_settings.use_snap = False
    got = snaps.snap_point(bpy.context, region, rv, co, raw, plane, commit=True)
    assert (got-raw).length < 1e-6, (override, got)
print('SNAP_APPLY disabled snaps and None override never commit target PASS', flush=True)
