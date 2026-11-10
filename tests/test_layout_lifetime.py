"""A closed window must never receive a workspace write during Restore."""
import unittest
from notuodesk_3ds_maxxed import operators
import bpy


class FreedWindow:
    def __setattr__(self, name, value):
        raise AssertionError('Restore wrote to a closed window')


class LayoutLifetimeTests(unittest.TestCase):
    def test_restore_switches_a_live_window_back(self):
        window = bpy.context.window
        workspace = window.workspace
        other = next(ws for ws in bpy.data.workspaces if ws != workspace)
        window.workspace = other
        operators._layout_snapshot[window.as_pointer()] = (window, workspace, workspace.name)
        operators.restore_layout(bpy.context)
        self.assertEqual(window.workspace, workspace)
        self.assertFalse(operators._layout_snapshot)

    def test_restore_discards_closed_window_before_dereferencing_it(self):
        workspace = bpy.context.workspace
        operators._layout_snapshot[-1] = (FreedWindow(), workspace, workspace.name)
        try:
            operators.restore_layout(bpy.context)
            self.assertFalse(operators._layout_snapshot)
        finally:
            operators._layout_snapshot.clear()


unittest.main(argv=['layout lifetime'], exit=False)
