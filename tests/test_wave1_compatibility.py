"""Existing host interfaces must remain usable during the wave-1 transition."""
from types import SimpleNamespace
import unittest
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import ffd, turbosmooth, gn_mods, vray, theme

class Layout:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
    def row(self, **kwargs):
        return Layout(self.calls)
    column = row
    box = row
    split = row
    def label(self, **kwargs):
        pass
    def prop(self, owner, name, **kwargs):
        owner.path_resolve(name)
        self.calls.append((owner, name))
    def prop_enum(self, owner, name, value, **kwargs):
        self.prop(owner, name)
    def context_pointer_set(self, name, owner):
        pass
    def operator(self, *args, **kwargs):
        return SimpleNamespace()

class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_legacy_modifier_drawers_bind_the_explicit_instance(self):
        a = ffd.add(self.ob, 2)
        b = ffd.add(self.ob, 3)
        self.assertTrue(ffd.is_ffd(a))
        self.assertFalse(ffd.is_ffd(None))
        self.assertEqual(ffd.OWNER_KEY, 'max_ffd_owner')
        ffd.draw(Layout(), self.ob, a, editing_cage=True)
        self.assertEqual(ffd.modifier(self.ob), a)
        x = turbosmooth.add(self.ob, 1)
        y = turbosmooth.add(self.ob, 2)
        self.assertTrue(turbosmooth.is_turbosmooth(x))
        self.assertFalse(turbosmooth.is_turbosmooth(b))
        self.assertFalse(turbosmooth.is_turbosmooth(None))
        turbosmooth.draw(Layout(), self.ob, x)
        self.assertEqual(turbosmooth.modifier(self.ob), x)

    def test_legacy_melt_keying_uses_named_input_storage(self):
        mod = gn_mods.add(self.ob, 'Melt')
        self.assertTrue(gn_mods.is_melt(mod))
        self.assertFalse(gn_mods.is_melt(None))
        gn_mods.set_input(mod, 'Amount', .2)
        self.assertTrue(gn_mods.keyframe_input(mod, 'Amount', 5))
        gn_mods.set_input(mod, 'Amount', .8)
        self.assertTrue(gn_mods.keyframe_input(mod, 'Amount', 15))
        self.assertFalse(gn_mods.keyframe_input(mod, 'Absent', 15))
        bpy.context.scene.frame_set(5)
        self.assertAlmostEqual(gn_mods.value(mod, 'Amount'), .2)
        bpy.context.scene.frame_set(15)
        self.assertAlmostEqual(gn_mods.value(mod, 'Amount'), .8)

    def test_camera_and_material_draw_use_the_supplied_data(self):
        bpy.ops.max.vray_camera()
        camera = bpy.context.object.data
        layout = Layout()
        vray.draw_vray_camera(layout, camera)
        self.assertTrue(any(owner == camera.max_vray for owner, _ in layout.calls))
        bpy.context.view_layer.objects.active = self.ob
        self.ob.select_set(True)
        bpy.ops.max.vray_material(preset='GLASS')
        material = self.ob.active_material
        layout = Layout()
        vray.draw_vraymtl(layout, material)
        self.assertTrue(layout.calls)
        self.assertTrue(all(owner == material or owner.id_data == material.node_tree
                            for owner, _ in layout.calls))

    def test_reset_theme_restores_the_owned_snapshot(self):
        old = bpy.context.preferences.view.show_tooltips_python
        theme.apply()
        theme.reset_theme()
        self.assertEqual(bpy.context.preferences.view.show_tooltips_python, old)
        self.assertFalse(theme._changes)

result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CompatibilityTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('W1 LEGACY HOST COMPATIBILITY PASS')
