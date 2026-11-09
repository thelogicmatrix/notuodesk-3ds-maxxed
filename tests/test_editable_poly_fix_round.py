"""Run in isolated Blender: blender -b --factory-startup --python tests/test_editable_poly_fix_round.py."""
import sys
import unittest
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).parent))
from test_editable_poly_panel import mesh, QUAD
from test_editable_poly_rework import Layout
from notuodesk_3ds_maxxed import editable_poly_ui as ui


class FixRoundTests(unittest.TestCase):
    def test_quickslice_keeps_new_faces_selected_and_respects_hidden_scope(self):
        from notuodesk_3ds_maxxed import editable_poly as ep, poly_modal
        for level in (4, 5):
            verts = QUAD + [(x,y+4,z) for x,y,z in QUAD] + [(x,y+8,z) for x,y,z in QUAD]
            ob, bm = mesh(verts, faces=[(0,1,2,3), (4,5,6,7), (8,9,10,11)], level=level)
            ep.settings(bpy.context, "SLICE_PLANE").split = False
            bpy.ops.mesh.select_all(action="DESELECT")
            bm.faces.ensure_lookup_table()
            bm.faces[0].select_set(True)
            bm.faces[2].hide_set(True)
            poly_modal.slice_mesh(bpy.context, (1,0,0), (1,0,0))
            poly_modal.slice_mesh(bpy.context, (0,1,0), (0,1,0))
            self.assertEqual(len(bm.faces), 6)
            self.assertEqual(sum(f.select for f in bm.faces), 4)
            self.assertEqual(sum(f.hide for f in bm.faces), 1)

    def test_quickslice_split_setting(self):
        from notuodesk_3ds_maxxed import editable_poly as ep, poly_modal
        for split, count in ((False,6), (True,8)):
            ob, bm = mesh(QUAD, faces=[(0,1,2,3)])
            ep.settings(bpy.context, "SLICE_PLANE").split = split
            poly_modal.slice_mesh(bpy.context, (1,0,0), (1,0,0))
            self.assertEqual(len(bm.faces), 2)
            self.assertEqual(len(bm.verts), count)
        ep.settings(bpy.context, "SLICE_PLANE").split = False

    def test_target_weld_shortcut_and_cut_dispatch(self):
        from notuodesk_3ds_maxxed import keymap
        binding = ("max.edit_poly", "W", "PRESS", True, True, False, {"op": "TARGET_WELD"})
        self.assertIn(binding, keymap.MESH)
        self.assertIn(("max.edit_poly", "C", "PRESS", False, False, True, {"op": "CUT"}), keymap.MESH)

    def test_hsx_settings_execute_uses_panel_last_values(self):
        from notuodesk_3ds_maxxed import editable_poly as ep
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=4)
        ep.settings(bpy.context, "EXTRUDE").amount = .375
        self.assertTrue(hasattr(bpy.types, "MAX_OT_hsx_settings"), "hsx compatibility route missing")
        self.assertEqual(bpy.ops.max.hsx_settings(op="EXTRUDE"), {"FINISHED"})
        self.assertAlmostEqual(max(v.co.z for v in bm.verts), .375)

    def test_edge_border_delete_and_remove_keep_vertices_when_unchecked(self):
        for level in (2, 3):
            for action in ("DELETE", "REMOVE"):
                for whole in (False, True):
                    for cleanup in (False, True):
                        with self.subTest(level=level, action=action, whole=whole, cleanup=cleanup):
                            ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=level)
                            if not whole:
                                bpy.ops.mesh.select_all(action="DESELECT")
                                bm.edges.ensure_lookup_table()
                                bm.edges[0].select_set(True)
                            ob.max_poly.delete_isolated = cleanup
                            result = bpy.ops.max.delete() if action == "DELETE" else bpy.ops.max.edit_poly(op="REMOVE")
                            self.assertEqual(result, {"FINISHED"})
                            if not cleanup:
                                self.assertEqual(len(bm.verts), 4, "unchecked must retain every vertex")
                            else:
                                self.assertTrue(all(v.link_faces for v in bm.verts), "checked must purge isolated vertices")

    def test_object_level_cut_and_quickslice_buttons_enabled(self):
        mesh(QUAD, faces=[(0, 1, 2, 3)])
        bpy.ops.max.subobject(level=0)
        lay = Layout()
        ui.geometry(lay, bpy.context)
        self.assertIn(("operator", "Cut", True), lay.calls)
        self.assertIn(("operator", "QuickSlice", True), lay.calls)

    def test_delete_checkbox_only_at_applicable_levels(self):
        for level in range(6):
            mesh(QUAD, faces=[(0, 1, 2, 3)], level=level or 4)
            if level == 0:
                bpy.ops.max.subobject(level=0)
            lay = Layout()
            ui.geometry(lay, bpy.context)
            self.assertEqual(any(kind == "prop" and key == "delete_isolated" for kind, key, enabled in lay.calls), level in (2, 3, 4, 5))


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixRoundTests))
    print(f"FIX ROUND RESULT tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}", flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
