"""blender -b --factory-startup --python tests/test_snap_marker_ui.py.

Use the shared launcher and an isolated BLENDER_USER_* profile.
"""
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import snap_markers, snaps

# Pin the direct viewport references. Other types use the supplied glyph table.
assert snap_markers.REFERENCED_TYPES == frozenset({'grid_points', 'vertex'})
assert snap_markers.ACTIVE == (0, 1, 0, 1)
assert snap_markers.SNAPPED == (1, 1, 0, 1)
cross = snap_markers.segments('vertex', (100, 100), 20)
assert set(cross) == {((90, 100), (110, 100)), ((100, 90), (100, 110))}
assert snap_markers.segments('grid_points', (100, 100), 20)[-1] == ((100, 100), (110, 110))
assert len(snap_markers.segments('grid_points', (100, 100), 20)) == 5
assert len(snap_markers.segments('source', (100, 100), 20)) == 4
for key, _ in snaps.TYPES:
    lines = snap_markers.segments(key, (100, 100), 20)
    coords = [point for line in lines for point in line]
    assert all(90 <= x <= 110 and 90 <= y <= 110 for x, y in coords), key
    assert snap_markers.segments(key, (100, 100), 40) != lines
s = snaps.settings(bpy.context)
assert s.marker and s.marker_size == 20
assert snap_markers.feedback(s, ('vertex', 21)) == snap_markers.ACTIVE
assert snap_markers.feedback(s, ('vertex', 20)) == snap_markers.SNAPPED
print('SNAP UI marker references, shapes, size, active/snapped colours PASS', flush=True)
