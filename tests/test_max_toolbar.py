"""Run with run_checks.py tests test_max_toolbar."""
import unittest
from mathutils import Vector
from notuodesk_3ds_maxxed.max_toolbar import bounds_hit


class RectangleTests(unittest.TestCase):
    def test_window_crossing_and_empty_bounds(self):
        points = [Vector((10,10)), Vector((30,40))]
        self.assertTrue(bounds_hit(points, (0,0,50,50), False))
        self.assertFalse(bounds_hit(points, (20,20,50,50), False))
        self.assertTrue(bounds_hit(points, (20,20,50,50), True))
        self.assertFalse(bounds_hit(points, (31,0,50,50), True))
        self.assertFalse(bounds_hit([], (0,0,50,50), True))


unittest.main(argv=['toolbar'], exit=False)
