"""Run with the isolated Blender run_checks.py launcher."""
import unittest

import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import operators, prims, ui_panel, hsx_import


class ConvertPolyTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        from notuodesk_3ds_maxxed import create
        self.ob = create.new_object(bpy.context, 'Box001', bpy.data.meshes.new('Box'))
        prims.set_params(self.ob, 'BOX', length=3, width=4, height=5)
        bpy.context.window_manager.max_cmd_tab = 'MODIFY'

    def test_unconverted_primitive_refuses_every_level(self):
        for level in range(1, 6):
            result = bpy.ops.max.subobject(level=level)
            self.assertEqual(result, {'CANCELLED'}, level)
            self.assertEqual(self.ob.mode, 'OBJECT')
            self.assertEqual(self.ob.max_prim.kind, 'BOX')
        self.assertTrue(ui_panel.parameter_visible(bpy.context))
        self.assertFalse(ui_panel.is_poly(bpy.context))

    def test_conversion_enables_rollouts_and_preserves_geometry(self):
        self.assertEqual(bpy.ops.max.object_cmd(cmd='CONVERT_POLY'), {'FINISHED'})
        self.assertEqual(self.ob.max_prim.kind, '')
        for level in range(1, 6):
            self.assertEqual(bpy.ops.max.subobject(level=level), {'FINISHED'})
            self.assertEqual(operators.current_level(bpy.context), level)
            self.assertTrue(ui_panel.is_poly(bpy.context))
            panel = getattr(bpy.types, 'MAX_PT_poly_level_' + str(level))
            self.assertTrue(panel.poll(bpy.context))

    def test_native_edit_entry_is_returned_to_object_mode(self):
        from notuodesk_3ds_maxxed import mode_feedback
        bpy.ops.object.mode_set(mode='EDIT')
        mode_feedback.refresh()
        self.assertEqual(self.ob.mode, 'OBJECT')
        self.assertEqual(self.ob.max_prim.kind, 'BOX')

    def test_base_parameters_survive_a_real_modifier_until_conversion(self):
        bpy.ops.max.add_modifier(kind='SIMPLE_DEFORM:BEND|Bend')
        self.ob.max_prim.height = 9
        self.assertEqual(self.ob.max_prim.kind, 'BOX')
        bpy.ops.max.modifier_set_active(name='')
        self.assertEqual(ui_panel.base_name(self.ob), 'Box')
        self.assertTrue(ui_panel.parameter_visible(bpy.context))
        self.assertAlmostEqual(max(v.co.z for v in self.ob.data.vertices), 9)
        bpy.ops.max.object_cmd(cmd='CONVERT_POLY')
        self.assertEqual(len(self.ob.modifiers), 0)
        self.assertEqual(self.ob.max_prim.kind, '')
        self.assertTrue(ui_panel.is_poly(bpy.context))

    def test_new_hsx_three_actions_resolve(self):
        entries = hsx_import.parse_hsx('''<MaxHotkeyTransformations>
          <Assign_Hotkey Shortcut="Shift+E" Description="Edit Poly Modifier" Id="647394-EditPolyMod`Modifiers"/>
          <Assign_Hotkey Shortcut="Ctrl+Alt+E" Description="Editable Poly" Id="647394-MePoly`RappaTools3"/>
          <Assign_Hotkey Shortcut="Ctrl+Alt+Shift+E" Description="Export Selected" Id="0-40373"/>
        </MaxHotkeyTransformations>''')
        bindings, unmapped = hsx_import.build_bindings(entries)
        self.assertFalse(unmapped)
        self.assertEqual([(op, props) for _, _, op, props in bindings], [
            ('max.add_modifier', {'kind': 'EDIT_POLY|Edit Poly'}),
            ('max.object_cmd', {'cmd': 'CONVERT_POLY'}),
            ('export_scene.fbx', {'use_selection': True})])

    def test_full_stack_collapse_matches_viewport_evaluation(self):
        from notuodesk_3ds_maxxed import modifier_ui
        bpy.ops.max.add_modifier(kind='SYMMETRY')
        bpy.ops.max.add_modifier(kind='TURBOSMOOTH')
        shell = modifier_ui.add_modifier(self.ob, 'SHELL')
        shell.thickness = 20
        shell.show_viewport = False
        bpy.context.view_layer.update()
        evaluated = self.ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        expected = [tuple(v.co) for v in mesh.vertices]
        faces = len(mesh.polygons)
        evaluated.to_mesh_clear()
        self.assertGreater(len(expected), 8)
        self.assertEqual(bpy.ops.max.object_cmd(cmd='CONVERT_POLY'), {'FINISHED'})
        self.assertEqual(len(self.ob.modifiers), 0)
        self.assertEqual(len(modifier_ui.stack_rows(self.ob)), 1)
        self.assertEqual(len(self.ob.data.polygons), faces)
        self.assertEqual(len(self.ob.data.vertices), len(expected))
        for actual, wanted in zip(self.ob.data.vertices, expected):
            self.assertLess((actual.co - __import__('mathutils').Vector(wanted)).length, 1e-6)

    def test_reusable_collapse_function(self):
        self.assertEqual(operators.convert_to_editable_poly(bpy.context), {'FINISHED'})
        self.assertEqual(self.ob.max_prim.kind, '')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ConvertPolyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
