"""Run through the isolated run_checks.py launcher, tests test_mode_feedback."""
import unittest
import addon_utils
import bpy
import bmesh

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)

class ModeFeedbackTests(unittest.TestCase):
    def test_refresh_waits_when_shutdown_removes_selection_context(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from notuodesk_3ds_maxxed import mode_feedback as mf, operators
        ctx = SimpleNamespace(mode='OBJECT', window_manager=SimpleNamespace(
            max_sublevel=0, windows=[]))
        with patch.object(mf, 'bpy', SimpleNamespace(context=ctx, data=bpy.data)), \
             patch.object(mf, 'level', return_value=0), \
             patch.object(operators, 'sync_sublevel') as sync:
            self.assertEqual(mf.refresh(), .1)
            sync.assert_not_called()

    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()

    def test_deleted_hover_object_is_cleared(self):
        from types import SimpleNamespace
        from notuodesk_3ds_maxxed import mode_feedback as mf
        ob = bpy.context.object
        key = bpy.context.window.as_pointer()
        pointer = SimpleNamespace(window=bpy.context.window, hit=ob)
        mf._pointers[key] = pointer
        bpy.data.objects.remove(ob, do_unlink=True)
        try:
            self.assertIs(mf.pointer_state(key), pointer)
            self.assertIsNone(pointer.hit)
        finally:
            mf._pointers.pop(key, None)

    def test_null_modal_entry_keeps_actual_tool(self):
        from types import SimpleNamespace
        from notuodesk_3ds_maxxed import mode_feedback as mf
        ctx = SimpleNamespace(mode='OBJECT',
            window=SimpleNamespace(as_pointer=lambda: 0, modal_operators=[None]),
            workspace=SimpleNamespace(tools=SimpleNamespace(
                from_space_view3d_mode=lambda *args, **kw: SimpleNamespace(idname='max.rotate'))))
        self.assertEqual(mf.active_tool(ctx), 'ROTATE')

    def test_null_modal_entry_keeps_status_prompt(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from notuodesk_3ds_maxxed import mode_feedback as mf
        labels = []
        layout = SimpleNamespace(label=lambda **kw: labels.append(kw['text']), separator_spacer=lambda: None)
        ctx = SimpleNamespace(workspace=SimpleNamespace(name='3ds Max'),
                              window=SimpleNamespace(modal_operators=[None]))
        with patch.object(mf, 'active_tool', return_value='ROTATE'), \
             patch.object(mf, 'prompt_text', return_value='Rotate prompt'):
            mf.draw_status(SimpleNamespace(layout=layout), ctx,
                           lambda *_: self.fail('null modal suppressed feedback'), lambda *_: None)
        self.assertEqual(labels, ['Rotate prompt'])

    def test_base_stack_click_leaves_subobject(self):
        bpy.ops.max.subobject(level=2)
        bpy.ops.max.modifier_set_active(name='')
        self.assertEqual(bpy.context.mode, 'OBJECT')

    def test_exit_and_bracket_shortcuts(self):
        from notuodesk_3ds_maxxed.keymap import VIEWPORT
        self.assertTrue(any(k[0]=='max.subobject' and k[1]=='B' and k[3] and k[6].get('level')==0 for k in VIEWPORT))
        self.assertTrue(any(k[0]=='max.selection_brackets' and k[1]=='J' for k in VIEWPORT))

    def test_level_and_selection_summary_follow_real_mode(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        for lev, expected in ((1,'8 Vertices Selected'), (2,'12 Edges Selected'),
                              (3,'12 Edges Selected'), (4,'6 Polygons Selected'),
                              (5,'6 Polygons Selected')):
            bpy.ops.max.subobject(level=lev)
            self.assertEqual(mf.level(bpy.context), lev)
            self.assertEqual(mf.selection_text(bpy.context), expected)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(mf.level(bpy.context), 0)
        self.assertEqual(mf.selection_text(bpy.context), '1 Object Selected')
        bpy.ops.object.select_all(action='DESELECT')
        self.assertEqual(mf.selection_text(bpy.context), 'None Selected')

    def test_hidden_subobjects_do_not_count(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=1)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.verts.ensure_lookup_table()
        for vert in bm.verts:
            vert.select_set(False)
        bm.verts[0].select_set(True)
        self.assertEqual(mf.selection_text(bpy.context), '1 Vertex Selected')
        self.assertEqual(mf.rollout_selection_text(bpy.context), 'Vertex 1 Selected')
        bm.verts[0].hide_set(True)
        self.assertEqual(mf.selection_text(bpy.context), '0 Vertices Selected')

    def test_status_and_rollout_share_one_selection_scan(self):
        from unittest.mock import patch
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=1)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        for vert in bm.verts:
            vert.select_set(False)
        bm.verts.ensure_lookup_table()
        bm.verts[0].select_set(True)
        bmesh.update_edit_mesh(bpy.context.object.data)
        bpy.context.view_layer.update()
        # Count the real component iteration, including the single-ID rollout.
        scans = []
        original = bmesh.from_edit_mesh
        # current_level also reads the edit mesh once saved level data is added.
        # Only track iterations using the BMVertSeq iterator, not metadata reads.
        class CountedSequence:
            def __init__(self, seq):
                self.seq = seq
            def __iter__(self):
                scans.append(True)
                return iter(self.seq)
            def __getattr__(self, name):
                return getattr(self.seq, name)
        class MeshProxy:
            def __init__(self, bm):
                self.verts = CountedSequence(bm.verts)
                self.edges, self.faces = bm.edges, bm.faces
        with patch.object(bmesh, 'from_edit_mesh', side_effect=lambda mesh: MeshProxy(original(mesh))):
            self.assertEqual(mf.selection_text(bpy.context), '1 Vertex Selected')
            self.assertEqual(mf.rollout_selection_text(bpy.context), 'Vertex 1 Selected')
            self.assertEqual(mf.rollout_selection_text(bpy.context), 'Vertex 1 Selected')
        self.assertLessEqual(len(scans), 1, 'status and rollout repeatedly walked the edit mesh')

    def test_selection_summary_changes_after_mesh_update(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=1)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.verts.ensure_lookup_table()
        for vert in bm.verts:
            vert.select_set(False)
        bm.verts[0].select_set(True)
        bmesh.update_edit_mesh(bpy.context.object.data)
        bpy.context.view_layer.update()
        self.assertEqual(mf.rollout_selection_text(bpy.context), 'Vertex 1 Selected')
        bm.verts[0].select_set(False)
        bm.verts[1].select_set(True)
        bmesh.update_edit_mesh(bpy.context.object.data)
        bpy.context.view_layer.update()
        self.assertEqual(mf.rollout_selection_text(bpy.context), 'Vertex 2 Selected')

    def test_panel_change_leaves_edit_and_clears_level(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=4)
        bpy.context.window_manager.max_cmd_tab = 'CREATE'
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertEqual(mf.level(bpy.context), 0)

    def test_native_mode_change_overrides_stale_level(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=3)
        bpy.ops.mesh.select_mode(type='FACE')
        self.assertEqual(mf.level(bpy.context), 4)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(mf.level(bpy.context), 0)

    def test_saved_level_read_before_edit_bmesh_is_ready(self):
        from notuodesk_3ds_maxxed.operators import stored_mesh_level
        bpy.ops.max.subobject(level=3)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(stored_mesh_level(bpy.context.object), 3)

    def test_native_mode_change_does_not_revive_old_border(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        bpy.ops.max.subobject(level=3)
        bpy.ops.mesh.select_mode(type='FACE')
        mf.refresh()
        bpy.ops.mesh.select_mode(type='EDGE')
        self.assertEqual(mf.level(bpy.context), 2)

    def test_level_storage_survives_an_empty_mesh(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        from notuodesk_3ds_maxxed.operators import stored_mesh_level
        bpy.ops.max.subobject(level=1)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete(type='VERT')
        bpy.ops.max.subobject(level=3)
        self.assertEqual(mf.level(bpy.context), 3)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(stored_mesh_level(bpy.context.object), 3)

    def test_multi_object_edit_stores_each_mesh_level(self):
        from notuodesk_3ds_maxxed.operators import stored_mesh_level
        first = bpy.context.object
        bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
        second = bpy.context.object
        first.select_set(True)
        bpy.ops.max.subobject(level=5)
        self.assertEqual(stored_mesh_level(first), 5)
        self.assertEqual(stored_mesh_level(second), 5)

    def test_tool_aliases_and_cursor_policy(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        for kind in ('MOVE','ROTATE','SCALE'):
            for prefix in ('builtin.', 'max.snap_', 'max.'):
                self.assertEqual(mf.tool_kind(prefix+kind.lower()), kind)
            self.assertEqual(mf.cursor_kind(kind, True, True), kind)
            self.assertEqual(mf.cursor_kind(kind, True, False), 'CROSSHAIR')
            self.assertEqual(mf.cursor_kind(kind, False, False), 'DEFAULT')
        for ident in ('builtin.select','builtin.select_box','builtin.select_circle','builtin.select_lasso'):
            self.assertEqual(mf.tool_kind(ident),'SELECT')
        self.assertEqual(mf.tool_kind('max.select_link'),'LINK')
        self.assertEqual(mf.tool_kind('builtin.knife'),'builtin.knife')

    def test_brackets_have_three_strokes_at_each_corner(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        points = mf.bracket_segments(bpy.context.object.bound_box)
        self.assertEqual(len(points),48)
        for a,b in zip(points[::2],points[1::2]):
            self.assertAlmostEqual((b-a).length,.36,places=5)

    def test_passive_chrome_keeps_status_prompt(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from notuodesk_3ds_maxxed import mode_feedback as mf
        labels = []
        layout = SimpleNamespace(label=lambda **kw: labels.append(kw['text']),
                                 separator_spacer=lambda: None)
        ctx = SimpleNamespace(workspace=SimpleNamespace(name='3ds Max'),
                              window=SimpleNamespace(modal_operators=[
                                  SimpleNamespace(bl_idname='MAX_OT_chrome_pointer')]))
        original = []
        with patch.object(mf, 'active_tool', return_value='MOVE'), \
             patch.object(mf, 'prompt_text', return_value='Move prompt'):
            mf.draw_status(SimpleNamespace(layout=layout), ctx,
                           lambda *_: original.append(True), lambda *_: None)
        self.assertEqual(labels, ['Move prompt'])
        self.assertEqual(original, [])
        ctx.window.modal_operators.append(SimpleNamespace(bl_idname='TRANSFORM_OT_translate'))
        mf.draw_status(SimpleNamespace(layout=layout), ctx,
                       lambda *_: original.append(True), lambda *_: None)
        self.assertEqual(original, [True])

    def test_brackets_toggle_without_selection_change(self):
        selected = tuple(bpy.context.selected_objects)
        initial = bpy.context.scene.max_selection_brackets
        bpy.ops.max.selection_brackets()
        self.assertEqual(bpy.context.scene.max_selection_brackets, not initial)
        self.assertEqual(tuple(bpy.context.selected_objects),selected)
        bpy.ops.max.selection_brackets()
        self.assertEqual(bpy.context.scene.max_selection_brackets, initial)

    def test_active_level_toggles_off(self):
        for lev in range(1,6):
            bpy.ops.max.subobject(level=lev)
            bpy.ops.max.subobject(level=lev)
            self.assertEqual(bpy.context.mode,'OBJECT')

    def test_modifier_stack_click_leaves_edit(self):
        ob=bpy.context.object
        mod=ob.modifiers.new('Bend','SIMPLE_DEFORM')
        bpy.ops.max.subobject(level=2)
        bpy.ops.max.modifier_set_active(name=mod.name)
        self.assertEqual(bpy.context.mode,'OBJECT')
        self.assertEqual(ob.modifiers.active, mod)

    def test_modifier_list_index_click_leaves_edit(self):
        from notuodesk_3ds_maxxed.ui_panel import _stack_set
        ob=bpy.context.object
        mod=ob.modifiers.new('Bend','SIMPLE_DEFORM')
        bpy.ops.max.subobject(level=2)
        _stack_set(ob,0)
        self.assertEqual(bpy.context.mode,'OBJECT')
        self.assertEqual(ob.modifiers.active,mod)

    def test_nathan_blue_stack_theme_and_blue_buttons(self):
        from notuodesk_3ds_maxxed import theme
        theme.apply_theme()
        ui=bpy.context.preferences.themes[0].user_interface
        # Nathan video 2, event 6, TurboSmooth active-row interior.
        for actual, expected in zip(ui.wcol_list_item.inner_sel, (100/255,138/255,187/255,1)):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertEqual(tuple(ui.wcol_list_item.text_sel), (1,1,1))
        self.assertGreater(ui.wcol_tool.inner_sel[2],ui.wcol_tool.inner_sel[0])

    def test_link_preserves_world_and_rejects_cycles(self):
        from notuodesk_3ds_maxxed import mode_feedback as mf
        child=bpy.context.object
        child.location=(2,3,4)
        bpy.ops.mesh.primitive_cube_add(location=(-3,7,2))
        parent=bpy.context.object
        bpy.context.view_layer.update()
        original=child.matrix_world.copy()
        mf.link_objects([child],parent)
        bpy.context.view_layer.update()
        self.assertEqual(child.parent,parent)
        self.assertLess(sum(abs(child.matrix_world[i][j]-original[i][j]) for i in range(4) for j in range(4)),1e-5)
        mf.link_objects([parent],child)
        self.assertIsNone(parent.parent)

if __name__ == '__main__':
    unittest.main(argv=['test_mode_feedback'], exit=False)
