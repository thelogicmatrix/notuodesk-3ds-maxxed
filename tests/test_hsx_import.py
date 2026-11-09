"""Run in an isolated profile: blender -b --factory-startup --python tests/test_hsx_import.py -- [personal.hsx]."""

import sys
from pathlib import Path
import tempfile
import unittest

import bpy
import addon_utils

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import hsx_import as hsx

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
            self.assertEqual(bpy.ops.max.hsx_settings(op=operation, amount=0.2, segments=1, cuts=1), {"FINISHED"})
            self.assertEqual(len(bmesh.from_edit_mesh(bpy.context.object.data).faces), want_faces)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_plane_add()
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        self.assertEqual(bpy.ops.max.hsx_settings(op="EXTRUDE", amount=0.75), {"FINISHED"})
        mesh = bmesh.from_edit_mesh(bpy.context.object.data)
        # Blender's region extrusion retains the base of an isolated plane.
        self.assertEqual(len(mesh.faces), 6)
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
result = unittest.TextTestRunner(verbosity=2).run(suite)
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
