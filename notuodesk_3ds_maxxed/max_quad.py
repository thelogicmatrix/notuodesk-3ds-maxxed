"""A modal four-quadrant menu. ViewCube and Snaps retain press ownership."""
from dataclasses import dataclass

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty

from . import quad_sets

_instances = []
_installed = False
_history = {}

# Pixel anchors sampled from the Autodesk 2026 quad image in the reference pack.
WIDTH = 179
ROW = 15
TITLE = 15
COLORS = {'body': (70/255,)*3+(1,), 'title': (60/255,)*3+(1,), 'border': (0, 0, 0, 1),
          'text': (159/255,)*3+(1,), 'disabled': (35/255,)*3+(1,),
          'hover_text': (1, 1, 1, 1), 'hover': (70/255,)*3+(1,),
          'centre': (60/255, 130/255, 220/255, 1)}


@dataclass(frozen=True)
class Cell:
    rect: tuple
    quadrant: int
    index: int
    entry: object = None
    title: str = ''

    def contains(self, x, y):
        a, b, w, h = self.rect
        return a <= x < a+w and b <= y < b+h


def height(rows):
    return sum(1 if not row.label else ROW for row in rows)


def arrange(quadrants):
    """Logical coordinates use the shared inner corner as (0, 0), Y down."""
    cells = []
    for i, q in enumerate(quadrants):
        if not q.title:
            continue
        left, upper = i % 2 == 0, i < 2
        x = 1-q.width if left else 0
        title_y = 1-TITLE if upper else 0
        y = title_y-height(q.entries)-sum(q.padding) if upper else TITLE
        cells.append(Cell((x, title_y, q.width, TITLE), i, -1, title=q.title))
        if q.padding[0]:
            cells.append(Cell((x, y, q.width, q.padding[0]), i, -2))
            y += q.padding[0]
        for j, row in enumerate(q.entries):
            h = ROW if row.label else 1
            cells.append(Cell((x, y, q.width, h), i, j, row))
            y += h
        if q.padding[1]:
            cells.append(Cell((x, y, q.width, q.padding[1]), i, -3))
    return cells


def place(cells, point, size, scale):
    """Translate all four quadrants together at edges, preserving their joint."""
    if not cells:
        return point
    minx = min(c.rect[0] for c in cells)*scale
    maxx = max(c.rect[0]+c.rect[2] for c in cells)*scale
    miny = min(c.rect[1] for c in cells)*scale
    maxy = max(c.rect[1]+c.rect[3] for c in cells)*scale
    x, y = point
    x = max(1-minx, min(x, size[0]-1-maxx))
    y = max(1+maxy, min(y, size[1]-1+miny))
    return x, y


def fit_scale(cells, size, requested):
    """Keep every command reachable when the viewport is smaller than the menu."""
    width = max(c.rect[0]+c.rect[2] for c in cells)-min(c.rect[0] for c in cells)
    extent = max(c.rect[1]+c.rect[3] for c in cells)-min(c.rect[1] for c in cells)
    return min(requested, max(1, size[0]-2)/width, max(1, size[1]-2)/extent)


def close_all():
    for menu in tuple(_instances):
        menu.close()


@persistent
def _before_load(_):
    close_all()


def install():
    global _installed
    if _installed:
        return
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(_before_load)
    _installed = True


def uninstall():
    global _installed
    close_all()
    if not _installed:
        return
    if _before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_before_load)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _installed = False


def compatibility(layout, quad_set='DEFAULT'):
    """Keep legacy menu IDs callable while F replaces their keymap routes."""
    layout.operator_context = 'INVOKE_DEFAULT'
    layout.operator('max.quad_menu', text='Open Quad Menu').quad_set = quad_set


class MAX_OT_quad_typein(bpy.types.Operator):
    bl_idname = 'max.quad_typein'
    bl_label = 'Transform Type-In'
    kind: EnumProperty(items=[(k, k.title(), '') for k in ('MOVE', 'ROTATE', 'SCALE')], options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        bpy.ops.max.select_transform(kind=self.kind)
        return bpy.ops.max.transform_typein('INVOKE_DEFAULT')


class MAX_OT_quad_toggle(bpy.types.Operator):
    bl_idname = 'max.quad_toggle'
    bl_label = 'Editable Poly Toggle'
    bl_options = {'UNDO', 'INTERNAL'}
    flag: EnumProperty(items=[('nurms', 'NURMS Toggle', ''),
                             ('ignore_backfacing', 'Ignore Backfacing', '')], options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        state = context.active_object.max_poly
        setattr(state, self.flag, not getattr(state, self.flag))
        return {'FINISHED'}


class MAX_OT_quad_reference(bpy.types.Operator):
    bl_idname = 'max.quad_reference'
    bl_label = 'Reference Coordinate System'
    reference: EnumProperty(items=[(key, label, '') for key, label in
        (('WORLD','World'),('WORKING','Working'),('VIEW','View'),('SCREEN','Screen'),
         ('PARENT','Parent'),('LOCAL_ALIGNED','Local Aligned'),('LOCAL','Local'))], options={'SKIP_SAVE'})

    def execute(self, context):
        from . import max_rotate, mode_feedback
        kind = mode_feedback.active_tool(context)
        field = {'ROTATE':'reference', 'SCALE':'scale_reference'}.get(kind, 'move_reference')
        setattr(max_rotate.settings(context), field, self.reference)
        return {'FINISHED'}


class MAX_OT_quad_menu(bpy.types.Operator):
    bl_idname = 'max.quad_menu'
    bl_label = 'Quad Menu'
    bl_options = {'INTERNAL', 'BLOCKING'}
    quad_set: EnumProperty(items=[(k, k.title(), '') for k in ('AUTO',)+quad_sets.SET_NAMES],
                           default='AUTO', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def invoke(self, context, event):
        from . import create, max_chrome, max_editor_windows
        if event.shift and not event.ctrl and not event.alt:
            return bpy.ops.max.snap_quad('INVOKE_DEFAULT')
        self.area, self.region = create.region_under_mouse(context, event.mouse_x, event.mouse_y)
        if self.region is None or max_chrome.timeline_area(self.area) or self.area.as_pointer() in max_editor_windows._docked:
            return {'CANCELLED'}
        close_all()
        self.window = context.window
        self.window_key = self.window.as_pointer()
        self.area_key = self.area.as_pointer()
        self.region_key = self.region.as_pointer()
        self.closed = False
        self.scale = context.preferences.system.ui_scale
        self.set_name = self.quad_set if self.quad_set != 'AUTO' else quad_sets.choose_set(
            ctrl=event.ctrl, alt=event.alt, shift=event.shift)
        # A compatibility route still receives the original event modifiers.
        if self.set_name == 'DEFAULT' and (event.ctrl or event.alt):
            self.set_name = quad_sets.choose_set(ctrl=event.ctrl, alt=event.alt, shift=event.shift)
        with context.temp_override(area=self.area, region=self.region):
            self.snapshot = quad_sets.capture(context)
            self.quadrants = quad_sets.resolved(self.snapshot, self.set_name)
        self.cells = arrange(self.quadrants)
        self.scale = fit_scale(self.cells, (self.region.width, self.region.height), self.scale)
        self.anchor = place(self.cells, (event.mouse_x-self.region.x, event.mouse_y-self.region.y),
                            (self.region.width, self.region.height), self.scale)
        self.mouse = (0, 0)
        self.focus = None
        self.submenu = None
        self.subcells = []
        self.pending = None
        self.timer = context.window_manager.event_timer_add(.25, window=self.window)
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.paint, (), 'WINDOW', 'POST_PIXEL')
        _instances.append(self)
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def logical(self, event):
        return ((event.mouse_x-self.region.x-self.anchor[0])/self.scale,
                (self.anchor[1]-(event.mouse_y-self.region.y))/self.scale)

    def target(self, x, y):
        for cell in reversed(self.subcells+self.cells):
            if cell.title and cell.contains(x, y):
                return cell, 'repeat'
            if cell.entry and cell.entry.label and cell.contains(x, y):
                xx, yy, w, h = cell.rect
                settings = cell.entry.settings is not None and (x < xx+14 if cell.quadrant % 2 == 0 else x >= xx+w-14)
                return cell, 'settings' if settings else 'command'
        return None

    def action_center(self, key, settings=False):
        cell = next(c for c in self.subcells+self.cells if c.entry and c.entry.key == key)
        x, y, w, h = cell.rect
        x += 7 if settings and cell.quadrant % 2 == 0 else w-7 if settings else w/2
        return self.region.x+self.anchor[0]+x*self.scale, self.region.y+self.anchor[1]-(y+h/2)*self.scale

    def open_submenu(self, cell):
        self.submenu = cell
        x, y, w, h = cell.rect
        sx = x-w if cell.quadrant % 2 == 0 else x+w
        if self.anchor[0]+(sx+WIDTH)*self.scale > self.region.width:
            sx = x-WIDTH
        if self.anchor[0]+sx*self.scale < 0:
            sx = x+w
        total = height(cell.entry.children)
        sy = max((self.anchor[1]-self.region.height+1)/self.scale,
                 min(y, (self.anchor[1]-1)/self.scale-total))
        self.subcells = []
        for j, row in enumerate(cell.entry.children):
            rh = ROW if row.label else 1
            self.subcells.append(Cell((sx, sy, WIDTH, rh), cell.quadrant, j, row))
            sy += rh

    def close(self):
        if self.closed:
            return
        self.closed = True
        bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
        try:
            bpy.context.window_manager.event_timer_remove(self.timer)
        except (ReferenceError, RuntimeError):
            pass
        if self in _instances:
            _instances.remove(self)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def cancel(self, context):
        self.close()

    def activate(self, context, target):
        if target is None:
            self.close()
            return {'CANCELLED'}
        cell, part = target
        history_key = (self.set_name, self.quadrants[cell.quadrant].title)
        if part == 'repeat':
            previous = _history.get(history_key)
            if previous is None:
                return {'RUNNING_MODAL'}
            def search(rows):
                for row in rows:
                    if row.key == previous[0]:
                        return row
                    child = search(row.children)
                    if child:
                        return child
            entry = search(self.quadrants[cell.quadrant].entries)
            if entry is None:
                return {'RUNNING_MODAL'}
            part = previous[1]
        else:
            entry = cell.entry
        if not entry.enabled:
            return {'RUNNING_MODAL'}
        if part == 'settings' and not entry.settings_enabled:
            return {'RUNNING_MODAL'}
        if entry.children:
            self.open_submenu(cell)
            self.focus = None
            return {'RUNNING_MODAL'}
        cmd = entry.settings if part == 'settings' else entry.command
        if cmd is None:
            return {'RUNNING_MODAL'}
        self.close()
        group, name = cmd.operator.split('.')
        with context.temp_override(window=self.window, area=self.area, region=self.region):
            op = getattr(getattr(bpy.ops, group), name)
            if op.poll():
                result = op('INVOKE_DEFAULT', **dict(cmd.values))
                if result != {'CANCELLED'}:
                    _history[history_key] = (entry.key, part)
        return {'FINISHED'}

    def navigate(self, event):
        cells = [c for c in (self.subcells or self.cells) if c.entry and c.entry.enabled and c.entry.label]
        if not cells:
            return
        current = self.focus[0] if self.focus else None
        if event.type in {'TAB', 'UP_ARROW', 'DOWN_ARROW'}:
            step = -1 if event.type == 'UP_ARROW' or event.shift else 1
            index = cells.index(current) if current in cells else (-1 if step > 0 else 0)
            self.focus = cells[(index+step) % len(cells)], 'command'
        elif event.type == 'RIGHT_ARROW' and current and current.entry:
            if current.entry.children:
                self.open_submenu(current)
                self.focus = next(((c, 'command') for c in self.subcells if c.entry.enabled), None)
            elif current.entry.settings:
                self.focus = current, 'settings'
        elif event.type == 'LEFT_ARROW':
            self.subcells = []
            self.focus = (self.submenu, 'command') if self.submenu else (current, 'command') if current else None
            self.submenu = None

    def modal(self, context, event):
        if self.closed:
            return {'FINISHED'}
        live_area = next((a for w in context.window_manager.windows if w.as_pointer() == self.window_key
                          for a in w.screen.areas if a.as_pointer() == self.area_key), None)
        if live_area is None or not any(r.as_pointer() == self.region_key for r in live_area.regions):
            self.close()
            return {'CANCELLED'}
        if event.type == 'TIMER':
            return {'RUNNING_MODAL'}
        self.mouse = self.logical(event)
        target = self.target(*self.mouse)
        if event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'} and event.value != 'RELEASE':
            self.close()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            if target != self.focus and target and target[0].entry and not target[0].entry.enabled:
                from . import max_status
                max_status.notify(target[0].entry.reason or 'Unavailable in the current context')
            self.focus = target
            if target and target[0].entry and target[0].entry.enabled and target[0].entry.children:
                self.open_submenu(target[0])
            elif target and target[0] in self.cells and target[0] != self.submenu:
                self.subcells = []
                self.submenu = None
        elif event.value == 'PRESS' and event.type in {'TAB', 'UP_ARROW', 'DOWN_ARROW', 'LEFT_ARROW', 'RIGHT_ARROW'}:
            self.navigate(event)
        elif event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            return self.activate(context, self.focus)
        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # Consume release as well before dispatching a command.
                self.pending = (target, self.mouse)
            elif event.value == 'RELEASE' and self.pending:
                pressed, _ = self.pending
                self.pending = None
                if pressed == target:
                    return self.activate(context, target)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def paint(self):
        if self.closed or not bpy.context.region or bpy.context.region.as_pointer() != self.region_key:
            return
        import gpu
        from .max_ui_draw import Canvas
        gpu.state.blend_set('ALPHA')
        c = Canvas(*self.anchor, self.scale, 'tahoma')
        for cell in self.cells+self.subcells:
            x, y, w, h = cell.rect
            row = cell.entry
            c.rect(x, y, w, h, COLORS['title'] if cell.title else COLORS['body'])
            if row is None:
                if cell.title:
                    c.border(x, y, w, h, COLORS['border'])
                    c.text(x+2, y-1, cell.title, COLORS['text'], 11,
                           align='LEFT' if cell.quadrant % 2 == 0 else 'RIGHT', width=w-4)
                continue
            if not row.label:
                c.rect(x, y, w, 1, COLORS['border'])
                continue
            focused = self.focus is not None and self.focus[0] == cell and row.enabled
            if focused:
                c.rect(x+1, y, w-2, h, COLORS['hover'])
            remembered = _history.get((self.set_name, self.quadrants[cell.quadrant].title), (None,))[0] == row.key
            color = COLORS['hover_text'] if row.enabled and (focused or remembered) else COLORS['text'] if row.enabled else COLORS['disabled']
            left = cell.quadrant % 2 == 0 and cell not in self.subcells
            c.text(x+14, y, row.label, color, 11, align='RIGHT' if left else 'LEFT', width=w-29)
            if row.checked:
                c.tick(x+w-11 if left else x+3, y+4, COLORS['border'])
            if row.children:
                c.arrow(x+w-11, y+3, color=COLORS['border'])
            if row.settings:
                sx = x+3 if left else x+w-11
                c.border(sx, y+5, 8, 8, COLORS['border'])
                c.rect(sx+1, y+6, 6, 1, COLORS['text'])
                if focused and self.focus[1] == 'settings':
                    c.border(sx-2, y+2, 12, 12, COLORS['hover_text'])
        # A single-pixel frame encloses each quadrant, including the title strip.
        for i in range(4):
            cells = [cell for cell in self.cells if cell.quadrant == i]
            if cells:
                x = min(cell.rect[0] for cell in cells)
                y = min(cell.rect[1] for cell in cells)
                bottom = max(cell.rect[1]+cell.rect[3] for cell in cells)
                c.border(x, y, self.quadrants[i].width, bottom-y, COLORS['border'])
        for x in (-13, 1):
            for y in (-13, 1):
                c.rect(x, y, 13, 13, COLORS['centre'])
        if self.subcells:
            x, y, w, _ = self.subcells[0].rect
            c.border(x, y, w, height(self.submenu.entry.children), COLORS['border'])
        gpu.state.blend_set('NONE')


classes = (MAX_OT_quad_typein, MAX_OT_quad_toggle, MAX_OT_quad_reference, MAX_OT_quad_menu)
