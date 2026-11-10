"""Background editor contract and supported relationship model."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from _w15_setup import bpy, box, empty_scene
from notuodesk_3ds_maxxed import max_editor_windows as editors
editors.install()


class EditorTests(unittest.TestCase):
    def test_detached_editor_listener_preserves_the_next_click(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        listener = SimpleNamespace(_pointer=0, _area_pointer=0)
        with patch.dict(editors._hosts, {}, clear=True), patch.dict(editors._docked, {}, clear=True):
            self.assertEqual(editors.MAX_OT_editor_interact.modal(listener, None, None),
                             {"FINISHED", "PASS_THROUGH"})

    def test_registered_editor_dialog_fields(self):
        fields = bpy.ops.max.render_setup_dialog.get_rna_type().properties
        self.assertIn("engine", fields)
        self.assertIn("format", fields)
        self.assertIn(bpy.context.scene.render.engine, [item[0] for item in editors.renderer_items(bpy.context)])
        self.assertFalse(editors.attach_explorer(bpy.context, None))

    def test_render_settings_apply_and_invalid_range_is_atomic(self):
        scene = bpy.context.scene
        result = bpy.ops.max.render_setup_dialog(width=800, height=600, percentage=75,
            start=1, end=10, output="//render/", engine=scene.render.engine, format="PNG")
        self.assertEqual(result, {"FINISHED"})
        self.assertEqual((scene.render.resolution_x, scene.render.resolution_y), (800, 600))
        self.assertEqual((scene.frame_start, scene.frame_end), (1, 10))
        result = bpy.ops.max.render_setup_dialog(start=20, end=10, engine=scene.render.engine, format="PNG")
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual((scene.frame_start, scene.frame_end), (1, 10))

    def test_environment_rejects_connected_color_without_writes(self):
        scene = bpy.context.scene
        world = bpy.data.worlds.new("Connected environment")
        world.use_nodes = True
        scene.world = world
        background = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
        rgb = world.node_tree.nodes.new("ShaderNodeRGB")
        world.node_tree.links.new(rgb.outputs[0], background.inputs["Color"])
        before = scene.view_settings.exposure
        result = bpy.ops.max.environment_dialog(color=(1, 0, 0), exposure=2)
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(scene.view_settings.exposure, before)

    def test_relationship_graph_and_backend_unavailable(self):
        empty_scene()
        a, b = box("Parent"), box("Child")
        b.parent = a
        nodes, edges = editors.relationships(bpy.context.scene)
        self.assertEqual({n.name for n in nodes}, {"Parent", "Child"})
        self.assertIn((a, b, "Parent"), edges)
        self.assertIsNone(editors.open_editor(bpy.context, "SCHEMATIC"))
        editors.close_all()
        self.assertEqual(editors.owned_windows(), [])

    def test_no_material_host_without_integrator(self):
        from unittest.mock import patch
        with patch.object(editors, '_material_adapter', None):
            self.assertFalse(editors.available("MATERIAL"))
        self.assertIn("Python", editors.TITLES["SCRIPT_EDITOR"])
        self.assertIn("Python", editors.TITLES["LISTENER"])

    def test_registration_repeated_and_saved_scene_unchanged(self):
        units = bpy.context.scene.unit_settings.scale_length
        frame = bpy.context.scene.frame_end
        editors.install()
        editors.uninstall()
        editors.uninstall()
        editors.install()
        self.assertEqual(bpy.context.scene.unit_settings.scale_length, units)
        self.assertEqual(bpy.context.scene.frame_end, frame)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
