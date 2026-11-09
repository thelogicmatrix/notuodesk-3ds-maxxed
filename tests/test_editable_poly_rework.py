"""Run: blender -b --factory-startup --python tests/test_editable_poly_rework.py."""
import unittest
import sys
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).parent))
from test_editable_poly_panel import mesh, QUAD, CUBE, CUBE_FACES
from notuodesk_3ds_maxxed import editable_poly as ep


class Layout:
    """Record UI draw calls, including inherited disabled state."""
    def __init__(self, calls=None, parent=None):
        self.calls = calls if calls is not None else []
        self.parent, self.enabled = parent, True

    def active(self):
        return self.enabled and (self.parent is None or self.parent.active())

    def row(self, **kw): return Layout(self.calls, self)
    column = grid_flow = row
    def label(self, **kw): self.calls.append(("label", kw.get("text"), self.active()))
    def prop(self, data, key, **kw): self.calls.append(("prop", key, self.active()))
    def prop_enum(self, data, key, value, **kw): self.calls.append(("radio", key, self.active()))
    def operator(self, name, **kw):
        from types import SimpleNamespace
        item = SimpleNamespace()
        self.calls.append(("operator", kw.get("text", name), self.active()))
        return item


class ReworkTests(unittest.TestCase):
    def test_viewport_tools_receive_window_region(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from notuodesk_3ds_maxxed import operators
        mesh(QUAD, faces=[(0, 1, 2, 3)])
        area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")
        sidebar = next(r for r in area.regions if r.type == "UI")
        # The native modal tools need a GUI. Replace only their entry points
        # here, and assert on the real Blender context at the native boundary.
        # The GUI harness separately clicks both real buttons and tools.
        seen = []
        def start_tool(*args, **kwargs):
            seen.append((bpy.context.area.type, bpy.context.region.type))
            self.assertEqual(seen[-1], ("VIEW_3D", "WINDOW"))
            return {"FINISHED"}
        proxy = SimpleNamespace(types=SimpleNamespace(), ops=SimpleNamespace(max=SimpleNamespace(poly_native_cut=start_tool, poly_quick_slice=start_tool)))
        for action in ("CUT", "QUICK_SLICE"):
            with self.subTest(action=action), patch.object(ep, "bpy", proxy), patch.object(operators, "bpy", proxy):
                with bpy.context.temp_override(area=area, region=sidebar):
                    command = SimpleNamespace(op=action, report=lambda *a: None)
                    self.assertEqual(operators.MAX_OT_edit_poly.run(command, bpy.context, "INVOKE_DEFAULT"), {"FINISHED"})
        self.assertEqual(len(seen), 2)

    def test_reference_controls_and_rollouts(self):
        from notuodesk_3ds_maxxed import editable_poly_ui as ui, ui_panel
        ob, bm = mesh(QUAD, faces=[(0,1,2,3)], level=3)
        lay = Layout()
        ui.selection(lay, bpy.context)
        self.assertIn(("operator", "Ring", True), lay.calls)
        self.assertEqual(sum(kind == "radio" and key == "preview" for kind,key,on in lay.calls), 3)
        lay = Layout()
        ui.geometry(lay, bpy.context)
        self.assertEqual(sum(kind == "radio" and key == "constraints" for kind,key,on in lay.calls), 4)
        self.assertIn(("prop", "delete_isolated", True), lay.calls)
        self.assertTrue(any(key == "full_interactivity" for kind,key,on in lay.calls))
        bpy.ops.max.subobject(level=2)
        lay = Layout()
        ui.edit_level(lay, bpy.context)
        for key in ("depth", "display_hard_edges"):
            self.assertTrue(any(k == key for kind,k,on in lay.calls), key)
        for label in ("Hard", "Smooth"):
            self.assertTrue(any(k == label for kind,k,on in lay.calls), label)
        labels = {cls.bl_label for cls in ui_panel.ROLLOUTS}
        self.assertTrue({"Polygon: Vertex Colors", "Subdivision Displacement", "Paint Deformation"} <= labels)

    def test_slice_selected_visible_faces_only(self):
        for level in (4, 5):
            verts = [(x, y, z) for y in (0, 4, 8) for x, z in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            ob, bm = mesh(verts, faces=[(i, i+1, i+2, i+3) for i in (0, 4, 8)], level=level)
            bpy.ops.mesh.select_all(action="DESELECT")
            bm.faces.ensure_lookup_table()
            bm.faces[0].select_set(True)
            bm.faces[2].hide_set(True)
            self.assertEqual(bpy.ops.max.edit_poly(op="SLICE"), {"FINISHED"})
            self.assertEqual(len(bm.faces), 4, "only the selected quad should split")
            self.assertEqual(sum(f.hide for f in bm.faces), 1)
            self.assertEqual(sum(len(f.verts) == 4 for f in bm.faces if f.calc_center_median().y > 2), 2)

    def test_individual_extrude_selects_only_new_tops(self):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
        s = ep.settings(bpy.context, "EXTRUDE")
        s.extrusion_type, s.amount = "POLYGON", .5
        bpy.ops.max.edit_poly(op="EXTRUDE")
        selected = [f for f in bm.faces if f.select]
        self.assertEqual(len(selected), 1)
        self.assertTrue(all(abs(v.co.z - .5) < 1e-6 for v in selected[0].verts), "top must remain selected")

    def test_isolated_means_no_polygons_including_wire_edges(self):
        ob, bm = mesh(QUAD + [(4, 0, 0), (5, 0, 0), (7, 0, 0)], edges=[(4, 5)], faces=[(0, 1, 2, 3)], level=1)
        bpy.ops.max.edit_poly(op="DELETE_ISOLATED")
        self.assertEqual(len(bm.verts), 4, "wire vertices are isolated too")

    def test_delete_isolated_checkbox_controls_delete_cleanup(self):
        for enabled, count in ((True, 0), (False, 4)):
            ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
            self.assertIn("delete_isolated", ob.max_poly.bl_rna.properties)
            self.assertTrue(ob.max_poly.delete_isolated)
            ob.max_poly.delete_isolated = enabled
            bpy.ops.max.delete()
            self.assertEqual(len(bm.verts), count)

    def test_soft_selection_default_and_sg_clear_are_independent(self):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2), (0, 2, 3)])
        self.assertEqual(ob.max_poly.falloff, 20)
        self.assertIn("sg_clear_selection", ob.max_poly.bl_rna.properties)
        ob.max_poly.clear_selection = False
        ob.max_poly.sg_clear_selection = True
        bpy.ops.mesh.select_all(action="DESELECT")
        bm.faces.ensure_lookup_table()
        bm.faces[0].select_set(True)
        bpy.ops.max.poly_smoothing(action="TOGGLE", group=1)
        bm.faces[1].select_set(True)
        bpy.ops.max.poly_smoothing(action="SELECT")
        self.assertEqual(sum(f.select for f in bm.faces), 1)

    def test_bevel_types_move_new_tops_and_persist(self):
        for kind in ("GROUP", "LOCAL", "POLYGON"):
            ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
            s = ep.settings(bpy.context, "BEVEL")
            self.assertIn("bevel_type", s.bl_rna.properties)
            s.bevel_type, s.height, s.amount = kind, .5, .1
            self.assertEqual(bpy.ops.max.edit_poly(op="BEVEL"), {"FINISHED"})
            self.assertEqual(len(bm.faces), 5)
            self.assertEqual(sum(f.select for f in bm.faces), 1)
            self.assertAlmostEqual(max(v.co.z for v in bm.verts), .5)
            self.assertEqual(ep.settings(bpy.context, "BEVEL").bevel_type, kind)

    def test_bridge_has_independent_twist_and_pick_settings(self):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=3)
        s = ep.settings(bpy.context, "BRIDGE")
        for key in ("twist1", "twist2", "bridge_selection"):
            self.assertIn(key, s.bl_rna.properties)
        s.twist1, s.twist2 = 1, 3
        self.assertEqual(ep.settings(bpy.context, "BRIDGE").twist1, 1)
        self.assertEqual(ep.settings(bpy.context, "BRIDGE").twist2, 3)

    def test_target_weld_vertex_rules_and_exact_target_position(self):
        from notuodesk_3ds_maxxed import target_weld as tw
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=1)
        bm.verts.ensure_lookup_table()
        source, neighbour, opposite = bm.verts[0], bm.verts[1], bm.verts[2]
        self.assertTrue(tw.invalid_reason(bm, source, opposite, 1))
        self.assertFalse(tw.invalid_reason(bm, source, neighbour, 1))
        target_co = neighbour.co.copy()
        tw.weld(bm, source, neighbour, 1)
        self.assertEqual(len(bm.verts), 3)
        self.assertEqual(neighbour.co, target_co)
        self.assertFalse(source.is_valid)

    def test_target_weld_wrong_level_cancels_without_exception(self):
        mesh(QUAD, faces=[(0, 1, 2, 3)], level=4)
        self.assertEqual(bpy.ops.max.edit_poly(op="TARGET_WELD"), {"CANCELLED"})

    def test_target_weld_edges_only_borders_and_no_illegal_geometry(self):
        from notuodesk_3ds_maxxed import target_weld as tw
        verts = QUAD + [(x+4, y, z) for x,y,z in QUAD]
        ob, bm = mesh(verts, faces=[(0,1,2,3), (4,5,6,7)], level=2)
        bm.verts.ensure_lookup_table()
        source = bm.edges.get((bm.verts[1], bm.verts[2]))
        target = bm.edges.get((bm.verts[4], bm.verts[7]))
        coords = [v.co.copy() for v in target.verts]
        self.assertFalse(tw.invalid_reason(bm, source, target, 2))
        tw.weld(bm, source, target, 2)
        self.assertEqual(len(bm.verts), 6)
        self.assertEqual(len(target.link_faces), 2)
        self.assertEqual([v.co for v in target.verts], coords)
        ob, bm = mesh(CUBE, faces=CUBE_FACES[:-1], level=3)
        boundary = [e for e in bm.edges if e.is_boundary]
        opposite = next(e for e in boundary if not set(e.verts) & set(boundary[0].verts))
        self.assertTrue(tw.invalid_reason(bm, boundary[0], opposite, 3))
        inner = next(e for e in bm.edges if not e.is_boundary)
        self.assertTrue(tw.invalid_reason(bm, inner, boundary[0], 2))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReworkTests)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    print(f"REWORK RESULT tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}", flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
