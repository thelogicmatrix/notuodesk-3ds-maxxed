"""A time slider and selected-object key track, independent of native timeline drawing."""
import math
from pathlib import Path

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_handle = None
_viewport_handle = None
_font = None


def font():
    global _font
    if _font is None:
        path = Path('C:/Windows/Fonts/tahoma.ttf')
        _font = blf.load(str(path)) if path.is_file() else 0
    return _font


def key_curves(ob):
    animation = ob.animation_data
    if not animation or not animation.action:
        return []
    action = animation.action
    legacy = getattr(action, 'fcurves', None)
    if legacy is not None:
        return list(legacy)
    curves = []
    slot = getattr(animation, 'action_slot', None)
    if slot:
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, 'channelbag'):
                    bag = strip.channelbag(slot)
                    if bag:
                        curves.extend(bag.fcurves)
    return curves


def key_frames(context):
    return sorted({float(key.co.x) for ob in context.selected_objects for curve in key_curves(ob)
                   for key in curve.keyframe_points})


def frame_from_x(scene, x, width, margin=12):
    fraction = max(0., min(1., (x-margin)/max(1, width-2*margin)))
    return round(scene.frame_start + fraction * (scene.frame_end-scene.frame_start))


def frame_x(scene, frame, width, margin=12):
    return margin + (frame-scene.frame_start)/max(1, scene.frame_end-scene.frame_start) * max(1, width-2*margin)


def track_margin(context):
    return 44*context.preferences.system.ui_scale


def owned(context):
    from . import max_chrome
    return (max_chrome.active(context) and (max_chrome.timeline_area(context.area) or
            (context.area.type == 'DOPESHEET_EDITOR' and context.space_data.mode == 'TIMELINE')))


def _rectangle(x0, y0, x1, y1, color):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos': [(x0,y0), (x1,y0), (x1,y1), (x0,y0), (x1,y1), (x0,y1)]})
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def _text(x, y, text, size=11, color=(.85,.85,.85,1)):
    face = font()
    blf.size(face, size)
    blf.position(face, x, y, 0)
    blf.color(face, *color)
    blf.draw(face, text)


def track_metrics(width, height, scale):
    """Reference-sized 20px slider and 28px track above two 22px status rows."""
    return dict(slider=(0, 72*scale, width, 92*scale),
                track=(0, 44*scale, width, 72*scale))


def _frame(x0, y0, x1, y1, fill=(.32,.32,.32,1)):
    _rectangle(x0, y0, x1, y1, (.15,.15,.15,1))
    _rectangle(x0+1, y0+1, x1-1, y1-1, fill)


def draw_track():
    context = bpy.context
    if not owned(context):
        return
    region, scene = context.region, context.scene
    width, height = region.width, region.height
    scale = context.preferences.system.ui_scale
    height = 92*scale
    metrics = track_metrics(width, height, scale)
    track_bottom, track_top = metrics['track'][1], metrics['track'][3]
    _rectangle(0, 0, width, height, (42/255,42/255,42/255,1))
    _rectangle(0, track_top, width, height, (.267,.267,.267,1))
    _rectangle(44*scale, track_bottom+3*scale, width, track_top, (.16,.16,.16,1))
    yellow = (.64,.60,.15,1)
    _rectangle(0, track_bottom, width, track_bottom+2*scale,
               (.55,.12,.08,1) if scene.tool_settings.use_keyframe_insert_auto else (.27,.27,.27,1))
    margin = track_margin(context)
    count = max(1, round((scene.frame_end-scene.frame_start)/max(2, (width-2*margin)/(70*scale))))
    step = max(1, 10 ** math.floor(math.log10(count)))
    step *= next((v for v in (1, 2, 5, 10) if step*v >= count), 10)
    first = math.ceil(scene.frame_start/step)*step
    for frame in range(first, scene.frame_end+1, step):
        x = frame_x(scene, frame, width, margin)
        _rectangle(x, track_top-19*scale, x+scale, track_top, (.43,.43,.43,1))
        _text(x-3*scale, track_bottom+6*scale, str(frame), round(10*scale), (.7,.7,.7,1))
    minor = max(1, step//5)
    for frame in range(math.ceil(scene.frame_start/minor)*minor, scene.frame_end+1, minor):
        if frame % step:
            x = frame_x(scene, frame, width, margin)
            _rectangle(x, track_top-9*scale, x+scale, track_top, (.43,.43,.43,1))
    for frame in key_frames(context):
        if scene.frame_start <= frame <= scene.frame_end:
            x = frame_x(scene, frame, width, margin)
            _rectangle(x-1*scale, track_bottom+3*scale, x+1*scale, track_top-2*scale, (.82,.22,.18,1))
    x = frame_x(scene, scene.frame_current, width, margin)
    _rectangle(x-3*scale, track_bottom+3*scale, x+3*scale, track_top-1*scale, yellow)
    _rectangle(x, track_bottom+3*scale, x+scale, track_top-1*scale, (.83,.80,.23,1))
    thumb_width = 128*scale
    left = max(2*scale, min(width-thumb_width-2*scale,
                          x-thumb_width/2))
    _frame(left, track_top+3*scale, left+thumb_width, height-3*scale, (.38,.38,.38,1))
    _rectangle(left+13*scale,track_top+3*scale,left+14*scale,height-3*scale,(.27,.27,.27,1))
    _rectangle(left+thumb_width-14*scale,track_top+3*scale,left+thumb_width-13*scale,height-3*scale,(.27,.27,.27,1))
    _text(left+4*scale, track_top+6*scale, '<', round(9*scale))
    _text(left+thumb_width-10*scale, track_top+6*scale, '>', round(9*scale))
    caption = f'{scene.frame_current} / {scene.frame_end}'
    blf.size(font(), round(10*scale))
    _text(left+(thumb_width-blf.dimensions(font(),caption)[0])/2,
          track_top+6*scale, caption, round(10*scale))
    from . import max_status
    from . import max_icons
    gpu.state.blend_set('ALPHA')
    max_icons.draw('curve_editor',20*scale,(track_bottom+track_top)/2,18*scale)
    max_status.draw_pixels(context)
    draw_bottom_controls(context)


def bottom_items(context):
    """Pixel controls and their real routes share one layout for draw and hit testing."""
    s = context.preferences.system.ui_scale
    width = context.region.width/s
    start = max(0, width-366)
    items = []
    def item(key, rect, *, art='', text='', command='', props=None, enabled=True, pressed=False):
        items.append(dict(key=key, rect=tuple(v*s for v in rect), art=art, text=text,
                          command=command, props=props or {}, enabled=enabled, pressed=pressed))
    for i, (action, art) in enumerate((('FIRST','first_frame'), ('PREVIOUS','previous_frame'),
                                     ('PLAY','play'), ('NEXT','next_frame'), ('LAST','last_frame'))):
        item(action, (start+i*19,22,start+(i+1)*19,44), art=art,
             command='max.chrome_transport', props={'action':action},
             pressed=action == 'PLAY' and context.screen.is_animation_playing)
    item('key_mode',(start,0,start+20,22), art='time_key_mode', command='max.chrome_key_mode',
         pressed=context.window_manager.max_chrome_key_mode)
    item('frame',(start+20,1,start+76,21),text=str(context.scene.frame_current), command='max.chrome_frame')
    item('time_config',(start+77,0,start+97,22), art='time_config',command='max.chrome_time_config')
    x = start+100
    # Max's large key button arms Set Key mode. There is no matching owner yet.
    item('set_key',(x,1,x+36,43),art='time_set_key',enabled=False)
    item('auto_key',(x+39,23,x+81,43),text='Auto',command='max.chrome_auto_key',
         pressed=context.scene.tool_settings.use_keyframe_insert_auto)
    item('set_key_text',(x+39,1,x+81,21),text='Set K.',command='max.chrome_key',
         enabled=context.mode == 'OBJECT' and bool(context.selected_objects))
    item('key_filter',(x+84,23,x+180,43),text='Selected',enabled=False)
    item('selection_list',(x+84,1,x+106,21),art='time_selection_list',enabled=False)
    item('key_filters',(x+109,1,x+180,21),text='Filters...',enabled=False)
    for i, (key, art, command, props) in enumerate((
        ('zoom','nav_zoom','view3d.zoom',{}), ('zoom_all','nav_zoom_all','',{}),
        ('extents','nav_extents','max.zoom_extents',{}), ('extents_all','nav_extents_all','view3d.view_all',{'use_all_regions':True}),
        ('zoom_region','nav_zoom_region','view3d.zoom_border',{}), ('pan','nav_pan','view3d.move',{}),
        ('orbit','nav_orbit','view3d.rotate',{}), ('maximize','nav_maximize','max.toggle_quad',{}))):
        nx = start+286+(i%4)*20
        ny = 22 if i < 4 else 0
        item(key,(nx,ny,nx+20,ny+22),art=art,command=command,props=props,enabled=bool(command))
    return items


def draw_bottom_controls(context):
    from . import max_icons
    scale = context.preferences.system.ui_scale
    gpu.state.blend_set('ALPHA')
    for item in bottom_items(context):
        x0,y0,x1,y1 = item['rect']
        if item['key'] in {'frame','key_filter'}:
            _frame(x0,y0,x1,y1,(.30,.30,.30,1))
        elif item['key'] in {'set_key','auto_key','set_key_text','key_filters'}:
            _frame(x0,y0,x1,y1,(.43,.12,.10,1) if item['pressed'] else (.36,.36,.36,1))
        elif item['pressed']:
            _rectangle(x0,y0,x1,y1,(.37,.54,.76,1))
        if item['art']:
            gpu.state.blend_set('ALPHA')
            size = min(x1-x0,y1-y0)-3*scale
            max_icons.draw(item['art'],(x0+x1)/2,(y0+y1)/2,size)
        if item['text']:
            _text(x0+4*scale,(y0+y1)/2-3*scale,item['text'],round(10*scale))
        if item['key'] == 'key_filter':
            _text(x1-13*scale,y0+6*scale,'\u2304',round(11*scale))
        if not item['enabled']:
            gpu.state.blend_set('ALPHA')
            _rectangle(x0,y0,x1,y1,(.267,.267,.267,.50))
    gpu.state.blend_set('NONE')


def pointer(context, event):
    from . import max_chrome, max_status
    if event.type != 'LEFTMOUSE':
        return False
    area = next((a for a in context.window.screen.areas if max_chrome.timeline_area(a)
                 and a.x <= event.mouse_x < a.x+a.width and a.y <= event.mouse_y < a.y+a.height),None)
    if area is None:
        return False
    region = next(r for r in area.regions if r.type == 'WINDOW')
    x,y = event.mouse_x-region.x,event.mouse_y-region.y
    scale = context.preferences.system.ui_scale
    if 44*scale <= y < 72*scale and x < 44*scale:
        if event.value == 'PRESS':
            override = max_status._viewport(context)
            with context.temp_override(**override):
                if bpy.ops.max.workspace_track_view.poll():
                    bpy.ops.max.workspace_track_view('INVOKE_DEFAULT')
        return True
    if y >= 44*scale:
        return False
    if event.value != 'PRESS':
        return True
    with context.temp_override(area=area,region=region):
        ctx = bpy.context
        if max_status.pointer(ctx,x,y):
            return True
        item = next((i for i in bottom_items(ctx) if i['rect'][0] <= x < i['rect'][2]
                     and i['rect'][1] <= y < i['rect'][3]),None)
        if item and item['enabled'] and item['command']:
            override = max_status._viewport(ctx) if item['key'] in {
                'zoom','zoom_all','extents','extents_all','zoom_region','pan','orbit','maximize'} else {}
            with ctx.temp_override(**override):
                category,name = item['command'].split('.')
                operator = getattr(getattr(bpy.ops,category),name)
                if operator.poll():
                    operator('INVOKE_DEFAULT',**item['props'])
    area.tag_redraw()
    return True


def draw_controls(layout, context):
    from . import max_icons, max_status
    row = layout.row(align=True)
    max_status.draw(row, context)
    row.separator_spacer()
    for action, art, fallback in (('FIRST','first_frame','REW'), ('PREVIOUS','previous_frame','PREV_KEYFRAME'),
                                  ('PLAY','play','PAUSE' if context.screen.is_animation_playing else 'PLAY'),
                                  ('NEXT','next_frame','NEXT_KEYFRAME'), ('LAST','last_frame','FF')):
        row.operator('max.chrome_transport', text='', **max_icons.ui(art, fallback)).action = action
    keys = row.row(align=True)
    keys.alert = context.scene.tool_settings.use_keyframe_insert_auto
    keys.prop(context.scene.tool_settings, 'use_keyframe_insert_auto', text='Auto Key', toggle=True)


class MAX_OT_chrome_time_config(bpy.types.Operator):
    bl_idname = 'max.chrome_time_config'
    bl_label = 'Time Configuration'
    bl_description = 'Set the active animation range and frame rate'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        for name, label in (('frame_start', 'Start Time'), ('frame_end', 'End Time')):
            self.layout.prop(context.scene, name, text=label)
        self.layout.prop(context.scene.render, 'fps', text='Frame Rate')
        self.layout.prop(context.scene.render, 'fps_base', text='Rate Base')

    def execute(self, context):
        return {'FINISHED'}


class MAX_OT_chrome_transport(bpy.types.Operator):
    bl_idname = 'max.chrome_transport'
    bl_label = 'Time Control'
    bl_description = 'Move to a range end, adjacent selected-object key, or play and stop'
    action: bpy.props.EnumProperty(items=[(v,v.title(),'') for v in ('FIRST','PREVIOUS','PLAY','NEXT','LAST')])

    def execute(self, context):
        scene = context.scene
        if self.action == 'PLAY':
            bpy.ops.screen.animation_play()
        elif self.action in {'FIRST', 'LAST'}:
            scene.frame_set(scene.frame_start if self.action == 'FIRST' else scene.frame_end)
        else:
            if not context.window_manager.max_chrome_key_mode:
                scene.frame_set(max(scene.frame_start, min(scene.frame_end,
                    scene.frame_current+(-1 if self.action == 'PREVIOUS' else 1))))
                return {'FINISHED'}
            keys = key_frames(context)
            candidates = [f for f in keys if f < scene.frame_current] if self.action == 'PREVIOUS' else [f for f in keys if f > scene.frame_current]
            target = (max(candidates) if self.action == 'PREVIOUS' else min(candidates)) if candidates else scene.frame_current
            scene.frame_set(round(target))
        return {'FINISHED'}


class MAX_OT_chrome_key(bpy.types.Operator):
    bl_idname = 'max.chrome_key'
    bl_label = 'Set Key'
    bl_description = 'Insert or delete selected-object location, rotation and scale keys'
    bl_options = {'REGISTER', 'UNDO'}
    remove: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            rotation = 'rotation_quaternion' if ob.rotation_mode == 'QUATERNION' else 'rotation_axis_angle' if ob.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler'
            for path in ('location', rotation, 'scale'):
                if self.remove:
                    if ob.animation_data and ob.animation_data.action:
                        ob.keyframe_delete(data_path=path, frame=context.scene.frame_current)
                else:
                    ob.keyframe_insert(data_path=path, frame=context.scene.frame_current, group='Transform')
        return {'FINISHED'}


class MAX_OT_chrome_scrub(bpy.types.Operator):
    bl_idname = 'max.chrome_scrub'
    bl_label = 'Time Slider'
    bl_description = 'Drag to change the current animation frame. Right-click cancels'

    def invoke(self, context, event):
        if not owned(context) or event.mouse_region_y < 44*context.preferences.system.ui_scale:
            return {'PASS_THROUGH'}
        self.original = context.scene.frame_current
        context.scene.frame_set(frame_from_x(context.scene, event.mouse_region_x, context.region.width,
                                            track_margin(context)))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not owned(context):
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            context.scene.frame_set(self.original)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            context.scene.frame_set(frame_from_x(context.scene, event.mouse_region_x, context.region.width,
                                                track_margin(context)))
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}


def register():
    global _handle, _viewport_handle
    if _handle is None and not bpy.app.background:
        _handle = bpy.types.SpaceDopeSheetEditor.draw_handler_add(draw_track, (), 'WINDOW', 'POST_PIXEL')
    if _viewport_handle is None and not bpy.app.background:
        _viewport_handle = bpy.types.SpaceView3D.draw_handler_add(draw_track, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle, _viewport_handle
    if _handle is not None:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    if _viewport_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_viewport_handle, 'WINDOW')
        _viewport_handle = None


class MAX_OT_chrome_key_mode(bpy.types.Operator):
    bl_idname = 'max.chrome_key_mode'
    bl_label = 'Key Mode Toggle'

    def execute(self, context):
        context.window_manager.max_chrome_key_mode = not context.window_manager.max_chrome_key_mode
        return {'FINISHED'}


class MAX_OT_chrome_auto_key(bpy.types.Operator):
    bl_idname = 'max.chrome_auto_key'
    bl_label = 'Auto Key'

    def execute(self, context):
        settings = context.scene.tool_settings
        settings.use_keyframe_insert_auto = not settings.use_keyframe_insert_auto
        return {'FINISHED'}


class MAX_OT_chrome_time_tag(bpy.types.Operator):
    bl_idname = 'max.chrome_time_tag'
    bl_label = 'Add Time Tag'
    bl_description = 'Name a timeline marker at the current frame'
    bl_options = {'REGISTER', 'UNDO'}
    name: bpy.props.StringProperty(name='Name', default='Time Tag')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        context.scene.timeline_markers.new(self.name, frame=context.scene.frame_current)
        return {'FINISHED'}


class MAX_OT_chrome_frame(bpy.types.Operator):
    bl_idname = 'max.chrome_frame'
    bl_label = 'Current Time'
    frame: bpy.props.IntProperty(name='Frame')

    def invoke(self, context, event):
        self.frame = context.scene.frame_current
        return context.window_manager.invoke_props_dialog(self, width=180)

    def execute(self, context):
        context.scene.frame_set(self.frame)
        return {'FINISHED'}


classes = (MAX_OT_chrome_time_config, MAX_OT_chrome_transport, MAX_OT_chrome_key, MAX_OT_chrome_scrub,
           MAX_OT_chrome_key_mode, MAX_OT_chrome_auto_key, MAX_OT_chrome_time_tag, MAX_OT_chrome_frame)
