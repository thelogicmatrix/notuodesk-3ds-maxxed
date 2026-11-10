"""Pin Max marker geometry. Run through run_checks.py tests test_snap_markers."""
import unittest

import addon_utils

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import snap_markers, snaps


# Hand-read shapes from the supplied Max marker table and reference crops.
# A generic box, swapped type, missing stroke or reversed angle must fail.
EXPECTED = {
    'grid_points': (((-10, -10), (10, -10)), ((10, -10), (10, 10)),
                    ((10, 10), (-10, 10)), ((-10, 10), (-10, -10)),
                    ((0, 0), (10, 10))),
    'vertex': (((-10, 0), (10, 0)), ((0, -10), (0, 10))),
    'grid_lines': (((-10, -10), (10, -10)), ((10, -10), (10, 10)),
                   ((10, 10), (-10, 10)), ((-10, 10), (-10, -10))),
    'pivot': (((-10, -10), (10, -10)), ((10, -10), (10, 10)),
              ((10, 10), (-10, 10)), ((-10, 10), (-10, -10)), ((-10, -10), (10, 10))),
    'bounding_box': (((-10, -10), (0, 10)), ((0, 10), (10, -10)),
                     ((10, -10), (-10, -10))),
    'perpendicular': (((-10, 10), (10, 10)), ((10, 10), (0, -10)),
                      ((0, -10), (-10, 10))),
    'tangent': (((-6, -6), (6, -6)), ((6, -6), (6, 6)),
                ((6, 6), (-6, 6)), ((-6, 6), (-6, -6))),
    'endpoint': (((0, 10), (0, -1.25)), ((0, -1.25), (-8.75, -10)),
                 ((0, -1.25), (8.75, -10))),
    'edge': (((-10, 4), (-10, 10)), ((-10, 10), (-4, 10)),
             ((4, 10), (10, 10)), ((10, 10), (10, 4)),
             ((10, -4), (10, -10)), ((10, -10), (4, -10)),
             ((-4, -10), (-10, -10)), ((-10, -10), (-10, -4))),
    'midpoint': (((-10, 10), (-10, -10)), ((-10, -10), (10, -10)),
                 ((-10, 2), (2, 2)), ((2, 2), (2, -10))),
    'face': (((0, 5), (5, 2.5)), ((5, 2.5), (7.5, -2.5)),
             ((7.5, -2.5), (5, -7.5)), ((5, -7.5), (0, -10)),
             ((0, -10), (-5, -7.5)), ((-5, -7.5), (-7.5, -2.5)),
             ((-7.5, -2.5), (-5, 2.5)), ((-5, 2.5), (0, 5)),
             ((-10, 5), (10, 5))),
    'center_face': (((-10, 0), (10, 0)), ((0, -10), (0, 10))),
}


class SnapMarkers(unittest.TestCase):
    def test_every_supported_type_has_its_reference_segments(self):
        self.assertEqual(set(EXPECTED), {kind for kind, _ in snaps.TYPES})
        for kind, expected in EXPECTED.items():
            with self.subTest(kind=kind):
                self.assertEqual(snap_markers.segments(kind, (0, 0), 20), expected)

    def test_setting_scales_and_translates_every_segment(self):
        for kind, expected in EXPECTED.items():
            with self.subTest(kind=kind):
                self.assertEqual(snap_markers.segments(kind, (100, 80), 40),
                                 tuple(tuple((100 + 2*x, 80 + 2*y) for x, y in line)
                                       for line in expected))

    def test_source_and_unknown_keep_the_old_box(self):
        for kind in ('source', 'unknown'):
            self.assertEqual(snap_markers.segments(kind, (0, 0), 20), EXPECTED['grid_lines'])


if __name__ == '__main__':
    unittest.main(argv=['test_snap_markers'])
