"""Target Weld pointer artwork. Evidence and unresolved dimensions are in docs/."""
from pathlib import Path

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .mode_feedback import draw_cursor_strokes

# Autodesk's 2026 selection capture shows separate, outlined cross arms.
# Target Weld's own help specifies a + but supplies no cursor bitmap.
CROSS_STROKES = ((-7, 0), (-3, 0), (3, 0), (7, 0),
                 (0, -7), (0, -3), (0, 3), (0, 7))
CROSS_PASSES = ((3, (1, 1, 1, 1)), (1, (0, 0, 0, 1)))
_arrow = None
_arrow_batch = None
_arrow_shader = None


def draw(mouse, valid, scale):
    global _arrow, _arrow_batch, _arrow_shader
    if valid:
        draw_cursor_strokes(mouse, CROSS_STROKES, scale, CROSS_PASSES)
        return
    if _arrow is None:
        path = Path(__file__).with_name('icons') / 'target-weld-system-arrow.png'
        _arrow = bpy.data.images.load(str(path), check_existing=False)
        _arrow.alpha_mode = 'PREMUL'
        _arrow.colorspace_settings.name = 'Non-Color'
    if _arrow_batch is None:
        # Texture filtering blurs a one-pixel cursor outline at fractional DPI.
        # Draw the captured pixels as rectangles instead, without interpolation.
        pixels = list(_arrow.pixels)
        positions, colors = [], []
        for y in range(32):
            for x in range(32):
                color = pixels[(y*32+x)*4:(y*32+x)*4+4]
                if not color[3]:
                    continue
                positions.extend(((x,y-32),(x+1,y-32),(x+1,y-31),
                                  (x,y-32),(x+1,y-31),(x,y-31)))
                colors.extend((color,)*6)
        _arrow_shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        _arrow_batch = batch_for_shader(_arrow_shader, 'TRIS', {'pos':positions, 'color':colors})
    previous = gpu.state.blend_get()
    try:
        gpu.state.blend_set('ALPHA_PREMULT')
        # The captured Windows arrow has a top-left hotspot at (0, 0).
        with gpu.matrix.push_pop():
            gpu.matrix.translate(mouse)
            gpu.matrix.scale((scale,scale))
            _arrow_shader.bind()
            _arrow_batch.draw(_arrow_shader)
    finally:
        gpu.state.blend_set(previous)


def clear():
    global _arrow, _arrow_batch, _arrow_shader
    _arrow_batch = None
    _arrow_shader = None
    if _arrow is not None:
        try:
            bpy.data.images.remove(_arrow)
        except (ReferenceError, RuntimeError):
            pass
        _arrow = None
