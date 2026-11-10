"""Run through run_checks.py tests test_chrome2_bottom."""
import unittest
import bpy
from notuodesk_3ds_maxxed import max_chrome, max_timeline


class BottomTests(unittest.TestCase):
    def setUp(self):
        max_chrome.install()

    def tearDown(self):
        max_chrome.uninstall()

    def test_key_mode_switches_between_adjacent_keys_and_frames(self):
        scene = bpy.context.scene
        scene.frame_start, scene.frame_end = 0, 100
        ob = bpy.context.active_object
        for frame in (0, 20):
            ob.keyframe_insert('location', frame=frame)
        scene.frame_set(5)
        bpy.context.window_manager.max_chrome_key_mode = False
        bpy.ops.max.chrome_transport(action='NEXT')
        self.assertEqual(scene.frame_current, 6)
        bpy.context.window_manager.max_chrome_key_mode = True
        bpy.ops.max.chrome_transport(action='NEXT')
        self.assertEqual(scene.frame_current, 20)

    def test_add_time_tag_creates_a_real_scene_marker(self):
        bpy.context.scene.frame_set(37)
        bpy.ops.max.chrome_time_tag(name='Review pose')
        tag = bpy.context.scene.timeline_markers['Review pose']
        self.assertEqual(tag.frame, 37)

    def test_compact_track_geometry_uses_reference_height(self):
        metrics = max_timeline.track_metrics(1200, 92, 1)
        self.assertEqual(metrics['slider'], (0, 72, 1200, 92))
        self.assertEqual(metrics['track'], (0, 44, 1200, 72))


unittest.main(argv=['bottom'], exit=False)
