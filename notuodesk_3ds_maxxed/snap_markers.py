"""Screen-pixel snap feedback, separate from magnetic target selection.

Grid Points is the Snaps dialog glyph: a box with a half diagonal from the
centre to the top-right corner (grid-points-dialog-crop.png). Autodesk's
"box + crosshairs" wording does not match that image, and the image wins
(Nathan, 2026-11-10). Vertex keeps the 2026 viewport crosshair. Other shapes follow max-ui-reference/snap-markers.md:
the 2023 Standard Snaps dialog and flylib-fig8-17 show Grid Lines (box),
Bounding Box (upright triangle), Perpendicular (inverted triangle), Tangent
(small box), Edge/Segment (corner brackets), Midpoint (extended right angle),
Face (ring/top bar) and Center Face (plus). Pivot is the dialog's square with
a diagonal and Endpoint is the dialog's Y (stem and two lower arms). The
toolbar's Pivot Y is not used, so Pivot and Endpoint stay distinct as in Max.
The per-type dialog crops supply proportions, without the checkbox or yellow
toolbar overlay. These glyph sources do not prove current viewport pixels.
"""

ACTIVE = (0, 1, 0, 1)
SNAPPED = (1, 1, 0, 1)
REFERENCED_TYPES = frozenset({'grid_points', 'vertex'})

# Coordinates are fractions of half the Size setting, in viewport Y-up space.
# Open boxes mean unfilled outlines. Tangent is smaller than Grid Lines.
_GLYPHS = {
    'pivot': (((-1, -1), (1, -1)), ((1, -1), (1, 1)),
              ((1, 1), (-1, 1)), ((-1, 1), (-1, -1)), ((-1, -1), (1, 1))),
    'bounding_box': (((-1, -1), (0, 1)), ((0, 1), (1, -1)),
                     ((1, -1), (-1, -1))),
    'perpendicular': (((-1, 1), (1, 1)), ((1, 1), (0, -1)),
                      ((0, -1), (-1, 1))),
    'tangent': (((-.6, -.6), (.6, -.6)), ((.6, -.6), (.6, .6)),
                ((.6, .6), (-.6, .6)), ((-.6, .6), (-.6, -.6))),
    # Measured from endpoint-dialog-crop.png (11x12 px): stem to just below
    # centre, then 45-degree arms to the bottom corners.
    'endpoint': (((0, 1), (0, -.125)), ((0, -.125), (-.875, -1)),
                 ((0, -.125), (.875, -1))),
    'edge': (((-1, .4), (-1, 1)), ((-1, 1), (-.4, 1)),
             ((.4, 1), (1, 1)), ((1, 1), (1, .4)),
             ((1, -.4), (1, -1)), ((1, -1), (.4, -1)),
             ((-.4, -1), (-1, -1)), ((-1, -1), (-1, -.4))),
    'midpoint': (((-1, 1), (-1, -1)), ((-1, -1), (1, -1)),
                 ((-1, .2), (.2, .2)), ((.2, .2), (.2, -1))),
    'face': (((0, .5), (.5, .25)), ((.5, .25), (.75, -.25)),
             ((.75, -.25), (.5, -.75)), ((.5, -.75), (0, -1)),
             ((0, -1), (-.5, -.75)), ((-.5, -.75), (-.75, -.25)),
             ((-.75, -.25), (-.5, .25)), ((-.5, .25), (0, .5)),
             ((-1, .5), (1, .5))),
}


def segments(kind, center, size):
    """Return pixel endpoints. Size is pixels, independent of UI scaling."""
    x, y = center
    h = size / 2
    cross = (((x-h, y), (x+h, y)), ((x, y-h), (x, y+h)))
    box = (((x-h, y-h), (x+h, y-h)), ((x+h, y-h), (x+h, y+h)),
           ((x+h, y+h), (x-h, y+h)), ((x-h, y+h), (x-h, y-h)))
    if kind in {'vertex', 'center_face'}:
        return cross
    if kind == 'grid_points':
        return box + (((x, y), (x+h, y+h)),)
    if kind in _GLYPHS:
        return tuple(tuple((x+dx*h, y+dy*h) for dx, dy in line)
                     for line in _GLYPHS[kind])
    return box


def feedback(settings, hit):
    return SNAPPED if hit is not None and hit[1] <= settings.snap_radius else ACTIVE


def draw(context, hit, base, raw):
    from . import snaps
    import gpu
    from gpu_extras.batch import batch_for_shader
    s = snaps.settings(context)
    if not s.marker:
        return
    region, rv3d = context.region, context.region_data
    target = hit[0] if hit else raw
    point = snaps._screen(region, rv3d, target)
    endpoint = snaps._screen(region, rv3d, hit[0] if hit and hit[2] <= s.snap_radius else raw)
    start = snaps._screen(region, rv3d, base) if base is not None else None
    color = feedback(s, (hit[1], hit[2]) if hit else None)
    lines = []
    if hit and point is not None:
        lines.extend(segments(hit[1], point, s.marker_size))
    if start is not None and endpoint is not None and s.rubber_band:
        lines.append((tuple(start), tuple(endpoint)))
        lines.extend(segments('source', start, s.marker_size))
    if not lines:
        return
    # Integer pixel rectangles retain the one-pixel Max stroke at both UI scales.
    # GPU line widths are backend-dependent and may silently clamp on Metal.
    vertices = []
    for (x1, y1), (x2, y2) in lines:
        dx, dy = x2-x1, y2-y1
        length = (dx*dx+dy*dy)**.5
        if not length:
            continue
        nx, ny = -dy/length*.5, dx/length*.5
        a, b = (x1+nx, y1+ny), (x1-nx, y1-ny)
        c, d = (x2-nx, y2-ny), (x2+nx, y2+ny)
        vertices.extend((a, b, c, a, c, d))
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)
    gpu.state.blend_set('NONE')
