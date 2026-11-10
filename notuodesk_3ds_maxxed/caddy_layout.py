"""Control bounds measured in the Autodesk 2026 caddy images, at 100% DPI.

Coordinates start at the title's upper left. Artwork is authored separately.
The Outline topic publishes no caddy image, so it uses Inset's numeric row.
"""


def controls(action, level, keys):
    dark = action in {'EXTRUDE', 'CHAMFER', 'BEVEL'}
    title_height = 34 if dark else 17
    numeric, choice = (71, 48) if dark else (74, 44)
    title_width = {'EXTRUDE': 108, 'CHAMFER': 65, 'CONNECT': 85, 'BEVEL': 50,
                   'INSET': 38, 'OUTLINE': 48, 'BRIDGE': 83, 'WELD': 77,
                   'TESSELLATE': 60, 'MSMOOTH': 74, 'RELAX': 40}[action]
    top = title_height+7
    rows = [[key] for key in keys]
    if action == 'CHAMFER' and level != 1:
        rows = [[keys[0]], ['amount'], ['segments'], [keys[3]],
                ['end_bias', 'radial_bias'], ['open', 'invert_open'],
                ['chamfer_smooth', 'smooth_type', 'smooth_threshold']]
    elif action == 'BRIDGE':
        rows = ([['segments', 'smooth'], ['bridge_adjacent', 'reverse_triangulation']]
                if level == 2 else [['segments', 'taper'], ['bias', 'smooth'], ['twist1', 'twist2']])
        rows += [['bridge_selection', 'pick2', 'pick1']]
    elif action in {'RELAX', 'MSMOOTH'}:
        rows = [[key] for key in keys[:-2]]+[keys[-2:]]
    bounds = {'TITLE': (0, 0, title_width, title_height)}
    for row in rows:
        x = 0
        height = 17 if row == ['weld_counts'] else 22
        for key in row:
            is_choice = key in {'extrusion_type', 'bevel_type', 'individual', 'tessellate_type',
                                'chamfer_miter', 'smooth_type', 'bridge_selection'}
            is_toggle = key in {'open', 'invert_open', 'chamfer_smooth', 'hold_boundary',
                                'hold_outer', 'separate_smoothing', 'separate_materials',
                                'pick1', 'pick2', 'reverse_triangulation'}
            width = 103 if key == 'weld_counts' else choice if is_choice or is_toggle else numeric
            bounds[key] = (x, top, width, height)
            # Chamfer's bias pair has a 9px gap. Other columns have 7px.
            x += width+(9 if row == ['end_bias', 'radial_bias'] else 7)
        top += height+7
    bounds['BUTTONS'] = (0, top, 80, 22)
    return bounds, rows


def extent(bounds):
    return (max(x+w for x, y, w, h in bounds.values()),
            max(y+h for x, y, w, h in bounds.values()))
