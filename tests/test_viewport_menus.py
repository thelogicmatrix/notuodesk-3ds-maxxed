"""Run with run_checks.py tests test_viewport_menus."""
import unittest
import bpy
from notuodesk_3ds_maxxed import viewport_menus as vp, overlay


class ViewportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for entry in vp.classes:
            bpy.utils.register_class(entry)

    @classmethod
    def tearDownClass(cls):
        for entry in reversed(vp.classes):
            bpy.utils.unregister_class(entry)

    def test_modes_are_real_state_and_unavailable_keeps_state(self):
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            for mode, expected in [('WIRE','Wireframe'), ('CLAY','Clay'), ('FLAT','Flat Color'),
                                   ('MAPS','Shaded with Maps'), ('MATERIALS','Materials'),
                                   ('REALISTIC','Realistic'), ('DEFAULT','Default Shading')]:
                self.assertEqual(bpy.ops.max.viewport_shading(mode=mode), {'FINISHED'})
                self.assertEqual(overlay.shading_name(area.spaces.active), expected)
            before = area.spaces.active.shading.type
            self.assertEqual(bpy.ops.max.viewport_shading(mode='ACTIVESHADE'), {'CANCELLED'})
            self.assertEqual(area.spaces.active.shading.type, before)
            self.assertEqual(bpy.ops.max.view_camera(name='missing'), {'CANCELLED'})
            self.assertEqual(vp._space(bpy.context), area.spaces.active)
            self.assertEqual(vp.region_at(bpy.context, region.x+10, region.y+10), (area, region))
            self.assertEqual(vp.region_at(bpy.context, -10, -10), (None, None))


unittest.main(argv=['viewport menus'], exit=False)
