"""Autodesk element/state colour regressions. Run through run_checks.py."""
import unittest
from types import SimpleNamespace

import addon_utils

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import max_gizmos as g, max_rotate as r
import bpy
from mathutils import Matrix, Vector


class GizmoColors(unittest.TestCase):
    def test_default_handle_settings_match_preferences_image(self):
        prefs = r.settings(bpy.context)
        self.assertEqual((prefs.plane_offset, prefs.uniform_handle, prefs.two_axis_handle), (33, 50, 20))
        self.assertTrue(prefs.uniform_2axis)

    def test_xz_drag_uses_canonical_zx_plane(self):
        for operation in ('MOVE', 'SCALE'):
            self.assertEqual(r.set_constraint(bpy.context, 'XZ', operation), 'ZX')
            owner = SimpleNamespace()
            context = SimpleNamespace(window=None, area=None,
                                      region=SimpleNamespace(as_pointer=lambda: 987654))
            try:
                g.begin(context, owner, operation, Vector(), Matrix.Identity(3), 'XZ')
                self.assertEqual(owner.handle, 'ZX')
            finally:
                g.finish(context.region)

    def test_move_and_scale_keep_native_tips_under_all_constraints(self):
        for operation in ('MOVE', 'SCALE'):
            for constraint in ('X', 'Y', 'Z', 'XY', 'YZ', 'ZX', 'XYZ'):
                for axis, rgb in zip('XYZ', ((255, 0, 0), (0, 200, 0), (0, 0, 255))):
                    native = tuple(v / 255 for v in rgb) + (1,)
                    self.assertEqual(g.element_color(operation, 'tip', axis, native, 'OFF', constraint), native)
                    self.assertEqual(g.element_color(operation, 'tip', axis, native, axis, constraint), native)
                    selected = axis in constraint and constraint != 'XYZ'
                    expected = g.TRANSFORM_YELLOW if selected else native
                    self.assertEqual(g.element_color(operation, 'shaft', axis, native, 'OFF', constraint), expected)

    def test_hover_overrides_lock_without_recolouring_tips(self):
        red = (1, 0, 0, 1)
        self.assertEqual(g.element_color('MOVE', 'shaft', 'X', red, 'Y', 'X'), red)
        self.assertEqual(g.element_color('MOVE', 'label', 'X', red, 'X', 'Z'), g.TRANSFORM_YELLOW)
        self.assertEqual(g.element_color('MOVE', 'tip', 'X', red, 'X', 'Z'), red)

    def test_uniform_center_fills_yellow_only_when_active(self):
        clear = (0, 0, 0, 0)
        for active, locked in (('CENTER', 'X'), ('OFF', 'XYZ')):
            fill = g.element_color('SCALE', 'fill', 'CENTER', clear, active, locked)
            self.assertEqual(fill[:3], g.TRANSFORM_YELLOW[:3])
            self.assertGreaterEqual(fill[3], .18)
            self.assertLess(fill[3], .6)
            for axis, native in zip('XYZ', g.TRANSFORM_COLORS):
                self.assertEqual(g.element_color('SCALE', 'shaft', axis, native, active, locked), native)
                self.assertEqual(g.element_color('SCALE', 'uniform_inner', axis, native, active, locked),
                                 g.TRANSFORM_YELLOW)
        self.assertEqual(g.element_color('SCALE', 'fill', 'CENTER', clear, 'X', 'XYZ'), clear)
        self.assertEqual(g.element_color('SCALE', 'fill', 'YZ', clear, 'CENTER', 'X'), clear)

    def test_active_planes_darken_background_without_a_colour_tint(self):
        clear = (0, 0, 0, 0)
        for operation in ('MOVE', 'SCALE'):
            for plane in ('XY', 'YZ', 'ZX'):
                for active, locked in ((plane, 'X'), ('OFF', plane)):
                    fill = g.element_color(operation, 'fill', plane, clear, active, locked)
                    self.assertLess(max(fill[:3]) - min(fill[:3]), .001)
                    self.assertGreaterEqual(fill[3], .25)
                    self.assertLess(fill[3], .6)
                    for background in (.035, .4, 1):
                        composite = sum(fill[:3]) / 3 * fill[3] + background * (1 - fill[3])
                        self.assertLess(composite, background * .8)
                    self.assertEqual(g.element_color(operation, 'outline', plane, g.GREY,
                                                     active, locked), g.TRANSFORM_YELLOW)
                self.assertEqual(g.element_color(operation, 'fill', plane, clear, 'X', 'Z'), clear)

    def test_move_center_box_stays_yellow(self):
        for locked in ('X', 'Y', 'Z', 'XY', 'YZ', 'ZX'):
            self.assertEqual(g.element_color('MOVE', 'outline', 'CENTER', g.GREY, 'OFF', locked),
                             g.TRANSFORM_YELLOW)

    def test_rotate_palette_and_muted_tripod_stay_unchanged(self):
        self.assertEqual(g.COLORS, ((1.0, .08, .045, 1), (.18, .95, .055, 1), (.12, .28, 1.0, 1)))
        self.assertEqual(g.tripod_color('X', 'Z'), g.GREY)
        self.assertEqual(g.tripod_color('Z', 'Z'), g.COLORS[2])


unittest.main(argv=['gizmo-colors'], exit=False)
