"""Run with Blender --background --factory-startup --python this file."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from _w15_setup import bpy, box, empty_scene, max_layers as layers


class LayerTests(unittest.TestCase):
    def setUp(self):
        empty_scene()
        self.scene = bpy.context.scene
        for layer in list(layers.catalogue(self.scene)):
            layers.remove(self.scene, layer)

    def test_membership_keeps_unrelated_collections_and_world_identity(self):
        obj = box("LayerBox")
        obj.location = (2, 3, 4)
        mesh = obj.data
        native = bpy.data.collections.new("Ordinary collection")
        self.scene.collection.children.link(native)
        native.objects.link(obj)
        first = layers.create(self.scene, "Architecture")
        second = layers.create(self.scene, "Furniture")
        layers.assign(self.scene, [obj], first)
        layers.assign(self.scene, [obj], second)
        self.assertEqual(layers.membership(self.scene, obj), second)
        self.assertIn(obj.name, native.objects)
        self.assertNotIn(obj.name, first.objects)
        self.assertEqual(tuple(obj.location), (2, 3, 4))
        self.assertEqual(obj.data, mesh)
        layers.remove(self.scene, second)
        self.assertIn(obj.name, self.scene.objects)
        self.assertIn(native.name, bpy.data.collections)

    def test_layer_restore_keeps_object_hidden_and_frozen_intent(self):
        from notuodesk_3ds_maxxed import freezing
        a, b = box("A"), box("B")
        a.hide_set(True)
        freezing.freeze(b, self.scene)
        layer = layers.create(self.scene, "State")
        layers.assign(self.scene, [a, b], layer)
        layers.set_hidden(self.scene, layer, True)
        layers.set_frozen(self.scene, layer, True)
        layers.set_hidden(self.scene, layer, False)
        layers.set_frozen(self.scene, layer, False)
        self.assertTrue(a.hide_get())
        self.assertFalse(b.hide_get())
        self.assertFalse(a.max_frozen)
        self.assertTrue(b.max_frozen)

    def test_assignment_into_disabled_layer_and_removal_restores(self):
        layer = layers.create(self.scene, "Off")
        layers.set_hidden(self.scene, layer, True)
        layers.set_frozen(self.scene, layer, True)
        obj = box("New member")
        mesh = obj.data
        layers.assign(self.scene, [obj], layer)
        self.assertTrue(obj.hide_get())
        self.assertTrue(obj.max_frozen)
        layers.remove(self.scene, layer)
        self.assertFalse(obj.hide_get())
        self.assertFalse(obj.max_frozen)
        self.assertEqual(obj.data, mesh)

    def test_multiple_and_nested_collections_have_deterministic_policy(self):
        obj = box("Nested")
        native = bpy.data.collections.new("Nested ordinary")
        self.scene.collection.children.link(native)
        layer = layers.create(self.scene, "Managed")
        native.children.link(layer)
        layers.assign(self.scene, [obj], layer)
        self.assertEqual(layers.catalogue(self.scene), [layer])
        self.assertEqual(layers.membership(self.scene, obj), layer)

    def test_linked_object_rejects_entire_membership_change(self):
        import tempfile
        source = box("LibraryObject")
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "fixture.blend")
            bpy.data.libraries.write(path, {source})
            bpy.data.objects.remove(source, do_unlink=True)
            with bpy.data.libraries.load(path, link=True) as (library, result):
                result.objects = ["LibraryObject"]
            linked = result.objects[0]
            self.scene.collection.objects.link(linked)
            local = box("Local")
            layer = layers.create(self.scene, "ReadOnlyCheck")
            with self.assertRaises(ValueError):
                layers.assign(self.scene, [local, linked], layer)
            self.assertNotIn(local.name, layer.objects)

    def test_ambiguous_managed_links_require_explicit_assignment(self):
        obj = box("MultiLayer")
        first = layers.create(self.scene, "First")
        second = layers.create(self.scene, "Second")
        layers.assign(self.scene, [obj], first)
        second.objects.link(obj)
        with self.assertRaises(ValueError):
            layers.set_hidden(self.scene, second, True)
        self.assertFalse(second.get("max_layer_hidden"))
        layers.assign(self.scene, [obj], second)
        self.assertNotIn(obj.name, first.objects)
        layers.set_hidden(self.scene, second, True)
        self.assertTrue(obj.hide_get())


if __name__ == "__main__":
    unittest.main(argv=[__file__])
