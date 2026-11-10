"""Screen-pixel snap feedback, separate from magnetic target selection.

2026 Snap Options calls the grid cursor a box with crosshairs. The vertex
viewport captures in GUID-66F42B65 show a plain crosshair, without a label.
Other types have no viewport illustration in the retrieved 2026 help. Use
the documented box-shaped hit point for those, not their toolbar artwork.
"""

ACTIVE = (0, 1, 0, 1)
SNAPPED = (1, 1, 0, 1)
REFERENCED_TYPES = frozenset({'grid_points', 'vertex'})


def segments(kind, center, size):
    """Return pixel endpoints. Size is pixels, independent of UI scaling."""
    x, y = center
    h = size / 2
    cross = (((x-h, y), (x+h, y)), ((x, y-h), (x, y+h)))
    box = (((x-h, y-h), (x+h, y-h)), ((x+h, y-h), (x+h, y+h)),
           ((x+h, y+h), (x-h, y+h)), ((x-h, y+h), (x-h, y-h)))
    if kind == 'vertex':
        return cross
    if kind == 'grid_points':
        return box + cross
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
