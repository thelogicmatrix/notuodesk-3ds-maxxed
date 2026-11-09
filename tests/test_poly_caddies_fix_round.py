"""Run through run_checks.py tests test_poly_caddies_fix_round, isolated profile."""
import sys
import unittest
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).parent))
from test_editable_poly_panel import mesh, QUAD, CUBE, CUBE_FACES
from notuodesk_3ds_maxxed import editable_poly as ep, poly_caddies as pc


class FixRoundTests(unittest.TestCase):
    def test_finding_3_signed_tessellate_is_flat_at_zero(self):
        bounds = []
        for tension in (-.5, 0, .5):
            ob, bm = mesh(CUBE, faces=CUBE_FACES)
            bpy.context.scene.max_poly_operations.clear()
            s = ep.settings(bpy.context, 'TESSELLATE')
            key = 'tess_tension' if hasattr(s, 'tess_tension') else 'tension'
            setattr(s, key, tension)
            with self.subTest(tension=tension):
                self.assertAlmostEqual(getattr(s, key), tension, msg='Tessellate must accept negative tension')
                self.assertEqual(bpy.ops.max.edit_poly(op='TESSELLATE'), {'FINISHED'})
                # Tessellation retains original corners. Measure its new vertices only.
                bounds.append(max(abs(c) for v in bm.verts if tuple(v.co) not in CUBE for c in v.co))
                self.assertEqual(len(bm.faces), 24)
        self.assertEqual(len(bounds), 3)
        self.assertLess(bounds[0], 1)
        self.assertAlmostEqual(bounds[1], 1)
        self.assertGreater(bounds[2], 1)
        self.assertAlmostEqual(ep.settings(bpy.context, 'CHAMFER').tension, 1)
        print('PASS finding 3: Tessellate negative pulls inward, zero stays flat, positive pushes outward, Chamfer unchanged')

    def test_finding_4_fresh_defaults_and_accepted_values(self):
        mesh(QUAD, faces=[(0, 1, 2, 3)])
        bpy.context.scene.max_poly_operations.clear()
        for action, key, want in [('EXTRUDE', 'amount', 10), ('EXTRUDE', 'base_width', 3),
                                  ('CHAMFER', 'amount', 1), ('BEVEL', 'height', 10),
                                  ('BEVEL', 'amount', -1), ('INSET', 'amount', 1),
                                  ('OUTLINE', 'amount', -1), ('WELD', 'threshold', .1),
                                  ('RELAX', 'iterations', 1)]:
            with self.subTest(action=action, key=key):
                self.assertAlmostEqual(getattr(ep.settings(bpy.context, action), key), want, places=6)
        s = ep.settings(bpy.context, 'EXTRUDE')
        s.amount = .37
        self.assertAlmostEqual(ep.settings(bpy.context, 'EXTRUDE').amount, .37)
        # Old files stored Tessellate's entered value in the shared tension slot.
        bpy.context.scene.max_poly_operations.clear()
        legacy = bpy.context.scene.max_poly_operations.add()
        legacy.name = 'TESSELLATE:4'
        legacy.tension = .4
        current = ep.settings(bpy.context, 'TESSELLATE')
        self.assertAlmostEqual(current.tess_tension, .4)
        self.assertAlmostEqual(ep.settings(bpy.context, 'CHAMFER').tension, 1)
        # The documented world-unit policy must reach the actual preview.
        bpy.context.scene.max_poly_operations.clear()
        session = pc.Session(bpy.context, 'EXTRUDE')
        try:
            self.assertTrue(session.preview(bpy.context))
            self.assertAlmostEqual(max(v.co.z for v in bmesh.from_edit_mesh(bpy.context.object.data).verts), 10)
        finally:
            session.close(bpy.context, cancel=True)
        print('PASS finding 4: Max defaults use 1 world unit = 1 Blender unit, fresh height previews 10, stored values survive')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixRoundTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
