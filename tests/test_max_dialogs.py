"""Run in an isolated Blender process. Dialog transactions and file decisions."""
import sys
from pathlib import Path
import unittest
import math
from types import SimpleNamespace
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).parent))
from _w15_setup import bpy, box, empty_scene
from notuodesk_3ds_maxxed import max_dialogs as dialogs
dialogs.install()


class TypeInHost:
    """Use real operator methods without opening a native popup in background."""
    invoke = dialogs.MAX_OT_typein_dialog.invoke
    check = dialogs.MAX_OT_typein_dialog.check
    execute = dialogs.MAX_OT_typein_dialog.execute
    cancel = dialogs.MAX_OT_typein_dialog.cancel

    def __init__(self, system="WORLD"):
        for prop in bpy.ops.max.typein_dialog.get_rna_type().properties:
            if prop.identifier in {"rna_type", "system"}:
                continue
            value = tuple(prop.default_array) if getattr(prop, "is_array", False) else prop.default
            setattr(self, prop.identifier, value)
        self.system = system

    def __getattr__(self, name):
        method = getattr(dialogs.MAX_OT_typein_dialog, name, None)
        if callable(method):
            return method.__get__(self)
        raise AttributeError(name)

    def report(self, kind, message):
        raise AssertionError(message)


def invoke_typein(host):
    context = SimpleNamespace(**{name: getattr(bpy.context, name) for name in
        ("active_object", "selected_objects", "scene", "view_layer", "workspace", "mode", "screen", "region_data")})
    context.window_manager = SimpleNamespace(invoke_props_dialog=lambda operator, **kwargs: {"RUNNING_MODAL"})
    assert host.invoke(context, None) == {"RUNNING_MODAL"}
    return context


class DialogTests(unittest.TestCase):
    def test_operator_target_is_registered(self):
        properties = bpy.ops.max.align_dialog.get_rna_type().properties
        self.assertIn("target", properties)
        self.assertEqual(properties["target"].type, "STRING")

    def setUp(self):
        empty_scene()
        self.obj = box("Subject")

    def test_f4_unchanged_parent_typein_preserves_scaled_parent_pose(self):
        child = box("Child")
        child.parent = self.obj
        self.obj.location.x = 10
        self.obj.scale.x = 2
        child.location.x = 1
        self.obj.select_set(False)
        bpy.context.view_layer.update()
        before = child.matrix_world.copy()
        host = TypeInHost("PARENT")
        context = invoke_typein(host)
        self.assertAlmostEqual(host.absolute[0], 2)
        self.assertEqual(host.execute(context), {"FINISHED"})
        self.assertEqual(child.matrix_world, before)
        print("F4 UNCHANGED PARENT world X=12 preserved PASS", flush=True)

    def test_f6_move_fields_have_scene_length_units(self):
        props = bpy.ops.max.typein_dialog.get_rna_type().properties
        for name in ("absolute", "offset"):
            self.assertEqual(props[name].unit, "LENGTH")
        for name in ("absolute_angle", "offset_angle"):
            self.assertEqual(props[name].unit, "ROTATION")
        for name in ("absolute_scale", "offset_scale"):
            self.assertEqual(props[name].unit, "NONE")
        print("F6 MOVE LENGTH / ROTATE ROTATION / SCALE PERCENT PASS", flush=True)

    def assert_pose(self, obj, expected):
        self.assertLess(max(abs(a-b) for row, want in zip(obj.matrix_world, expected)
                            for a, b in zip(row, want)), 2e-5)

    def test_f4_every_frame_and_tool_unchanged_with_rotated_scaled_parent(self):
        child = box("Child")
        child.parent = self.obj
        self.obj.location = (10, -3, 2)
        self.obj.rotation_euler.z = math.pi / 2
        self.obj.scale = (2, 3, .5)
        child.location = (1, 2, -1)
        child.rotation_euler = (.2, -.3, .4)
        self.obj.select_set(False)
        bpy.context.view_layer.update()
        expected = child.matrix_world.copy()
        for system in ("WORLD", "PARENT", "LOCAL", "VIEW", "SCREEN"):
            for tool in ("MOVE", "ROTATE", "SCALE"):
                with self.subTest(system=system, tool=tool):
                    host = TypeInHost(system)
                    context = invoke_typein(host)
                    host.tool = tool
                    host._tx.reframe(system, tool)
                    host._refresh_fields()
                    self.assertEqual(host.execute(context), {"FINISHED"})
                    self.assert_pose(child, expected)
        print("F4 UNCHANGED 5 FRAMES x 3 TOOLS rotated/scaled parent PASS", flush=True)

    def test_f4_reference_switch_preserves_preview_and_cancel_start(self):
        child = box("Child")
        child.parent = self.obj
        self.obj.location.x = 10
        self.obj.rotation_euler.z = math.pi / 2
        self.obj.scale = (2, 3, 1)
        child.location = (1, 0, 0)
        self.obj.select_set(False)
        bpy.context.view_layer.update()
        original = child.matrix_world.copy()
        host = TypeInHost("PARENT")
        context = invoke_typein(host)
        host.preview, host.group, host.offset = True, "OFFSET", (1, 0, 0)
        host.check(context)
        self.assertAlmostEqual(child.matrix_world.translation.y, 3, places=5)
        preview = child.matrix_world.copy()
        for system in ("WORLD", "LOCAL", "SCREEN", "VIEW", "PARENT"):
            host.system = system
            host.check(context)
            self.assert_pose(child, preview)
            host.check(context)
            self.assert_pose(child, preview)
        host.cancel(context)
        self.assert_pose(child, original)
        print("F4 REFRAME preserves preview / cancel restores start / unit offset ignores parent scale PASS", flush=True)

    def test_shared_writer_preview_cancel_and_accept(self):
        def reader(context, offset):
            return "MOVE", tuple(context.active_object.location), "LENGTH"

        def writer(context, values, offset):
            obj = context.active_object
            obj.location = obj.location + dialogs.Vector(values) if offset else values
            context.view_layer.update()
            return True

        dialogs.configure_transform(reader=reader, writer=writer)
        try:
            host = TypeInHost()
            context = invoke_typein(host)
            host.preview, host.group, host.offset = True, "OFFSET", (2, -1, 0)
            host.check(context)
            host.check(context)
            self.assertEqual(tuple(self.obj.location), (2, -1, 0))
            host.cancel(context)
            self.assertEqual(tuple(self.obj.location), (0, 0, 0))
            host = TypeInHost()
            context = invoke_typein(host)
            host.group, host.offset = "OFFSET", (-3, 2, 1)
            self.assertEqual(host.execute(context), {"FINISHED"})
            self.assertEqual(tuple(self.obj.location), (-3, 2, 1))
        finally:
            dialogs.configure_transform()
        print("F4 SHARED READ/WRITE preview / cancel / accept PASS", flush=True)

    def test_absolute_offset_and_cancel(self):
        tx = dialogs.TransformDraft(bpy.context)
        tx.type_in("MOVE", "ABSOLUTE", (4, 5, 6))
        self.assertEqual(tuple(self.obj.location), (4, 5, 6))
        tx.cancel()
        self.assertEqual(tuple(self.obj.location), (0, 0, 0))
        tx = dialogs.TransformDraft(bpy.context)
        tx.type_in("MOVE", "OFFSET", (-2, 1, 3))
        tx.accept()
        self.assertEqual(tuple(self.obj.location), (-2, 1, 3))

    def test_parent_basis_and_selected_hierarchy(self):
        child = box("Child")
        child.parent = self.obj
        child.location = (2, 0, 0)
        self.obj.location = (5, 0, 0)
        bpy.context.view_layer.update()
        child.select_set(True)
        self.obj.select_set(True)
        tx = dialogs.TransformDraft(bpy.context)
        tx.type_in("MOVE", "OFFSET", (3, 0, 0))
        tx.accept()
        self.assertEqual(round(child.matrix_world.translation.x), 10)
        self.assertEqual(round(self.obj.matrix_world.translation.x), 8)

    def test_scale_percent_rotate_and_mirror_offset(self):
        tx = dialogs.TransformDraft(bpy.context)
        tx.type_in("SCALE", "ABSOLUTE", (200, 150, 50))
        tx.accept()
        self.assertEqual(tuple(self.obj.scale), (2, 1.5, .5))
        self.obj.location.x = 3
        bpy.context.view_layer.update()
        tx = dialogs.TransformDraft(bpy.context)
        tx.mirror("X", 1)
        tx.accept()
        self.assertAlmostEqual(self.obj.matrix_world.translation.x, -1)

    def test_align_points_and_missing_target_are_atomic(self):
        target = box("Target")
        target.location = (10, 4, 0)
        target.select_set(False)
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.context.view_layer.update()
        tx = dialogs.TransformDraft(bpy.context)
        tx.align(target, position=(True, False, False), current_point="MAX", target_point="MIN")
        tx.accept()
        self.assertAlmostEqual(self.obj.location.x, 8)
        before = self.obj.matrix_world.copy()
        tx = dialogs.TransformDraft(bpy.context)
        with self.assertRaises(ValueError):
            tx.align(None)
        self.assertEqual(self.obj.matrix_world, before)

    def test_align_bounds_after_orientation_and_scale(self):
        target = box("RotatedTarget")
        target.location.x = 10
        target.rotation_euler.z = .6
        target.scale = (3, 1, 1)
        target.select_set(False)
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.context.view_layer.update()
        tx = dialogs.TransformDraft(bpy.context)
        tx.align(target, current_point="MAX", target_point="MIN",
                 orientation=(True, True, True), scale=(True, True, True))
        tx.accept()
        source = dialogs.object_point(self.obj, self.obj.matrix_world, "MAX")
        destination = dialogs.object_point(target, target.matrix_world, "MIN")
        self.assertLess((source-destination).length, 1e-5)

    def test_copy_instance_reference_and_cancel(self):
        clones = dialogs.clone(bpy.context, "COPY", 2, "Copy")
        self.assertEqual(len(clones), 2)
        self.assertNotEqual(clones[0].data, self.obj.data)
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        clones = dialogs.clone(bpy.context, "REFERENCE", 1, "Ref")
        self.assertEqual(clones[0].data, self.obj.data)
        self.assertIn("modifier", dialogs.REFERENCE_LIMIT.lower())

    def test_deleted_source_does_not_restore_another_object(self):
        tx = dialogs.TransformDraft(bpy.context)
        bpy.data.objects.remove(self.obj, do_unlink=True)
        replacement = box("Subject")
        replacement.location.x = 9
        tx.cancel()
        self.assertEqual(replacement.location.x, 9)

    def test_mirror_preview_clone_cancel_and_accept(self):
        self.obj.location.x = 3
        bpy.context.view_layer.update()
        tx = dialogs.MirrorDraft(bpy.context)
        tx.preview("X", 1, "COPY")
        self.assertEqual(len(bpy.context.scene.objects), 2)
        self.assertAlmostEqual(self.obj.location.x, 3)
        tx.cancel()
        self.assertEqual(len(bpy.context.scene.objects), 1)
        self.assertAlmostEqual(self.obj.location.x, 3)
        tx = dialogs.MirrorDraft(bpy.context)
        tx.preview("X", 1, "INSTANCE")
        clones = tx.accept()
        self.assertEqual(len(clones), 1)
        self.assertEqual(clones[0].data, self.obj.data)
        self.assertAlmostEqual(clones[0].location.x, -1)

    def test_disable_cancels_live_preview(self):
        tx = dialogs.TransformDraft(bpy.context)
        tx.type_in("MOVE", "OFFSET", (9, 0, 0))
        dialogs.uninstall()
        self.assertEqual(self.obj.location.x, 0)
        dialogs.install()

    def test_file_guard_save_failure_and_cancel_do_not_continue(self):
        called = []
        self.assertFalse(dialogs.resolve_scene_action("CANCEL", lambda: True, lambda: called.append(1)))
        self.assertFalse(dialogs.resolve_scene_action("SAVE", lambda: False, lambda: called.append(1)))
        self.assertEqual(called, [])
        self.assertTrue(dialogs.resolve_scene_action("DISCARD", lambda: False, lambda: called.append(1)))
        self.assertEqual(called, [1])

    def test_object_properties_cancel_and_apply(self):
        draft = dialogs.ObjectPropertiesDraft(self.obj)
        draft.values["hide_render"] = True
        draft.cancel()
        self.assertFalse(self.obj.hide_render)
        draft = dialogs.ObjectPropertiesDraft(self.obj)
        draft.values["hide_render"] = True
        draft.apply()
        self.assertTrue(self.obj.hide_render)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
