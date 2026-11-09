"""Real parameter adapters, without the shared Command Panel host."""
from pathlib import Path
import sys
import unittest
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _w11 import load


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = load('modifier_ui')
        cls.widgets = load('max_widgets')
        cls.modules = (cls.widgets, load('ffd'), load('turbosmooth'), cls.ui)
        for module in cls.modules:
            for item in module.classes:
                bpy.utils.register_class(item)
            if hasattr(module, 'register_props'):
                module.register_props()

    @classmethod
    def tearDownClass(cls):
        for module in reversed(cls.modules):
            if hasattr(module, 'unregister_props'):
                module.unregister_props()
            for item in reversed(module.classes):
                bpy.utils.unregister_class(item)

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_shell_maps_inner_and_outer_without_touching_duplicate(self):
        a = self.ui.add_modifier(self.ob, 'SHELL')
        b = self.ui.add_modifier(self.ob, 'SHELL')
        self.ui.select_modifier(self.ob, a)
        settings = self.ob.max_modifier_parameters
        settings.shell_inner = .2
        settings.shell_outer = .6
        self.assertAlmostEqual(a.thickness, .8)
        self.assertAlmostEqual(a.offset, .5)
        self.assertAlmostEqual(settings.shell_inner, .2)
        self.assertNotAlmostEqual(b.thickness, .8)
        self.ui.select_modifier(self.ob, b)
        self.assertNotAlmostEqual(settings.shell_inner, .2)

    def test_catalogue_and_stack_instances(self):
        a = self.ui.add_modifier(self.ob, 'NOISE')
        b = self.ui.add_modifier(self.ob, 'NOISE')
        self.ui.select_modifier(self.ob, a)
        self.assertEqual(self.ui.active_modifier(bpy.context), a)
        self.assertEqual([r[1] for r in self.ui.stack_rows(self.ob)], [b.name, a.name, self.ob.name])
        self.assertIsNone(self.ui.add_modifier(self.ob, 'UNSUPPORTED'))
        mod = self.ui.add_modifier(self.ob, 'ARRAY')
        self.assertTrue(mod.use_constant_offset)
        self.assertFalse(mod.use_relative_offset)

    def test_spinner_units_and_negative_values(self):
        self.assertAlmostEqual(self.widgets.snap_value(-1.24, .1), -1.2)
        self.assertEqual(self.widgets.snap_value(.123, .1, False), .123)
        self.assertEqual(self.widgets.snap_value(.123, 0), .123)

    def test_host_install_is_repeatable_and_removes_only_owned_panels(self):
        from types import SimpleNamespace
        host = SimpleNamespace(ROLLOUTS=[])

        def when(predicate):
            return lambda callback: callback

        def rollout(label, tabs, order, closed=False):
            def decorate(callback):
                panel = type('VIEW3D_PT_w11_install_contract', (bpy.types.Panel,), {
                    'bl_label': label, 'bl_space_type': 'VIEW_3D', 'bl_region_type': 'UI',
                    'bl_category': 'W1.1', 'draw': lambda self, context: callback(self.layout, context)})
                host.ROLLOUTS.append(panel)
                return callback
            return decorate
        host.when, host.rollout = when, rollout
        first = self.ui.install(host)
        self.assertIs(self.ui.install(host), first)
        self.assertEqual(len(host.ROLLOUTS), 1)
        panel = host.ROLLOUTS[0]
        bpy.utils.register_class(panel)
        self.ui.uninstall(host)
        self.assertFalse(host.ROLLOUTS)
        self.assertFalse(panel.is_registered)
        self.ui.uninstall(host)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdapterTests))
    print('W11 UI tests=%d failures=%d errors=%d' % (result.testsRun, len(result.failures), len(result.errors)), flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
