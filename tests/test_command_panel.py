"""Run in an isolated Blender process through run_checks.py."""
import unittest
import os
from pathlib import Path
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import command_panel_ui as host, ui_panel as ui, modifier_ui, symmetry


class CommandPanelTests(unittest.TestCase):
    def setUp(self):
        host.clear_runtime()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_registry_and_seven_categories(self):
        self.assertEqual([item[0] for item in ui.CREATE_CATS],
                         ['GEOMETRY', 'SHAPES', 'LIGHTS', 'CAMERAS', 'HELPERS', 'SPACE_WARPS', 'SYSTEMS'])
        ids = [cls.__name__ for cls in ui.ROLLOUTS]
        self.assertEqual(len(ids), len(set(ids)))
        required = {'MAX_PT_' + suffix for suffix in (
            'create_object_type', 'create_name_color', 'creation_method', 'keyboard_entry_rollout',
            'parameters', 'loft_creation', 'loft_skin', 'loft_surface', 'loft_path', 'loft_deformations',
            'poly_selection', 'poly_edit_geometry', 'hier_pivot', 'hier_transform', 'hier_link',
            'motion_anim', 'motion_editors', 'motion_traj', 'disp_hide', 'disp_freeze', 'disp_props',
            'util_main', 'util_maxxed', 'draw_method', 'draw_keyboard')}
        required |= {'MAX_PT_poly_level_' + str(level) for level in range(1, 6)}
        self.assertLessEqual(required, set(ids))
        self.assertTrue(all(cls.bl_parent_id == 'MAX_PT_command_panel' for cls in ui.ROLLOUTS))

    def test_stack_uses_real_indices_and_nurms_base(self):
        bend = modifier_ui.add_modifier(self.ob, 'BEND')
        self.ob.modifiers.active = bend
        self.assertEqual(ui._stack_get(self.ob), 0)
        self.ob.max_poly.nurms = True
        nurms = next(m for m in self.ob.modifiers if m.name.startswith('NURMS'))
        self.ob.modifiers.active = nurms
        self.assertEqual(ui._stack_get(self.ob), -1)
        self.ob.max_stack_index = 0
        self.assertEqual(ui._stack_get(self.ob), 0)

    def test_rollout_toggle_keeps_workspace_state(self):
        identifier = 'MAX_PT_poly_selection'
        key = '_max_rollout_' + identifier
        workspace = bpy.context.workspace
        try:
            if key in workspace:
                del workspace[key]
            self.assertEqual(bpy.ops.max.rollout_toggle(identifier=identifier), {'FINISHED'})
            self.assertTrue(workspace[key])
            self.assertEqual(bpy.ops.max.rollout_toggle(identifier=identifier), {'FINISHED'})
            self.assertFalse(workspace[key])
            self.assertTrue(all('HIDE_HEADER' in cls.bl_options for cls in ui.ROLLOUTS))
        finally:
            if key in workspace:
                del workspace[key]

    def test_pin_and_end_result_restore(self):
        a = modifier_ui.add_modifier(self.ob, 'BEND')
        b = modifier_ui.add_modifier(self.ob, 'SHELL')
        self.ob.modifiers.active = a
        self.assertEqual(bpy.ops.max.command_stack(action='PIN'), {'FINISHED'})
        pinned = self.ob
        bpy.ops.mesh.primitive_cube_add()
        self.assertEqual(host.object_for(bpy.context), pinned)
        self.assertEqual(bpy.ops.max.command_stack(action='END_RESULT'), {'FINISHED'})
        self.assertFalse(b.show_viewport)
        host.clear_runtime()
        self.assertTrue(b.show_viewport)
        self.assertEqual(host.object_for(bpy.context), bpy.context.object)

    def test_symmetry_remove_uses_owner_route(self):
        mod = symmetry.add(self.ob)
        self.ob.modifiers.active = mod
        self.assertEqual(bpy.ops.max.command_stack(action='REMOVE'), {'FINISHED'})
        self.assertEqual(len(self.ob.modifiers), 0)

    def test_z_rollout_state_survives_save_open(self):
        key = '_max_rollout_MAX_PT_poly_selection'
        name = bpy.context.workspace.name
        bpy.context.workspace[key] = True
        path = Path(os.environ['MAXXED_OUT']) / 'rollout-state.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.context.workspace[key] = False
        bpy.ops.wm.open_mainfile(filepath=str(path))
        self.assertTrue(bpy.data.workspaces[name][key])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommandPanelTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
