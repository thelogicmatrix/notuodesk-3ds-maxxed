"""Max-style ViewCube, drawn and picked independently in every viewport region."""

import math
import time

import blf
import bpy
import gpu
from bpy.props import EnumProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Quaternion, Vector

_handle = None
_keys = []
_gizmos = {}
_hover = None
_menu_target = None
_animations = {}
_shader = None
_enabled = False

FACES = (((0, 0, 1), 'TOP'), ((0, 0, -1), 'BOTTOM'),
         ((0, -1, 0), 'FRONT'), ((0, 1, 0), 'BACK'),
         ((-1, 0, 0), 'LEFT'), ((1, 0, 0), 'RIGHT'))
SIZES = {'TINY': 22, 'SMALL': 30, 'NORMAL': 40, 'LARGE': 50}


def rotation_for(direction, basis=None):
    """View rotation looking from a cube face, edge or corner toward its centre."""
    d = Vector(direction).normalized()
    if abs(d.z) > .99999:
        q = Quaternion() if d.z > 0 else Euler((math.pi, 0, 0)).to_quaternion()
    else:
        q = (-d).to_track_quat('-Z', 'Y')
    return basis @ q if basis is not None else q


def orbit_rotation(rotation, dx, dy, upright):
    if not upright:
        return rotation @ Quaternion((0, 1, 0), -dx * .01) @ Quaternion((1, 0, 0), dy * .01)
    d = rotation @ Vector((0, 0, 1))
    # The viewing direction has no yaw at either pole. Use the rotation's yaw
    # there so signed zero cannot introduce an accidental half-turn.
    yaw = rotation.to_euler('XYZ').z if abs(d.z) > .99999 else math.atan2(d.x, -d.y)
    yaw -= dx * .01
    elevation = max(-math.pi / 2 + .001, min(math.pi / 2 - .001,
                    math.asin(max(-1, min(1, d.z))) + dy * .01))
    return rotation_for((math.cos(elevation) * math.sin(yaw),
                         -math.cos(elevation) * math.cos(yaw), math.sin(elevation)))


def _basis(scene):
    return Quaternion(scene.get('max_viewcube_front', (1, 0, 0, 0)))


def cube_geometry(rotation, cx, cy, radius):
    """Projected faces, each split into nine face/edge/corner picking patches."""
    inv = rotation.inverted()
    faces = []
    for normal, label in FACES:
        n = Vector(normal)
        if (inv @ n).z <= .00001:
            continue
        u = Vector((1, 0, 0)) if n.x == 0 else Vector((0, 1, 0))
        v = n.cross(u)
        def project(p):
            p = inv @ p
            return (cx + radius * p.x, cy + radius * p.y)
        patches = []
        cuts = (-1, -.64, .64, 1)
        for i in range(3):
            for j in range(3):
                a, b, c, d = cuts[i], cuts[i + 1], cuts[j], cuts[j + 1]
                poly = [project(n + u * x + v * y) for x, y in ((a, c), (b, c), (b, d), (a, d))]
                target = n + u * (i - 1) + v * (j - 1)
                patches.append((tuple(int(x) for x in target), poly))
        poly = [project(n + u * x + v * y) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        faces.append(dict(normal=normal, label=label, poly=poly, patches=patches,
                          centre=project(n), right=project(n + u), up=project(n + v),
                          light=.64 + .28 * (inv @ n).z))
    return faces


def _inside(poly, x, y):
    signs = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        signs.append((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]))
    return all(s >= -.01 for s in signs) or all(s <= .01 for s in signs)


def pick(geometry, x, y):
    for face in geometry:
        for target, poly in face['patches']:
            if _inside(poly, x, y):
                return target
    return None


def _prefs():
    from . import get_prefs
    return get_prefs()


def visible(context):
    p = _prefs()
    return bool(_enabled and p and p.show_viewcube and context.workspace
                and context.workspace.name == '3ds Max' and context.region_data
                and context.region_data.view_perspective != 'CAMERA')


def layout(context):
    region, area = context.region, context.area
    scale = context.preferences.system.ui_scale
    r = SIZES[_prefs().viewcube_size] * scale
    right, top = region.width, region.height
    # Header and sidebar can overlay a WINDOW region. Account for those only
    # on the outside of the quad layout, never at an internal quad boundary.
    for reg in area.regions:
        if reg.type == 'UI' and context.space_data.show_region_ui and reg.width > 1:
            if region.x + region.width >= reg.x + reg.width - 2:
                right -= reg.width
        if reg.type in {'HEADER', 'TOOL_HEADER'} and reg.height > 1:
            if region.y + region.height >= reg.y + reg.height - 2 and reg.y > region.y + region.height / 2:
                top -= reg.height
    return right - 2 * r - 12 * scale, top - 2 * r - 15 * scale, r


def geometry(context):
    cx, cy, r = layout(context)
    return cube_geometry(_basis(context.scene).inverted() @ context.region_data.view_rotation, cx, cy, r)


def _face_on(context):
    q = _basis(context.scene).inverted() @ context.region_data.view_rotation
    return context.region_data.view_perspective == 'ORTHO' and max(abs(v) for v in q @ Vector((0, 0, 1))) > .9999


def _controls(context):
    cx, cy, r = layout(context)
    controls = [('HOME', cx - 1.6 * r, cy + 1.65 * r)]
    if _face_on(context):
        controls += [('UP', cx, cy + 1.32 * r), ('DOWN', cx, cy - 1.32 * r),
                     ('LEFT', cx - 1.32 * r, cy), ('RIGHT', cx + 1.32 * r, cy),
                     ('ROLL_LEFT', cx - .55 * r, cy + 1.75 * r),
                     ('ROLL_RIGHT', cx + .55 * r, cy + 1.75 * r)]
    return controls


def hit(context, x, y):
    if not visible(context):
        return None
    cx, cy, r = layout(context)
    for name, px, py in _controls(context):
        if abs(x - px) < .25 * r and abs(y - py) < .25 * r:
            return name
    target = pick(geometry(context), x, y)
    if target is not None:
        return target
    if any((x - px) ** 2 + (y - py) ** 2 < (.22 * r) ** 2 for px, py in _compass(context)):
        return 'COMPASS'
    return None


def _compass(context):
    cx, cy, r = layout(context)
    q = context.region_data.view_rotation.inverted() @ _basis(context.scene)
    points = []
    for i in range(65):
        a = i * 2 * math.pi / 64
        p = q @ Vector((1.65 * math.sin(a), 1.65 * math.cos(a), -1.65))
        points.append((cx + r * p.x, cy + r * p.y))
    return points


def _poly(points, color, line=False):
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    if line:
        coords, kind = points, 'LINE_STRIP'
    else:
        coords = [p for i in range(1, len(points) - 1) for p in (points[0], points[i], points[i + 1])]
        kind = 'TRIS'
    batch = batch_for_shader(_shader, kind, {'pos': coords})
    _shader.bind()
    _shader.uniform_float('color', color)
    batch.draw(_shader)


def _text(text, x, y, size, color, angle=0):
    blf.size(0, size)
    blf.color(0, *color)
    w, h = blf.dimensions(0, text)
    blf.enable(0, blf.ROTATION)
    blf.rotation(0, angle)
    blf.position(0, x - .5 * w * math.cos(angle) + .5 * h * math.sin(angle),
                 y - .5 * w * math.sin(angle) - .5 * h * math.cos(angle), 0)
    blf.draw(0, text)
    blf.disable(0, blf.ROTATION)


def _draw():
    context = bpy.context
    if not visible(context):
        return
    cx, cy, r = layout(context)
    current = _hover[1] if _hover and _hover[0] == context.region.as_pointer() else None
    alpha = 1.0 if current is not None else int(_prefs().viewcube_opacity) / 100
    gpu.state.blend_set('ALPHA')
    try:
        _poly(_compass(context), (.66, .67, .68, alpha), line=True)
        q = context.region_data.view_rotation.inverted() @ _basis(context.scene)
        for name, direction in (('N', (0, 1, -1.65)), ('E', (1, 0, -1.65)),
                                ('S', (0, -1, -1.65)), ('W', (-1, 0, -1.65))):
            p = q @ Vector((direction[0] * 1.85, direction[1] * 1.85, direction[2]))
            _text(name, cx + r * p.x, cy + r * p.y, r * .27, (.8, .8, .8, alpha))
        for face in geometry(context):
            light = face['light']
            _poly(face['poly'], (light, light, light, alpha))
            if isinstance(current, tuple):
                for target, patch in face['patches']:
                    if target == current:
                        _poly(patch, (.23, .57, .88, alpha))
            _poly(face['poly'] + face['poly'][:1], (.28, .29, .30, alpha), line=True)
            if _prefs().viewcube_size != 'TINY':
                # Keep words legible on a foreshortened face, as on Max's cube.
                x, y = face['centre']
                dx = face['right'][0] - x
                dy = face['right'][1] - y
                angle = math.atan2(dy, dx)
                if abs(angle) > math.pi / 2:
                    angle += math.pi
                size = min(r * .32, math.hypot(dx, dy) * .48)
                _text(face['label'], x, y, max(5, size), (.18, .19, .20, alpha), angle)
        for name, x, y in _controls(context):
            color = (.24, .59, .91, alpha) if current == name else (.72, .73, .74, alpha)
            if name == 'HOME':
                _poly([(x - r * .18, y), (x - r * .18, y - r * .18),
                       (x + r * .18, y - r * .18), (x + r * .18, y)], color)
                _poly([(x - r * .27, y), (x, y + r * .23), (x + r * .27, y)], color)
            elif name.startswith('ROLL'):
                sign = -1 if name == 'ROLL_LEFT' else 1
                points = [(x + .16 * r * math.cos(a), y + .16 * r * math.sin(a))
                          for a in [i * math.pi / 12 for i in range(17)]]
                _poly(points, color, line=True)
                _poly([(x + sign * .24 * r, y + .12 * r), (x, y + .19 * r), (x + sign * .12 * r, y - .02 * r)], color)
            else:
                dx, dy = {'UP': (0, 1), 'DOWN': (0, -1), 'LEFT': (-1, 0), 'RIGHT': (1, 0)}[name]
                _poly([(x + dx * .15 * r, y + dy * .15 * r),
                       (x - dx * .1 * r + dy * .13 * r, y - dy * .1 * r - dx * .13 * r),
                       (x - dx * .1 * r - dy * .13 * r, y - dy * .1 * r + dx * .13 * r)], color)
    finally:
        gpu.state.blend_set('NONE')


def transition(context, rotation, perspective='ORTHO', location=None, distance=None):
    rv = context.region_data
    rv.lock_rotation = False
    rv.view_perspective = perspective
    duration = context.preferences.view.smooth_view / 1000
    destination = (rotation.copy(), Vector(location) if location is not None else rv.view_location.copy(),
                   distance if distance is not None else rv.view_distance)
    key = context.region.as_pointer()
    _animations.pop(key, None)
    if duration == 0 or bpy.app.background:
        rv.view_rotation, rv.view_location, rv.view_distance = destination
        context.area.tag_redraw()
        return
    record = (rv, context.area, time.monotonic(), duration, rv.view_rotation.copy(),
              rv.view_location.copy(), rv.view_distance, destination)
    _animations[key] = record
    def step():
        if not _enabled or _animations.get(key) is not record:
            return None
        try:
            rv, area, started, duration, q, loc, dist, (endq, endl, endd) = record
            t = min(1, (time.monotonic() - started) / duration)
            t = t * t * (3 - 2 * t)
            rv.view_rotation = q.slerp(endq, t)
            rv.view_location = loc.lerp(endl, t)
            rv.view_distance = dist + (endd - dist) * t
            area.tag_redraw()
            if t < 1:
                return .016
        except ReferenceError:
            pass
        _animations.pop(key, None)
        return None
    bpy.app.timers.register(step)


def _snap(context, target):
    transition(context, rotation_for(target, _basis(context.scene)))


def _home(context):
    scene = context.scene
    rotation = Quaternion(scene.get('max_viewcube_home_rotation',
                          tuple(Euler((math.radians(65), 0, math.radians(-45))).to_quaternion())))
    transition(context, rotation, scene.get('max_viewcube_home_projection', 'PERSP'),
               scene.get('max_viewcube_home_location', (0, 0, 0)), scene.get('max_viewcube_home_distance', 10.0))


def _set_hover(context, hover):
    global _hover
    if hover != _hover:
        _hover = hover
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _open_menu(context):
    global _menu_target
    _menu_target = (context.window, context.area, context.region)
    bpy.ops.wm.call_menu(name='MAX_MT_viewcube')


class MAX_OT_viewcube_mouse(bpy.types.Operator):
    """Pick or drag the ViewCube. All input outside it passes through"""
    bl_idname = 'max.viewcube_mouse'
    bl_label = 'ViewCube'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if context.region is None or context.region.type != 'WINDOW' or context.area.type != 'VIEW_3D':
            _set_hover(context, None)
            return {'PASS_THROUGH'}
        target = hit(context, event.mouse_x - context.region.x, event.mouse_y - context.region.y)
        hover = (context.region.as_pointer(), target) if target is not None else None
        _set_hover(context, hover)
        if event.type == 'MOUSEMOVE' or target is None:
            return {'PASS_THROUGH'}
        if event.type == 'RIGHTMOUSE':
            _open_menu(context)
            return {'FINISHED'}
        self.target = target
        self.origin = (event.mouse_x, event.mouse_y)
        self.rotation = context.region_data.view_rotation.copy()
        self.region = context.region
        self.dragged = False
        _animations.pop(context.region.as_pointer(), None)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not visible(context):
            return {'CANCELLED'}
        rv = self.region.data
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            rv.view_rotation = self.rotation
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            dx, dy = event.mouse_x - self.origin[0], event.mouse_y - self.origin[1]
            if dx * dx + dy * dy > 16:
                self.dragged = True
            if self.dragged:
                rv.lock_rotation = False
                if self.target == 'COMPASS':
                    rv.view_rotation = Quaternion((0, 0, 1), -dx * .01) @ self.rotation
                else:
                    rv.view_rotation = orbit_rotation(self.rotation, dx, dy, _prefs().viewcube_upright)
                if rv.view_perspective == 'CAMERA':
                    rv.view_perspective = 'PERSP'
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.dragged:
                if _prefs().viewcube_snap:
                    candidates = [rotation_for((x, y, z), _basis(context.scene))
                                  for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)]
                    closest = min(candidates, key=lambda q: q.rotation_difference(rv.view_rotation).angle)
                    if closest.rotation_difference(rv.view_rotation).angle < math.radians(10):
                        transition(context, closest, rv.view_perspective)
            elif isinstance(self.target, tuple):
                _snap(context, self.target)
            elif self.target == 'HOME':
                _home(context)
            elif self.target.startswith('ROLL'):
                angle = math.pi / 2 * (-1 if self.target == 'ROLL_LEFT' else 1)
                transition(context, rv.view_rotation @ Quaternion((0, 0, 1), angle))
            elif self.target in {'UP', 'DOWN', 'LEFT', 'RIGHT'}:
                axis, angle = {'UP': ((1, 0, 0), -math.pi / 2), 'DOWN': ((1, 0, 0), math.pi / 2),
                               'LEFT': ((0, 1, 0), -math.pi / 2), 'RIGHT': ((0, 1, 0), math.pi / 2)}[self.target]
                direction = rv.view_rotation @ Quaternion(axis, angle) @ Vector((0, 0, 1))
                transition(context, rotation_for(direction) if _prefs().viewcube_upright else rv.view_rotation @ Quaternion(axis, angle))
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class MAX_OT_viewcube_action(bpy.types.Operator):
    bl_idname = 'max.viewcube_action'
    bl_label = 'ViewCube'
    action: EnumProperty(items=[(s, s.replace('_', ' ').title(), '') for s in
                               ('HOME', 'ORTHO', 'PERSP', 'SET_HOME', 'SET_FRONT', 'RESET_FRONT', 'CONFIGURE', 'TOGGLE')])

    def execute(self, context):
        if self.action == 'TOGGLE':
            p = _prefs()
            p.show_viewcube = not p.show_viewcube
            return {'FINISHED'}
        if self.action == 'CONFIGURE':
            bpy.ops.max.viewcube_configure('INVOKE_DEFAULT')
            return {'FINISHED'}
        from .operators import find_view3d
        area, region = find_view3d(context)
        window = context.window
        if _menu_target is not None and context.region and context.region.type != 'WINDOW':
            window, area, region = _menu_target
        if area is None or region is None:
            return {'CANCELLED'}
        with context.temp_override(window=window, area=area, region=region):
            rv = region.data
            scene = context.scene
            if self.action == 'HOME':
                _home(context)
            elif self.action in {'ORTHO', 'PERSP'}:
                rv.view_perspective = self.action
            elif self.action == 'SET_HOME':
                scene['max_viewcube_home_rotation'] = tuple(rv.view_rotation)
                scene['max_viewcube_home_location'] = tuple(rv.view_location)
                scene['max_viewcube_home_distance'] = rv.view_distance
                scene['max_viewcube_home_projection'] = rv.view_perspective
            elif self.action == 'SET_FRONT':
                scene['max_viewcube_front'] = tuple(rv.view_rotation @ rotation_for((0, -1, 0)).inverted())
            elif self.action == 'RESET_FRONT':
                scene['max_viewcube_front'] = (1, 0, 0, 0)
            area.tag_redraw()
        return {'FINISHED'}


class MAX_OT_viewcube_context(bpy.types.Operator):
    """Route Max's existing right-click binding before Blender merges keymaps."""
    bl_idname = 'max.viewcube_context'
    bl_label = 'ViewCube or Quad Menu'

    def invoke(self, context, event):
        if context.region and context.region.type == 'WINDOW':
            if hit(context, event.mouse_x - context.region.x, event.mouse_y - context.region.y) is not None:
                _open_menu(context)
                return {'FINISHED'}
        bpy.ops.wm.call_menu(name='MAX_MT_quad')
        return {'FINISHED'}


def draw_settings(layout, prefs):
    layout.prop(prefs, 'show_viewcube')
    for name in ('viewcube_size', 'viewcube_opacity'):
        row = layout.row()
        row.label(text='ViewCube Size:' if name == 'viewcube_size' else 'Inactive Opacity:')
        row.prop(prefs, name, text='')
    layout.prop(prefs, 'viewcube_snap')
    layout.prop(prefs, 'viewcube_upright')


class MAX_OT_viewcube_configure(bpy.types.Operator):
    bl_idname = 'max.viewcube_configure'
    bl_label = 'ViewCube Configuration'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        draw_settings(self.layout, _prefs())

    def execute(self, context):
        return {'FINISHED'}


class MAX_MT_viewcube(bpy.types.Menu):
    bl_label = 'ViewCube'

    def draw(self, context):
        for action, text in (('HOME', 'Home'), ('ORTHO', 'Orthographic'), ('PERSP', 'Perspective'),
                             ('SET_HOME', 'Set Current View as Home'), ('SET_FRONT', 'Set Current View as Front'),
                             ('RESET_FRONT', 'Reset Front'), ('CONFIGURE', 'Configure')):
            self.layout.operator('max.viewcube_action', text=text).action = action


def sync_gizmos():
    """Remember the original setting once, including newly opened viewports."""
    p = _prefs()
    active = bool(_enabled and p and p.show_viewcube)
    live = set()
    for ws in bpy.data.workspaces:
        for screen in ws.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type != 'VIEW_3D':
                        continue
                    key = space.as_pointer()
                    if active and ws.name == '3ds Max':
                        live.add(key)
                        if key not in _gizmos:
                            _gizmos[key] = (space, space.show_gizmo_navigate)
                        if space.show_gizmo_navigate:
                            space.show_gizmo_navigate = False
                            area.tag_redraw()
    for key in list(_gizmos):
        if key not in live:
            space, original = _gizmos.pop(key)
            try:
                space.show_gizmo_navigate = original
            except ReferenceError:
                pass


def update(self, context):
    sync_gizmos()
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _maintain():
    if not _enabled:
        return None
    sync_gizmos()
    return .25


classes = (MAX_OT_viewcube_mouse, MAX_OT_viewcube_action, MAX_OT_viewcube_context,
           MAX_OT_viewcube_configure, MAX_MT_viewcube)


def register():
    global _handle, _enabled
    _enabled = True
    if bpy.app.background:
        return
    _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Window', space_type='EMPTY', region_type='WINDOW')
        _keys.append((km, km.keymap_items.new('max.viewcube_mouse', 'MOUSEMOVE', 'ANY')))
        for name, space in (('3D View', 'VIEW_3D'), ('Object Mode', 'EMPTY'), ('Mesh', 'EMPTY'), ('Curve', 'EMPTY')):
            km = kc.keymaps.new(name=name, space_type=space, region_type='WINDOW')
            for event in ('LEFTMOUSE', 'RIGHTMOUSE', 'MOUSEMOVE'):
                item = km.keymap_items.new('max.viewcube_mouse', event,
                                          'ANY' if event == 'MOUSEMOVE' else 'PRESS', head=True)
                _keys.append((km, item))
            item = km.keymap_items.new('max.viewcube_action', 'H', 'PRESS', ctrl=True, alt=True, head=True)
            item.properties.action = 'TOGGLE'
            _keys.append((km, item))
    bpy.app.timers.register(_maintain, first_interval=.1, persistent=True)


def unregister():
    global _handle, _enabled, _hover, _menu_target, _shader
    _enabled = False
    if bpy.app.timers.is_registered(_maintain):
        bpy.app.timers.unregister(_maintain)
    sync_gizmos()
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    for km, item in _keys:
        km.keymap_items.remove(item)
    _keys.clear()
    _animations.clear()
    _hover = None
    _menu_target = None
    _shader = None
