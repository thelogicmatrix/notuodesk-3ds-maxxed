"""Run: blender -b --factory-startup --python tests/test_shift_clone.py

Use the isolated add-on profile described in README.md / the feature brief.
"""
import math
import unittest

import addon_utils
import bmesh
import bpy
from mathutils import Matrix

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import shift_clone


class ShiftCloneTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.mesh.primitive_cube_add()
        self.box = bpy.context.object
        self.box.name = 'Box001'

    def test_move_copy_count_names_original_and_cancel(self):
        tx = shift_clone.ObjectClone(bpy.context)
        tx.preview[0].location.x = 3
        bpy.context.view_layer.update()
        tx.finish('COPY', 3, 'Box002', 'COPY')
        boxes = sorted(bpy.context.scene.objects, key=lambda o: o.name)
        self.assertEqual([o.name for o in boxes], ['Box001', 'Box002', 'Box003', 'Box004'])
        self.assertEqual([round(o.location.x, 4) for o in boxes], [0, 3, 6, 9])
        self.assertEqual(len({o.data.as_pointer() for o in boxes}), 4)
        tx = shift_clone.ObjectClone(bpy.context)
        tx.cancel()
        self.assertEqual(len(bpy.context.scene.objects), 4)

    def test_instance_reference_scale_and_rotation(self):
        for mode in ('INSTANCE', 'REFERENCE'):
            bpy.ops.object.select_all(action='DESELECT')
            self.box.select_set(True)
            bpy.context.view_layer.objects.active = self.box
            tx = shift_clone.ObjectClone(bpy.context)
            tx.preview[0].matrix_world = Matrix.Rotation(math.pi / 4, 4, 'Z')
            bpy.context.view_layer.update()
            clones = tx.finish(mode, 4, '', 'COPY')
            self.assertTrue(all(o.data == self.box.data for o in clones))
            for i, ob in enumerate(clones, 1):
                expected = Matrix.Rotation(i * math.pi / 4, 4, 'Z')
                self.assertLess(max(abs(ob.matrix_world[r][c] - expected[r][c])
                                    for r in range(4) for c in range(4)), 1e-5)
        bpy.ops.object.select_all(action='DESELECT')
        self.box.select_set(True)
        tx = shift_clone.ObjectClone(bpy.context)
        tx.preview[0].scale = (2, 2, 2)
        bpy.context.view_layer.update()
        clones = tx.finish('COPY', 3, '', 'COPY')
        self.assertEqual([round(o.scale.x) for o in clones], [2, 4, 8])

    def test_hierarchy_and_controller_instance(self):
        child = self.box.copy()
        bpy.context.collection.objects.link(child)
        child.parent = self.box
        child.location.x = 2
        child.select_set(True)
        tx = shift_clone.ObjectClone(bpy.context)
        tx.preview[0].location.y += 3
        bpy.context.view_layer.update()
        clones = tx.finish('COPY', 1, '', 'INSTANCE')
        mapped = dict(zip(tx.originals, clones))
        self.assertEqual(mapped[child].parent, mapped[self.box])
        self.assertTrue(mapped[child].animation_data.drivers)
        self.assertFalse(mapped[self.box].animation_data)

    def test_custom_name_and_animation_preview_isolation(self):
        self.box.keyframe_insert(data_path='location', frame=1)
        action = self.box.animation_data.action
        tx = shift_clone.ObjectClone(bpy.context)
        self.assertNotEqual(tx.preview[0].animation_data.action, action)
        tx.preview[0].location.y = 4
        tx.preview[0].keyframe_insert(data_path='location', frame=2)
        tx.cancel()
        self.assertEqual(self.box.animation_data.action, action)
        self.assertEqual(self.box.location.y, 0)
        tx = shift_clone.ObjectClone(bpy.context)
        tx.preview[0].location.x = 2
        bpy.context.view_layer.update()
        clones = tx.finish('COPY', 2, 'building', 'COPY')
        self.assertEqual([o.name for o in clones], ['building', 'building001'])

    def mesh_tx(self, level):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.context.window_manager.max_sublevel = level
        return shift_clone.MeshClone(bpy.context, level)

    def test_faces_element_object_cancel_and_vertex(self):
        tx = self.mesh_tx(4)
        self.assertEqual(len(tx.bm.faces), 12)
        tx.finish('ELEMENT', '')
        self.assertEqual(len(tx.bm.faces), 12)
        tx = shift_clone.MeshClone(bpy.context, 4)
        tx.cancel()
        self.assertEqual(len(bmesh.from_edit_mesh(self.box.data).faces), 12)
        tx = shift_clone.MeshClone(bpy.context, 4)
        tx.finish('OBJECT', 'Part001')
        self.assertEqual(len(bpy.data.objects['Part001'].data.polygons), 6)
        self.assertEqual(len(bmesh.from_edit_mesh(self.box.data).faces), 12)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        tx = self.mesh_tx(1)
        before_faces = len(tx.bm.faces)
        self.assertTrue(all(not v.link_edges for v in tx.new_verts))
        tx.finish('ELEMENT', '')
        self.assertEqual(len(tx.bm.faces), before_faces)

    def test_open_border_extrude_and_cancel(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(self.box, do_unlink=True)
        bpy.ops.mesh.primitive_plane_add()
        self.box = bpy.context.object
        tx = self.mesh_tx(3)
        self.assertEqual((len(tx.bm.verts), len(tx.bm.faces)), (8, 5))
        for v in tx.new_verts:
            v.co.z += 2
        tx.finish('ELEMENT', '')
        tx = shift_clone.MeshClone(bpy.context, 3)
        tx.cancel()
        self.assertEqual((len(tx.bm.verts), len(tx.bm.faces)), (8, 5))


suite = unittest.defaultTestLoader.loadTestsFromTestCase(ShiftCloneTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('SHIFT_CLONE_HEADLESS', 'PASS' if result.wasSuccessful() else 'FAIL',
      'tests', result.testsRun, flush=True)
if not result.wasSuccessful():
    raise SystemExit(1)
