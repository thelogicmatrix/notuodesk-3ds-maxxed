"""Run in an isolated profile: blender -b --factory-startup --python tests/test_hsx_import.py -- [personal.hsx]."""

import sys
from pathlib import Path
import tempfile
import unittest
from math import radians, sqrt

import bpy
import bmesh
import addon_utils

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import hsx_import as hsx, editable_poly as ep

FIXTURE = '''<MaxHotkeyTransformations>
<Unassign_Hotkey Shortcut="Shift+E" Description="Extrude Mode" Id="1250838234-40017"/>
<Assign_Hotkey Shortcut="Ctrl+Shift+B" Description="Bridge" Id="1250838234-40090"/>
<Assign_Hotkey Shortcut="Ctrl+Shift+B" Description="fastBridge" Id="647394-fastBridge`rapidTools"/>
<Assign_Hotkey Shortcut="Ctrl+P" Description="Cap" Id="unknown-cap"/>
<Assign_Hotkey Shortcut="Alt+Shift+E" Description="Extrude Settings" Id="369982487-40054"/>
<Assign_Hotkey Shortcut="Alt+R" Description="Select Edge Ring" Id="1250838234-40041"/>
<Assign_Hotkey Shortcut="Ctrl+Shift+P" Description="rapidQCap" Id="647394-rapidQCap`rapidTools"/>
<Assign_Hotkey Shortcut="Ctrl+F12" Description="Unknown action" Id="unknown"/>
</MaxHotkeyTransformations>'''


class HsxTests(unittest.TestCase):
    def setUp(self):
        self.entries = hsx.parse_hsx(FIXTURE)
        bpy.context.scene.max_poly_operations.clear()

    def apply_settings(self, op, **values):
        settings = ep.settings(bpy.context, op)
        for name, value in values.items():
            setattr(settings, name, value)
        return bpy.ops.max.hsx_settings(op=op)

    def edit_mesh(self, vertices, edges=(), faces=(), mode="EDGE", selected=None):
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        mesh = bpy.data.meshes.new("HSX regression")
        mesh.from_pydata(vertices, edges, faces)
        obj = bpy.data.objects.new("HSX regression", mesh)
        bpy.context.collection.objects.link(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type=mode)
        bm = bmesh.from_edit_mesh(mesh)
        bpy.ops.mesh.select_all(action="DESELECT")
        sequence = bm.verts if mode == "VERT" else bm.edges
        sequence.ensure_lookup_table()
        for index in (range(len(sequence)) if selected is None else selected):
            sequence[index].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        return obj, bm

    def test_bridge_segments_default_and_explicit(self):
        vertices = [(x, y, z) for z in (0, 2) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        edges = [(i + base, (i + 1) % 4 + base) for base in (0, 4) for i in range(4)]
        for kwargs, want_faces, want_vertices in [({}, 4, 8), ({"segments": 3}, 12, 16)]:
            with self.subTest(kwargs=kwargs):
                obj, bm = self.edit_mesh(vertices, edges)
                self.assertEqual(self.apply_settings(op="BRIDGE", **kwargs), {"FINISHED"})
                self.assertEqual((len(bm.faces), len(bm.verts)), (want_faces, want_vertices))
                print(f"HSX FIX PASS Bridge {kwargs or 'defaults'} faces={len(bm.faces)} vertices={len(bm.verts)}", flush=True)

    def test_connect_segments_default_and_explicit(self):
        for kwargs, want_edges in [({}, 2), ({"segments": 2}, 3)]:
            with self.subTest(kwargs=kwargs):
                obj, bm = self.edit_mesh([(0, 0, 0), (3, 0, 0)], [(0, 1)])
                self.assertEqual(self.apply_settings(op="CONNECT", **kwargs), {"FINISHED"})
                self.assertEqual(len(bm.edges), want_edges)

    def test_chamfer_reuses_panel_amount(self):
        obj, bm = self.edit_mesh([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)],
                                 faces=[(0, 1, 2, 3)], mode="VERT", selected=[0])
        self.assertEqual(self.apply_settings(op="CHAMFER", amount=.375), {"FINISHED"})
        points = {tuple(round(c, 5) for c in v.co) for v in bm.verts}
        self.assertIn((0.375, 0.0, 0.0), points)
        self.assertIn((0.0, 0.375, 0.0), points)
        print("HSX FIX PASS Chamfer shared panel Amount=0.375", flush=True)

    def test_tessellate_face_type(self):
        obj, bm = self.edit_mesh([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], faces=[(0, 1, 2, 3)])
        self.assertIn("tessellate_type", bpy.ops.max.poly_settings.get_rna_type().properties)
        self.assertEqual(self.apply_settings(op="TESSELLATE", tessellate_type="FACE"), {"FINISHED"})
        self.assertEqual((len(bm.faces), len(bm.verts)), (4, 5))
        self.assertTrue(all(len(f.verts) == 3 for f in bm.faces))
        print("HSX FIX PASS Tessellate Type=Face makes 4 triangles", flush=True)

    def test_edge_and_vertex_extrude_follow_surface_normals(self):
        # The two faces share an edge along Y and have normals +Z and +X.
        vertices = [(0, 0, 0), (0, 2, 0), (-2, 2, 0), (-2, 0, 0), (0, 0, -2), (0, 2, -2)]
        faces = [(0, 1, 2, 3), (1, 0, 4, 5)]
        for mode in ("EDGE", "VERT"):
            for rotated in (False, True):
                for amount in (1.0, -0.5):
                    with self.subTest(mode=mode, rotated=rotated, amount=amount):
                        obj, bm = self.edit_mesh(vertices, faces=faces, mode=mode, selected=[0])
                        if mode == "EDGE":
                            bpy.ops.mesh.select_all(action="DESELECT")
                            next(e for e in bm.edges if {v.index for v in e.verts} == {0, 1}).select_set(True)
                            bm.select_flush_mode()
                            bmesh.update_edit_mesh(obj.data)
                        if rotated:
                            obj.rotation_euler.x = radians(90)
                            bpy.context.view_layer.update()
                        old = set(bm.verts)
                        before = {v: v.co.copy() for v in old}
                        self.assertEqual(self.apply_settings(op="EXTRUDE", amount=amount), {"FINISHED"})
                        new = set(bm.verts) - old
                        self.assertEqual(len(new), 2 if mode == "EDGE" else 1)
                        matrix = obj.matrix_world.to_3x3()
                        for vert in new:
                            source = next(e.other_vert(vert) for e in vert.link_edges if e.other_vert(vert) in old)
                            delta = matrix @ (vert.co - before[source])
                            step = amount / sqrt(2)
                            expected = (step, -step, 0) if rotated else (step, 0, step)
                            for got, want in zip(delta, expected):
                                self.assertAlmostEqual(got, want, places=5)
                        self.assertTrue(all((v.co - before[v]).length < 1e-6 for v in old))
                        self.assertFalse(any(v.select for v in old), "Extrude must select only the new top geometry")

    def test_rotated_flat_surface_extrudes_along_world_minus_y(self):
        for mode in ("VERT", "EDGE"):
            with self.subTest(mode=mode):
                obj, bm = self.edit_mesh([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)],
                                         faces=[(0, 1, 2, 3)], mode=mode, selected=[0])
                obj.rotation_euler.x = radians(90)
                bpy.context.view_layer.update()
                old = set(bm.verts)
                self.assertEqual(self.apply_settings(op="EXTRUDE", amount=1), {"FINISHED"})
                for vert in set(bm.verts) - old:
                    source = next(e.other_vert(vert) for e in vert.link_edges if e.other_vert(vert) in old)
                    delta = obj.matrix_world.to_3x3() @ (vert.co - source.co)
                    for got, want in zip(delta, (0, -1, 0)):
                        self.assertAlmostEqual(got, want, places=5)

    def test_extrude_without_surface_normal_uses_panel_local_z_fallback(self):
        for mode in ("VERT", "EDGE"):
            with self.subTest(mode=mode):
                obj, bm = self.edit_mesh([(0, 0, 0), (1, 0, 0)], [(0, 1)], mode=mode)
                old = set(bm.verts)
                self.assertEqual(self.apply_settings(op="EXTRUDE", amount=1), {"FINISHED"})
                self.assertEqual(len(bm.verts), 4)
                self.assertTrue(all(abs(v.co.z - 1) < 1e-6 for v in set(bm.verts) - old))
                self.assertTrue(all(abs(v.co.z) < 1e-6 for v in old))

    def test_parse_and_resolve(self):
        self.assertEqual(len(self.entries), 8)
        self.assertEqual(hsx.resolve_action(self.entries[1]), ("Mesh", "max.edit_poly", {"op": "BRIDGE"}))
        self.assertEqual(hsx.resolve_action(self.entries[3]), ("Mesh", "max.edit_poly", {"op": "CAP"}))
        self.assertEqual(hsx.resolve_action(self.entries[4]), ("Mesh", "max.hsx_settings", {"op": "EXTRUDE"}))
        self.assertEqual(hsx.resolve_action(self.entries[5]), ("Mesh", "max.edit_poly", {"op": "RING"}))
        bindings, unmapped = hsx.build_bindings(self.entries)
        optional = hsx.operator_exists("max.quad_cap")
        self.assertEqual(len(bindings), 5 if optional else 4)
        self.assertEqual([e["description"] for e in unmapped], ["Unknown action"] if optional else ["rapidQCap", "Unknown action"])

    def test_shortcuts(self):
        for source, want in [("Ctrl+Alt+Shift+E", "E"), ("0", "ZERO"), ("9", "NINE"),
                             ("F24", "F24"), ("Delete", "DEL"), ("Del", "DEL"), ("Backspace", "BACK_SPACE"),
                             ("Page Up", "PAGE_UP"), ("PgDn", "PAGE_DOWN"), ("Home", "HOME"),
                             ("End", "END"), ("Left Arrow", "LEFT_ARROW"), ("NumPad 3", "NUMPAD_3"),
                             ("Num +", "NUMPAD_PLUS"), ("Num /", "NUMPAD_SLASH"),
                             ("Num Enter", "NUMPAD_ENTER"), ("Num .", "NUMPAD_PERIOD"),
                             ("Num -", "NUMPAD_MINUS")]:
            self.assertEqual(hsx.parse_shortcut(source)[0], want, source)
        self.assertEqual(hsx.parse_shortcut("Ctrl+Alt+Shift+E"), ("E", True, True, True))
        for bad in ("", "Ctrl+", "Ctrl+Banana", "Ctrl+Alt", "Num"):
            with self.assertRaises(ValueError):
                hsx.parse_shortcut(bad)

    def test_optional_operators_rechecked_at_registration(self):
        entry = self.entries[6]
        if hsx.operator_exists("max.quad_cap"):
            self.assertEqual(hsx.resolve_action(entry), ("Mesh", "max.quad_cap", {}))
            return
        self.assertIsNone(hsx.resolve_action(entry))

        class MAX_OT_quad_cap(bpy.types.Operator):
            bl_idname = "max.quad_cap"
            bl_label = "Synthetic Quad Cap"

            def execute(self, context):
                return {"FINISHED"}

        bpy.utils.register_class(MAX_OT_quad_cap)
        try:
            self.assertEqual(hsx.resolve_action(entry), ("Mesh", "max.quad_cap", {}))
        finally:
            bpy.utils.unregister_class(MAX_OT_quad_cap)
        self.assertIsNone(hsx.resolve_action(entry))

    def test_unassign_removes_only_same_operation_and_key(self):
        bridge = self.entries[1]
        unassign = dict(bridge, kind="Unassign_Hotkey")
        bindings, _ = hsx.build_bindings([bridge, unassign])
        self.assertEqual(bindings, [])
        other_key = dict(unassign, shortcut="Alt+B")
        self.assertEqual(len(hsx.build_bindings([bridge, other_key])[0]), 1)
        bevel = dict(unassign, id="1250838234-40013", description="Bevel Mode")
        self.assertEqual(len(hsx.build_bindings([bridge, bevel])[0]), 1)

    def test_settings_apply_parameters(self):
        import bmesh
        for operation, want_faces in [("TESSELLATE", 24), ("CHAMFER", 26)]:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.mesh.primitive_cube_add()
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_mode(type="EDGE")
            bpy.ops.mesh.select_all(action="SELECT")
            self.assertEqual(self.apply_settings(op=operation, amount=0.2, segments=1), {"FINISHED"})
            self.assertEqual(len(bmesh.from_edit_mesh(bpy.context.object.data).faces), want_faces)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_plane_add()
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        self.assertEqual(self.apply_settings(op="EXTRUDE", amount=0.75), {"FINISHED"})
        mesh = bmesh.from_edit_mesh(bpy.context.object.data)
        # The shared panel operation removes the original face.
        self.assertEqual(len(mesh.faces), 5)
        self.assertAlmostEqual(max(v.co.z for v in mesh.verts), 0.75)
        bpy.ops.object.mode_set(mode="OBJECT")

    def test_default_overrides_and_clear(self):
        from notuodesk_3ds_maxxed import get_prefs, keymap
        p = get_prefs()
        hsx.store_entries(p, self.entries)
        self.assertTrue(hsx.skip_default("Mesh", ("view3d.edit_mesh_extrude_move_normal", "E", "PRESS", False, True, False, {}), self.entries))
        self.assertTrue(hsx.skip_default("Mesh", ("max.set_view", "P", "PRESS", True, False, False, {}), self.entries))
        self.assertFalse(hsx.skip_default("Mesh", ("max.set_view", "P", "PRESS", False, False, False, {}), self.entries))
        bpy.ops.max.clear_hsx_hotkeys()
        self.assertEqual(hsx.load_entries(p), [])
        keymap.unregister_keymaps()

    def test_malformed_does_not_replace_preferences(self):
        from notuodesk_3ds_maxxed import get_prefs
        p = get_prefs()
        hsx.store_entries(p, self.entries)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.hsx"
            path.write_text("<broken", encoding="utf8")
            try:
                result = bpy.ops.max.import_hsx(filepath=str(path))
            except RuntimeError:
                result = {"CANCELLED"}
            self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(len(hsx.load_entries(p)), 8)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(HsxTests)
result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
if "--" in sys.argv:
    path = sys.argv[sys.argv.index("--") + 1]
    entries = hsx.parse_hsx(Path(path).read_bytes())
    bindings, unmapped = hsx.build_bindings(entries)
    for entry in entries:
        print("HSX MAP", entry["kind"], entry["shortcut"], entry["id"], entry["description"], "=>", hsx.resolve_action(entry), flush=True)
    print(f"HSX PERSONAL entries={len(entries)} assigned={sum(e['kind'] == 'Assign_Hotkey' for e in entries)} bindings={len(bindings)} unmapped={len(unmapped)}", flush=True)
print("HSX TESTS PASS", flush=True)
