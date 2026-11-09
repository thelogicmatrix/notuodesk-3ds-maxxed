"""Run: blender -b --factory-startup --python-exit-code 1 --python tests/test_viewcube_reload.py"""

import os
import sys
import tempfile
import unittest

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notuodesk_3ds_maxxed import get_prefs, viewcube


class ViewCubeReloadTests(unittest.TestCase):
    def test_save_reload_restores_each_viewports_original_gizmo(self):
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        get_prefs().first_run_done = True
        get_prefs().auto_check_updates = False
        bpy.context.workspace.name = '3ds Max'
        areas = bpy.context.screen.areas
        # Use two independent spaces, one with a user-hidden native gizmo.
        areas[0].type = areas[1].type = 'VIEW_3D'
        indices = (0, 1)
        originals = (True, False)
        get_prefs().show_viewcube = False
        for index, original in zip(indices, originals):
            areas[index].spaces.active.show_gizmo_navigate = original
        get_prefs().show_viewcube = True
        viewcube.sync_gizmos()
        try:
            with tempfile.TemporaryDirectory(prefix='viewcube-reload-') as folder:
                path = os.path.join(folder, 'gizmos.blend')
                for action in ('toggle', 'disable'):
                    with self.subTest(action=action):
                        bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
                        self.assertEqual([bpy.context.screen.areas[i].spaces.active.show_gizmo_navigate
                                          for i in indices], [False, False])
                        bpy.ops.wm.open_mainfile(filepath=path)
                        self.assertEqual([bpy.context.screen.areas[i].spaces.active.show_gizmo_navigate
                                          for i in indices], [False, False])
                        if action == 'toggle':
                            get_prefs().show_viewcube = False
                        else:
                            addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)
                        self.assertEqual([bpy.context.screen.areas[i].spaces.active.show_gizmo_navigate
                                          for i in indices], [True, False])
                        if action == 'toggle':
                            get_prefs().show_viewcube = True
                # The file itself must keep the originals with no add-on active.
                bpy.ops.wm.open_mainfile(filepath=path)
                self.assertEqual([bpy.context.screen.areas[i].spaces.active.show_gizmo_navigate
                                  for i in indices], [True, False])
        finally:
            if viewcube._enabled:
                addon_utils.disable('notuodesk_3ds_maxxed', default_set=False)


result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(ViewCubeReloadTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('VIEWCUBE RELOAD PASS: save/reopen/toggle and disable restore [True, False]')
