"""Run with run_checks.py tests test_ffd. Tests real cages without the old host."""
import importlib.util
from pathlib import Path
import sys
import unittest
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _w11 import load, evaluated


class FFDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert importlib.util.find_spec('_maxxed_w11.ffd'), 'clean-room FFD service is missing'
        cls.ffd = load('ffd')
        for item in cls.ffd.classes:
            bpy.utils.register_class(item)
        cls.ffd.register_props()

    @classmethod
    def tearDownClass(cls):
        cls.ffd.unregister_props()
        for item in reversed(cls.ffd.classes):
            bpy.utils.unregister_class(item)

    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_cage_fit_transforms_and_deformation(self):
        self.ob.scale = (2, .5, 3)
        self.ob.rotation_euler = (.2, .3, .4)
        mod = self.ffd.add(self.ob, 3)
        cage = mod.object
        before = evaluated(self.ob)[0]
        for point in cage.data.points:
            point.co_deform.x += .25
        cage.data.update_tag()
        after = evaluated(self.ob)[0]
        self.assertGreater(after[0][0], before[0][0])
        self.ffd.reset(self.ob, mod)
        for a, b in zip(before, evaluated(self.ob)[0]):
            self.assertLess((Vector(a)-Vector(b)).length, 1e-5)
        transform = self.ob.matrix_world.copy()
        self.ffd.fit(self.ob, mod)
        self.assertEqual(transform, self.ob.matrix_world)
        self.ob.name = 'Renamed owner'
        self.ffd.resolve_owner(cage)
        self.assertEqual(cage['max_ffd_owner'], self.ob.name)

    def test_fit_encloses_the_input_stack(self):
        gn = load('gn_mods')
        push = gn.add(self.ob, 'Push')
        gn.set_input(push, 'Push Value', 1.)
        mod = self.ffd.add(self.ob, 2)
        cage = mod.object
        high = max((cage.matrix_basis @ p.co).x for p in cage.data.points)
        self.assertGreater(high, 1.5)
        self.assertTrue(push.show_viewport)
        self.assertTrue(mod.show_viewport)

    def test_duplicate_cages_dimensions_and_levels(self):
        a = self.ffd.add(self.ob, 2)
        b = self.ffd.add(self.ob, 4)
        self.assertNotEqual(a.object, b.object)
        self.ffd.select_modifier(self.ob, a)
        self.ob.max_ffd.points_u = 3
        self.assertEqual(a.object.data.points_u, 3)
        self.assertEqual(b.object.data.points_u, 4)
        self.assertEqual(bpy.ops.max.ffd_level(level='POINTS'), {'FINISHED'})
        self.assertEqual(bpy.context.object, a.object)
        self.assertEqual(bpy.context.object.mode, 'EDIT')
        self.assertEqual(bpy.ops.max.ffd_level(level='OBJECT'), {'FINISHED'})
        self.assertEqual(bpy.context.object, self.ob)
        a.object = None
        self.assertFalse(self.ffd.fit(self.ob, a))

    def test_flat_geometry_conform_and_keys(self):
        self.ob.data.clear_geometry()
        self.ob.data.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        mod = self.ffd.add(self.ob, 3)
        self.assertGreater(abs(mod.object.matrix_world.determinant()), 0)
        self.assertTrue(self.ffd.conform(self.ob, mod))
        self.assertEqual(bpy.ops.max.ffd_animate_all(), {'FINISHED'})
        self.assertIsNotNone(mod.object.data.animation_data)
        self.assertEqual(len(evaluated(self.ob)[0]), 4)

    def test_volume_and_falloff_leave_outside_vertices_unchanged(self):
        mod = self.ffd.add(self.ob, 2)
        cage = mod.object
        cage.scale *= .5
        for point in cage.data.points:
            point.co_deform.x += .5
        self.ob.max_ffd.deform_mode = 'VOLUME'
        self.ffd.update_volume(self.ob, mod)
        expected = [tuple(v.co) for v in self.ob.data.vertices]
        self.assertEqual(evaluated(self.ob)[0], expected)
        self.ob.max_ffd.deform_mode = 'ALL'
        self.ob.max_ffd.falloff = 10
        self.assertNotEqual(evaluated(self.ob)[0], expected)

    def test_renamed_owner_save_reload(self):
        import os
        mod = self.ffd.add(self.ob, 2)
        self.ob.name = 'Persisted FFD owner'
        cage_name = mod.object.name
        self.ffd.resolve_owner(mod.object)
        path = str(Path(os.environ['MAXXED_OUT']) / 'w11-ffd.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        cage = bpy.data.objects[cage_name]
        self.assertEqual(self.ffd.resolve_owner(cage).name, 'Persisted FFD owner')
        self.assertEqual(cage['max_ffd_owner'], 'Persisted FFD owner')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FFDTests))
    print('W11 FFD tests=%d failures=%d errors=%d' % (result.testsRun, len(result.failures), len(result.errors)), flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
