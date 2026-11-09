"""Run with run_checks.py tests test_overlay."""
import unittest
from types import SimpleNamespace
import bpy
from notuodesk_3ds_maxxed import overlay


class OverlayTests(unittest.TestCase):
    def test_overlapping_headers_only_offset_intersecting_quad_regions(self):
        for scale in (1., 1.5):
            header = SimpleNamespace(type='HEADER', x=20, y=362, width=800, height=38)
            tool = SimpleNamespace(type='TOOL_HEADER', x=20, y=336, width=800, height=26)
            area = SimpleNamespace(type='VIEW_3D', regions=[header, tool])
            context = SimpleNamespace(area=area, region_data=None,
                preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=scale)),
                space_data=bpy.context.space_data)
            area3d = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
            context.space_data = area3d.spaces.active
            for x, bottom, height, ceiling in ((20, 0, 400, 336), (420, 200, 200, 336),
                                               (20, 0, 200, 200), (900, 0, 400, 400)):
                context.region = SimpleNamespace(type='WINDOW', x=x, y=bottom, width=400, height=height)
                labels = overlay.label_regions(context)
                self.assertTrue(labels)
                for _, _, (_, y0, _, y1) in labels:
                    self.assertGreaterEqual(y0, 0)
                    self.assertAlmostEqual(bottom + y1, ceiling - 7 * scale)

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
