"""Viewport label drawing with one source of truth for click rectangles."""
import blf
import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

_handle = None
label_rects = {}


def view_name(context):
    rv = context.region_data
    space = context.space_data
    if rv is None:
        return 'Perspective'
    if rv.view_perspective == 'CAMERA':
        camera = space.camera or context.scene.camera
        return camera.name if camera else 'Camera'
    if rv.view_perspective == 'PERSP':
        return 'Perspective'
    direction = rv.view_rotation @ Vector((0, 0, 1))
    axes = [((0, 0, 1), 'Top'), ((0, 0, -1), 'Bottom'),
            ((0, -1, 0), 'Front'), ((0, 1, 0), 'Back'),
            ((-1, 0, 0), 'Left'), ((1, 0, 0), 'Right')]
    for axis, label in axes:
        if direction.dot(axis) > .9999:
            return label
    return 'User'


def shading_name(space):
    s = space.shading
    if s.type == 'WIREFRAME':
        return 'Wireframe'
    if s.type == 'MATERIAL':
        return 'Materials'
    if s.type == 'RENDERED':
        return 'Realistic'
    if s.color_type == 'SINGLE':
        return 'Clay'
    if s.light == 'FLAT':
        return 'Flat Color'
    if s.color_type == 'TEXTURE':
        return 'Shaded with Maps'
    return 'Default Shading'


def label_regions(context):
    """Return (menu id, drawn text, x0/y0/x1/y1), clipped to this window region."""
    region = context.region
    if not region or region.type != 'WINDOW' or context.area.type != 'VIEW_3D':
        return []
    scale = max(.5, context.preferences.system.ui_scale)
    blf.size(0, max(9, round(12 * scale)))
    x, y = 8 * scale, region.height - 22 * scale
    shading = context.space_data.shading
    quality = ('High Quality' if shading.type in {'MATERIAL', 'RENDERED'} else
               'Performance' if not shading.show_shadows and not shading.show_cavity else 'Standard')
    labels = [('MAX_MT_vp_general', '+'), ('MAX_MT_vp_point_of_view', view_name(context)),
              ('MAX_MT_vp_quality', quality), ('MAX_MT_vp_shading', shading_name(context.space_data))]
    result = []
    for menu, text in labels:
        text = '[' + text + ']'
        width = blf.dimensions(0, text)[0] + 4 * scale
        if x + width > region.width - 4 * scale:
            break
        result.append((menu, text, (x, y - 3 * scale, x + width, y + 15 * scale)))
        x += width
    return result


def hit_test(context, x, y):
    return next((menu for menu, _, (x0, y0, x1, y1) in label_regions(context)
                 if x0 <= x < x1 and y0 <= y < y1), None)


def _visible(context):
    if not context.workspace or context.workspace.name != '3ds Max':
        return False
    from . import max_chrome
    if max_chrome.timeline_area(context.area):
        return False
    from . import get_prefs
    prefs = get_prefs()
    return not prefs or prefs.show_labels


def draw_labels():
    context = bpy.context
    if context.area.type != 'VIEW_3D' or not _visible(context):
        return
    blf.color(0, .87, .87, .87, 1.)
    regions = label_regions(context)
    keys = ('PLUS', 'VIEW', 'QUALITY', 'SHADING')
    label_rects[context.region.as_pointer()] = [(key, *rect) for key, (_, _, rect) in zip(keys, regions)]
    for _, text, (x0, y0, _, _) in regions:
        blf.position(0, x0, y0 + 3 * context.preferences.system.ui_scale, 0)
        blf.draw(0, text)


@persistent
def _load(_):
    # The callback resolves context each draw. No area/region survives a file load.
    label_rects.clear()
    unregister_handler()
    register_handler()


def register_handler():
    global _handle
    if _handle is None and not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw_labels, (), 'WINDOW', 'POST_PIXEL')


def unregister_handler():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None


def register():
    register_handler()
    if _load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load)


def unregister():
    if _load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load)
    unregister_handler()
    label_rects.clear()


classes = ()
