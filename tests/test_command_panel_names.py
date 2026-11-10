"""Pin the frozen W2.B base-object labels and primitive precedence."""
import unittest
from types import SimpleNamespace
import addon_utils

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import ui_panel as ui, prims


class BaseNamesTests(unittest.TestCase):
    def test_frozen_mapping_by_value(self):
        self.assertEqual(ui.BASE_NAMES, {
            'MESH': 'Editable Poly', 'CURVE': 'Editable Spline', 'FONT': 'Text',
            'SURFACE': 'NURBS Surface', 'LIGHT': 'Light', 'CAMERA': 'Camera',
            'EMPTY': 'Dummy', 'ARMATURE': 'Bones', 'META': 'Blob Mesh',
            'LATTICE': 'FFD', 'GREASEPENCIL': 'Grease Pencil', 'CURVES': 'Hair',
            'POINTCLOUD': 'Point Cloud', 'VOLUME': 'Volume',
        })

    def test_base_labels_and_empty_object(self):
        for kind, label in {
            'MESH': 'Editable Poly', 'CURVE': 'Editable Spline', 'FONT': 'Text',
            'SURFACE': 'NURBS Surface', 'LIGHT': 'Light', 'CAMERA': 'Camera',
            'EMPTY': 'Dummy', 'ARMATURE': 'Bones', 'META': 'Blob Mesh',
            'LATTICE': 'FFD', 'GREASEPENCIL': 'Grease Pencil', 'CURVES': 'Hair',
            'POINTCLOUD': 'Point Cloud', 'VOLUME': 'Volume',
        }.items():
            with self.subTest(kind=kind):
                self.assertEqual(ui.base_name(SimpleNamespace(type=kind, max_prim=SimpleNamespace(kind=''))), label)
        self.assertEqual(ui.base_name(None), '')
        for kind, definition in prims.PRIMITIVES.items():
            with self.subTest(primitive=kind):
                self.assertEqual(ui.base_name(SimpleNamespace(type='MESH', max_prim=SimpleNamespace(kind=kind))), definition[0])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BaseNamesTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
