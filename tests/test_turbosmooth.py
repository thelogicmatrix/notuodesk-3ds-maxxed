"""Run with run_checks.py tests test_turbosmooth, in a fresh process."""
import importlib.util
from pathlib import Path
import sys
import unittest
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _w11 import load, evaluated


class TurboSmoothTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert importlib.util.find_spec('_maxxed_w11.turbosmooth'), 'clean-room TurboSmooth service is missing'
        cls.ts = load('turbosmooth')
        for item in cls.ts.classes:
            bpy.utils.register_class(item)
        cls.ts.register_props()

    @classmethod
    def tearDownClass(cls):
        cls.ts.unregister_props()
        for item in reversed(cls.ts.classes):
            bpy.utils.unregister_class(item)

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_separate_settings_and_render_override(self):
        a = self.ts.add(self.ob, 1)
        b = self.ts.add(self.ob, 2)
        self.ts.select_modifier(self.ob, a)
        self.ob.max_turbosmooth.render_iters_on = True
        self.ob.max_turbosmooth.render_iters = 3
        self.assertEqual((a.levels, a.render_levels), (1, 3))
        self.ts.select_modifier(self.ob, b)
        self.assertFalse(self.ob.max_turbosmooth.render_iters_on)
        self.ob.max_turbosmooth.iterations = 1
        self.assertEqual(b.render_levels, 1)
        self.assertEqual(a.render_levels, 3)
        self.ob.max_turbosmooth.update_mode = 'RENDER'
        self.assertFalse(b.show_viewport)
        self.assertTrue(b.show_render)

    def test_smoothing_and_crease_restoration(self):
        self.ob.data.polygons[0].use_smooth = True
        crease = self.ob.data.attributes.new('crease_edge', 'FLOAT', 'EDGE')
        crease.data[0].value = .37
        mod = self.ts.add(self.ob, 1)
        self.assertTrue(all(evaluated(self.ob)[2]))
        self.ob.max_turbosmooth.smooth_result = False
        self.assertTrue(any(evaluated(self.ob)[2]))
        self.assertTrue(any(not flag for flag in evaluated(self.ob)[2]))
        self.ob.max_turbosmooth.separate_materials = True
        self.ob.max_turbosmooth.separate_smoothing = True
        self.ob.modifiers.remove(mod)
        self.ts.sync(self.ob)
        self.assertAlmostEqual(crease.data[0].value, .37, places=5)
        self.assertEqual([p.use_smooth for p in self.ob.data.polygons], [True, False, False, False, False, False])
        self.assertFalse(self.ob.modifiers)

    def test_material_and_real_smoothing_boundaries(self):
        self.ob.data.polygons[0].material_index = 1
        groups = self.ob.data.attributes.new('max_smoothing_group', 'INT', 'FACE')
        for i, entry in enumerate(groups.data):
            entry.value = 1 if i == 0 else 2
        mod = self.ts.add(self.ob, 1)
        before = evaluated(self.ob)[0]
        self.ob.max_turbosmooth.separate_materials = True
        after = evaluated(self.ob)[0]
        self.assertNotEqual(before, after)
        self.ob.max_turbosmooth.separate_materials = False
        self.ob.max_turbosmooth.separate_smoothing = True
        self.assertNotEqual(before, evaluated(self.ob)[0])

    def test_overlapping_group_masks_do_not_create_false_boundaries(self):
        masks = self.ob.data.attributes.new('max_smoothing_group', 'INT', 'FACE')
        for entry in masks.data:
            entry.value = 1
        mod = self.ts.add(self.ob, 1)
        self.ob.max_turbosmooth.separate_smoothing = True
        before = evaluated(self.ob)[0]
        masks.data[0].value = 3
        self.ob.data.update()
        self.assertEqual(before, evaluated(self.ob)[0])

    def test_legacy_smooth_backup_and_saved_instance_settings(self):
        backup = self.ob.data.attributes.new('max_ts_orig_smooth', 'BOOLEAN', 'FACE')
        backup.data[0].value = True
        for face in self.ob.data.polygons:
            face.use_smooth = True
        mod = self.ts.add(self.ob, 1)
        self.ob.max_turbosmooth.smooth_result = False
        self.assertEqual([p.use_smooth for p in self.ob.data.polygons], [True, False, False, False, False, False])
        self.assertIsNone(self.ob.data.attributes.get('max_ts_orig_smooth'))
        self.ob.max_turbosmooth.render_iters_on = True
        self.ob.max_turbosmooth.render_iters = 3
        import os
        path = str(Path(os.environ['MAXXED_OUT']) / 'w11-ts.blend')
        name, modname = self.ob.name, mod.name
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        self.ob = bpy.data.objects[name]
        self.ts.select_modifier(self.ob, self.ob.modifiers[modname])
        self.assertFalse(self.ob.max_turbosmooth.smooth_result)
        self.assertTrue(self.ob.max_turbosmooth.render_iters_on)
        self.assertEqual(self.ob.modifiers[modname].render_levels, 3)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TurboSmoothTests))
    print('W11 TS tests=%d failures=%d errors=%d' % (result.testsRun, len(result.failures), len(result.errors)), flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
