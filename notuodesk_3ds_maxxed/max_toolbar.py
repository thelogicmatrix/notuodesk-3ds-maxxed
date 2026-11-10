"""Ordered Main Toolbar. Transform, snap, icon and mode services keep their ownership."""
import bpy
import gpu
import time
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty, StringProperty
from . import max_icons, max_status

_commands = {}
_selections = set()
_set_items = []
_set_signature = None
_header_handle = None
_tooltip_handle = None
_hover = {}
_tooltip_drawn = {}
_pressed = {}
_flyouts = {}


def chrome_items(context):
    """Reference-sized toolbar cells. Each cell routes to the existing owner."""
    from . import max_rotate, snaps
    owner = max_status.feedback()
    active = lambda kind: bool(owner and owner.tool_pressed(context, kind))
    items = []
    x = 2

    def cell(label, art='', command='', props=None, width=26, menu='', pressed=False, enabled=True, hold=''):
        nonlocal x
        items.append(dict(label=label, art=art, command=command, props=props or {},
                          x=x, width=width, menu=menu, pressed=pressed, enabled=enabled, hold=hold))
        x += width

    def gap():
        nonlocal x
        x += 5

    cell('Undo', 'undo', 'ed.undo')
    cell('Redo', 'redo', 'ed.redo')
    gap()
    cell('Select and Link', 'link', 'wm.tool_set_by_id', {'name':'max.select_link'}, pressed=active('LINK'))
    cell('Unlink Selection', 'unlink', 'max.object_cmd', {'cmd':'UNLINK'})
    cell('Bind to Space Warp', 'bind_space_warp', enabled=False)
    gap()
    cell('All', width=58, menu='MAX_MT_chrome_filter')
    cell('Select Object', 'select_object', 'wm.tool_set_by_id', {'name':'builtin.select_box'}, pressed=active('SELECT'))
    cell('Select by Name', 'select_by_name', _commands.get('select_by_name',''), enabled='select_by_name' in _commands)
    cell('Selection Region', 'region_rect', 'max.chrome_selection_tool', {'shape':'RECT'}, hold='MAX_MT_chrome_region')
    cell('Window / Crossing', 'window_crossing', 'max.chrome_crossing_toggle',
         pressed=context.window_manager.max_chrome_crossing, enabled=context.mode == 'OBJECT')
    gap()
    for kind, label in [('MOVE','Select and Move'), ('ROTATE','Select and Rotate'), ('SCALE','Select and Uniform Scale')]:
        cell(label, kind.lower(), 'max.select_transform', {'kind':kind}, pressed=active(kind),
             hold='MAX_MT_scale_flyout' if kind == 'SCALE' else '')
    cell('Select and Place', 'select_place', enabled=False)
    gap()
    operation = max_status.tool(context)
    operation = operation if operation in {'MOVE','ROTATE','SCALE'} else 'ROTATE'
    cell(max_rotate.reference_name(context,operation).replace('_',' ').title(), width=58, menu='MAX_MT_chrome_reference')
    cell('Use Center', 'pivot', menu='MAX_MT_transform_center')
    cell('Select and Manipulate', 'manipulate', enabled=False)
    gap()
    cell('Keyboard Shortcut Override', 'shortcut_override', enabled=False)
    s = snaps.settings(context)
    cell('Snaps Toggle', {'2D':'snap_2d','2_5D':'snap_25d','3D':'snap_3d'}[s.mode],
         'max.snap_toggle', {'kind':'SNAP'}, pressed=context.scene.tool_settings.use_snap, hold='MAX_MT_snap_modes')
    for kind, art, pressed in [('ANGLE_SNAP','angle_snap',s.angle_snap),
                               ('PERCENT_SNAP','percent_snap',s.percent_snap), ('SPINNER_SNAP','spinner_snap',s.spinner_snap)]:
        cell({'ANGLE_SNAP':'Angle Snap Toggle','PERCENT_SNAP':'Percent Snap Toggle','SPINNER_SNAP':'Spinner Snap Toggle'}[kind],
             art, 'max.snap_toggle', {'kind':kind}, pressed=pressed)
    gap()
    cell('Edit Named Selection Sets', 'named_selection_sets', menu='MAX_MT_chrome_sets')
    cell('Create Selection Set', width=108, menu='MAX_MT_chrome_sets')
    gap()
    for key, art, label in [('mirror','mirror','Mirror'), ('align','align','Align'),
                             ('scene_explorer','scene_explorer','Scene Explorer'),
                             ('layer_explorer','layer_explorer','Layer Explorer'),
                             ('ribbon','ribbon','Toggle Ribbon'), ('track_view','track_view','Track View'),
                             ('schematic_view','schematic_view','Schematic View')]:
        cell(label, art, _commands.get(key,''), enabled=key in _commands,
             hold='MAX_MT_chrome_align' if key == 'align' else '')
    return items


def _rect(x0, y0, x1, y1, color):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos':[(x0,y0),(x1,y0),(x1,y1),(x0,y0),(x1,y1),(x0,y1)]})
    shader.bind()
    shader.uniform_float('color',color)
    batch.draw(shader)


def _triangle(x, y, size, color):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos':[(x,y),(x+size,y+size),(x+size,y)]})
    shader.bind()
    shader.uniform_float('color',color)
    batch.draw(shader)


def draw_pixels():
    from . import max_chrome, max_timeline
    context = bpy.context
    if not max_chrome.active(context) or max_chrome.timeline_area(context.area) or context.region.height < 10:
        return
    scale = context.preferences.system.ui_scale
    height = context.region.height
    _rect(0,0,context.region.width,height,(.267,.267,.267,1))
    gpu.state.blend_set('ALPHA')
    previous_right = 2*scale
    for cell in chrome_items(context):
        left, width = cell['x']*scale, cell['width']*scale
        bottom, top = max(0,(height-24*scale)/2), min(height,(height+24*scale)/2)
        if left-previous_right > 2*scale:
            _rect(left-3*scale,bottom+3*scale,left-2*scale,top-3*scale,(.15,.15,.15,1))
        previous_right = left+width
        if cell['pressed']:
            _rect(left,bottom,left+width,top,(95/255,138/255,193/255,1))
        if cell['art']:
            gpu.state.blend_set('ALPHA')
            max_icons.draw(cell['art'], left+width/2, height/2, 22*scale)
            if cell['hold'] or cell['menu'] == 'MAX_MT_transform_center':
                _triangle(left+width-5*scale,bottom+2*scale,3*scale,(.85,.85,.85,1))
        else:
            _rect(left+2*scale,bottom+3*scale,left+width-2*scale,top-3*scale,(.25,.25,.25,1))
            _rect(left+3*scale,bottom+4*scale,left+width-3*scale,top-4*scale,(.36,.36,.36,1))
            max_timeline._text(left+6*scale,height/2-3*scale,cell['label'],round(10*scale),(.78,.78,.78,1))
            # The dropdown arrow points down, not the flyout corner triangle.
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            cx, cy = left+width-9*scale, height/2
            batch = batch_for_shader(shader,'TRIS',{'pos':[(cx-3*scale,cy+2*scale),
                (cx+3*scale,cy+2*scale),(cx,cy-2*scale)]})
            shader.bind()
            shader.uniform_float('color',(.8,.8,.8,1))
            batch.draw(shader)
        if not cell['enabled']:
            gpu.state.blend_set('ALPHA')
            _rect(left,bottom,left+width,top,(.267,.267,.267,.65))
    gpu.state.blend_set('NONE')


def header_cell(context, x, y):
    from . import max_chrome
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D' or max_chrome.timeline_area(area):
            continue
        header = next((r for r in area.regions if r.type == 'HEADER'), None)
        if header and header.x <= x < header.x+header.width and header.y <= y < header.y+header.height:
            region = next(r for r in area.regions if r.type == 'WINDOW')
            with context.temp_override(area=area,region=region):
                scale = context.preferences.system.ui_scale
                item = next((cell for cell in chrome_items(bpy.context)
                             if cell['x']*scale <= x-header.x < (cell['x']+cell['width'])*scale), None)
            return area, region, item
    return None, None, None


def pointer(context, event):
    """The native header stays empty. This listener owns only drawn cell hits."""
    window = context.window.as_pointer()
    flyout = _flyouts.get(window)
    if flyout:
        with context.temp_override(area=flyout.area, region=flyout.region):
            result = flyout.modal(bpy.context,event)
        if result != {'RUNNING_MODAL'}:
            _flyouts.pop(window,None)
        return True
    if event.type == 'MOUSEMOVE':
        area, region, item = header_cell(context,event.mouse_x,event.mouse_y)
        previous = _hover.get(window)
        key = (area.as_pointer(), item['x']) if area and item else None
        if not previous or previous['key'] != key:
            if previous and previous['area']:
                previous['area'].tag_redraw()
            _hover[window] = dict(key=key, area=area, region=region, item=item, started=time.monotonic())
            if area:
                area.tag_redraw()
                if not bpy.app.timers.is_registered(_tooltip_tick):
                    bpy.app.timers.register(_tooltip_tick,first_interval=.1)
        elif previous['area']:
            previous['area'].tag_redraw()
        return False
    if event.type not in {'LEFTMOUSE','RIGHTMOUSE'}:
        return False
    area, region, item = header_cell(context,event.mouse_x,event.mouse_y)
    if not item:
        return False
    _hover.pop(window,None)
    if event.value == 'PRESS':
        if event.type == 'LEFTMOUSE' and item['command'] == 'max.snap_toggle' and item['props'].get('kind') == 'SNAP':
            from .snap_flyout import Flyout
            with context.temp_override(area=area,region=region):
                _flyouts[window] = Flyout(bpy.context,event)
            return True
        _pressed[window] = item['x'], time.monotonic()
        return True
    if event.value != 'RELEASE':
        return True
    pressed = _pressed.pop(window,None)
    if not pressed or pressed[0] != item['x'] or not item['enabled']:
        return True
    with context.temp_override(area=area,region=region):
        if event.type == 'RIGHTMOUSE' and item['command'] == 'max.snap_toggle':
            kind = item['props']['kind']
            if kind == 'SPINNER_SNAP':
                bpy.ops.max.spinner_snap_settings('INVOKE_DEFAULT')
            else:
                bpy.ops.max.snap_settings('INVOKE_DEFAULT',tab='SNAPS' if kind == 'SNAP' else 'OPTIONS')
        else:
            menu = item['menu'] or (item['hold'] if time.monotonic()-pressed[1] > .4 or event.type == 'RIGHTMOUSE' else '')
            if menu:
                bpy.ops.wm.call_menu('INVOKE_DEFAULT',name=menu)
            elif item['command']:
                category, name = item['command'].split('.')
                getattr(getattr(bpy.ops,category),name)('INVOKE_DEFAULT',**item['props'])
    area.tag_redraw()
    return True


def draw_tooltip():
    from . import max_timeline, max_chrome
    context = bpy.context
    if not max_chrome.active(context) or not context.preferences.view.show_tooltips:
        return
    record = _hover.get(context.window.as_pointer())
    if not record or record['area'] != context.area or not record['item'] or time.monotonic()-record['started'] < .6:
        return
    item = record['item']
    label = max_icons.tooltip(context,item['label'],item['command'],**item['props']) if item['command'] else item['label']
    scale = context.preferences.system.ui_scale
    import blf
    blf.size(max_timeline.font(),round(11*scale))
    width = blf.dimensions(max_timeline.font(),label)[0]+20*scale
    x = min(item['x']*scale,context.region.width-width-4*scale)
    y = context.region.height-32*scale
    _rect(x-1,y-1,x+width+1,y+25*scale+1,(.12,.12,.12,1))
    _rect(x,y,x+width,y+25*scale,(.26,.26,.26,1))
    max_timeline._text(x+10*scale,y+8*scale,label,round(11*scale),(.93,.93,.93,1))
    _tooltip_drawn[context.window.as_pointer()] = dict(label=label, rect=(x,y,x+width,y+25*scale),
                                                     drawn=time.monotonic(), area=context.area.as_pointer())


def _tooltip_tick():
    from . import max_chrome
    if not max_chrome._installed or not any(record['item'] for record in _hover.values()):
        return None
    waiting = False
    for record in _hover.values():
        try:
            if record['area']:
                if time.monotonic()-record['started'] >= .6:
                    record['area'].tag_redraw()
                else:
                    waiting = True
        except ReferenceError:
            pass
    return .1 if waiting else None


def install_drawing():
    global _header_handle, _tooltip_handle
    if not bpy.app.background:
        _header_handle = bpy.types.SpaceView3D.draw_handler_add(draw_pixels, (), 'HEADER', 'POST_PIXEL')
        _tooltip_handle = bpy.types.SpaceView3D.draw_handler_add(draw_tooltip, (), 'WINDOW', 'POST_PIXEL')


def remove_drawing():
    global _header_handle, _tooltip_handle
    if _header_handle:
        bpy.types.SpaceView3D.draw_handler_remove(_header_handle,'HEADER')
        _header_handle = None
    if _tooltip_handle:
        bpy.types.SpaceView3D.draw_handler_remove(_tooltip_handle,'WINDOW')
        _tooltip_handle = None
    if bpy.app.timers.is_registered(_tooltip_tick):
        bpy.app.timers.unregister(_tooltip_tick)
    _hover.clear()
    _pressed.clear()
    _tooltip_drawn.clear()


class MAX_OT_chrome_crossing_toggle(bpy.types.Operator):
    bl_idname = 'max.chrome_crossing_toggle'
    bl_label = 'Window / Crossing'

    def execute(self, context):
        context.window_manager.max_chrome_crossing = not context.window_manager.max_chrome_crossing
        return {'FINISHED'}


class MAX_MT_chrome_filter(bpy.types.Menu):
    bl_label = 'Selection Filter'

    def draw(self, context):
        self.layout.prop(context.window_manager,'max_chrome_filter',expand=True)


class MAX_MT_chrome_reference(bpy.types.Menu):
    bl_label = 'Reference Coordinate System'

    def draw(self, context):
        operation = max_status.tool(context)
        prop = {'MOVE':'move_reference','SCALE':'scale_reference'}.get(operation,'reference')
        self.layout.prop(context.scene.max_rotate,prop,expand=True)


def set_items(self, context):
    # RNA keeps pointers into these strings until the next redraw.
    global _set_items, _set_signature
    signature = tuple(entry.name for entry in context.scene.max_chrome_sets) if context else ()
    if signature != _set_signature:
        _set_signature = signature
        _set_items = [('CREATE', 'Create Selection Set', 'Save the current selection')]
        _set_items += [(name, name, 'Recall ' + name) for name in signature if name != 'CREATE']
    return _set_items


def recall_set(self, context):
    name = self.max_chrome_set
    if name == 'CREATE':
        bpy.ops.max.chrome_named_set('INVOKE_DEFAULT', action='SAVE')
    else:
        bpy.ops.max.chrome_named_set(action='RECALL', name=name)


def filter_control(row, context):
    field = row.row(align=True)
    field.ui_units_x = 3.3
    field.prop(context.window_manager, 'max_chrome_filter', text='')


def sets_control(row, context):
    field = row.row(align=True)
    field.ui_units_x = 6
    field.prop(context.window_manager, 'max_chrome_set', text='')


def bounds_hit(points, rectangle, crossing):
    """Window encloses object bounds. Crossing intersects the projected bounds."""
    if not points:
        return False
    x0,y0,x1,y1 = rectangle
    left, right = min(p.x for p in points), max(p.x for p in points)
    bottom, top = min(p.y for p in points), max(p.y for p in points)
    if crossing:
        return right >= x0 and left <= x1 and top >= y0 and bottom <= y1
    return x0 <= left and right <= x1 and y0 <= bottom and top <= y1


def cancel_pending():
    for flyout in tuple(_flyouts.values()):
        flyout.close()
    _flyouts.clear()
    _hover.clear()
    _pressed.clear()
    _tooltip_drawn.clear()
    for operator in tuple(_selections):
        operator.cleanup()


class MAX_OT_chrome_rectangle(bpy.types.Operator):
    bl_idname = 'max.chrome_rectangle'
    bl_label = 'Rectangular Selection'
    bl_description = 'Drag a Window or Crossing rectangle over visible object bounds. Right-click cancels'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self.area = context.area
        self.window = context.window
        self.start = self.end = None
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self._draw_rectangle, (), 'WINDOW', 'POST_PIXEL')
        _selections.add(self)
        self.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _draw_rectangle(self):
        if bpy.context.area != self.area or self.start is None:
            return
        x0,y0 = self.start
        x1,y1 = self.end
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader,'LINE_STRIP',{'pos':[(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)]})
        shader.bind()
        shader.uniform_float('color', (1.,.8,.1,1.))
        batch.draw(shader)

    def cleanup(self):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW')
            self.handle = None
        try:
            self.window.cursor_modal_restore()
            self.area.tag_redraw()
        except ReferenceError:
            pass
        _selections.discard(self)

    def cancel(self, context):
        self.cleanup()

    def modal(self, context, event):
        if self not in _selections:
            return {'CANCELLED'}
        if context.area != self.area or event.type in {'ESC','RIGHTMOUSE'}:
            self.cleanup()
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.start = self.end = (event.mouse_region_x,event.mouse_region_y)
            self.extend, self.subtract = event.shift, event.ctrl
        elif event.type == 'MOUSEMOVE' and self.start is not None:
            self.end = (event.mouse_region_x,event.mouse_region_y)
            self.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and self.start is not None:
            x0,y0 = self.start
            x1,y1 = self.end
            rectangle = min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)
            found = []
            for ob in context.visible_objects:
                if ob.hide_select:
                    continue
                corners = [location_3d_to_region_2d(context.region,context.region_data,ob.matrix_world @ Vector(point))
                           for point in ob.bound_box]
                points = [point for point in corners if point is not None]
                if bounds_hit(points,rectangle,context.window_manager.max_chrome_crossing):
                    found.append(ob)
            if not self.extend and not self.subtract:
                for ob in context.selected_objects:
                    ob.select_set(False)
            for ob in found:
                ob.select_set(not self.subtract)
            context.view_layer.objects.active = next(iter(context.selected_objects),None)
            self.cleanup()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


def configure(commands=None):
    """Map optional host action names to operator IDs after the corresponding batch lands."""
    _commands.clear()
    _commands.update(commands or {})


def available(idname):
    try:
        category, name = idname.split('.')
        getattr(getattr(bpy.ops, category), name).get_rna_type()
        return True
    except (AttributeError, RuntimeError, ValueError):
        return False


def button(layout, command, art, fallback='DOT', *, pressed=False, reason='', **props):
    row = layout.row(align=True)
    row.enabled = available(command) and not reason
    if not row.enabled:
        op = row.operator('max.chrome_unavailable', text='', **max_icons.ui(art, fallback))
        op.reason = reason or 'This command is unavailable until its module is installed'
    else:
        op = row.operator(command, text='', depress=pressed, **max_icons.ui(art, fallback))
        for key, value in props.items():
            setattr(op, key, value)
    return op


def optional(layout, name, art, label):
    button(layout, _commands.get(name, 'max.chrome_unavailable'), art,
           reason='' if name in _commands else label + ' is unavailable until its host module is installed')


class MAX_OT_chrome_unavailable(bpy.types.Operator):
    bl_idname = 'max.chrome_unavailable'
    bl_label = 'Unavailable Command'
    bl_description = 'This command is not supported by the installed modules'
    reason: StringProperty(default='This command is unavailable')

    @classmethod
    def description(cls, context, properties):
        return properties.reason

    def execute(self, context):
        self.report({'WARNING'}, self.reason)
        return {'CANCELLED'}


class MAX_PG_chrome_member(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)


class MAX_PG_chrome_set(bpy.types.PropertyGroup):
    members: CollectionProperty(type=MAX_PG_chrome_member)


class MAX_OT_chrome_named_set(bpy.types.Operator):
    bl_idname = 'max.chrome_named_set'
    bl_label = 'Named Selection Set'
    bl_description = 'Save, recall or remove an object selection set'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[(v,v.title(),'') for v in ('SAVE', 'RECALL', 'REMOVE')])
    name: StringProperty(name='Selection Set')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self) if self.action == 'SAVE' else self.execute(context)

    def draw(self, context):
        self.layout.prop(self, 'name', text='Name')

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, 'Named sets currently store object selections')
            return {'CANCELLED'}
        sets = context.scene.max_chrome_sets
        name = self.name.strip()
        if not name:
            return {'CANCELLED'}
        entry = sets.get(name)
        if self.action == 'SAVE':
            if not context.selected_objects:
                self.report({'WARNING'}, 'Select objects before saving a set')
                return {'CANCELLED'}
            if not entry:
                entry = sets.add()
                entry.name = name
            entry.members.clear()
            for ob in context.selected_objects:
                entry.members.add().object = ob
        elif not entry:
            return {'CANCELLED'}
        elif self.action == 'REMOVE':
            sets.remove(sets.find(name))
        else:
            objects = [member.object for member in entry.members if member.object
                       and context.view_layer.objects.get(member.object.name) == member.object
                       and not member.object.hide_get() and not member.object.hide_select]
            for ob in context.selected_objects:
                ob.select_set(False)
            for ob in objects:
                ob.select_set(True)
            context.view_layer.objects.active = objects[0] if objects else None
        return {'FINISHED'}


class MAX_MT_chrome_sets(bpy.types.Menu):
    bl_label = 'Named Selection Sets'

    def draw(self, context):
        self.layout.operator('max.chrome_named_set', text='Create Selection Set...').action = 'SAVE'
        for entry in context.scene.max_chrome_sets:
            row = self.layout.row(align=True)
            op = row.operator('max.chrome_named_set', text=entry.name)
            op.action, op.name = 'RECALL', entry.name
            op = row.operator('max.chrome_named_set', text='', icon='X')
            op.action, op.name = 'REMOVE', entry.name


class MAX_OT_chrome_selection_tool(bpy.types.Operator):
    bl_idname = 'max.chrome_selection_tool'
    bl_label = 'Selection Region'
    bl_description = 'Use a rectangular, circular or lasso selection region'
    shape: EnumProperty(items=[('RECT','Rectangular Selection',''), ('CIRCLE','Circular Selection',''),
                              ('LASSO','Lasso Selection','')])

    def execute(self, context):
        if self.shape == 'RECT' and context.mode == 'OBJECT':
            bpy.ops.max.chrome_rectangle('INVOKE_DEFAULT')
            return {'FINISHED'}
        name = {'RECT':'builtin.select_box', 'CIRCLE':'builtin.select_circle', 'LASSO':'builtin.select_lasso'}[self.shape]
        bpy.ops.wm.tool_set_by_id(name=name)
        return {'FINISHED'}


class MAX_MT_chrome_region(bpy.types.Menu):
    bl_label = 'Selection Region'

    def draw(self, context):
        for shape, label in (('RECT','Rectangular Selection'), ('CIRCLE','Circular Selection')):
            self.layout.operator('max.chrome_selection_tool', text=label).shape = shape
        row = self.layout.row()
        row.enabled = False
        row.operator('max.chrome_unavailable', text='Fence Selection').reason = 'Fence selection is not supported'
        self.layout.operator('max.chrome_selection_tool', text='Lasso Selection').shape = 'LASSO'
        row = self.layout.row()
        row.enabled = False
        row.operator('max.chrome_unavailable', text='Paint Selection').reason = 'Paint selection is not supported'


class MAX_MT_chrome_align(bpy.types.Menu):
    bl_label = 'Align'

    def draw(self, context):
        for key, label in (('align','Align'), ('quick_align','Quick Align'), ('normal_align','Normal Align'),
                           ('place_highlight','Place Highlight'), ('align_camera','Align Camera'), ('align_view','Align To View')):
            command = _commands.get(key)
            row = self.layout.row()
            row.enabled = command is not None and available(command)
            if row.enabled:
                row.operator(command, text=label)
            else:
                row.operator('max.chrome_unavailable', text=label).reason = label + ' is unavailable'


class MAX_MT_chrome_scale(bpy.types.Menu):
    bl_label = 'Select and Scale'

    def draw(self, context):
        settings = getattr(context.scene, 'max_rotate', None)
        if settings:
            for mode in ('UNIFORM', 'NON_UNIFORM', 'SQUASH'):
                self.layout.operator('max.chrome_scale_mode', text={'UNIFORM':'Select and Uniform Scale',
                    'NON_UNIFORM':'Select and Non-Uniform Scale','SQUASH':'Select and Squash'}[mode],
                    icon='RADIOBUT_ON' if settings.scale_mode == mode else 'RADIOBUT_OFF').mode = mode
        else:
            self.layout.operator('max.select_transform', text='Select and Uniform Scale').kind = 'SCALE'
            for label in ('Non-Uniform Scale', 'Squash'):
                row = self.layout.row()
                row.enabled = False
                row.operator('max.chrome_unavailable', text=label).reason = 'The shared Scale module is not installed'


class MAX_OT_chrome_scale_mode(bpy.types.Operator):
    bl_idname = 'max.chrome_scale_mode'
    bl_label = 'Select and Scale'
    bl_description = 'Activate the shared Scale tool with this scale mode'
    mode: EnumProperty(items=[(v,v.title(),'') for v in ('UNIFORM','NON_UNIFORM','SQUASH')])

    def execute(self, context):
        settings = getattr(context.scene,'max_rotate',None)
        if not settings:
            return {'CANCELLED'}
        settings.scale_mode = self.mode
        from .snaps import select_transform
        select_transform(context,'SCALE')
        return {'FINISHED'}


class MAX_MT_chrome_center(bpy.types.Menu):
    bl_label = 'Use Center'

    def draw(self, context):
        settings = getattr(context.scene, 'max_rotate', None)
        if settings:
            for mode in ('PIVOT', 'SELECTION', 'COORDINATE'):
                self.layout.prop_enum(settings, 'center', mode)
        else:
            row = self.layout.row()
            row.enabled = False
            row.label(text='Transform centre adapter unavailable')


def draw(layout, context):
    """Keep XML-confirmed groups in order. Blender scrolls an overfull header."""
    owner = max_status.feedback()
    row = layout.row(align=True)
    button(row, 'ed.undo', 'undo', 'LOOP_BACK')
    button(row, 'ed.redo', 'redo', 'LOOP_FORWARDS')
    row.separator()
    button(row, 'wm.tool_set_by_id', 'link', 'LINKED', name='max.select_link',
           pressed=bool(owner and owner.tool_pressed(context, 'LINK')),
           reason='' if owner else 'Link picking requires the mode-feedback module')
    button(row, 'object.parent_clear', 'unlink', 'UNLINKED', type='CLEAR_KEEP_TRANSFORM')
    button(row, 'max.chrome_unavailable', 'bind_space_warp', reason='Space Warp binding is not supported')
    row.separator()
    filter_control(row, context)
    button(row, 'wm.tool_set_by_id', 'select_object', 'RESTRICT_SELECT_OFF', name='builtin.select_box',
           pressed=bool(owner and owner.tool_pressed(context, 'SELECT')))
    optional(row, 'select_by_name', 'select_by_name', 'Select From Scene')
    row.menu('MAX_MT_chrome_region', text='', **max_icons.ui('region_rect', 'SELECT_SET'))
    sub = row.row(align=True)
    sub.enabled = context.mode == 'OBJECT'
    sub.prop(context.window_manager, 'max_chrome_crossing', text='', toggle=True,
             **max_icons.ui('window_crossing', 'SELECT_INTERSECT'))
    row.separator()
    for kind, art in (('MOVE','move'), ('ROTATE','rotate'), ('SCALE','scale')):
        button(row, 'max.select_transform', art, 'ORIENTATION_GLOBAL', kind=kind,
               pressed=bool(owner and owner.tool_pressed(context, kind)))
        if kind == 'SCALE':
            row.menu('MAX_MT_chrome_scale', text='', icon='DOWNARROW_HLT')
    optional(row, 'select_place', 'select_place', 'Select and Place')
    row.separator()
    settings = getattr(context.scene, 'max_rotate', None)
    if settings:
        row.prop(settings, 'reference', text='')
        if settings.reference == 'PICK':
            row.prop(settings, 'pick', text='')
    else:
        disabled = row.row()
        disabled.enabled = False
        disabled.label(text='Reference unavailable')
    row.menu('MAX_MT_chrome_center', text='', **max_icons.ui('pivot', 'PIVOT_MEDIAN'))
    row.separator()
    optional(row, 'shortcut_override', 'shortcut_override', 'Keyboard Shortcut Override')
    from . import snaps
    snaps.draw_toolbar(row, context)
    row.separator()
    sets_control(row, context)
    row.separator()
    optional(row, 'mirror', 'mirror', 'Mirror')
    row.menu('MAX_MT_chrome_align', text='', **max_icons.ui('align', 'ALIGN_CENTER'))
    row.separator()
    for key, art, label in (('scene_explorer','scene_explorer','Scene Explorer'),
                            ('layer_explorer','layer_explorer','Layer Explorer'),
                            ('ribbon','ribbon','Toggle Ribbon'), ('track_view','track_view','Track View'),
                            ('schematic_view','schematic_view','Schematic View')):
        optional(row, key, art, label)


classes = (MAX_OT_chrome_crossing_toggle, MAX_MT_chrome_filter, MAX_MT_chrome_reference,
           MAX_OT_chrome_unavailable, MAX_PG_chrome_member, MAX_PG_chrome_set,
           MAX_OT_chrome_named_set, MAX_MT_chrome_sets, MAX_OT_chrome_selection_tool,
           MAX_MT_chrome_region, MAX_MT_chrome_align, MAX_MT_chrome_scale, MAX_MT_chrome_center,
           MAX_OT_chrome_rectangle, MAX_OT_chrome_scale_mode)
