"""Disable/re-enable in a dedicated process. Run through run_checks.py."""
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry


def shape(ob):
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    coords = sorted(tuple(round(x, 5) for x in v.co) for v in mesh.vertices)
    ev.to_mesh_clear()
    assert coords
    return coords


for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
symmetry.reconcile()
bpy.ops.mesh.primitive_cube_add(size=.2, location=(2, .4, 0))
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
ob = bpy.context.object
mod = symmetry.add(ob)
p = symmetry.settings(mod)
p.radial, p.count, p.slice = True, 6, False
symmetry.plane(mod).location = (.3, -.1, .2)
symmetry.plane(mod).rotation_euler = (.2, .3, .4)
before = shape(ob)
addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)
assert shape(ob) == before
assert symmetry._draw_handle is None
assert symmetry._changed not in bpy.app.handlers.depsgraph_update_post
assert not bpy.app.timers.is_registered(symmetry._maintain)
ob.data.vertices[0].co.z += .25
ob.data.update()
disabled_edit = shape(ob)
assert disabled_edit != before
addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
symmetry.reconcile()
assert shape(ob) == disabled_edit
assert sum(bool(o.get(symmetry.HELPER)) for o in bpy.data.objects) == 1
ob.modifiers.remove(mod)
symmetry.reconcile()
assert not any(o.get(symmetry.HELPER) for o in bpy.data.objects)
print('RADIAL PASS disabled geometry and native live edits preserved, re-enable and removal clean', flush=True)
