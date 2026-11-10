"""Floating Editable Poly caddies. Preview never enters Blender's redo/popup stack."""
import math
from types import SimpleNamespace

import bpy
import bmesh
from bpy.app.handlers import persistent

ACTIONS = {'EXTRUDE', 'CHAMFER', 'CONNECT', 'BEVEL', 'INSET', 'OUTLINE',
           'BRIDGE', 'WELD', 'TESSELLATE', 'MSMOOTH', 'RELAX'}
# Autodesk documents these Shift+click shortcuts on the Modeling ribbon.
SHIFT_ACTIONS = ACTIONS - {'OUTLINE'}
_active = {}


class MeshOps:
    """Native mesh operators inside a preview must not add undo entries."""
    def __getattr__(self, name):
        op = getattr(bpy.ops.mesh, name)
        return lambda **kw: op('EXEC_DEFAULT', False, **kw)


class Snapshot:
    def __init__(self, obj):
        bm = bmesh.from_edit_mesh(obj.data)
        for seq in (bm.verts, bm.edges, bm.faces):
            seq.index_update()
        self.bm = bm.copy()
        self.history = [(type(e).__name__, e.index) for e in bm.select_history]
        self.face = bm.faces.active.index if bm.faces.active else None

    def restore(self, obj):
        bm = bmesh.from_edit_mesh(obj.data)
        mesh = bpy.data.meshes.new('.max_caddy_transfer')
        try:
            self.bm.to_mesh(mesh)
            bm.clear()
            bm.from_mesh(mesh)
        finally:
            bpy.data.meshes.remove(mesh)
        seqs = {'BMVert': bm.verts, 'BMEdge': bm.edges, 'BMFace': bm.faces}
        for seq in seqs.values():
            seq.ensure_lookup_table()
        bm.select_history.clear()
        for kind, index in self.history:
            bm.select_history.add(seqs[kind][index])
        if self.face is not None:
            bm.faces.active = bm.faces[self.face]
        bm.normal_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)

    def free(self):
        if self.bm is not None:
            self.bm.free()
            self.bm = None


class Session:
    """One pristine baseline per iteration, with accepted iterations kept on Cancel."""
    def __init__(self, context, action):
        from . import editable_poly as ep
        from .operators import current_level
        self.obj = context.active_object
        self.was_object = context.mode == 'OBJECT'
        self.level = current_level(context)
        if self.obj is None or self.obj.type != 'MESH':
            raise ValueError('Select a mesh for the caddy')
        if self.obj.data.shape_keys:
            raise ValueError('Apply shape keys before changing topology with a caddy')
        if not self.was_object and len(context.objects_in_mode) != 1:
            raise ValueError('Edit one mesh at a time with a caddy')
        if self.was_object and action not in ep.OBJECT_ACTIONS:
            raise ValueError('Choose a sub-object selection for this caddy')
        self.action = action
        self.store = ep.settings(context, action)
        self.keys = ep.CADDIES[action]
        self.values = SimpleNamespace(**{key: getattr(self.store, key) for key in ep.option_properties()})
        self.closed = False
        self.valid = False
        self.applied = 0
        self.error = ''
        if self.was_object:
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='EDIT')
        self.baseline = Snapshot(self.obj)
        # Object-level operations affect all visible geometry but Cancel restores selection too.
        self.whole = self.was_object

    def preview(self, context):
        from . import editable_poly as ep
        if self.closed:
            return False
        self.baseline.restore(self.obj)
        if self.whole:
            bm = bmesh.from_edit_mesh(self.obj.data)
            for seq in (bm.verts, bm.edges, bm.faces):
                for elem in seq:
                    elem.select_set(not elem.hide)
        command = SimpleNamespace(op=self.action, report=lambda types, text: setattr(self, 'error', text))
        self.error = ''
        try:
            self.valid = ep.run(command, context, 'CADDY_PREVIEW', self.values) == {'FINISHED'}
        except Exception:
            self.baseline.restore(self.obj)
            self.valid = False
            raise
        if not self.valid:
            self.baseline.restore(self.obj)
            self.error = self.error or 'Select suitable sub-objects'
        return self.valid

    def persist(self):
        for key in self.keys:
            setattr(self.store, key, getattr(self.values, key))

    def reselect(self, context, select):
        """Select only against accepted geometry, then preview the new selection once."""
        self.baseline.restore(self.obj)
        select()
        new_baseline = Snapshot(self.obj)
        self.baseline.free()
        self.baseline = new_baseline
        return self.preview(context)

    def apply(self, context):
        if not self.valid:
            return False
        self.persist()
        new_baseline = Snapshot(self.obj)
        self.baseline.free()
        self.baseline = new_baseline
        self.applied += 1
        # Each explicit Apply is an accepted operation. Preview calls never push undo.
        bpy.ops.ed.undo_push(message=self.action.title())
        return True

    def close(self, context, cancel=False):
        if self.closed:
            return
        try:
            if cancel:
                self.baseline.restore(self.obj)
            elif self.valid:
                self.persist()
            if self.was_object:
                bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='OBJECT')
        finally:
            self.baseline.free()
            self.closed = True


# Field artwork comes from max_icons, with vector fallbacks and names on hover.
LABELS = {
    'amount': ('Amount', 'distance'), 'height': ('Height', 'height'),
    'extrusion_type': ('Extrusion Type', 'type'), 'bevel_type': ('Bevel Type', 'type'),
    'local_bias': ('Bias', 'bias'), 'base_width': ('Extrusion Base Width', 'width'),
    'threshold': ('Weld Threshold', 'weld'), 'segments': ('Segments', 'segments'),
    'open': ('Open', 'open'), 'tension': ('Tension', 'tension'),
    'tess_tension': ('Tension', 'tension'),
    'taper': ('Taper', 'taper'), 'bias': ('Bias', 'bias'), 'smooth': ('Smooth', 'smooth'),
    'twist1': ('Twist 1', 'twist'), 'twist2': ('Twist 2', 'twist'),
    'bridge_selection': ('Selection', 'type'), 'pinch': ('Pinch', 'width'),
    'slide': ('Slide', 'bias'), 'smoothness': ('Smoothness', 'smooth'),
    'tessellate_type': ('Type', 'segments'), 'relax': ('Amount', 'relax'),
    'iterations': ('Iterations', 'segments'), 'hold_boundary': ('Hold Boundary Points', 'hold'),
    'hold_outer': ('Hold Outer Points', 'hold'), 'individual': ('Inset Type', 'type'),
    'pick1': ('Pick Border/Polygon 1', 'pick'), 'pick2': ('Pick Border/Polygon 2', 'pick'),
    'separate_smoothing': ('Separate by Smoothing Groups', 'smooth'),
    'separate_materials': ('Separate by Materials', 'material'),
    'weld_counts': ('Before / After', 'weld'),
}
UI_ONLY = {'pick1', 'pick2', 'separate_smoothing', 'separate_materials', 'weld_counts'}


def fields(session):
    keys = list(session.keys)
    if session.action == 'INSET':
        keys = ['individual', 'amount']
    if session.action == 'EXTRUDE':
        if session.level < 4:
            keys = ['amount', 'base_width']
        else:
            keys = ['extrusion_type', 'amount', 'local_bias']
    if session.action == 'BRIDGE' and session.level == 2:
        keys = ['segments', 'smooth', 'bridge_selection']
    if session.action == 'CHAMFER':
        keys = ['amount', 'segments', 'tension', 'open']
    if session.action == 'MSMOOTH':
        keys += ['separate_smoothing', 'separate_materials']
    if session.action == 'BRIDGE':
        keys += ['pick1', 'pick2']
    if session.action == 'WELD':
        keys += ['weld_counts']
    return keys


def enabled(session, key):
    if key in UI_ONLY:
        return False
    if key in {'base_width', 'bridge_selection', 'local_bias'}:
        return False
    if session.action == 'CONNECT' and key in {'pinch', 'slide'}:
        return False
    if session.action == 'TESSELLATE' and key == 'tess_tension':
        return session.values.tessellate_type == 'EDGE'
    if session.action == 'CHAMFER' and key == 'segments' and session.level == 1:
        return False
    return True


def label(session, key):
    if key == 'amount':
        return {'EXTRUDE': 'Extrusion Height', 'BEVEL': 'Outline Amount',
                'INSET': 'Inset Amount', 'OUTLINE': 'Outline Amount',
                'CHAMFER': 'Chamfer Amount'}.get(session.action, 'Amount')
    return LABELS[key][0]


def artwork(session, key):
    from . import max_icons
    name = max_icons.CADDY_OPERATIONS.get(session.action, {}).get(key)
    if name is None:
        return generic_artwork(session, key)
    if key in {'extrusion_type', 'bevel_type', 'tessellate_type'}:
        name += '_'+getattr(session.values, key).lower()
    elif key == 'individual':
        name += '_polygon' if session.values.individual else '_group'
    return name


def generic_artwork(session, key):
    from . import max_icons
    if key == 'amount':
        if session.action == 'EXTRUDE':
            return 'caddy_height'
        if session.action == 'CHAMFER':
            return 'caddy_chamfer'
    if key in {'extrusion_type', 'bevel_type'}:
        return 'caddy_type_' + getattr(session.values, key).lower()
    if key == 'individual':
        return 'caddy_type_polygon' if session.values.individual else 'caddy_type_group'
    if key == 'tessellate_type':
        return 'caddy_type_' + session.values.tessellate_type.lower()
    return max_icons.CADDY_FIELDS[key]


def draw_field_icon(session, key, cx, cy, size):
    from . import max_icons
    return (max_icons.draw(artwork(session, key), cx, cy, size) or
            max_icons.draw(generic_artwork(session, key), cx, cy, size))


def choices(session, key):
    if key in UI_ONLY:
        return []
    if key == 'individual':
        return [(False, 'Group'), (True, 'By Polygon')]
    prop = session.store.bl_rna.properties[key]
    if prop.type == 'ENUM':
        return [(e.identifier, e.name) for e in prop.enum_items]
    return []


class Caddy:
    """Draw and handle one viewport overlay, without dialogs or modal timers."""
    def __init__(self, operator, context, event):
        from .operators import find_view3d
        self.operator = operator
        self.session = Session(context, operator.action)
        self.window = context.window
        self.area, self.region = find_view3d(context)
        self.layout(context)
        self.x, self.y = self.position(event)
        self.hover = None
        self.drag = None
        self.edit = None
        self.menu = None
        self.text = ''
        self.select_all = False
        self.cursor = self.anchor = 0
        self.value_history = []
        self.redo_history = []
        self.gesture = None
        self.handler = None
        try:
            self.session.preview(context)
            self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), 'WINDOW', 'POST_PIXEL')
        except Exception:
            self.session.close(context, cancel=True)
            raise

    def canvas(self):
        left, bottom, right, top = 0, 0, self.region.width, self.region.height
        for r in self.area.regions:
            if r.type not in {'UI', 'TOOLS'} or r.width <= 1:
                continue
            lo, hi = r.x-self.region.x, r.x+r.width-self.region.x
            if hi <= 0 or lo >= right:
                continue
            if lo <= 0:
                left = max(left, hi)
            elif hi >= self.region.width:
                right = min(right, lo)
        return left+8, bottom+8, right-8, top-12

    def layout(self, context):
        self.keys = fields(self.session)
        self.rows = [[key] for key in self.keys]
        base_width = 104
        if self.session.action == 'BRIDGE':
            base_width = 213
            self.rows = ([['segments', 'smooth']] if self.session.level == 2 else
                         [['segments', 'taper'], ['bias', 'smooth'], ['twist1', 'twist2']])
            self.rows += [['bridge_selection', 'pick1', 'pick2']]
        elif self.session.action in {'RELAX', 'MSMOOTH'}:
            self.rows = [[key] for key in self.keys[:-2]]+[self.keys[-2:]]
        left, bottom, right, top = self.canvas()
        self.scale = max(.1, min(context.preferences.system.ui_scale,
                                (right-left)/base_width, (top-bottom)/((len(self.rows)+2)*29)))
        self.width, self.row, self.gap = base_width*self.scale, 24*self.scale, 5*self.scale
        self.height = (len(self.rows)+2)*(self.row+self.gap)
        if hasattr(self, 'x'):
            self.x, self.y = self.clamp(self.x, self.y)

    def position(self, event):
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        from mathutils import Vector
        bm = bmesh.from_edit_mesh(self.session.obj.data)
        points = [v.co for v in bm.verts if v.select and not v.hide]
        point = None
        if points:
            center = self.session.obj.matrix_world @ (sum(points, Vector()) / len(points))
            rv3d = self.region.data or self.area.spaces.active.region_3d
            point = location_3d_to_region_2d(self.region, rv3d, center)
        if point is None:
            point = (event.mouse_x-self.region.x, event.mouse_y-self.region.y)
        return self.clamp(point[0]+50*self.scale, point[1]+self.height*.6)

    def clamp(self, x, y):
        left, bottom, right, top = self.canvas()
        return (max(left, min(x, right-self.width)),
                max(self.height+bottom, min(y, top)))

    def rect(self, index):
        if index == 0:
            return (self.x, self.y-self.row-self.gap, self.width, self.row)
        if index == len(self.keys)+1:
            return (self.x, self.y-self.height, self.width, self.row)
        key = self.keys[index-1]
        for row, keys in enumerate(self.rows):
            if key in keys:
                width = (self.width-(len(keys)-1)*self.gap)/len(keys)
                col = keys.index(key)
                return (self.x+col*(width+self.gap), self.y-(row+2)*(self.row+self.gap), width, self.row)

    def hit(self, x, y):
        for index, key in enumerate(['TITLE']+self.keys+['BUTTONS']):
            left, bottom, width, height = self.rect(index)
            if left <= x <= left+width and bottom <= y <= bottom+height:
                if key == 'BUTTONS':
                    return ['OK', 'APPLY', 'CANCEL'][min(2, int((x-left)/(width/3)))]
                return key
        return None

    def change(self, context, key, value):
        prop = self.session.store.bl_rna.properties[key]
        if prop.type in {'INT', 'FLOAT'}:
            value = max(prop.hard_min, min(prop.hard_max, value))
            if prop.type == 'INT':
                value = round(value)
        setattr(self.session.values, key, value)
        self.session.preview(context)
        self.area.tag_redraw()

    def finish_edit(self, context):
        if self.edit is None:
            return True
        try:
            value = float(self.text)
            if not math.isfinite(value):
                return False
        except ValueError:
            return False
        self.change(context, self.edit, value)
        self.edit = None
        self.remember()
        return True

    def begin_gesture(self):
        self.gesture = vars(self.session.values).copy()

    def remember(self):
        if self.gesture is not None and self.gesture != vars(self.session.values):
            self.value_history.append(self.gesture)
            self.redo_history.clear()
        self.gesture = None

    def undo_value(self, context, redo=False):
        self.remember()
        source, target = (self.redo_history, self.value_history) if redo else (self.value_history, self.redo_history)
        if source:
            target.append(vars(self.session.values).copy())
            vars(self.session.values).update(source.pop())
            self.session.preview(context)
        self.edit = self.drag = self.menu = None

    def replace_text(self, context, value):
        lo, hi = (0, len(self.text)) if self.select_all else sorted((self.cursor, self.anchor))
        self.text = self.text[:lo]+value+self.text[hi:]
        self.cursor = self.anchor = lo+len(value)
        self.select_all = False
        self.live_text(context)

    def text_key(self, context, event):
        if event.type == 'A' and event.ctrl:
            self.anchor, self.cursor = 0, len(self.text)
            self.select_all = True
        elif event.ctrl and event.type in {'C', 'X', 'V'}:
            lo, hi = (0, len(self.text)) if self.select_all else sorted((self.cursor, self.anchor))
            if event.type in {'C', 'X'}:
                context.window_manager.clipboard = self.text[lo:hi]
                if event.type == 'X':
                    self.replace_text(context, '')
            else:
                value = context.window_manager.clipboard.strip()
                if value and all(c in '0123456789.-+eE' for c in value):
                    self.replace_text(context, value)
        elif event.type in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
            lo, hi = (0, len(self.text)) if self.select_all else sorted((self.cursor, self.anchor))
            if event.type == 'HOME':
                self.cursor = 0
            elif event.type == 'END':
                self.cursor = len(self.text)
            elif not event.shift and lo != hi:
                self.cursor = lo if event.type == 'LEFT_ARROW' else hi
            else:
                self.cursor = max(0, min(len(self.text), self.cursor+(-1 if event.type == 'LEFT_ARROW' else 1)))
            if not event.shift:
                self.anchor = self.cursor
            self.select_all = False
        elif event.type in {'BACK_SPACE', 'DEL'}:
            if self.cursor == self.anchor and not self.select_all:
                self.anchor = max(0, self.cursor-1) if event.type == 'BACK_SPACE' else min(len(self.text), self.cursor+1)
            self.replace_text(context, '')
        elif event.type == 'TAB':
            self.finish_edit(context)
        elif event.unicode and all(c in '0123456789.-+eE' for c in event.unicode):
            self.replace_text(context, event.unicode)

    def reset_value(self, context, key):
        defaults = {'segments': 1, 'iterations': 1, 'tension': 1, 'smoothness': 1, 'smooth': 45}
        self.begin_gesture()
        self.change(context, key, defaults.get(key, 0))
        self.remember()

    def select_event(self, context, event, x, y):
        """Keep topology-changing shortcuts out of the transaction's pristine mesh."""
        if event.value != 'PRESS':
            return False
        levels = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5, 'SIX': 0}
        if event.type in levels and not (event.ctrl or event.alt or event.shift):
            from . import editable_poly as ep
            from .operators import current_level
            level = levels[event.type]
            if self.session.was_object or level == 0 or level == self.session.level:
                self.close(context, cancel=True)
                bpy.ops.max.subobject('EXEC_DEFAULT', False, level=level if self.session.was_object else 0)
                return True
            self.session.baseline.restore(self.session.obj)
            bpy.ops.max.subobject('EXEC_DEFAULT', False, level=level)
            self.session.level = current_level(context)
            self.session.store = ep.settings(context, self.session.action)
            vars(self.session.values).update({key: getattr(self.session.store, key) for key in ep.option_properties()})
            self.value_history.clear()
            self.redo_history.clear()
            self.session.baseline.free()
            self.session.baseline = Snapshot(self.session.obj)
            self.session.preview(context)
            self.layout(context)
            return True
        if event.ctrl and event.type in {'A', 'D', 'I'} and not event.alt:
            action = {'A': 'SELECT', 'D': 'DESELECT', 'I': 'INVERT'}[event.type]
            self.session.reselect(context, lambda: bpy.ops.mesh.select_all('EXEC_DEFAULT', False, action=action))
            return True
        left, bottom, right, top = self.canvas()
        if event.type == 'LEFTMOUSE' and left <= x <= right and bottom <= y <= top:
            self.session.reselect(context, lambda: bpy.ops.view3d.select(
                'EXEC_DEFAULT', False, location=(int(x), int(y)),
                extend=event.ctrl, deselect=event.alt, toggle=event.shift))
            return True
        return False

    def live_text(self, context):
        try:
            value = float(self.text)
            if math.isfinite(value):
                self.change(context, self.edit, value)
        except ValueError:
            pass

    def close(self, context, cancel=False):
        try:
            self.session.close(context, cancel=cancel)
            if not cancel:
                for key in self.session.keys:
                    setattr(self.operator, key, getattr(self.session.values, key))
        finally:
            if self.handler is not None:
                bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
                self.handler = None
            _active.pop(self.window.as_pointer(), None)
            self.area.tag_redraw()

    def modal(self, context, event):
        if self.session.closed:
            return {'CANCELLED'}
        if context.active_object != self.session.obj or self.session.obj.mode != 'EDIT':
            self.close(context, cancel=True)
            return {'CANCELLED'}
        self.layout(context)
        x, y = event.mouse_x-self.region.x, event.mouse_y-self.region.y
        hit = self.hit(x, y)
        self.hover = hit
        if event.type == 'Z' and event.ctrl and event.value == 'PRESS':
            self.undo_value(context, redo=event.shift)
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if event.type == 'RIGHTMOUSE' and self.drag and self.drag[0] != 'TITLE':
                key, _, _, value = self.drag
                self.change(context, key, value)
                self.drag = None
                self.gesture = None
            elif event.type == 'RIGHTMOUSE' and hit in self.keys and enabled(self.session, hit) and self.edit is None:
                left, _, _, _ = self.rect(self.keys.index(hit)+1)
                prop = self.session.store.bl_rna.properties.get(hit)
                if prop and prop.type in {'INT', 'FLOAT'} and x < left+27*self.scale:
                    self.reset_value(context, hit)
                else:
                    self.close(context, cancel=True)
                    return {'CANCELLED'}
            else:
                self.close(context, cancel=True)
                return {'CANCELLED'}
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if self.edit is not None:
                self.finish_edit(context)
            elif event.ctrl:
                if self.session.apply(context):
                    self.value_history.clear()
                    self.redo_history.clear()
                    self.session.preview(context)
            elif self.session.valid:
                self.close(context)
                return {'FINISHED'}
        elif self.edit is not None and event.value == 'PRESS' and event.type != 'LEFTMOUSE':
            self.text_key(context, event)
        elif event.type == 'LEFTMOUSE':
            if event.value == 'RELEASE':
                if self.drag and self.drag[0] != 'TITLE' and abs(y-self.drag[2]) < 1 and abs(x-self.drag[1]) < 1:
                    key, _, start_y, value = self.drag
                    bottom = self.rect(self.keys.index(key)+1)[1]
                    step = 1 if isinstance(value, int) else .01
                    self.change(context, key, value+(step if start_y > bottom+self.row/2 else -step))
                if self.drag:
                    self.remember()
                self.drag = None
            elif event.value == 'PRESS':
                if self.edit is not None and hit != 'CANCEL' and not self.finish_edit(context):
                    return {'RUNNING_MODAL'}
                if self.menu is not None:
                    key = self.menu
                    options = choices(self.session, key)
                    idx = int((self.menu_top-y)/(self.row+self.gap))
                    if self.x <= x <= self.x+max(self.width, 180*self.scale) and 0 <= idx < len(options):
                        self.begin_gesture()
                        self.change(context, key, options[idx][0])
                        self.remember()
                    self.menu = None
                elif hit == 'TITLE':
                    self.drag = ('TITLE', x, y, (self.x, self.y))
                elif hit in {'OK', 'APPLY', 'CANCEL'}:
                    if hit == 'CANCEL':
                        self.close(context, cancel=True)
                        return {'CANCELLED'}
                    if self.session.valid:
                        if hit == 'OK':
                            self.close(context)
                            return {'FINISHED'}
                        if self.session.apply(context):
                            self.value_history.clear()
                            self.redo_history.clear()
                            self.session.preview(context)
                elif hit in self.keys and enabled(self.session, hit):
                    left, bottom, width, height = self.rect(self.keys.index(hit)+1)
                    value = getattr(self.session.values, hit)
                    opts = choices(self.session, hit)
                    if opts:
                        if x > left+width-22*self.scale:
                            self.menu = hit
                            self.menu_top = self.rect(self.keys.index(hit)+1)[1]
                        else:
                            idx = next(i for i, (v, _) in enumerate(opts) if v == value)
                            self.begin_gesture()
                            self.change(context, hit, opts[(idx+1) % len(opts)][0])
                            self.remember()
                    elif isinstance(value, bool):
                        self.begin_gesture()
                        self.change(context, hit, not value)
                        self.remember()
                    elif x < left+27*self.scale:
                        self.begin_gesture()
                        self.drag = (hit, x, y, value)
                    else:
                        self.begin_gesture()
                        self.edit = hit
                        self.text = str(value) if isinstance(value, int) else f'{value:.6g}'
                        self.select_all = True
                        self.anchor, self.cursor = 0, len(self.text)
                elif hit is None:
                    self.select_event(context, event, x, y)
        elif event.type == 'MOUSEMOVE' and self.drag:
            key, start_x, start_y, value = self.drag
            if key == 'TITLE':
                self.x, self.y = self.clamp(value[0]+x-start_x, value[1]+y-start_y)
            else:
                prop = self.session.store.bl_rna.properties[key]
                step = 1 if prop.type == 'INT' else .01
                step *= 10 if event.ctrl else .1 if event.alt else 1
                self.change(context, key, value+(y-start_y)*step)
        elif not (self.edit or self.drag or self.menu or hit):
            self.select_event(context, event, x, y)
        if self.session.closed:
            return {'CANCELLED'}
        self.area.tag_redraw()
        # Consume editing input, keep navigation in the viewport available.
        if self.drag or self.edit or self.menu or hit or event.type not in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'MOUSEMOVE'}:
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def draw(self):
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
        from . import max_icons
        if self.session.closed or bpy.context.region != self.region:
            return
        self.layout(bpy.context)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')

        def polygon(points, color):
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'TRI_FAN', {'pos': points}).draw(shader)

        def box(x, y, w, h, color, radius=None):
            radius = min(h/2 if radius is None else radius, h/2, w/2)
            points = []
            for cx, cy, start in ((x+w-radius, y+h-radius, 0), (x+radius, y+h-radius, 90),
                                  (x+radius, y+radius, 180), (x+w-radius, y+radius, 270)):
                for a in range(start, start+91, 15):
                    points.append((cx+radius*math.cos(math.radians(a)), cy+radius*math.sin(math.radians(a))))
            polygon(points, color)

        def text(x, y, value, color=(.91, .92, .93, 1), size=11):
            blend = gpu.state.blend_get()
            blf.size(0, size*self.scale)
            blf.color(0, *color)
            blf.position(0, x, y, 0)
            blf.draw(0, value)
            # BLF leaves blending disabled. Keep subsequent transparent icons
            # and pill edges from overwriting the viewport with alpha zero.
            gpu.state.blend_set(blend)

        def lines(points, color=(.18, .35, .42, 1)):
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINES', {'pos': points}).draw(shader)

        def tick(cx, cy, checked):
            # State control only. Field icon artwork is maintained separately.
            s = 5*self.scale
            points = [(cx-s,cy), (cx-s/4,cy-s), (cx+s,cy+s)]
            color = (.08,.24,.28,1) if checked else (.32,.36,.37,1)
            if checked:
                for offset in (-self.scale, 0, self.scale):
                    lines([(points[0][0],points[0][1]+offset),
                           (points[1][0],points[1][1]+offset),
                           (points[1][0],points[1][1]+offset),
                           (points[2][0],points[2][1]+offset)], color)
            else:
                outline = [(cx-s,cy+2*self.scale),(cx-s/4,cy-s+2*self.scale),
                           (cx+s,cy+s+2*self.scale),(cx+s+2*self.scale,cy+s),
                           (cx-s/4,cy-s-2*self.scale),(cx-s-2*self.scale,cy)]
                lines([p for i in range(len(outline)) for p in (outline[i],outline[(i+1)%len(outline)])], color)

        def mark(cx, cy, kind, hover=False):
            s = 6*self.scale
            if hover:
                polygon([(cx-s, cy+2), (cx+s, cy+2), (cx, cy+s+2)], (.15, .27, .3, 1))
                polygon([(cx-s, cy-2), (cx+s, cy-2), (cx, cy-s-2)], (.15, .27, .3, 1))
                return
            if kind in {'height', 'distance'}:
                lines([(cx,cy-s), (cx,cy+s), (cx-s,cy), (cx+s,cy),
                       (cx,cy+s), (cx-3,cy+s-3), (cx,cy+s), (cx+3,cy+s-3)])
            elif kind == 'type':
                for dx in (-4, 0, 4):
                    lines([(cx+dx-2,cy-s), (cx+dx-2,cy+s)])
                lines([(cx-s,cy-s), (cx+s,cy-s), (cx-s,cy+s), (cx+s,cy+s)])
            elif kind == 'segments':
                for dx in (-5, 0, 5):
                    lines([(cx+dx,cy-s), (cx+dx,cy+s)])
                lines([(cx-s,cy), (cx+s,cy)])
            elif kind == 'chamfer':
                lines([(cx-s,cy+s),(cx+s,cy+s),(cx+s,cy+s),(cx+s,cy-s),
                       (cx-s,cy+s),(cx-s,cy),(cx-s,cy),(cx,cy-s),(cx,cy-s),(cx+s,cy-s)])
            elif kind in {'weld', 'bias', 'width', 'taper', 'twist'}:
                lines([(cx-s,cy-s), (cx,cy), (cx+s,cy+s), (cx,cy),
                       (cx-s,cy+s), (cx,cy), (cx+s,cy-s), (cx,cy)])
            else:
                lines([(cx-s,cy-s), (cx-s,cy+s), (cx-s,cy+s), (cx+s,cy+s),
                       (cx+s,cy+s), (cx+s,cy-s), (cx+s,cy-s), (cx-s,cy-s)])
                lines([(cx-s,cy-s), (cx+s,cy+s)])

        def field_mark(key, cx, cy, fallback):
            if not draw_field_icon(self.session, key, cx, cy, 20*self.scale):
                mark(cx, cy, fallback)

        from .operators import EDIT_POLY_OPS
        title = dict((k,n) for k,n,_ in EDIT_POLY_OPS)[self.session.action]
        action, level = self.session.action, self.session.level
        if action == 'EXTRUDE':
            title = 'Extrude '+('Vertices' if level == 1 else 'Edges' if level in (2,3) else 'Polygons')
        elif action == 'BRIDGE':
            title = 'Bridge '+('Edges' if level == 2 else 'Borders' if level == 3 else 'Polygons')
        elif action == 'WELD':
            title = 'Weld '+('Vertices' if level == 1 else 'Edges')
        elif action == 'CONNECT' and level in (2,3):
            title = 'Connect Edges'
        elif action == 'BEVEL':
            title = 'Bevel Polygons'
        elif action == 'MSMOOTH':
            title = 'MeshSmooth'
        if self.hover in self.keys:
            title += ': '+label(self.session, self.hover)
        blf.size(0, 11*self.scale)
        tx, ty, tw, th = self.rect(0)
        title_width = min(self.canvas()[2]-tx, max(tw, blf.dimensions(0, title)[0]+30*self.scale))
        while title and blf.dimensions(0, title)[0] > title_width-28*self.scale:
            title = title[:-1]
        box(tx, ty, title_width, th, (.045, .05, .052, .96), radius=7*self.scale)
        lines([(tx+7*self.scale,ty+7*self.scale),(tx+7*self.scale,ty+17*self.scale),
               (tx+10*self.scale,ty+7*self.scale),(tx+10*self.scale,ty+17*self.scale)],(.4,.42,.43,1))
        text(tx+16*self.scale, ty+8*self.scale, title)
        for i, key in enumerate(self.keys, 1):
            x, y, w, h = self.rect(i)
            on = enabled(self.session, key)
            box(x, y, w, h, (.04, .045, .05, .9))
            box(x+1, y+1, w-2, h-2, (.51, .53, .54, .98) if on else (.16, .18, .19, .95))
            # A shallow light upper half gives Max's value pills their bevel.
            box(x+2*self.scale, y+h/2, w-4*self.scale, h/2-2*self.scale,
                (.64,.66,.67,.25) if on else (.3,.32,.33,.14))
            if key == 'weld_counts':
                before = len(self.session.baseline.bm.verts if self.session.level == 1 else self.session.baseline.bm.edges)
                bm = bmesh.from_edit_mesh(self.session.obj.data)
                after = len(bm.verts if self.session.level == 1 else bm.edges)
                text(x+5*self.scale,y+8*self.scale,f'Before: {before}, After: {after}',size=9)
                continue
            if key in UI_ONLY:
                field_mark(key,x+13*self.scale,y+h/2,LABELS[key][1])
                if key in {'pick1','pick2'}:
                    text(x+w-15*self.scale,y+8*self.scale,'1' if key=='pick1' else '2',(.5,.52,.53,1))
                else:
                    tick(x+w-13*self.scale,y+h/2,False)
                continue
            value = getattr(self.session.values, key)
            opts = choices(self.session, key)
            prop = self.session.store.bl_rna.properties[key]
            if opts:
                field_mark(key,x+15*self.scale,y+h/2,'type')
                polygon([(x+w-17*self.scale,y+14*self.scale), (x+w-7*self.scale,y+14*self.scale),
                         (x+w-12*self.scale,y+8*self.scale)], (.12,.18,.2,1))
            elif prop.type == 'BOOLEAN':
                field_mark(key,x+13*self.scale,y+h/2,'hold')
                tick(x+w-12*self.scale,y+h/2,value)
            else:
                kind = 'height' if self.session.action == 'EXTRUDE' and key == 'amount' else LABELS[key][1]
                if self.session.action == 'CHAMFER' and key == 'amount':
                    kind = 'chamfer'
                field_mark(key,x+14*self.scale,y+h/2,kind)
                display = self.text if self.edit == key else str(value) if isinstance(value,int) else f'{value:.4g}'
                if self.edit == key:
                    blf.size(0, 11*self.scale)
                    lo, hi = (0,len(self.text)) if self.select_all else sorted((self.cursor,self.anchor))
                    start = blf.dimensions(0,self.text[:lo])[0]
                    end = blf.dimensions(0,self.text[:hi])[0]
                    if lo != hi:
                        box(x+32*self.scale+start,y+3,end-start,h-6,(.19,.37,.5,1))
                    else:
                        caret = blf.dimensions(0,self.text[:self.cursor])[0]
                        lines([(x+32*self.scale+caret,y+5),(x+32*self.scale+caret,y+h-5)],(.04,.08,.1,1))
                text(x+32*self.scale,y+8*self.scale, display, (.04,.08,.1,1) if on else (.52,.53,.54,1))
        x,y,w,h = self.rect(len(self.keys)+1)
        for i, kind in enumerate(('OK','APPLY','CANCEL')):
            cx, cy = x+(i+.5)*w/3, y+h/2
            # The SVG already owns its round disc. Do not draw a second ring.
            if max_icons.draw('caddy_'+kind.lower(),cx,cy,28*self.scale):
                continue
            box(cx-11*self.scale,cy-11*self.scale,22*self.scale,22*self.scale,(.5,.53,.54,.98),radius=11*self.scale)
            s = 5*self.scale
            if kind == 'OK':
                lines([(cx-s,cy),(cx-1,cy-s),(cx-1,cy-s),(cx+s,cy+s)],(.12,.35,.3,1))
            elif kind == 'APPLY':
                lines([(cx-s,cy),(cx+s,cy),(cx,cy-s),(cx,cy+s)],(.14,.35,.38,1))
            else:
                lines([(cx-s,cy-s),(cx+s,cy+s),(cx-s,cy+s),(cx+s,cy-s)],(.45,.16,.16,1))
        if self.hover in {'OK','APPLY','CANCEL'}:
            text(x,y-15*self.scale,{'OK':'OK (Enter)','APPLY':'Apply and Continue (Ctrl+Enter)',
                                  'CANCEL':'Cancel (Esc)'}[self.hover])
        if self.menu:
            opts = choices(self.session,self.menu)
            for i,(value,name) in enumerate(opts):
                my = self.menu_top-(i+1)*(self.row+self.gap)
                box(self.x,my,180*self.scale,self.row,(.12,.14,.15,1))
                text(self.x+8*self.scale,my+8*self.scale,name)
        if self.session.error:
            text(x,y-32*self.scale,self.session.error,(1,.55,.3,1))
        gpu.state.blend_set('NONE')


def invoke(operator, context, event):
    from .operators import viewport_override
    override = viewport_override(context)
    if override is None or override['region'] is None:
        operator.report({'WARNING'}, 'Caddies require a 3D viewport')
        return {'CANCELLED'}
    key = context.window.as_pointer()
    if _active:
        return {'CANCELLED'}
    try:
        with context.temp_override(**override):
            caddy = Caddy(operator, context, event)
        operator.caddy = caddy
        _active[key] = caddy
        context.window_manager.modal_handler_add(operator)
        caddy.area.tag_redraw()
        return {'RUNNING_MODAL'}
    except (ValueError, RuntimeError) as exc:
        operator.report({'WARNING'}, str(exc))
        return {'CANCELLED'}


def modal(operator, context, event):
    caddy = getattr(operator, 'caddy', None)
    if caddy is None:
        return {'CANCELLED'}
    try:
        with context.temp_override(window=caddy.window, area=caddy.area, region=caddy.region):
            return caddy.modal(context, event)
    except Exception as exc:
        caddy.close(context, cancel=True)
        operator.report({'ERROR'}, str(exc))
        return {'CANCELLED'}


def cancel(operator, context):
    caddy = getattr(operator, 'caddy', None)
    if caddy is not None and not caddy.session.closed:
        with context.temp_override(window=caddy.window, area=caddy.area, region=caddy.region):
            caddy.close(context, cancel=True)


@persistent
def teardown(_=None):
    for caddy in list(_active.values()):
        with bpy.context.temp_override(window=caddy.window, area=caddy.area, region=caddy.region):
            caddy.close(bpy.context, cancel=True)


def register_handlers():
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if teardown not in handlers:
            handlers.append(teardown)


def unregister_handlers():
    teardown()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if teardown in handlers:
            handlers.remove(teardown)
