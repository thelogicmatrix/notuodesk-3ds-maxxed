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
    def test_owned_editor_and_dock_exclude_viewcube_before_first_draw(self):
        from types import SimpleNamespace
        from notuodesk_3ds_maxxed import get_prefs, max_editor_windows as editors
        workspace = bpy.context.workspace
        original_name = workspace.name
        original_visible = get_prefs().show_viewcube
        window = bpy.context.window
        try:
            workspace.name = '3ds Max'
            get_prefs().show_viewcube = True
            with bpy.context.temp_override(window=window, area=self.area, region=self.region):
                self.assertTrue(viewcube.visible(bpy.context))
                # Ownership exists before deferred editor configuration runs.
                host = SimpleNamespace(area=self.area, ready=False)
                editors._hosts[window.as_pointer()] = host
                self.assertFalse(viewcube.visible(bpy.context))
                editors._hosts.pop(window.as_pointer())
                editors._docked[self.area.as_pointer()] = host
                self.assertFalse(viewcube.visible(bpy.context))
                editors._docked.pop(self.area.as_pointer())
                self.assertTrue(viewcube.visible(bpy.context))
        finally:
            editors._hosts.pop(window.as_pointer(), None)
            editors._docked.pop(self.area.as_pointer(), None)
            get_prefs().show_viewcube = original_visible
            workspace.name = original_name

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

    def test_gizmo_cleanup_never_writes_a_closed_spaces_rna(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        class Space:
            type = 'VIEW_3D'
            valid = True
            value = True

            def as_pointer(self):
                return 123

            @property
            def show_gizmo_navigate(self):
                if not self.valid:
                    raise AssertionError('read through expired RNA owner')
                return self.value

            @show_gizmo_navigate.setter
            def show_gizmo_navigate(self, value):
                if not self.valid:
                    raise AssertionError('write through expired RNA owner')
                self.value = value

        for removed in (False, True):
            with self.subTest(removed=removed):
                old = Space()
                area = SimpleNamespace(spaces=[old], tag_redraw=lambda: None)
                ws = SimpleNamespace(name='3ds Max', screens=[SimpleNamespace(areas=[area])])
                data = SimpleNamespace(data=SimpleNamespace(workspaces=[ws]))
                prefs = SimpleNamespace(show_viewcube=True)
                with patch.object(viewcube, 'bpy', data), patch.object(viewcube, '_enabled', True), \
                        patch.object(viewcube, '_prefs', return_value=prefs), patch.object(viewcube, '_gizmos', {}):
                    viewcube.sync_gizmos()
                    self.assertFalse(old.value)
                    old.valid = False
                    # Closing removes the space. A surviving native space can also
                    # acquire a fresh owner/wrapper across a workspace/file change.
                    fresh = Space()
                    fresh.value = False
                    area.spaces = [] if removed else [fresh]
                    viewcube._save_pre(None)
                    if not removed:
                        self.assertTrue(fresh.value)
                    prefs.show_viewcube = False
                    viewcube.sync_gizmos()
                    self.assertEqual(viewcube._gizmos, {})
                    if not removed:
                        self.assertTrue(fresh.value)

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

    def test_clicked_edge_and_corner_keep_upright_or_preserve_current_roll(self):
        for target in ((0, 1, 1), (1, 1, 1)):
            for upright in (False, True):
                rotation = viewcube.clicked_rotation(target, Quaternion(), Quaternion(), upright)
                self.assertGreater((rotation @ Vector((0, 0, 1))).dot(Vector(target).normalized()), .9999)
                up = (rotation @ Vector((0, 1, 0))).z
                self.assertGreater(up if upright else -up, .4)
                if not upright:
                    self.assertLess(Quaternion().rotation_difference(rotation).angle, 1.0)

    def test_projection_has_pickable_face_edge_corner_and_no_scene_hits(self):
        geometry = viewcube.cube_geometry(Quaternion(), 200, 200, 40)
        self.assertEqual(viewcube.pick(geometry, 200, 200), (0, 0, 1))
        self.assertEqual(viewcube.pick(geometry, 235, 200), (1, 0, 1))
        self.assertEqual(viewcube.pick(geometry, 235, 235), (1, 1, 1))
        self.assertIsNone(viewcube.pick(geometry, 100, 100))
        self.assertFalse(viewcube._inside([(0, 10), (0, 10), (10, 10), (10, 10)], 5, 10))

    def test_orbit_from_top_preserves_yaw_and_upright_option(self):
        q = viewcube.orbit_rotation(Quaternion(), 12, -6, True)
        self.assertLess(Quaternion().rotation_difference(q).angle, .15)
        self.assertLess((q @ Vector((0, 0, 1))).y, 0)
        front = viewcube.rotation_for((0, -1, 0))
        q = viewcube.orbit_rotation(front, 0, 400, True)
        self.assertGreaterEqual((q @ Vector((0, 1, 0))).z, 0)
        q = viewcube.orbit_rotation(front, 0, 400, False)
        self.assertLess((q @ Vector((0, 1, 0))).z, 0)

    def test_chamfer_has_six_faces_twelve_edges_and_eight_corners(self):
        facets = viewcube.cube_facets()
        self.assertEqual(len(facets), 26)
        self.assertEqual(sorted(len(f['vertices']) for f in facets), [3] * 8 + [4] * 18)
        self.assertEqual({f['normal'] for f in facets},
                         {(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1)
                          for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)})
        # A bevel must connect adjacent planes, rather than paint a stripe on a box.
        edge = next(f for f in facets if f['normal'] == (1, 0, 1))
        self.assertEqual({round(v.x + v.z, 4) for v in edge['vertices']}, {1.9})
        self.assertTrue(all(len(set(round(v[i], 4) for v in edge['vertices'])) > 1 for i in (0, 2)))

    def test_compass_band_surrounds_top_face_and_foreshortens_with_cube(self):
        top = viewcube.compass_geometry(Quaternion(), 0, 0, 1)
        self.assertEqual(len(top), 96)
        picking = viewcube.compass_geometry(Quaternion(), 0, 0, 100)
        self.assertTrue(any(viewcube._inside(poly, 172, 0) for poly in picking))
        radii = [(x * x + y * y) ** .5 for poly in top for x, y in poly]
        self.assertAlmostEqual(min(radii), 1.69, places=5)
        self.assertAlmostEqual(max(radii), 2.15, places=5)
        tilted = viewcube.compass_geometry(viewcube.rotation_for((1, -1, 1)), 0, 0, 1)
        def height(band):
            ys = [p[1] for poly in band for p in poly]
            return max(ys) - min(ys)
        self.assertLess(height(tilted), height(top) * .7)

    def test_widget_never_becomes_opaque(self):
        self.assertAlmostEqual(viewcube.widget_opacity(True, 100), .8)
        self.assertLess(viewcube.widget_opacity(False, 100), .8)
        self.assertEqual(viewcube.widget_opacity(False, 0), 0)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ViewCubeTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('VIEWCUBE PASS: axes, diagonal views, custom Front, hits and gizmo restoration')
