"""Radial parameter and removal undo in a dedicated process."""
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
symmetry.reconcile()
bpy.ops.mesh.primitive_cube_add(size=.2, location=(2, .4, 0))
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
ob = bpy.context.object
ob.name = 'Radial undo'
p = symmetry.settings(symmetry.add(ob))
p.radial, p.count, p.slice = True, 3, False
bpy.context.preferences.edit.use_global_undo = True
bpy.ops.ed.undo_push(message='Radial three')
p.count = 12
symmetry.plane(p).location.x = .3
bpy.ops.ed.undo_push(message='Radial twelve')
bpy.ops.ed.undo()
ob = bpy.data.objects['Radial undo']
assert symmetry.settings(ob.modifiers[0]).count == 3
assert abs(symmetry.plane(ob.modifiers[0]).location.x) < 1e-5
bpy.ops.ed.redo()
ob = bpy.data.objects['Radial undo']
assert symmetry.settings(ob.modifiers[0]).count == 12
assert abs(symmetry.plane(ob.modifiers[0]).location.x-.3) < 1e-5
bpy.ops.ed.undo_push(message='Before native Radial removal')
bpy.ops.object.modifier_remove(modifier=ob.modifiers[0].name)
symmetry.reconcile()
bpy.ops.ed.undo_push(message='After native Radial removal')
assert not any(o.get(symmetry.HELPER) for o in bpy.data.objects)
bpy.ops.ed.undo()
ob = bpy.data.objects['Radial undo']
symmetry.reconcile()
assert symmetry.is_symmetry(ob.modifiers[0])
assert symmetry.settings(ob.modifiers[0]).count == 12
assert sum(bool(o.get(symmetry.HELPER)) for o in bpy.data.objects) == 1
print('RADIAL PASS Count and centre undo/redo, native removal undo restores one dependency', flush=True)
