"""Max-style ViewCube, drawn and picked independently in every viewport region."""

import math
import os
import sys
import time

import bpy
import gpu
from bpy.props import EnumProperty
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Matrix, Quaternion, Vector

_handle = None
_keys = []
_gizmos = {}
_hover = None
_menu_target = None
_animations = {}
_shader = None
_smooth_shader = None
_image_shader = None
_atlas_image = None
_atlas_texture = None
_offscreen = None
_enabled = False

FACES = (((0, 0, 1), 'TOP'), ((0, 0, -1), 'BOTTOM'),
         ((0, -1, 0), 'FRONT'), ((0, 1, 0), 'BACK'),
         ((-1, 0, 0), 'LEFT'), ((1, 0, 0), 'RIGHT'))
SIZES = {'TINY': 16, 'SMALL': 22, 'NORMAL': 30, 'LARGE': 40}
LABELS = tuple(label for _, label in FACES) + ('N', 'E', 'S', 'W')


def rotation_for(direction, basis=None):
    """View rotation looking from a cube face, edge or corner toward its centre."""
    d = Vector(direction).normalized()
    if abs(d.z) > .99999:
        q = Quaternion() if d.z > 0 else Euler((math.pi, 0, 0)).to_quaternion()
    else:
        q = (-d).to_track_quat('-Z', 'Y')
    return basis @ q if basis is not None else q


def clicked_rotation(direction, current, basis, upright):
    """Keep world up, or carry the current roll along the shortest view change."""
    if upright:
        return rotation_for(direction, basis)
    start = current @ Vector((0, 0, 1))
    end = basis @ Vector(direction).normalized()
    return start.rotation_difference(end) @ current


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


def _face_axes(n):
    if n.z:
        u = Vector((1, 0, 0))
    else:
        u = Vector((-n.y, n.x, 0))
    return u, n.cross(u)


def cube_facets():
    """Six inset faces, twelve chamfer strips and eight triangular corners."""
    facets = []
    inset = .9
    for normal, label in FACES:
        n = Vector(normal)
        u, v = _face_axes(n)
        vertices = [n + u * x + v * y for x, y in
                    ((-inset, -inset), (inset, -inset), (inset, inset), (-inset, inset))]
        facets.append(dict(normal=normal, label=label, vertices=vertices))
    for axis in range(3):
        a, b = [i for i in range(3) if i != axis]
        for sa in (-1, 1):
            for sb in (-1, 1):
                n = Vector((0, 0, 0))
                n[a], n[b] = sa, sb
                vertices = []
                for along, va, vb in ((-inset, 1, inset), (inset, 1, inset),
                                      (inset, inset, 1), (-inset, inset, 1)):
                    p = Vector((0, 0, 0))
                    p[axis], p[a], p[b] = along, sa * va, sb * vb
                    vertices.append(p)
                facets.append(dict(normal=tuple(n), label=None, vertices=vertices))
    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                n = Vector((x, y, z))
                vertices = []
                for axis in range(3):
                    p = n * inset
                    p[axis] = n[axis]
                    vertices.append(p)
                facets.append(dict(normal=tuple(n), label=None, vertices=vertices))
    return facets


def cube_geometry(rotation, cx, cy, radius):
    """Project the same solid used for drawing and face/edge/corner picking."""
    inv = rotation.inverted()
    def project(p):
        p = inv @ p
        return (cx + radius * p.x, cy + radius * p.y)
    faces = []
    light = Vector((-.45, -.6, 1)).normalized()
    face_on = max(abs(v) for v in rotation @ Vector((0, 0, 1))) > .99999
    for facet in cube_facets():
        n = Vector(facet['normal'])
        if (inv @ n).z <= .00001:
            continue
        if face_on and not facet['label']:
            continue
        poly = [project(p) for p in facet['vertices']]
        patches = []
        if facet['label']:
            u, v = _face_axes(n)
            extent = 1 if face_on else .9
            if face_on:
                poly = [project(n + u * x + v * y) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cuts = (-extent, -.64, .64, extent)
            for i in range(3):
                for j in range(3):
                    a, b, c, d = cuts[i], cuts[i + 1], cuts[j], cuts[j + 1]
                    patch = [project(n + u * x + v * y) for x, y in ((a, c), (b, c), (b, d), (a, d))]
                    target = n + u * (i - 1) + v * (j - 1)
                    patches.append((tuple(int(x) for x in target), patch))
        else:
            patches.append((tuple(int(x) for x in n), poly))
        faces.append(dict(normal=facet['normal'], label=facet['label'], poly=poly, patches=patches,
                          vertices=facet['vertices'], light=.62 + .23 * max(0, n.normalized().dot(light))))
    return faces


def _inside(poly, x, y):
    if abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) < .001:
        return False
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
    # Auxiliary canvases must not share the viewport's offscreen GPU buffer.
    editors = sys.modules.get(__package__ + '.max_editor_windows')
    if editors and context.area:
        host = editors._hosts.get(context.window.as_pointer()) if context.window else None
        if (host and host.area == context.area) or context.area.as_pointer() in editors._docked:
            return False
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
    return right - 2.8 * r - 8 * scale, top - 2.8 * r - 8 * scale, r


def geometry(context):
    cx, cy, r = layout(context)
    return cube_geometry(_basis(context.scene).inverted() @ context.region_data.view_rotation, cx, cy, r)


def _face_on(context):
    q = _basis(context.scene).inverted() @ context.region_data.view_rotation
    return context.region_data.view_perspective == 'ORTHO' and max(abs(v) for v in q @ Vector((0, 0, 1))) > .9999


def _controls(context):
    cx, cy, r = layout(context)
    controls = [('HOME', cx - 2.5 * r, cy + 2.15 * r)]
    if _face_on(context):
        controls += [('UP', cx, cy + 1.32 * r), ('DOWN', cx, cy - 1.32 * r),
                     ('LEFT', cx - 1.32 * r, cy), ('RIGHT', cx + 1.32 * r, cy),
                     ('ROLL_LEFT', cx + 1.05 * r, cy + 2.32 * r),
                     ('ROLL_RIGHT', cx + 2.32 * r, cy + 1.05 * r)]
    return controls


def hit(context, x, y):
    if not visible(context):
        return None
    cx, cy, r = layout(context)
    if _face_on(context) and 2.25 * r < math.hypot(x - cx, y - cy) < 2.85 * r:
        angle = math.degrees(math.atan2(y - cy, x - cx))
        if 50 < angle < 85:
            return 'ROLL_LEFT'
        if 5 < angle < 40:
            return 'ROLL_RIGHT'
    for name, px, py in _controls(context):
        if abs(x - px) < .25 * r and abs(y - py) < .25 * r:
            return name
    target = pick(geometry(context), x, y)
    if target is not None:
        return target
    q = _basis(context.scene).inverted() @ context.region_data.view_rotation
    if any(_inside(poly, x, y) for poly in compass_geometry(q, cx, cy, r)):
        return 'COMPASS'
    # At a side elevation the ground plane is edge-on. Keep the visible line
    # usable after mouse coordinates are rounded to physical pixels.
    if any((x - px) ** 2 + (y - py) ** 2 < max(2, .1 * r) ** 2 for px, py in _compass(context)):
        return 'COMPASS'
    return None


def compass_geometry(rotation, cx, cy, radius):
    inv = rotation.inverted()
    def point(a, r):
        p = inv @ Vector((r * math.sin(a), r * math.cos(a), -1.18))
        return cx + radius * p.x, cy + radius * p.y
    return [[point(a, r) for a, r in ((i * math.tau / 96, 1.69),
                                     (i * math.tau / 96, 2.15),
                                     ((i + 1) * math.tau / 96, 2.15),
                                     ((i + 1) * math.tau / 96, 1.69))] for i in range(96)]


def _compass(context):
    cx, cy, r = layout(context)
    q = _basis(context.scene).inverted() @ context.region_data.view_rotation
    return [(sum(x for x, y in poly) / 4, sum(y for x, y in poly) / 4)
            for poly in compass_geometry(q, cx, cy, r)]


def widget_opacity(active, inactive):
    # Nathan wants some transparency even while using the cube.
    return .8 if active else min(.7, int(inactive) / 100)


def _poly(points, color, line=False, colors=None):
    global _shader, _smooth_shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    if line:
        coords, kind = points, 'LINE_STRIP'
    else:
        coords = [p for i in range(1, len(points) - 1) for p in (points[0], points[i], points[i + 1])]
        kind = 'TRIS'
    if colors is not None:
        if _smooth_shader is None:
            _smooth_shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        shades = [c for i in range(1, len(points) - 1) for c in (colors[0], colors[i], colors[i + 1])]
        batch = batch_for_shader(_smooth_shader, kind, {'pos': coords, 'color': shades})
        _smooth_shader.bind()
        batch.draw(_smooth_shader)
    else:
        batch = batch_for_shader(_shader, kind, {'pos': coords})
        _shader.bind()
        _shader.uniform_float('color', color)
        batch.draw(_shader)


def _texture_quad(texture, points, uv, color, sample_step=(0, 0)):
    global _image_shader
    if _image_shader is None:
        interface = gpu.types.GPUStageInterfaceInfo('viewcube_uv')
        interface.smooth('VEC2', 'uv')
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'color')
        info.push_constant('VEC2', 'sampleStep')
        info.sampler(0, 'FLOAT_2D', 'image')
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'VEC2', 'texCoord')
        info.vertex_out(interface)
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source('void main() { uv = texCoord; gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }')
        info.fragment_source('''void main() {
            vec4 pixel = vec4(0.0);
            if (sampleStep.x == 0.0) { pixel = texture(image, uv); }
            else {
                for (int y = 0; y < 4; y++) {
                    for (int x = 0; x < 4; x++) {
                        pixel += texture(image, uv + (vec2(x, y) - 1.5) * sampleStep) / 16.0;
                    }
                }
            }
            if (sampleStep.x != 0.0 && pixel.a > 0.0) {
                // The offscreen stores the widget's sRGB artwork. Composite in
                // linear light. Dark ink needs a little more coverage over
                // bright viewports, while faces retain the group opacity.
                vec3 rgb = pixel.rgb / pixel.a;
                float darkest = min(rgb.r, min(rgb.g, rgb.b));
                float lightest = max(rgb.r, max(rgb.g, rgb.b));
                float ink = (1.0 - smoothstep(0.40, 0.55, lightest))
                          * (1.0 - smoothstep(0.16, 0.25, lightest - darkest));
                float opacity = color.a * mix(1.0, 1.125, ink);
                rgb = mix(rgb / 12.92, pow((rgb + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), rgb));
                fragColor = vec4(rgb * pixel.a * opacity, pixel.a * opacity);
            }
            else { fragColor = pixel * color; }
        }''')
        _image_shader = gpu.shader.create_from_info(info)
    batch = batch_for_shader(_image_shader, 'TRIS',
                             {'pos': points, 'texCoord': uv}, indices=((0, 1, 2), (0, 2, 3)))
    _image_shader.bind()
    _image_shader.uniform_sampler('image', texture)
    _image_shader.uniform_float('color', color)
    _image_shader.uniform_float('sampleStep', sample_step)
    batch.draw(_image_shader)


def _label(label, poly):
    """Sample a bold, antialiased label atlas through the face's projected quad."""
    global _atlas_image, _atlas_texture
    if _atlas_texture is None:
        _atlas_image = bpy.data.images.load(os.path.join(os.path.dirname(__file__), 'viewcube_labels.png'),
                                            check_existing=False)
        _atlas_image.colorspace_settings.name = 'Non-Color'
        _atlas_texture = gpu.texture.from_image(_atlas_image)
    i = LABELS.index(label)
    x, y = i % 4 / 4, 1 - (i // 4 + 1) / 4
    uv = ((x, y), (x + .25, y), (x + .25, y + .25), (x, y + .25))
    _texture_quad(_atlas_texture, poly, uv, (.08, .16, .26, 1))


def _roll_arrow(cx, cy, r, start, end, color):
    # Both arrows follow the top-right of the compass, as in Max's face views.
    steps = 24
    angles = [start + (end - start) * i / steps for i in range(steps + 1)]
    def point(a, radius):
        return cx + radius * r * math.cos(a), cy + radius * r * math.sin(a)
    for a, b in zip(angles, angles[1:]):
        _poly([point(a, 2.48), point(a, 2.61), point(b, 2.61), point(b, 2.48)], color)
    outline = (.48, .54, .63, 1)
    for radius in (2.48, 2.61):
        _poly([point(a, radius) for a in angles], outline, line=True)
    a = end
    sign = 1 if end > start else -1
    head = [point(a + sign * .09, 2.545), point(a - sign * .08, 2.35), point(a - sign * .08, 2.74)]
    _poly(head, color)
    _poly(head + head[:1], outline, line=True)


def _draw_art(context, current):
    cx, cy, r = layout(context)
    q = context.region_data.view_rotation.inverted() @ _basis(context.scene)
    rotation = q.inverted()
    for poly in compass_geometry(rotation, cx, cy, r):
        _poly(poly, (.73, .77, .82, 1))
    # Inner rim gives the broad, flat band the same recessed centre as Max.
    for i in range(96):
        rim = []
        for a, radius in ((i * math.tau / 96, 1.69), (i * math.tau / 96, 1.80),
                          ((i + 1) * math.tau / 96, 1.80), ((i + 1) * math.tau / 96, 1.69)):
            p = q @ Vector((radius * math.sin(a), radius * math.cos(a), -1.18))
            rim.append((cx + r * p.x, cy + r * p.y))
        _poly(rim, (.20, .24, .29, 1))
    for name, direction in (('N', (0, 1)), ('E', (1, 0)), ('S', (0, -1)), ('W', (-1, 0))):
        centre = Vector((direction[0] * 1.965, direction[1] * 1.965, -1.18))
        poly = []
        for x, y in ((-.55, -.55), (.55, -.55), (.55, .55), (-.55, .55)):
            p = q @ (centre + Vector((x, y, 0)))
            poly.append((cx + r * p.x, cy + r * p.y))
        _label(name, poly)
    if not _face_on(context):
        p = [q @ Vector(v) for v in ((-.1, 1.72, -1.18), (.1, 1.72, -1.18), (0, 1.52, -1.18))]
        _poly([(cx + r * v.x, cy + r * v.y) for v in p], (.37, .43, .51, 1))
    for face in geometry(context):
        light = face['light']
        shades = []
        for v in face['vertices']:
            shade = light + .025 * v.z
            shades.append((shade * .98, shade, min(1, shade * 1.055), 1))
        _poly(face['poly'], None, colors=shades)
        if isinstance(current, tuple):
            for target, patch in face['patches']:
                if target == current:
                    _poly(patch, (.12, .27, .45, 1))
                    _poly(patch + patch[:1], (.97, .78, .16, 1), line=True)
        _poly(face['poly'] + face['poly'][:1], (.35, .38, .42, 1), line=True)
        if face['label'] and _prefs().viewcube_size != 'TINY':
            _label(face['label'], face['poly'])
    for name, x, y in _controls(context):
        color = (.24, .59, .91, 1) if current == name else (.78, .81, .86, 1)
        if name == 'HOME':
            house = [(x - r * .16, y), (x - r * .16, y - r * .21),
                     (x + r * .16, y - r * .21), (x + r * .16, y)]
            roof = [(x - r * .26, y), (x, y + r * .26), (x + r * .26, y)]
            for poly in (house, roof):
                _poly(poly, color)
                _poly(poly + poly[:1], (.45, .51, .60, 1), line=True)
            _poly([(x - r * .04, y - r * .21), (x - r * .04, y + r * .02),
                   (x + r * .04, y + r * .02), (x + r * .04, y - r * .21)], (.58, .64, .73, 1))
        elif name.startswith('ROLL'):
            start, end = ((math.radians(57), math.radians(78)) if name == 'ROLL_LEFT'
                          else (math.radians(33), math.radians(12)))
            _roll_arrow(cx, cy, r, start, end, color)
        else:
            dx, dy = {'UP': (0, -1), 'DOWN': (0, 1), 'LEFT': (1, 0), 'RIGHT': (-1, 0)}[name]
            _poly([(x + dx * .13 * r, y + dy * .13 * r),
                   (x - dx * .09 * r + dy * .14 * r, y - dy * .09 * r - dx * .14 * r),
                   (x - dx * .09 * r - dy * .14 * r, y - dy * .09 * r + dx * .14 * r)], color)


def _draw():
    global _offscreen
    context = bpy.context
    if not visible(context):
        return
    cx, cy, r = layout(context)
    current = _hover[1] if _hover and _hover[0] == context.region.as_pointer() else None
    alpha = widget_opacity(current is not None, _prefs().viewcube_opacity)
    # Supersample the complete widget. Apply opacity only once to the composited
    # solid, so rear compass segments cannot bleed through the cube's faces.
    size = int(math.ceil(7 * r * 4))
    if _offscreen is None or _offscreen.width != size:
        if _offscreen is not None:
            _offscreen.free()
        _offscreen = gpu.types.GPUOffScreen(size, size)
    x0, x1, y0, y1 = cx - 3.5 * r, cx + 3.5 * r, cy - 3.5 * r, cy + 3.5 * r
    viewport = gpu.state.viewport_get()
    depth_test, depth_mask = gpu.state.depth_test_get(), gpu.state.depth_mask_get()
    blend, line_width = gpu.state.blend_get(), gpu.state.line_width_get()
    try:
        with _offscreen.bind():
            gpu.state.depth_test_set('NONE')
            gpu.state.depth_mask_set(False)
            gpu.state.active_framebuffer_get().clear(color=(0, 0, 0, 0))
            gpu.state.viewport_set(0, 0, size, size)
            gpu.state.blend_set('ALPHA')
            with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix(((2 / (x1 - x0), 0, 0, -(x1 + x0) / (x1 - x0)),
                                                         (0, 2 / (y1 - y0), 0, -(y1 + y0) / (y1 - y0)),
                                                         (0, 0, -1, 0), (0, 0, 0, 1))))
                gpu.state.line_width_set(3.5)
                _draw_art(context, current)
        gpu.state.viewport_set(*viewport)
        gpu.state.blend_set('ALPHA_PREMULT')
        _texture_quad(_offscreen.texture_color, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                      ((0, 0), (1, 0), (1, 1), (0, 1)), (alpha, alpha, alpha, alpha), (1 / size, 1 / size))
    finally:
        gpu.state.viewport_set(*viewport)
        gpu.state.line_width_set(line_width)
        gpu.state.blend_set(blend)
        gpu.state.depth_test_set(depth_test)
        gpu.state.depth_mask_set(depth_mask)


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
    transition(context, clicked_rotation(target, context.region_data.view_rotation,
                                        _basis(context.scene), _prefs().viewcube_upright))


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
        bpy.ops.max.quad_menu('INVOKE_DEFAULT')
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
    spaces = {}
    for ws in bpy.data.workspaces:
        for screen in ws.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type != 'VIEW_3D':
                        continue
                    key = space.as_pointer()
                    spaces[key] = space
                    if active and ws.name == '3ds Max':
                        live.add(key)
                        if key not in _gizmos:
                            _gizmos[key] = space.show_gizmo_navigate
                        if space.show_gizmo_navigate:
                            space.show_gizmo_navigate = False
                            area.tag_redraw()
    for key in list(_gizmos):
        if key not in live:
            original = _gizmos.pop(key)
            # Nested RNA wrappers can outlive their freed Screen owner without
            # raising ReferenceError. Reacquire live spaces before any write.
            space = spaces.get(key)
            if space is not None:
                space.show_gizmo_navigate = original


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


def _release_artwork():
    global _offscreen, _atlas_image, _atlas_texture, _shader, _image_shader, _smooth_shader
    offscreen, image = _offscreen, _atlas_image
    _offscreen = _atlas_image = _atlas_texture = None
    _shader = _image_shader = _smooth_shader = None
    if offscreen is not None:
        try:
            offscreen.free()
        except (ReferenceError, RuntimeError):
            pass
    if image is not None:
        try:
            bpy.data.images.remove(image)
        except (ReferenceError, RuntimeError):
            pass


@persistent
def _load_pre(_):
    _release_artwork()


@persistent
def _save_pre(_):
    # Serialize the user's setting, not our temporary replacement. The native
    # space field follows its viewport across reloads without storing RNA.
    for ws in bpy.data.workspaces:
        for screen in ws.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == 'VIEW_3D' and space.as_pointer() in _gizmos:
                        space.show_gizmo_navigate = _gizmos[space.as_pointer()]


@persistent
def _save_post(_):
    sync_gizmos()


@persistent
def _load_post(_):
    global _hover, _menu_target
    # File loading replaces Images, areas and regions. Never retain their RNA
    # or GPU wrappers, even when a load occurred without our pre callback.
    _release_artwork()
    _animations.clear()
    _gizmos.clear()
    _hover = _menu_target = None
    sync_gizmos()


def register():
    global _handle, _enabled
    _enabled = True
    bpy.app.handlers.load_pre.append(_load_pre)
    bpy.app.handlers.load_post.append(_load_post)
    bpy.app.handlers.save_pre.append(_save_pre)
    bpy.app.handlers.save_post.append(_save_post)
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
    bpy.app.timers.register(_maintain, first_interval=.1, persistent=True)


def unregister():
    global _handle, _enabled, _hover, _menu_target
    _enabled = False
    for handlers, callback in ((bpy.app.handlers.load_pre, _load_pre),
                               (bpy.app.handlers.load_post, _load_post),
                               (bpy.app.handlers.save_pre, _save_pre),
                               (bpy.app.handlers.save_post, _save_post)):
        if callback in handlers:
            handlers.remove(callback)
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
    _release_artwork()
