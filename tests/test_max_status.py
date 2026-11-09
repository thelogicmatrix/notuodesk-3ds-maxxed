"""Run with run_checks.py tests test_max_status."""
import unittest
import bpy
from notuodesk_3ds_maxxed import max_chrome, max_status


class StatusTests(unittest.TestCase):
    def tearDown(self):
        max_chrome.uninstall()

    def test_shared_reader_writer_and_explicit_display_units(self):
        calls = []
        def read(context, offset):
            calls.append(('read',context.area.type,offset))
            return 'MOVE', (1,2,3), 'LENGTH'
        def write(context, values, offset):
            calls.append(('write',context.area.type,offset))
            context.active_object.location = values
            return True
        max_chrome.install(read_transform=read,write_transform=write)
        self.assertEqual(max_status.readout(bpy.context)[1], (1,2,3))
        bpy.ops.max.chrome_typein(move_values=(4,5,6))
        self.assertEqual(tuple(bpy.context.active_object.location), (4,5,6))
        self.assertTrue(all(entry[1] == 'VIEW_3D' for entry in calls))
        settings = bpy.context.scene.unit_settings
        settings.system = 'METRIC'
        settings.length_unit = 'CENTIMETERS'
        settings.scale_length = .01
        self.assertEqual(max_status.format_value(bpy.context.scene, 2, 'LENGTH'), '2.000 cm')
        settings.system = 'IMPERIAL'
        settings.length_unit = 'INCHES'
        settings.scale_length = .0254
        self.assertEqual(max_status.format_value(bpy.context.scene, 2, 'LENGTH'), '2.000 in')


unittest.main(argv=['status'],exit=False)
