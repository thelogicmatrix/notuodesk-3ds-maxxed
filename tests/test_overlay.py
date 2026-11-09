"""Run with run_checks.py tests test_overlay."""
import unittest
import bpy
from notuodesk_3ds_maxxed import overlay


class OverlayTests(unittest.TestCase):
    def test_scaled_hit_regions_and_viewport_edges(self):
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            labels = overlay.label_regions(bpy.context)
            self.assertEqual([l[0] for l in labels], ['MAX_MT_vp_general', 'MAX_MT_vp_point_of_view',
                                                    'MAX_MT_vp_quality', 'MAX_MT_vp_shading'])
            for menu, text, (x0,y0,x1,y1) in labels:
                self.assertEqual(overlay.hit_test(bpy.context, (x0+x1)/2, (y0+y1)/2), menu)
            self.assertIsNone(overlay.hit_test(bpy.context, 1, 1))
            self.assertIsNone(overlay.hit_test(bpy.context, region.width-1, region.height-1))


unittest.main(argv=['overlay'], exit=False)
