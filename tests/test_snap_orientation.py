"""blender -b --factory-startup --python tests/test_snap_orientation.py
Use isolated BLENDER_USER_* paths.
"""
import math
import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import snaps, max_rotate

ob = bpy.context.active_object
ob.rotation_euler.z = math.pi / 2
bpy.context.view_layer.update()
slot = bpy.context.scene.transform_orientation_slots[0]
slot.type = 'LOCAL'
basis = snaps.orientation_basis(bpy.context)
assert (basis.col[0] - Vector((0, 1, 0))).length < 1e-6
slot.type = 'GLOBAL'
assert (snaps.orientation_basis(bpy.context).col[0] - Vector((1, 0, 0))).length < 1e-6
bpy.context.scene.cursor.rotation_euler = (.2, .3, .4)
slot.type = 'CURSOR'
assert max(abs(a-b) for row_a,row_b in zip(snaps.orientation_basis(bpy.context), bpy.context.scene.cursor.matrix.to_3x3())
           for a,b in zip(row_a,row_b)) < 1e-6
assert all(tool.bl_widget == 'MAX_GGT_max_transform' for tool in snaps.tools + max_rotate.tools)
print('SNAPS Global Local Cursor orientation and transform gizmos PASS', flush=True)
