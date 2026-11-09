"""Run: blender -b --factory-startup --python tests/test_viewcube.py"""

import os
import sys
import unittest

import bpy
import addon_utils
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notuodesk_3ds_maxxed import viewcube


class ViewCubeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        cls.area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        cls.region = next(r for r in cls.area.regions if r.type == 'WINDOW')

    @classmethod
    def tearDownClass(cls):
        addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)

    def test_toggle_restores_each_original_navigation_gizmo_setting(self):
        from notuodesk_3ds_maxxed import get_prefs
        ws = bpy.context.workspace
        name = ws.name
        ws.name = '3ds Max'
        space = self.area.spaces.active
        try:
            for original in (False, True):
                get_prefs().show_viewcube = False
                space.show_gizmo_navigate = original
                get_prefs().show_viewcube = True
                viewcube.sync_gizmos()
                self.assertFalse(space.show_gizmo_navigate)
                get_prefs().show_viewcube = False
                viewcube.sync_gizmos()
                self.assertEqual(space.show_gizmo_navigate, original)
        finally:
            ws.name = name

    def test_face_rotations_match_max_axes(self):
        # A reversed front/back or left/right mapping breaks this contract.
        for direction in ((0, 0, 1), (0, 0, -1), (0, -1, 0),
                          (0, 1, 0), (-1, 0, 0), (1, 0, 0)):
            q = viewcube.rotation_for(direction)
            self.assertGreater((q @ Vector((0, 0, 1))).dot(Vector(direction)), .99999)
        self.assertLess(viewcube.rotation_for((0, 0, 1)).rotation_difference(Quaternion()).angle, .0001)

    def test_edge_corner_views_and_front_override(self):
        q = viewcube.rotation_for((1, -1, 1))
        self.assertLess(((q @ Vector((0, 0, 1))) - Vector((.5773503, -.5773503, .5773503))).length, .0001)
        q = viewcube.rotation_for((1, -1, 0))
        self.assertAlmostEqual((q @ Vector((0, 0, 1))).z, 0, places=5)
        front = viewcube.rotation_for((1, 0, 0))
        basis = front @ viewcube.rotation_for((0, -1, 0)).inverted()
        q = viewcube.rotation_for((0, -1, 0), basis)
        self.assertLess(q.rotation_difference(front).angle, .0001)

    def test_projection_has_pickable_face_edge_corner_and_no_scene_hits(self):
        geometry = viewcube.cube_geometry(Quaternion(), 200, 200, 40)
        self.assertEqual(viewcube.pick(geometry, 200, 200), (0, 0, 1))
        self.assertEqual(viewcube.pick(geometry, 235, 200), (1, 0, 1))
        self.assertEqual(viewcube.pick(geometry, 235, 235), (1, 1, 1))
        self.assertIsNone(viewcube.pick(geometry, 100, 100))

    def test_orbit_from_top_preserves_yaw_and_upright_option(self):
        q = viewcube.orbit_rotation(Quaternion(), 12, -6, True)
        self.assertLess(Quaternion().rotation_difference(q).angle, .15)
        self.assertLess((q @ Vector((0, 0, 1))).y, 0)
        front = viewcube.rotation_for((0, -1, 0))
        q = viewcube.orbit_rotation(front, 0, 400, True)
        self.assertGreaterEqual((q @ Vector((0, 1, 0))).z, 0)
        q = viewcube.orbit_rotation(front, 0, 400, False)
        self.assertLess((q @ Vector((0, 1, 0))).z, 0)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ViewCubeTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('VIEWCUBE PASS: axes, diagonal views, custom Front, hits and gizmo restoration')
