"""Run with scripts/run_checks.py --repo <repo> --sandbox <sandbox> --out <out> tests test_symmetry."""
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry


def evaluated(ob):
    bpy.context.view_layer.update()
    result = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = result.to_mesh()
    coords = [tuple(v.co) for v in mesh.vertices]
    faces = len(mesh.polygons)
    result.to_mesh_clear()
    return coords, faces


class SymmetryTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        symmetry.reconcile()
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object
        self.ob.name = 'SymmetryFixture'

    def add(self):
        self.assertEqual(bpy.ops.max.add_modifier(kind='SYMMETRY|Symmetry'), {'FINISHED'})
        mod = symmetry.settings(self.ob.modifiers.active)
        self.assertTrue(symmetry.is_symmetry(mod))
        return mod

    def test_defaults(self):
        m = self.add()
        self.assertEqual(m.name, 'Symmetry')
        self.assertEqual(tuple(m.use_axis), (True, False, False))
        self.assertEqual(tuple(m.use_bisect_axis), (True, True, True))
        self.assertEqual(tuple(m.use_bisect_flip_axis), (False, False, False))
        self.assertTrue(m.use_mirror_merge)
        self.assertAlmostEqual(m.merge_threshold, .01)
        self.assertAlmostEqual(m.bisect_threshold, .01)
        self.assertTrue(m.show_in_editmode)
        self.assertFalse(m.show_on_cage)
        self.assertIsNotNone(m.mirror_object)
        self.assertTrue(m.mirror_object.hide_get())

    def test_maintenance_without_area_active_object(self):
        m = self.add()
        plane = m.mirror_object
        name = plane.name
        layer = bpy.context.view_layer
        # Area reconstruction can leave timers with view_layer but without
        # the area-provided active_object context member.
        timer_bpy = SimpleNamespace(context=SimpleNamespace(view_layer=layer), data=bpy.data)
        with patch.object(symmetry, 'bpy', timer_bpy):
            symmetry._maintain()
            self.assertTrue(plane.hide_get())
            plane.hide_set(False)
            plane.hide_select = False
            plane.select_set(True)
            layer.objects.active = plane
            symmetry._maintain()
            self.assertFalse(plane.hide_get())
            self.ob.modifiers.remove(symmetry.raw(m))
            symmetry._maintain()
        self.assertEqual(layer.objects.active, self.ob)
        self.assertNotIn(name, bpy.data.objects)

    def test_axis_flip_slice_geometry(self):
        m = self.add()
        # Asymmetric cube makes a wrong source side visible in the result.
        for v in self.ob.data.vertices:
            v.co += Vector((.4, .3, .2))
        self.ob.data.update()
        for axis in range(3):
            m.use_axis = [i == axis for i in range(3)]
            for flip in (False, True):
                flips = list(m.use_bisect_flip_axis)
                flips[axis] = flip
                m.use_bisect_flip_axis = flips
                coords, _ = evaluated(self.ob)
                extent = max(abs(v[axis]) for v in coords)
                self.assertAlmostEqual(extent, 1 - (.4, .3, .2)[axis] if flip else 1 + (.4, .3, .2)[axis], places=5)
                self.assertTrue(all(any(abs(w[axis] + v[axis]) < 1e-5 for w in coords) for v in coords))
        m.use_axis = (True, False, False)
        m.use_bisect_axis = (False, False, False)
        m.use_mirror_merge = False
        coords, faces = evaluated(self.ob)
        self.assertEqual((len(coords), faces), (16, 12))

    def test_weld_threshold(self):
        m = self.add()
        m.proximity = True
        m.use_bisect_axis = (False, False, False)
        for v in self.ob.data.vertices:
            v.co.x = .003 if v.co.x < 0 else 1
        self.ob.data.update()
        m.merge_threshold = .01
        self.assertEqual(len(evaluated(self.ob)[0]), 12)
        m.merge_threshold = .001
        self.assertEqual(len(evaluated(self.ob)[0]), 16)
        m.use_mirror_merge = False
        self.assertEqual(len(evaluated(self.ob)[0]), 16)

    def test_plane_move_rotate_and_parent(self):
        m = self.add()
        m.use_bisect_axis = (False, False, False)
        m.use_mirror_merge = False
        plane = m.mirror_object
        plane.location.x = 2
        self.assertAlmostEqual(max(v[0] for v in evaluated(self.ob)[0]), 5)
        plane.location = (0, 0, 0)
        plane.rotation_euler.z = math.pi / 4
        for v in self.ob.data.vertices:
            v.co.x += 2
        self.ob.data.update()
        coords, _ = evaluated(self.ob)
        self.assertAlmostEqual(min(v[1] for v in coords), -3, places=4)
        self.ob.location = (7, 2, 3)
        self.ob.rotation_euler.z = .3
        self.assertEqual(plane.parent, self.ob)
        after, _ = evaluated(self.ob)
        for a, b in zip(coords, after):
            self.assertLess((Vector(a)-Vector(b)).length, 1e-4)

    def test_editable_poly_live_result(self):
        m = self.add()
        bpy.ops.max.subobject(level=1)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        import bmesh
        bm = bmesh.from_edit_mesh(self.ob.data)
        for v in bm.verts:
            if v.co.x > 0:
                v.co.x = 2
        bmesh.update_edit_mesh(self.ob.data)
        coords, _ = evaluated(self.ob)
        self.assertAlmostEqual(max(v[0] for v in coords), 2)
        self.assertAlmostEqual(min(v[0] for v in coords), -2)
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_cleanup_remove_and_owner_delete(self):
        m = self.add()
        plane = m.mirror_object
        name = plane.name
        self.ob.modifiers.remove(symmetry.raw(m))
        symmetry.reconcile()
        self.assertNotIn(name, bpy.data.objects)
        m = self.add()
        name = m.mirror_object.name
        bpy.data.objects.remove(self.ob, do_unlink=True)
        symmetry.reconcile()
        self.assertNotIn(name, bpy.data.objects)

    def test_cleanup_keeps_unrelated_collection_with_same_name(self):
        other = bpy.data.collections.new(symmetry.COLLECTION)
        bpy.context.scene.collection.children.link(other)
        m = self.add()
        self.assertFalse(other.hide_render)
        self.assertNotIn(m.mirror_object.name, other.objects)
        self.ob.modifiers.remove(symmetry.raw(m))
        symmetry.reconcile()
        self.assertIn(other.name, bpy.data.collections)
        bpy.data.collections.remove(other)

    def test_multiple_modifiers_rename_and_disable(self):
        a = self.add()
        b = self.add()
        a.name = 'Body symmetry'
        a.mirror_object.location.x = .25
        b.mirror_object.rotation_euler.y = .4
        before = evaluated(self.ob)
        symmetry.reconcile()
        addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)
        self.assertEqual(before, evaluated(self.ob))
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        symmetry.reconcile()
        self.assertTrue(symmetry.is_symmetry(a))
        self.assertTrue(symmetry.is_symmetry(b))
        self.assertNotEqual(a.mirror_object, b.mirror_object)
        self.assertAlmostEqual(a.mirror_object.location.x, .25)
        self.assertAlmostEqual(b.mirror_object.rotation_euler.y, .4)
        self.assertEqual(before, evaluated(self.ob))

    def test_save_reload(self):
        m = self.add()
        m.mirror_object.location = (.2, .3, .4)
        m.mirror_object.rotation_euler = (.1, .2, .3)
        m.use_axis = (False, True, True)
        m.use_bisect_flip_axis = (False, True, False)
        m.merge_threshold = .025
        expected = evaluated(self.ob)
        path = str(Path(os.environ['MAXXED_OUT']) / 'symmetry-headless.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
        bpy.ops.wm.open_mainfile(filepath=path)
        self.ob = bpy.data.objects['SymmetryFixture']
        m = symmetry.settings(self.ob.modifiers[0])
        self.assertTrue(symmetry.is_symmetry(m))
        self.assertEqual(tuple(m.use_axis), (False, True, True))
        self.assertAlmostEqual(m.merge_threshold, .025)
        self.assertEqual(expected, evaluated(self.ob))
        self.assertEqual(sum(bool(ob.get(symmetry.HELPER)) for ob in bpy.data.objects), 1)

    def test_copied_objects_get_independent_planes(self):
        m = self.add()
        m.mirror_object.location.x = .3
        copy = self.ob.copy()
        copy.data = self.ob.data.copy()
        bpy.context.collection.objects.link(copy)
        symmetry.reconcile()
        other = symmetry.settings(copy.modifiers[0])
        self.assertTrue(symmetry.is_symmetry(other))
        self.assertNotEqual(m.mirror_object, other.mirror_object)
        self.assertEqual(other.mirror_object.parent, copy)
        self.assertAlmostEqual(other.mirror_object.location.x, .3)
        other.mirror_object.location.x = .7
        self.assertAlmostEqual(m.mirror_object.location.x, .3)

    def test_reset_and_slice_controls(self):
        m = self.add()
        m.mirror_object.location = (.3, .2, .1)
        m.mirror_object.rotation_euler.z = .5
        self.assertEqual(bpy.ops.max.symmetry_action(name=m.name, action='RESET'), {'FINISHED'})
        self.assertEqual(m.mirror_object.matrix_basis, Matrix.Identity(4))
        self.assertEqual(bpy.ops.max.symmetry_action(name=m.name, action='SLICE'), {'FINISHED'})
        self.assertEqual(tuple(m.use_bisect_axis), (False, False, False))
        self.assertEqual(bpy.ops.max.symmetry_action(name=m.name, action='SLICE'), {'FINISHED'})
        self.assertEqual(tuple(m.use_bisect_axis), (True, True, True))

    def test_apply_and_remove_from_mirror_level(self):
        m = self.add()
        expected = evaluated(self.ob)
        symmetry.enter(bpy.context, m)
        self.assertEqual(bpy.ops.max.symmetry_action(name=m.name, action='APPLY'), {'FINISHED'})
        self.assertEqual(bpy.context.object, self.ob)
        self.assertFalse(self.ob.modifiers)
        self.assertEqual(expected, evaluated(self.ob))
        self.assertFalse(any(ob.get(symmetry.HELPER) for ob in bpy.data.objects))
        m = self.add()
        symmetry.enter(bpy.context, m)
        self.assertEqual(bpy.ops.max.symmetry_action(name=m.name, action='REMOVE'), {'FINISHED'})
        self.assertEqual(bpy.context.object, self.ob)
        self.assertFalse(self.ob.modifiers)
        self.assertNotIn(symmetry.STATE, self.ob)

    def test_new_scene_helper_and_plain_mirror_stays_plain(self):
        m = self.add()
        uid = int(getattr(m, 'persistent_uid', 0))
        self.ob.modifiers.remove(symmetry.raw(m))
        plain = self.ob.modifiers.new('Symmetry', 'MIRROR')
        symmetry.reconcile()
        if uid:
            self.assertFalse(symmetry.is_symmetry(plain))
        scene = bpy.data.scenes.new('Symmetry other scene')
        scene.collection.objects.link(self.ob)
        bpy.context.window.scene = scene
        self.ob.select_set(True)
        bpy.context.view_layer.objects.active = self.ob
        m = self.add()
        self.assertIn(m.mirror_object.name, scene.objects)

    def test_undo_plane_and_remove(self):
        m = self.add()
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message='Symmetry before plane move')
        m.mirror_object.location.x = .7
        bpy.ops.ed.undo_push(message='Symmetry after plane move')
        bpy.ops.ed.undo()
        self.ob = bpy.data.objects['SymmetryFixture']
        self.assertAlmostEqual(symmetry.plane(self.ob.modifiers[0]).location.x, 0)
        bpy.ops.ed.redo()
        self.ob = bpy.data.objects['SymmetryFixture']
        self.assertAlmostEqual(symmetry.plane(self.ob.modifiers[0]).location.x, .7)
        bpy.ops.ed.undo_push(message='Before remove')
        bpy.ops.object.modifier_remove(modifier=self.ob.modifiers[0].name)
        symmetry.reconcile()
        bpy.ops.ed.undo_push(message='After remove')
        self.assertFalse(any(ob.get(symmetry.HELPER) for ob in bpy.data.objects))
        bpy.ops.ed.undo()
        self.ob = bpy.data.objects['SymmetryFixture']
        symmetry.reconcile()
        self.assertTrue(symmetry.is_symmetry(self.ob.modifiers[0]))
        self.assertAlmostEqual(symmetry.plane(self.ob.modifiers[0]).location.x, .7)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SymmetryTests))
    print(f'SYMMETRY tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}', flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
