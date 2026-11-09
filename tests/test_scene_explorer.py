"""Run with Blender --background --factory-startup --python this file."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from _w15_setup import bpy, box, empty_scene, scene_explorer as explorer


class ExplorerTests(unittest.TestCase):
    def setUp(self):
        empty_scene()
        self.parent = box("Assembly")
        self.child = box("Bolt")
        self.child.parent = self.parent

    def test_filter_keeps_ancestors_and_clear_restores_tree(self):
        rows = explorer.scene_rows(bpy.context, "bolt")
        self.assertEqual([(r.obj.name, r.depth, r.matches) for r in rows],
                         [("Assembly", 0, False), ("Bolt", 1, True)])
        self.assertEqual(len(explorer.scene_rows(bpy.context)), 2)
        explorer.set_expanded(self.parent, False)
        self.assertEqual(len(explorer.scene_rows(bpy.context)), 1)
        self.assertEqual(len(explorer.scene_rows(bpy.context, "bolt")), 2)

    def test_multi_selection_respects_hide_and_freeze(self):
        explorer.select_objects(bpy.context, [self.parent, self.child])
        self.assertEqual(set(bpy.context.selected_objects), {self.parent, self.child})
        explorer.set_frozen(bpy.context, [self.child], True)
        explorer.select_objects(bpy.context, [self.child])
        self.assertFalse(self.child.select_get())
        explorer.set_frozen(bpy.context, [self.child], False)
        explorer.set_hidden(bpy.context, [self.child], True)
        explorer.select_objects(bpy.context, [self.child])
        self.assertFalse(self.child.select_get())

    def test_rename_delete_and_link_preserve_world_matrix(self):
        self.child.parent = None
        self.child.location = (4, 5, 6)
        bpy.context.view_layer.update()
        before = self.child.matrix_world.copy()
        explorer.reparent(bpy.context, [self.child], self.parent)
        self.assertLess(max(abs(a-b) for ar, br in zip(before, self.child.matrix_world)
                            for a, b in zip(ar, br)), 1e-5)
        with self.assertRaises(ValueError):
            explorer.reparent(bpy.context, [self.parent], self.child)
        self.child.name = "Renamed"
        self.assertEqual(explorer.scene_rows(bpy.context, "renamed")[-1].obj, self.child)
        bpy.data.objects.remove(self.child, do_unlink=True)
        self.assertEqual(len(explorer.scene_rows(bpy.context)), 1)

    def test_selection_dialog_cancel_is_non_mutating(self):
        explorer.select_objects(bpy.context, [self.parent])
        before = list(bpy.context.selected_objects)
        chooser = explorer.SelectionDraft(bpy.context)
        chooser.toggle(self.child)
        chooser.cancel()
        self.assertEqual(list(bpy.context.selected_objects), before)
        chooser = explorer.SelectionDraft(bpy.context)
        chooser.toggle(self.parent)
        chooser.toggle(self.child)
        chooser.accept()
        self.assertEqual(list(bpy.context.selected_objects), [self.child])


if __name__ == "__main__":
    unittest.main(argv=[__file__])
