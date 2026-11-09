"""Save/reload in a dedicated process. Run through run_checks.py."""
import os
from pathlib import Path
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
bpy.ops.mesh.primitive_cube_add(size=4)
ob = bpy.context.object
ob.name = 'Radial reload'
mod = symmetry.add(ob)
p = symmetry.settings(mod)
p.radial, p.count, p.mirror_symmetry, p.radial_flip = True, 5, True, True
symmetry.plane(mod).location = (.1, -.1, .2)
symmetry.plane(mod).rotation_euler = (.2, .1, .3)
before = shape(ob)
symmetry.enter(bpy.context, mod)
path = str(Path(os.environ['MAXXED_OUT']) / 'radial-reload.blend')
bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
bpy.ops.wm.open_mainfile(filepath=path)
ob = bpy.data.objects['Radial reload']
p = symmetry.settings(ob.modifiers[0])
assert p.radial and p.count == 5 and p.mirror_symmetry and p.radial_flip
assert shape(ob) == before
assert bpy.context.object == ob
assert symmetry.plane(ob.modifiers[0]).hide_get()
assert sum(bool(o.get(symmetry.HELPER)) for o in bpy.data.objects) == 1
print('RADIAL PASS save/reload preserves controls, centre, evaluated mesh and owner selection', flush=True)
