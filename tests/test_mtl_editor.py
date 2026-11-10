"""Compact material contracts in an isolated Blender process."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import bpy
import addon_utils

sys.path.insert(0, str(Path(__file__).parent))
addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import mtl_editor as mtl, max_editor_windows as editors


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.context = bpy.context
        editor = self.context.scene.max_mtl_editor
        editor.slots.clear()
        editor.active = 0
        editor.visible = '6'
        mtl.ensure_slots(self.context.scene)
        self.material = mtl.active_material(self.context)

    def test_initial_slots_and_every_grid_preserve_saved_extras(self):
        editor = mtl.state(self.context)
        self.assertEqual(len(editor.slots), 24)
        self.assertEqual(editor.visible, '6')
        self.assertEqual((self.material.max_spec_level, self.material.max_glossiness), (0, 10))
        self.assertFalse(self.material.max_two_sided)
        for visible, shape in [('6', (3, 2)), ('15', (5, 3)), ('24', (6, 4))]:
            editor.visible = visible
            self.assertEqual(mtl.grid_shape(editor), shape)
        extra = editor.slots.add()
        extra.material = self.material
        editor.visible = 'ALL'
        mtl.ensure_slots(self.context.scene)
        self.assertEqual(len(editor.slots), 25)
        self.assertEqual(mtl.grid_shape(editor), (6, 5))
        self.assertEqual(editor.slots[24].material, self.material)

    def test_computed_fields_write_to_rendered_shader(self):
        material = self.material
        material.max_diffuse = (.1, .2, .3)
        material.max_specular = (.6, .7, .8)
        material.max_spec_level = 72
        material.max_glossiness = 85
        material.max_opacity = 41
        material.max_ior = 1.72
        material.max_two_sided = False
        node = mtl.shader(material)
        self.assertAlmostEqual(node.inputs['Base Color'].default_value[1], .2)
        self.assertAlmostEqual(node.inputs['Specular Tint'].default_value[2], .8)
        self.assertAlmostEqual(node.inputs['Specular IOR Level'].default_value, .72)
        self.assertAlmostEqual(node.inputs['Roughness'].default_value, .15)
        self.assertAlmostEqual(node.inputs['Alpha'].default_value, .41)
        self.assertAlmostEqual(node.inputs['IOR'].default_value, 1.72)
        self.assertTrue(material.use_backface_culling)
        self.assertEqual((material.max_spec_level, material.max_glossiness, material.max_opacity), (72, 85, 41))

    def test_self_illumination_controls_change_rendered_emission(self):
        self.material.max_std.self_illum_color_on = True
        self.material.max_std.self_illum_color = (.2, .6, .8)
        self.material.max_std.self_illum_amount = 50
        node = mtl.shader(self.material)
        self.assertAlmostEqual(node.inputs['Emission Color'].default_value[2], .8)
        self.assertAlmostEqual(node.inputs['Emission Strength'].default_value, .5)

    def test_slot_selection_never_assigns_and_clear_preserves_assigned_material(self):
        obj = bpy.context.scene.objects.get('Cube')
        self.assertTrue(mtl.assign_material(obj, self.material))
        before = obj.active_material
        self.assertEqual(bpy.ops.max.mtl_slot(index=1), {'FINISHED'})
        self.assertEqual(obj.active_material, before)
        self.assertEqual(bpy.ops.max.mtl_reset_slots(), {'FINISHED'})
        self.assertEqual(obj.active_material, before)
        self.assertIn(before.name, bpy.data.materials)
        self.assertNotEqual(mtl.state(self.context).slots[0].material, before)

    def test_make_copy_keeps_scene_instance(self):
        obj = bpy.context.scene.objects.get('Cube')
        mtl.assign_material(obj, self.material)
        self.assertEqual(bpy.ops.max.mtl_make_unique(), {'FINISHED'})
        copy = mtl.active_material(self.context)
        self.assertNotEqual(copy, self.material)
        self.assertEqual(obj.active_material, self.material)
        copy.max_diffuse = (1, 0, 0)
        self.assertAlmostEqual(self.material.max_diffuse[0], .5)

    def test_every_map_channel_blank_enabled_disabled_cleared(self):
        image = bpy.data.images.new('Map fixture', width=4, height=4)
        for channel in mtl.MAP_INFO:
            with self.subTest(channel=channel):
                self.assertEqual(mtl.map_badge(self.material, channel), '')
                node = mtl.set_map(self.material, channel, image)
                self.assertEqual(node.name, 'MaxMap_' + channel)
                self.assertEqual(mtl.map_badge(self.material, channel), 'M')
                mtl.set_map_enabled(self.material, channel, False)
                self.assertEqual(mtl.map_badge(self.material, channel), 'm')
                self.assertEqual(node.image, image)
                mtl.set_map_enabled(self.material, channel, True)
                self.assertEqual(mtl.map_badge(self.material, channel), 'M')
                mtl.clear_map(self.material, channel)
                self.assertEqual(mtl.map_badge(self.material, channel), '')
                self.assertIn(image.name, bpy.data.images)

    def test_map_amount_and_disable_do_not_destroy_original_connection(self):
        shader = mtl.shader(self.material)
        original = self.material.node_tree.nodes.new('ShaderNodeRGB')
        self.material.node_tree.links.new(original.outputs[0], shader.inputs['Base Color'])
        image = bpy.data.images.new('Diffuse fixture', width=4, height=4)
        mtl.set_map(self.material, 'DIFFUSE', image)
        mix = shader.inputs['Base Color'].links[0].from_node
        self.assertEqual(mix.inputs[1].links[0].from_node, original)
        mtl.set_map_amount(self.material, 'DIFFUSE', 37)
        self.assertAlmostEqual(mix.inputs[0].default_value, .37)
        mtl.set_map_enabled(self.material, 'DIFFUSE', False)
        self.assertEqual(mix.inputs[0].default_value, 0)
        mtl.clear_map(self.material, 'DIFFUSE')
        self.assertEqual(shader.inputs['Base Color'].links[0].from_node, original)

    def test_gloss_map_inverts_and_bump_uses_normal_adapter(self):
        image = bpy.data.images.new('Gloss fixture', width=4, height=4)
        mtl.set_map(self.material, 'GLOSSINESS', image)
        self.assertIn('MaxMap_GLOSSINESS_Invert', self.material.node_tree.nodes)
        mtl.set_map(self.material, 'BUMP', image)
        self.assertIn('MaxMap_BUMP_Bump', self.material.node_tree.nodes)
        self.material.max_std.bump_amount = 45
        self.assertAlmostEqual(self.material.node_tree.nodes['MaxMap_BUMP_Bump'].inputs['Distance'].default_value, .45)

    def test_unsupported_maps_stay_unconnected(self):
        image = bpy.data.images.new('Stored map', width=4, height=4)
        for channel in ['AMBIENT', 'DISPLACEMENT']:
            node = mtl.set_map(self.material, channel, image)
            self.assertFalse(mtl.map_supported(self.material, channel))
            self.assertFalse(any(socket.is_linked for socket in node.outputs))

    def test_missing_image_load_is_atomic_and_keeps_existing_map(self):
        image = bpy.data.images.new('Retained image', width=4, height=4)
        mtl.set_map(self.material, 'DIFFUSE', image)
        result = bpy.ops.max.mtl_load_map(channel='DIFFUSE', filepath='Z:/missing-w2e/absent.png')
        self.assertEqual(result, {'CANCELLED'})
        self.assertEqual(mtl.map_node(self.material, 'DIFFUSE').image, image)

    def test_deferred_actions_keep_original_material_and_reject_scene_change(self):
        operator = SimpleNamespace()
        mtl._capture_target(operator, self.context)
        mtl.state(self.context).active = 3
        self.assertEqual(mtl._resolve_target(operator, self.context), self.material)
        other_scene = bpy.data.scenes.new('Deferred material scene')
        self.assertIsNone(mtl._resolve_target(operator, SimpleNamespace(scene=other_scene)))
        bpy.data.materials.remove(self.material, do_unlink=True)
        self.assertIsNone(mtl._resolve_target(operator, self.context))

    def test_get_material_popup_keeps_original_slot(self):
        editor = mtl.state(self.context)
        original = editor.slots[3].material
        operator = SimpleNamespace(material=self.material.name,
            _source_scene=self.context.scene, _source_slot=0)
        editor.active = 3
        self.assertEqual(mtl.MAX_OT_mtl_get.execute(operator, self.context), {'FINISHED'})
        self.assertEqual(editor.slots[3].material, original)
        self.assertEqual(editor.slots[0].material, self.material)

    def test_deferred_type_dialog_does_not_edit_the_new_active_slot(self):
        operator = SimpleNamespace(kind='PHYSICAL')
        mtl._capture_target(operator, self.context)
        editor = mtl.state(self.context)
        editor.active = 3
        other = editor.slots[3].material
        self.assertEqual(mtl.MAX_OT_mtl_set_type.execute(operator, self.context), {'FINISHED'})
        self.assertEqual(self.material['max_type'], 'PHYSICAL')
        self.assertEqual(other['max_type'], 'STANDARD')

    def test_bump_amount_uses_the_saved_bump_parameter(self):
        image = bpy.data.images.new('Bump amount fixture', width=4, height=4)
        mtl.set_map(self.material, 'BUMP', image)
        mtl.set_map_amount(self.material, 'BUMP', 120)
        self.assertAlmostEqual(self.material.max_std.bump_amount, 120)
        self.assertAlmostEqual(self.material.node_tree.nodes['MaxMap_BUMP_Bump'].inputs['Distance'].default_value, 1.2)

    def test_missing_on_disk_image_remains_in_saved_material(self):
        image = bpy.data.images.new('Missing on disk', width=4, height=4)
        image.filepath = 'Z:/missing-w2e/map.png'
        mtl.set_map(self.material, 'OPACITY', image)
        mtl.invalidate_preview()
        self.assertEqual(mtl.map_badge(self.material, 'OPACITY'), 'M')
        self.assertEqual(mtl.map_node(self.material, 'OPACITY').image, image)

    def test_deleted_active_material_is_empty_without_scene_assignment(self):
        bpy.data.materials.remove(self.material, do_unlink=True)
        self.assertIsNone(mtl.active_material(self.context))
        mtl.ensure_slots(self.context.scene)
        self.assertIsNone(mtl.active_material(self.context))

    def test_library_roundtrip_retains_maps_and_material_fields(self):
        image = bpy.data.images.new('Library image', width=4, height=4)
        mtl.set_map(self.material, 'DIFFUSE', image)
        mtl.set_map_enabled(self.material, 'DIFFUSE', False)
        self.material.max_glossiness = 61
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'materials.blend')
            self.assertEqual(bpy.ops.max.mtl_put_library(filepath=path), {'FINISHED'})
            name = self.material.name
            with bpy.data.libraries.load(path, link=False) as (source, target):
                self.assertIn(name, source.materials)
                target.materials = [name]
            restored = target.materials[0]
            self.assertEqual(restored.max_glossiness, 61)
            self.assertEqual(mtl.map_badge(restored, 'DIFFUSE'), 'm')

    def test_ordinary_material_classification_is_read_only(self):
        material = bpy.data.materials.new('Unclassified')
        before = dict(material.items())
        before_shader = mtl.shader(material)
        self.assertEqual(mtl.material_kind(material), 'STANDARD')
        self.assertEqual(dict(material.items()), before)
        self.assertEqual(mtl.shader(material), before_shader)

    def test_custom_surface_is_not_silently_replaced(self):
        tree = self.material.node_tree
        emission = tree.nodes.new('ShaderNodeEmission')
        output = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
        tree.links.new(emission.outputs[0], output.inputs['Surface'])
        self.assertIsNone(mtl.shader(self.material, create=True))
        self.material.max_glossiness = 20
        self.assertEqual(output.inputs['Surface'].links[0].from_node, emission)

    def test_editor_routes_use_one_service(self):
        from notuodesk_3ds_maxxed import operators
        calls = []
        with patch.object(editors, 'open_editor', side_effect=lambda ctx, kind: calls.append(kind) or object()):
            for kind in operators.EDITORS:
                self.assertEqual(bpy.ops.max.open_editor(editor=kind), {'FINISHED'})
        self.assertEqual(calls, list(operators.EDITORS))

    def test_picker_disable_restores_cursor_and_invalidates_session(self):
        picker = SimpleNamespace(_done=False, _windows=())
        mtl._pickers.append(picker)
        before = mtl._generation
        mtl.clear_runtime()
        self.assertTrue(picker._done)
        self.assertFalse(mtl._pickers)
        self.assertEqual(mtl._generation, before+1)

    def test_disable_cancels_debounced_preview_work(self):
        mtl._preview_hosts.add(123)
        mtl._preview_requests.add(self.material.as_pointer())
        bpy.app.timers.register(mtl._render_previews, first_interval=10)
        mtl.clear_runtime()
        self.assertFalse(mtl._preview_hosts)
        self.assertFalse(mtl._preview_requests)
        self.assertFalse(bpy.app.timers.is_registered(mtl._render_previews))

    def test_public_identifiers_and_toolbar_policy(self):
        self.assertEqual(set(mtl.MAP_INFO), {'AMBIENT', 'DIFFUSE', 'SPECULAR_COLOR', 'SPECULAR_LEVEL',
            'GLOSSINESS', 'SELF_ILLUM', 'OPACITY', 'FILTER', 'BUMP', 'REFLECTION', 'REFRACTION', 'DISPLACEMENT'})
        for name in ['slot', 'get', 'assign', 'reset', 'make_unique', 'put_library', 'select_by',
                     'show_in_viewport', 'set_type', 'load_map', 'clear_map', 'pick', 'reset_slots',
                     'add_slot', 'get_scene', 'drop', 'drag']:
            self.assertTrue(getattr(bpy.ops.max, 'mtl_'+name).get_rna_type())
        self.assertNotIn('max.mtl_drag', [op for op, key, fallback in mtl.TOOLBAR])
        self.assertNotIn('max.mtl_add_slot', [op for op, key, fallback in mtl.TOOLBAR])


if __name__ == '__main__':
    unittest.main(argv=[__file__])
