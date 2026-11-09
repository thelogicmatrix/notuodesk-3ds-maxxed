"""Historical file-load acceptance in its own fresh run_checks.py process."""
import sys
import unittest
from pathlib import Path

import addon_utils
import bpy


class HistoricalLoadTests(unittest.TestCase):
    def test_file_load_restores_all_historical_primitive_kinds(self):
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        fixture = Path(__file__).resolve().parent / 'fixtures/pre-rewrite-primitives.blend'
        bpy.ops.wm.open_mainfile(filepath=str(fixture), load_ui=False, use_scripts=False)
        objects = {ob.max_prim.kind: ob for ob in bpy.context.scene.objects if ob.type == 'MESH'}
        self.assertEqual(set(objects), {'BOX', 'CONE', 'SPHERE', 'GEOSPHERE', 'CYLINDER',
                                        'TUBE', 'TORUS', 'PYRAMID', 'PLANE'})
        for kind, ob in objects.items():
            with self.subTest(kind=kind):
                self.assertIn('_max_base_positions', ob.data)
                ob.max_prim.radius1 = 4
                self.assertEqual(ob.max_prim.kind, kind)
        print('F3 PASS file load restores all 9 historical primitive kinds', flush=True)


result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(HistoricalLoadTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('CLEANROOM HISTORICAL LOAD PASS', flush=True)
