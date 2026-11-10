"""Run through isolated run_checks.py, tests test_target_weld_cursor."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import addon_utils
import bpy
import bmesh

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import target_weld as tw


class CursorTests(unittest.TestCase):
    def setUp(self):
        self.window = SimpleNamespace(cursor_modal_set=Mock(), cursor_modal_restore=Mock())
        self.state = SimpleNamespace(window=self.window, cursor_hidden=False,
                                     handler=object(), workspace=SimpleNamespace(status_text_set=Mock()),
                                     area=SimpleNamespace(tag_redraw=Mock()))
        self.op = SimpleNamespace(key=123, inside=False, hover_valid=False)
        tw._resources[123] = self.state

    def tearDown(self):
        tw._resources.clear()
        tw._active.clear()

    def pointer(self, inside):
        tw.MAX_OT_target_weld.update_pointer(self.op, inside)

    def test_viewport_entry_exit_reentry_owns_one_hidden_cursor(self):
        self.pointer(True)
        self.pointer(True)
        self.assertTrue(self.op.inside)
        self.assertTrue(self.state.cursor_hidden)
        self.window.cursor_modal_set.assert_called_once_with('NONE')
        self.pointer(False)
        self.pointer(False)
        self.assertFalse(self.op.inside)
        self.assertFalse(self.op.hover_valid)
        self.window.cursor_modal_restore.assert_called_once_with()
        self.pointer(True)
        self.assertEqual(self.window.cursor_modal_set.call_count, 2)

    def test_release_restores_once_and_clears_active_and_draw_handler(self):
        self.pointer(True)
        tw._active[123] = SimpleNamespace(region=None)
        with patch.object(tw, 'remove_draw_handler') as remove:
            tw.release(123)
            tw.release(123)
        remove.assert_called_once_with(self.state.handler)
        self.window.cursor_modal_restore.assert_called_once_with()
        self.assertNotIn(123, tw._active)
        self.assertNotIn(123, tw._resources)

    def test_release_outside_does_not_pop_another_modal_cursor(self):
        with patch.object(tw, 'remove_draw_handler'):
            tw.release(123)
        self.window.cursor_modal_restore.assert_not_called()

    def test_handler_failure_still_restores_cursor(self):
        self.pointer(True)
        with patch.object(tw, 'remove_draw_handler', side_effect=ReferenceError):
            tw.release(123)
        self.window.cursor_modal_restore.assert_called_once_with()

    def test_closed_area_does_not_prevent_cursor_restore(self):
        class ClosedArea:
            @property
            def tag_redraw(self):
                raise ReferenceError('area was removed')
        self.pointer(True)
        self.state.area = ClosedArea()
        with patch.object(tw, 'remove_draw_handler'):
            tw.release(123)
        self.window.cursor_modal_restore.assert_called_once_with()

    def test_all_history_and_disable_paths_release_cursor(self):
        for cleanup in (tw.before_restore, tw.unregister_handlers):
            with self.subTest(cleanup=cleanup.__name__):
                self.state.cursor_hidden = True
                tw._resources[123] = self.state
                self.window.cursor_modal_restore.reset_mock()
                with patch.object(tw, 'remove_draw_handler'):
                    cleanup()
                self.window.cursor_modal_restore.assert_called_once_with()
        tw.register_handlers()
        for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
            self.assertIn(tw.before_restore, handlers)

    def test_release_removes_temporary_arrow_image(self):
        from notuodesk_3ds_maxxed import target_weld_cursor as cursor
        image = bpy.data.images.new('Temporary Target Weld arrow', width=32, height=32)
        name = image.name
        cursor._arrow = image
        with patch.object(tw, 'remove_draw_handler'):
            tw.release(123)
        self.assertIsNone(cursor._arrow)
        self.assertNotIn(name, bpy.data.images)

    def test_arrow_asset_has_dark_outline_and_white_fill(self):
        path = Path(tw.__file__).with_name('icons')/'target-weld-system-arrow.png'
        image = bpy.data.images.load(str(path), check_existing=False)
        try:
            pixels = list(image.pixels)
            colors = [pixels[i:i+4] for i in range(0,len(pixels),4)]
            self.assertGreaterEqual(sum(max(c[:3])<.1 and c[3]>.9 for c in colors),12)
            self.assertGreaterEqual(sum(min(c[:3])>.8 and c[3]>.9 for c in colors),12)
        finally:
            bpy.data.images.remove(image)

    def test_hover_validity_follows_real_mesh_restrictions(self):
        bm = bmesh.new()
        try:
            a, b, isolated = [bm.verts.new(co) for co in ((0, 0, 0), (1, 0, 0), (5, 0, 0))]
            bm.edges.new((a, b))
            op = SimpleNamespace(source=a, bm=bm, level=1, pick=Mock())
            for target, valid in ((None, False), (a, False), (isolated, False), (b, True)):
                op.pick.return_value = target
                tw.MAX_OT_target_weld.hover_target(op)
                self.assertEqual(op.hover_valid, valid)
            op.source = None
            tw.MAX_OT_target_weld.hover_target(op)
            self.assertTrue(op.hover_valid, 'a pickable source also uses the cross')
        finally:
            bm.free()

    def test_passive_feedback_does_not_draw_a_second_cursor(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        ctx = SimpleNamespace(workspace=SimpleNamespace(name='3ds Max'), window=Mock())
        with patch.object(mf.bpy, 'context', ctx), patch.object(mf, '_draw_view_border'), \
             patch.object(tw, 'is_active', return_value=True), patch.object(mf, 'pointer_state') as pointer:
            mf._draw_cursor()
        pointer.assert_not_called()


if __name__ == '__main__':
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CursorTests))
    print(f'WELD CURSOR RESULT tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}', flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
