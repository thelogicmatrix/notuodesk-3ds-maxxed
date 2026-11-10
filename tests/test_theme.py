"""Run with run_checks.py tests test_theme in an isolated profile."""
import unittest
import bpy
from notuodesk_3ds_maxxed import theme


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        theme.restore()

    def test_restore_reacquires_live_owners_after_reload(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        class Owner:
            bl_rna = SimpleNamespace(identifier='ThemeFixture')
            valid = True
            current = True

            def as_pointer(self):
                return 456

            @property
            def setting(self):
                if not self.valid:
                    raise AssertionError('read through expired theme RNA')
                return self.current

            @setting.setter
            def setting(self, value):
                if not self.valid:
                    raise AssertionError('write through expired theme RNA')
                self.current = value

        for removed in (False, True):
            with self.subTest(removed=removed), patch.object(theme, '_changes', {}):
                old = Owner()
                theme._remember(old, 'setting', False)
                old.valid = False
                fresh = Owner()
                fresh.current = False
                with patch.object(theme, '_live_owners', return_value=[] if removed else [fresh], create=True):
                    theme.restore()
                self.assertFalse(theme._changes)
                if not removed:
                    self.assertTrue(fresh.current)

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
        for actual, expected in zip(selected, (100/255, 138/255, 187/255, 1)):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertFalse(prefs.view.show_tooltips_python)
        self.assertEqual(prefs.view.ui_scale, scale)
        theme.restore()
        self.assertEqual(tuple(view.vertex_select), original)
        self.assertTrue(cursor.show_cursor)
        self.assertFalse(theme._changes)


unittest.main(argv=['theme'], exit=False)
