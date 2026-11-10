"""Run with run_checks.py tests test_poly_caddies_round3 in the sandbox."""
import math
import sys
import unittest
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).parent))
from test_editable_poly_panel import mesh, CUBE, CUBE_FACES, QUAD
from test_poly_caddies import geometry, equivalent_geometry
from notuodesk_3ds_maxxed import editable_poly as ep, poly_caddies as pc


class Round3Tests(unittest.TestCase):
    def setUp(self):
        mesh(CUBE, faces=CUBE_FACES, level=2)
        bpy.context.scene.max_poly_operations.clear()

    def test_chamfer_2026_defaults(self):
        s = ep.settings(bpy.context, 'CHAMFER')
        expected = dict(chamfer_miter='UNIFORM', chamfer_depth=.5, end_bias=.5,
                        radial_bias=0, chamfer_smooth=True, smooth_type='OBJECT',
                        smooth_threshold=30, invert_open=False, chamfer_clamp=True)
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertTrue(hasattr(s, key), key+' is absent')
                self.assertEqual(getattr(s, key), value)

    def test_every_visible_field_has_control_bounds_at_each_level(self):
        from notuodesk_3ds_maxxed.caddy_layout import controls
        from types import SimpleNamespace
        for action in pc.ACTIONS:
            for level in (1, 2, 3, 4, 5):
                session = SimpleNamespace(action=action, level=level, keys=ep.CADDIES[action],
                                          values=SimpleNamespace(chamfer_miter='QUAD'))
                fields = pc.fields(session)
                bounds, rows = controls(action, level, fields)
                with self.subTest(action=action, level=level):
                    self.assertEqual(set(bounds)-{'TITLE', 'BUTTONS'}, set(fields))

    def test_bridge_radian_display_and_edit_keep_degree_storage(self):
        s = pc.Session(bpy.context, 'BRIDGE')
        try:
            self.assertTrue(hasattr(pc, 'display_value'), 'Bridge has no display conversion')
            self.assertAlmostEqual(pc.display_value(s, 'smooth'), math.pi/4)
            self.assertAlmostEqual(pc.stored_value(s, 'smooth', math.pi/2), 90)
            self.assertEqual(pc.format_value(s, 'smooth'), '0.785')
        finally:
            s.close(bpy.context, cancel=True)

    def test_vertex_chamfer_ignores_hidden_edge_miter_and_invert(self):
        mesh(CUBE, faces=CUBE_FACES, level=1)
        session = pc.Session(bpy.context, 'CHAMFER')
        original = geometry()
        try:
            session.values.amount = .2
            session.values.open = True
            self.assertTrue(session.preview(bpy.context), session.error)
            expected = equivalent_geometry()
            session.values.chamfer_miter = 'RADIAL'
            session.values.chamfer_depth = 1
            session.values.invert_open = True
            self.assertTrue(session.preview(bpy.context), session.error)
            self.assertEqual(equivalent_geometry(), expected)
        finally:
            session.close(bpy.context, cancel=True)
            self.assertEqual(geometry(), original)

    def preview(self, **values):
        mesh(CUBE, faces=CUBE_FACES, level=2)
        bpy.context.scene.max_poly_operations.clear()
        session = pc.Session(bpy.context, 'CHAMFER')
        original = geometry()
        try:
            session.values.amount = .2
            session.values.segments = 4
            for key, value in values.items():
                setattr(session.values, key, value)
            self.assertTrue(session.preview(bpy.context), session.error)
            result = equivalent_geometry()
            self.assertNotEqual(geometry(), original)
            self.assertTrue(session.preview(bpy.context))
            self.assertEqual(equivalent_geometry(), result, 'preview accumulated geometry')
            return result
        finally:
            session.close(bpy.context, cancel=True)
            self.assertEqual(geometry(), original, 'Cancel did not restore the baseline')

    def test_chamfer_each_miter_and_width_mapping_changes_preview(self):
        signatures = {}
        for miter in ('QUAD', 'TRI', 'UNIFORM', 'RADIAL', 'PATCH'):
            with self.subTest(miter=miter):
                signatures[miter] = self.preview(chamfer_miter=miter)
        self.assertNotEqual(signatures['QUAD'], signatures['UNIFORM'])
        self.assertNotEqual(signatures['QUAD'], signatures['TRI'])
        self.assertNotEqual(signatures['QUAD'], signatures['RADIAL'])
        print('PASS round3 Chamfer five miter previews, offset/width and cutoff/arc mappings, repeat and Cancel')

    def test_chamfer_depth_and_tension_change_profile(self):
        self.assertNotEqual(self.preview(chamfer_miter='RADIAL', chamfer_depth=-.5),
                            self.preview(chamfer_miter='RADIAL', chamfer_depth=.5))
        self.assertNotEqual(self.preview(chamfer_miter='QUAD', tension=0),
                            self.preview(chamfer_miter='QUAD', tension=1))
        print('PASS round3 Chamfer signed Depth and Tension change the real bevel profile')

    def test_chamfer_open_and_invert_keep_complementary_faces(self):
        closed = self.preview()
        opened = self.preview(open=True)
        inverted = self.preview(open=True, invert_open=True)
        self.assertEqual(len(opened[2])+len(inverted[2]), len(closed[2]))
        self.assertEqual(len(opened[2]), 6)
        self.assertNotEqual(opened, inverted)
        print('PASS round3 Chamfer Open and Invert remove complementary faces')

    def test_chamfer_smooth_scope_and_threshold(self):
        flat = self.preview(chamfer_smooth=False)
        whole = self.preview(chamfer_smooth=True, smooth_type='OBJECT')
        chamfers = self.preview(chamfer_smooth=True, smooth_type='CHAMFERS')
        self.assertFalse(any(f[-1] for f in flat[2]))
        self.assertTrue(all(f[-1] for f in whole[2]))
        self.assertEqual(sum(not f[-1] for f in chamfers[2]), 6)
        # Threshold affects sharp-edge flags, not the vertex positions.
        sharp = self.preview(smooth_threshold=0)
        smooth = self.preview(smooth_threshold=180)
        self.assertEqual([v[0] for v in sharp[0]], [v[0] for v in smooth[0]])
        session = pc.Session(bpy.context, 'CHAMFER')
        try:
            session.values.amount = .2
            session.values.segments = 4
            counts = []
            for threshold in (0, 180):
                session.values.smooth_threshold = threshold
                self.assertTrue(session.preview(bpy.context))
                counts.append(sum(not e.smooth for e in bmesh.from_edit_mesh(session.obj.data).edges))
            self.assertGreater(counts[0], counts[1])
            self.assertEqual(counts[1], 0)
        finally:
            session.close(bpy.context, cancel=True)
        print('PASS round3 Chamfer Smooth off, entire object and chamfers-only preserve the requested scope')

    def test_chamfer_clamp_prevents_crossing(self):
        clamped = self.preview(amount=5, chamfer_clamp=True)
        unclamped = self.preview(amount=5, chamfer_clamp=False)
        self.assertLess(max(abs(c) for v in clamped[0] for c in v[0]),
                        max(abs(c) for v in unclamped[0] for c in v[0]))
        print('PASS round3 Chamfer overlap clamp prevents the oversized bevel crossing')

    def test_disabled_bias_controls_and_conditional_smoothing(self):
        session = pc.Session(bpy.context, 'CHAMFER')
        try:
            for key in ('end_bias', 'radial_bias'):
                self.assertIn(key, pc.fields(session))
                self.assertFalse(pc.enabled(session, key))
                self.assertIn('BMesh bevel', pc.tooltip(session, key))
            self.assertFalse(pc.enabled(session, 'invert_open'))
            session.values.open = True
            self.assertTrue(pc.enabled(session, 'invert_open'))
            session.values.chamfer_smooth = False
            self.assertFalse(pc.enabled(session, 'smooth_type'))
            self.assertFalse(pc.enabled(session, 'smooth_threshold'))
            session.values.chamfer_miter = 'RADIAL'
            self.assertIn('chamfer_depth', pc.fields(session))
            self.assertNotIn('tension', pc.fields(session))
        finally:
            session.close(bpy.context, cancel=True)

    def test_bridge_radian_edit_reaches_solver(self):
        verts = QUAD+[(x, y, 2) for x, y, z in QUAD]
        edges = [(i, (i+1)%4) for i in range(4)]+[(i+4, (i+1)%4+4) for i in range(4)]
        mesh(verts, edges=edges, level=3)
        session = pc.Session(bpy.context, 'BRIDGE')
        try:
            session.values.segments = 4
            session.values.taper = 50
            sharp_counts = []
            for radians in (0, math.pi):
                session.values.smooth = pc.stored_value(session, 'smooth', radians)
                self.assertTrue(session.preview(bpy.context))
                bm = bmesh.from_edit_mesh(session.obj.data)
                sharp_counts.append(sum(not e.smooth for e in bm.edges if len(e.link_faces) == 2))
            self.assertGreater(sharp_counts[0], sharp_counts[1])
            self.assertEqual(sharp_counts[1], 0)
        finally:
            session.close(bpy.context, cancel=True)
        print('PASS round3 Bridge 0.785 radians displays 45 stored degrees, edited radians reach smoothing solver')


if __name__ == '__main__':
    print('BEVEL API', bmesh.ops.bevel.__doc__, flush=True)
    print('BEVEL RNA', list(bpy.ops.mesh.bevel.get_rna_type().properties.keys()), flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Round3Tests))
    if not result.wasSuccessful():
        raise SystemExit(1)
