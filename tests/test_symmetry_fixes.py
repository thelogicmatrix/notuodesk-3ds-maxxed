"""Review reproductions. Run through run_checks.py tests test_symmetry_fixes."""
import unittest
import addon_utils
import bpy
from mathutils import Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry


def shape(ob):
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    result = sorted(tuple(round(x, 5) for x in v.co) for v in mesh.vertices), len(mesh.polygons)
    ev.to_mesh_clear()
    return result


class ReviewFixes(unittest.TestCase):
    def setUp(self):
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        symmetry.reconcile()
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object
        for v in self.ob.data.vertices:
            v.co.x += .4
        self.ob.data.update()
        self.mod = symmetry.settings(symmetry.add(self.ob))

    def pose(self):
        self.mod.mirror_object.location.x = .5
        self.mod.mirror_object.rotation_euler.z = .2
        symmetry.reconcile()

    def test_disable_keeps_evaluated_geometry(self):
        self.pose()
        expected = shape(self.ob)
        addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)
        try:
            self.assertEqual(shape(self.ob), expected)
            self.assertIsNotNone(self.mod.mirror_object)
            self.assertFalse(bpy.app.timers.is_registered(symmetry._maintain))
        finally:
            addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
            symmetry.reconcile()
        print('SYMMETRY FIX PASS disable preserves evaluated geometry', flush=True)

    def test_deleted_helper_recovers_saved_plane(self):
        self.pose()
        expected = shape(self.ob)
        collection = symmetry._collection()
        for ob in list(collection.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(collection)
        symmetry.reconcile()
        self.assertTrue(symmetry.is_symmetry(self.mod))
        self.assertEqual(shape(self.ob), expected)
        self.assertAlmostEqual(self.mod.mirror_object.location.x, .5)
        plain = self.ob.modifiers.new('Symmetry', 'MIRROR')
        self.assertFalse(symmetry.is_symmetry(plain))
        print('SYMMETRY FIX PASS deleted helper recovers UID and saved plane', flush=True)

    def test_convert_from_mirror_collapses_owner(self):
        self.pose()
        expected = shape(self.ob)
        symmetry.enter(bpy.context, self.mod)
        self.assertEqual(bpy.ops.max.object_cmd(cmd='CONVERT_POLY'), {'FINISHED'})
        self.assertEqual(bpy.context.object, self.ob)
        self.assertFalse(self.ob.modifiers)
        self.assertEqual(shape(self.ob), expected)
        symmetry.reconcile()
        self.assertFalse(any(o.get(symmetry.HELPER) for o in bpy.data.objects))
        print('SYMMETRY FIX PASS Mirror-level conversion collapses displayed owner', flush=True)

    def test_default_weld_does_not_merge_uncut_nearby_vertices(self):
        self.mod.use_bisect_axis = (False, False, False)
        for v in self.ob.data.vertices:
            v.co.x = .003 if v.co.x < 1 else 1
        self.ob.data.update()
        self.assertEqual(len(shape(self.ob)[0]), 16)
        print('SYMMETRY FIX PASS default weld preserves uncut nearby vertices', flush=True)

    def test_proximity_weld_does_not_collapse_thin_source_faces(self):
        self.mod.slice = False
        self.mod.proximity = True
        for v in self.ob.data.vertices:
            v.co.x = 1 if v.co.x < 1 else 2
            v.co.y = 0 if v.co.y < 0 else .003
        self.ob.data.update()
        self.assertEqual(len(shape(self.ob)[0]), 16)
        print('SYMMETRY FIX PASS proximity weld affects seam band, preserves thin source faces', flush=True)

    def test_previous_symmetry_scene_upgrades_without_losing_plane(self):
        self.ob.modifiers.remove(symmetry.raw(self.mod))
        symmetry.reconcile()
        old = self.ob.modifiers.new('Symmetry', 'MIRROR')
        old.use_axis = (True, False, False)
        old.use_bisect_axis = (True, True, True)
        old.merge_threshold = .01
        helper = symmetry._new_plane(self.ob, old)
        helper.location.x = .5
        helper.rotation_euler.z = .2
        expected = shape(self.ob)
        symmetry.reconcile()
        new = self.ob.modifiers[0]
        self.assertEqual(new.type, 'NODES')
        self.assertEqual(shape(self.ob), expected)
        self.assertEqual(symmetry.plane(new), helper)
        self.assertTrue(symmetry.settings(new).proximity)
        print('SYMMETRY FIX PASS previous native-Mirror scene upgrades with geometry and plane intact', flush=True)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewFixes))
    if not result.wasSuccessful():
        raise SystemExit(1)
