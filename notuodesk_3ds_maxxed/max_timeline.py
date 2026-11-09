"""A time slider and selected-object key track, independent of native timeline drawing."""
import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_handle = None
_viewport_handle = None


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
    blf.size(0, size)
    blf.position(0, x, y, 0)
    blf.color(0, *color)
    blf.draw(0, text)


def draw_track():
    context = bpy.context
    if not owned(context):
        return
    region, scene = context.region, context.scene
    width, height = region.width, region.height
    scale = context.preferences.system.ui_scale
    prompt_height = 22 * scale
    _rectangle(0, 0, width, height, (.23,.07,.07,1) if scene.tool_settings.use_keyframe_insert_auto else (.13,.13,.13,1))
    _rectangle(0, 0, width, prompt_height, (.19,.19,.19,1))
    baseline = min(height-12*scale, prompt_height + 27*scale)
    count = max(1, round((scene.frame_end-scene.frame_start)/max(2, width/(65*scale))))
    step = max(1, 10 ** math.floor(math.log10(count)))
    step *= next((v for v in (1, 2, 5, 10) if step*v >= count), 10)
    first = math.ceil(scene.frame_start/step)*step
    for frame in range(first, scene.frame_end+1, step):
        x = frame_x(scene, frame, width)
        _rectangle(x, baseline, x+1, baseline+6*scale, (.45,.45,.45,1))
        _text(x+2*scale, baseline+8*scale, str(frame), round(10*scale))
    for frame in key_frames(context):
        if scene.frame_start <= frame <= scene.frame_end:
            x = frame_x(scene, frame, width)
            _rectangle(x-2*scale, prompt_height+3*scale, x+2*scale, baseline-3*scale, (.75,.68,.30,1))
    x = frame_x(scene, scene.frame_current, width)
    _rectangle(x-1, prompt_height, x+2, height, (1.,.72,.10,1))
    _text(12*scale, max(prompt_height+2, height-16*scale),
          f'{scene.frame_current} / {scene.frame_start} to {scene.frame_end}', round(11*scale))
    from . import max_status
    _text(10*scale, 6*scale, max_status.prompt_text(context), round(11*scale))


def draw_controls(layout, context):
    from . import max_icons
    row = layout.row(align=True)
    keys = row.row(align=True)
    keys.alert = context.scene.tool_settings.use_keyframe_insert_auto
    keys.prop(context.scene.tool_settings, 'use_keyframe_insert_auto', text='Auto Key', toggle=True)
    keys.operator('max.chrome_key', text='Set Key').remove = False
    keys.operator('max.chrome_key', text='', icon='KEY_DEHLT').remove = True
    row.separator()
    for action, art, fallback in (('FIRST','first_frame','REW'), ('PREVIOUS','previous_frame','PREV_KEYFRAME'),
                                  ('PLAY','play','PAUSE' if context.screen.is_animation_playing else 'PLAY'),
                                  ('NEXT','next_frame','NEXT_KEYFRAME'), ('LAST','last_frame','FF')):
        row.operator('max.chrome_transport', text='', **max_icons.ui(art, fallback)).action = action
    row.prop(context.scene, 'frame_current', text='Frame')
    row.separator()
    row.operator('max.chrome_time_config', text='', icon='TIME')


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
        if not owned(context) or event.mouse_region_y < 22*context.preferences.system.ui_scale:
            return {'PASS_THROUGH'}
        self.original = context.scene.frame_current
        context.scene.frame_set(frame_from_x(context.scene, event.mouse_region_x, context.region.width))
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
            context.scene.frame_set(frame_from_x(context.scene, event.mouse_region_x, context.region.width))
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


classes = (MAX_OT_chrome_time_config, MAX_OT_chrome_transport, MAX_OT_chrome_key, MAX_OT_chrome_scrub)
