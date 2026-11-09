"""Clean-room construction and truthful creator acceptance."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy
from mathutils import Euler, Vector


class CreationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / 'notuodesk_3ds_maxxed'
        assert (root / 'create.py').is_file(), 'Replacement creation service is missing'
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        from notuodesk_3ds_maxxed import create
        cls.create = create

    def test_principal_frames_are_orthonormal(self):
        for perspective, angles in ((True, (.8, .2, .3)), (False, (0, 0, 0)),
                                     (False, (1.57079632679, 0, 0)),
                                     (False, (1.57079632679, 0, 1.57079632679))):
            rv = SimpleNamespace(is_perspective=perspective, view_rotation=Euler(angles).to_quaternion())
            u, v, n = self.create.construction_frame(rv)
            self.assertLess((u.cross(v) - n).length, 1e-6)
            self.assertAlmostEqual(n.length, 1)
            self.assertEqual(sum(abs(c) > .5 for c in n), 1)

    def test_unavailable_helper_does_not_create_arrows(self):
        before = set(bpy.data.objects)
        self.assertEqual(bpy.ops.max.create_helper(kind='ARROWS'), {'CANCELLED'})
        self.assertEqual(set(bpy.data.objects), before)

    def test_target_camera_has_separate_target(self):
        self.assertEqual(bpy.ops.max.create_camera(target=True), {'FINISHED'})
        camera = bpy.context.object
        self.assertEqual(tuple(camera.location), (0, 0, 0))
        self.assertEqual(camera.type, 'CAMERA')
        self.assertEqual(len(camera.constraints), 1)
        self.assertIsNotNone(camera.constraints[0].target)
        self.assertIn(camera.constraints[0].target.name, bpy.context.scene.objects)

    def test_ui_installation_does_not_duplicate_rollouts(self):
        calls = []
        class Host:
            @staticmethod
            def rollout(*args, **kwargs):
                def add(callback):
                    calls.append(callback)
                    return callback
                return add
            @staticmethod
            def when(predicate):
                return lambda callback: callback
        self.create.install_ui(Host)
        first = tuple(calls)
        self.create.install_ui(Host)
        self.assertEqual(tuple(calls), first)
        self.create.uninstall_ui(Host)


result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(CreationContractTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('CLEANROOM CREATE PASS', flush=True)
