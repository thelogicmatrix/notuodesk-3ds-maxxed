"""Run with run_checks.py tests test_workspace_commands in an isolated profile."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy
import bmesh
from mathutils import Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import operators as commands, ui_menus, max_chrome, mode_feedback


class WorkspaceCommands(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()

    def test_frozen_command_and_menu_ids(self):
        expected = {
            'max.subobject', 'max.set_view', 'max.zoom_extents', 'max.toggle',
            'max.expert_mode', 'max.select_all', 'max.delete', 'max.select_by_name',
            'max.clone', 'max.edit_poly', 'max.object_cmd', 'max.camera_from_view',
            'max.open_editor', 'max.transform_typein', 'max.add_modifier',
            'max.melt_preset', 'max.animate_melt', 'max.key_melt',
            'max.modifier_set_active', 'max.toggle_quad', 'max.adaptive_degradation',
            'max.set_key', 'max.group', 'max.set_workspace', 'max.apply',
            'max.restore', 'max.block_cursor',
        }
        self.assertEqual({c.bl_idname for c in commands.classes}, expected)
        self.assertEqual([c.__name__ for c in ui_menus.CATEGORY_MENUS],
                         [f'MAX_MT_modlist_{i}' for i in range(6)])
        self.assertIn('OCEAN|Ocean (Blender)', {v[0] for v in ui_menus._modifier_enum})
        self.assertNotIn('OCEAN|Ocean (Blender)', {v[0] for v in ui_menus._modifier_search_enum})
        self.assertEqual(commands.WS_NAME, '3ds Max')

    def test_geometry_and_children_survive_world_pivot(self):
        obj = bpy.context.object
        obj.location = (6, -2, 9)
        obj.rotation_euler = (.3, -.7, .4)
        obj.scale = (2, 3, 4)
        child = bpy.data.objects.new('Unselected child', None)
        bpy.context.collection.objects.link(child)
        child.parent = obj
        child.location = (2, 0, 1)
        bpy.context.view_layer.update()
        positions = [obj.matrix_world @ v.co for v in obj.data.vertices]
        world = child.matrix_world.copy()
        cursor = bpy.context.scene.cursor.location.copy()
        self.assertEqual(bpy.ops.max.object_cmd(cmd='PIVOT_TO_WORLD'), {'FINISHED'})
        bpy.context.view_layer.update()
        self.assertLess(obj.matrix_world.translation.length, 1e-5)
        for before, vert in zip(positions, obj.data.vertices):
            self.assertLess((before - obj.matrix_world @ vert.co).length, 1e-4)
        self.assertLess((world.translation - child.matrix_world.translation).length, 1e-4)
        self.assertEqual(cursor, bpy.context.scene.cursor.location)

    def test_align_world_preserves_pivot_and_scale(self):
        obj = bpy.context.object
        obj.location = (3, 7, -4)
        obj.rotation_euler = (.2, .8, -.4)
        obj.scale = (2, 3, 4)
        bpy.context.view_layer.update()
        position = obj.matrix_world.translation.copy()
        self.assertEqual(bpy.ops.max.workspace_align_world(), {'FINISHED'})
        bpy.context.view_layer.update()
        self.assertLess((obj.matrix_world.translation - position).length, 1e-5)
        self.assertLess(obj.matrix_world.to_quaternion().angle, 1e-5)
        self.assertLess((obj.matrix_world.to_scale() - Vector((2, 3, 4))).length, 1e-5)

    def test_group_is_distinct_from_layers_and_roundtrips_world(self):
        obj = bpy.context.object
        obj.location = (4, 5, 6)
        bpy.context.view_layer.update()
        original = obj.matrix_world.copy()
        bpy.ops.max.group(action='GROUP')
        self.assertTrue(obj.parent.get('max_group_head'))
        self.assertNotIn('max_layer_id', obj.parent)
        bpy.ops.max.group(action='UNGROUP')
        bpy.context.view_layer.update()
        self.assertIsNone(obj.parent)
        self.assertLess((obj.matrix_world.translation - original.translation).length, 1e-5)

    def test_snap_switches_are_independent(self):
        from notuodesk_3ds_maxxed import snaps
        settings = snaps.settings(bpy.context)
        bpy.context.scene.tool_settings.use_snap = False
        settings.angle_snap = settings.percent_snap = False
        bpy.ops.max.toggle(what='ANGLE_SNAP')
        self.assertTrue(settings.angle_snap)
        self.assertFalse(bpy.context.scene.tool_settings.use_snap)
        bpy.ops.max.toggle(what='PERCENT_SNAP')
        self.assertTrue(settings.percent_snap)
        self.assertFalse(bpy.context.scene.tool_settings.use_snap)

    def test_modifier_names_and_native_types_survive_dispatch(self):
        obj = bpy.context.object
        cases = [('SIMPLE_DEFORM:TWIST|Twist', 'Twist', 'SIMPLE_DEFORM'),
                 ('SUBSURF|OpenSubdiv', 'OpenSubdiv', 'SUBSURF'),
                 ('GN:SKEW|Skew', 'Skew', 'NODES'),
                 ('TURBOSMOOTH|TurboSmooth', 'TurboSmooth', 'SUBSURF'),
                 ('SYMMETRY|Symmetry', 'Symmetry', 'NODES')]
        for kind, name, backend in cases:
            self.assertEqual(bpy.ops.max.add_modifier(kind=kind), {'FINISHED'}, kind)
            self.assertEqual(obj.modifiers.active.name, name)
            self.assertEqual(obj.modifiers.active.type, backend)
        self.assertNotIn('_MAX Text Origin', obj.modifiers)
        self.assertEqual(bpy.ops.max.modifier_set_active(name=''), {'FINISHED'})
        self.assertIsNone(obj.modifiers.active)

    def test_delete_can_keep_isolated_vertices(self):
        bpy.ops.max.subobject(level=2)
        bpy.context.object.max_poly.delete_isolated = False
        before = len(bmesh.from_edit_mesh(bpy.context.object.data).verts)
        self.assertEqual(bpy.ops.max.delete(), {'FINISHED'})
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        self.assertEqual(len(bm.verts), before)
        self.assertEqual(len(bm.edges), 0)
        self.assertEqual(commands.current_level(bpy.context), 2)

    def test_new_poly_owner_gets_first_refusal(self):
        with patch.object(commands.editable_poly, 'run', return_value={'CANCELLED'}) as owner:
            self.assertEqual(bpy.ops.max.edit_poly(op='LOOP'), {'CANCELLED'})
            self.assertEqual(owner.call_args.args[2], 'EXEC_DEFAULT')

    def test_plain_poly_invocation_keeps_the_immediate_route(self):
        calls = []
        request = SimpleNamespace(op='EXTRUDE', run=lambda context, how: calls.append(how) or {'FINISHED'})
        result = commands.MAX_OT_edit_poly.invoke(request, bpy.context, SimpleNamespace(shift=False))
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(calls, ['INVOKE_DEFAULT'])

    def test_hide_by_name_is_a_hide_dialog(self):
        calls = []
        class Layout:
            def row(self, **kwargs):
                return self
            column = row
            def label(self, **kwargs):
                pass
            def separator(self):
                pass
            def menu(self, *args, **kwargs):
                pass
            def operator(self, idname, **kwargs):
                props = SimpleNamespace()
                calls.append((idname, kwargs.get('text'), props))
                return props
        ui_menus.MAX_MT_quad.draw(SimpleNamespace(layout=Layout()), bpy.context)
        route = next(c for c in calls if c[1] == 'Hide by Name...')
        self.assertEqual(route[0], 'max.scene_selection_dialog')
        self.assertTrue(route[2].hide)

    def test_offset_reads_the_existing_gizmo_owner(self):
        from notuodesk_3ds_maxxed import max_gizmos, max_rotate
        obj = bpy.context.object
        obj.location = (10, 20, 30)
        bpy.context.view_layer.update()
        start = obj.matrix_world.copy()
        transaction = SimpleNamespace(operation='MOVE', _owner_context=(bpy.context.window, None, None),
                                      matrices=[(obj, start)], meshes=[])
        obj.location += Vector((2, 3, 4))
        bpy.context.view_layer.update()
        with patch.object(mode_feedback, 'active_tool', return_value='MOVE'), \
             patch.object(max_gizmos, '_active', {123: transaction}):
            max_rotate.settings(bpy.context).move_reference = 'WORLD'
            self.assertEqual(commands.read_transform(bpy.context, True)[1], (2, 3, 4))

    def test_sublevel_identity_empty_mesh_and_native_mode_reconciliation(self):
        bpy.ops.max.subobject(level=3)
        self.assertEqual(commands.current_level(bpy.context), 3)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete(type='VERT')
        self.assertEqual(commands.stored_mesh_level(bpy.context.object), 3)
        bpy.ops.mesh.select_mode(type='FACE')
        commands.sync_sublevel(bpy.context)
        self.assertEqual(commands.current_level(bpy.context), 4)
        bpy.ops.mesh.select_mode(type='EDGE')
        self.assertEqual(commands.current_level(bpy.context), 2)

    def test_numeric_move_and_scale_use_reference_and_real_geometry(self):
        from notuodesk_3ds_maxxed import max_rotate
        with patch.object(mode_feedback, 'active_tool', return_value='MOVE'):
            max_rotate.settings(bpy.context).move_reference = 'WORLD'
            self.assertTrue(commands.write_transform(bpy.context, (3, 4, 5), False))
            self.assertEqual(commands.read_transform(bpy.context)[1], (3, 4, 5))
        with patch.object(mode_feedback, 'active_tool', return_value='SCALE'):
            max_rotate.settings(bpy.context).scale_reference = 'WORLD'
            self.assertTrue(commands.write_transform(bpy.context, (200, 300, 400), False))
            self.assertEqual(commands.read_transform(bpy.context)[1], (200, 300, 400))

    def test_scale_readout_rejects_an_ambiguous_frame(self):
        from notuodesk_3ds_maxxed import max_rotate
        obj = bpy.context.object
        obj.rotation_euler = (.2, .4, .7)
        obj.scale = (2, 3, 4)
        bpy.context.view_layer.update()
        settings = max_rotate.settings(bpy.context)
        with patch.object(mode_feedback, 'active_tool', return_value='SCALE'):
            settings.scale_reference = 'WORLD'
            self.assertIsNone(commands.read_transform(bpy.context)[1])
            settings.scale_reference = 'LOCAL'
            for value, expected in zip(commands.read_transform(bpy.context)[1], (200, 300, 400)):
                self.assertAlmostEqual(value, expected, places=3)

    def test_installation_is_single_and_restores_adapters(self):
        previous = tuple(max_chrome._originals)
        ui_menus.register_draw()
        self.assertEqual(tuple(max_chrome._originals), previous)
        self.assertEqual(len(max_chrome._keys), 7)
        self.assertEqual(len(ui_menus._installed_services), 5)


result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceCommands))
if not result.wasSuccessful():
    raise SystemExit(1)
print('W2A commands and installation PASS', flush=True)
