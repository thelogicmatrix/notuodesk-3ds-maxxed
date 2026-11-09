"""Run with run_checks.py tests test_theme in an isolated profile."""
import unittest
import bpy
from notuodesk_3ds_maxxed import theme


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        theme.restore()

    def test_repeat_apply_restore_and_unrelated_preferences(self):
        prefs = bpy.context.preferences
        view = prefs.themes[0].view_3d
        original = tuple(view.vertex_select)
        cursor = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D').spaces.active.overlay
        cursor.show_cursor = True
        scale = prefs.view.ui_scale
        theme.apply()
        theme.apply()
        self.assertFalse(cursor.show_cursor)
        self.assertGreater(view.vertex_select[0], .9)
        selected = prefs.themes[0].user_interface.wcol_list_item.inner_sel
        self.assertGreater(selected[0], .6)
        self.assertGreater(selected[1], .4)
        self.assertLess(selected[2], .15)
        self.assertFalse(prefs.view.show_tooltips_python)
        self.assertEqual(prefs.view.ui_scale, scale)
        theme.restore()
        self.assertEqual(tuple(view.vertex_select), original)
        self.assertTrue(cursor.show_cursor)
        self.assertFalse(theme._changes)


unittest.main(argv=['theme'], exit=False)
