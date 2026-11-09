"""Run with run_checks.py tests test_max_chrome. No inherited implementation is inspected."""
import math
import unittest
from types import SimpleNamespace
import bpy
from mathutils import Matrix
from notuodesk_3ds_maxxed import max_chrome as chrome, max_status as status, max_timeline as timeline


class FeedbackFixture:
    kind = 'MOVE'

    def active_tool(self, context):
        return self.kind

    def selection_text(self, context):
        return 'Fixture selection'

    def prompt_text(self, context):
        return 'Fixture command guidance'


feedback = FeedbackFixture()


class ChromeTests(unittest.TestCase):
    def test_region_overlap_restores_after_file_load(self):
        system = bpy.context.preferences.system
        original = system.use_region_overlap
        try:
            system.use_region_overlap = True
            chrome.apply_layout(bpy.context)
            self.assertFalse(system.use_region_overlap)
            chrome._load(None)
            chrome.uninstall()
            self.assertTrue(system.use_region_overlap)
        finally:
            system.use_region_overlap = original

    def setUp(self):
        chrome.install(feedback=feedback)
        self.scene = bpy.context.scene
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.active_object

    def tearDown(self):
        chrome.uninstall()

    def test_paired_install_and_frame_preservation(self):
        original = list(chrome._originals)
        values = (self.scene.frame_start, self.scene.frame_end, self.scene.render.fps,
                  self.scene.render.fps_base, self.scene.unit_settings.scale_length)
        chrome.install(feedback=feedback)

        self.assertEqual(chrome._originals, original)
        self.assertEqual(len(chrome._keys), 7)
        self.assertEqual(values, (self.scene.frame_start, self.scene.frame_end, self.scene.render.fps,
                                 self.scene.render.fps_base, self.scene.unit_settings.scale_length))
        chrome.uninstall()
        self.assertFalse(chrome._keys)
        self.assertFalse(chrome._originals)
        self.assertFalse(chrome._installed)
        for cls, original, ours in original:
            self.assertIs(cls.draw, original)
        chrome.install(feedback=feedback)

    def test_stale_window_listener_cannot_remove_reinstalled_listener(self):
        replacement = object()
        chrome._pointers[42] = replacement
        old_listener = SimpleNamespace(window_id=42)
        result = chrome.MAX_OT_chrome_pointer.modal(old_listener, None, None)
        self.assertEqual(result, {'CANCELLED'})
        self.assertIs(chrome._pointers[42], replacement)
        chrome._pointers.pop(42)

    def test_units_tool_specific_and_live_offset_readouts(self):
        self.scene.unit_settings.system = 'METRIC'
        self.scene.unit_settings.length_unit = 'ADAPTIVE'
        self.scene.unit_settings.scale_length = .01
        self.assertIn('cm', status.format_value(self.scene, 1, 'LENGTH'))
        self.scene.unit_settings.system = 'IMPERIAL'
        self.assertNotIn('m', status.format_value(self.scene, 1, 'LENGTH'))
        self.scene.unit_settings.system = 'NONE'
        self.ob.location = (2,3,4)
        bpy.context.view_layer.update()
        feedback.kind = 'MOVE'
        self.assertEqual(status.readout(bpy.context)[1], (2,3,4))
        self.assertIsNone(status.readout(bpy.context, True)[1])
        status.publish(bpy.context, 'MOVE', (1,2,3))
        self.assertEqual(status.readout(bpy.context, True)[1], (1,2,3))
        feedback.kind = 'ROTATE'
        self.ob.rotation_euler = (0,0,math.pi/4)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(status.readout(bpy.context)[1][2], math.pi/4, places=5)
        feedback.kind = 'SCALE'
        self.ob.scale = (2,3,4)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(status.readout(bpy.context)[1][1], 300, places=3)
        self.assertEqual(status.format_value(self.scene, 125, 'PERCENT'), '125.00%')
        status.clear()
        self.assertIsNone(status.readout(bpy.context, True)[1])
        feedback.kind = 'MOVE'

    def test_named_sets_keys_ranges_and_delete_stale_members(self):
        self.scene.frame_start, self.scene.frame_end = 0, 80
        self.assertEqual(timeline.frame_from_x(SimpleNamespace(frame_start=-20, frame_end=80), -100, 400), -20)
        self.assertEqual(timeline.frame_from_x(self.scene, 10000, 400), 80)
        self.assertEqual(timeline.frame_from_x(self.scene, 200, 400), 40)
        for frame in (-20, 3, 80):
            self.scene.frame_set(frame)
            self.assertEqual(bpy.ops.max.chrome_key(), {'FINISHED'})
        self.assertEqual(timeline.key_frames(bpy.context), [-20,3,80])
        bpy.ops.max.chrome_transport(action='FIRST')
        self.assertEqual(self.scene.frame_current, 0)
        bpy.ops.max.chrome_transport(action='NEXT')
        self.assertEqual(self.scene.frame_current, 3)
        bpy.ops.max.chrome_key(remove=True)
        self.assertEqual(timeline.key_frames(bpy.context), [-20,80])
        bpy.ops.max.chrome_transport(action='LAST')
        self.assertEqual(self.scene.frame_current, 80)
        bpy.ops.max.chrome_named_set(action='SAVE', name='Test Set')
        self.ob.select_set(False)
        bpy.ops.max.chrome_named_set(action='RECALL', name='Test Set')
        self.assertTrue(self.ob.select_get())
        bpy.data.objects.remove(self.ob, do_unlink=True)
        bpy.ops.max.chrome_named_set(action='RECALL', name='Test Set')
        self.assertEqual(list(bpy.context.selected_objects), [])
        bpy.ops.max.chrome_named_set(action='REMOVE', name='Test Set')
        self.assertNotIn('Test Set', self.scene.max_chrome_sets)


unittest.main(argv=['chrome'], exit=False)
