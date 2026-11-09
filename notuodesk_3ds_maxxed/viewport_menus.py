"""Max viewport label commands. Every command uses the clicked drawable region."""
import bpy
from bpy.props import EnumProperty, StringProperty

LABEL_MENUS = dict(zip(('PLUS', 'VIEW', 'QUALITY', 'SHADING'),
                      ('MAX_MT_vp_general', 'MAX_MT_vp_point_of_view', 'MAX_MT_vp_quality', 'MAX_MT_vp_shading')))


def _space(context):
    if context.area and context.area.type == 'VIEW_3D':
        return context.area.spaces.active
    window = context.window
    if window:
        return next((a.spaces.active for a in window.screen.areas if a.type == 'VIEW_3D'), None)
    return None


def region_at(context, x, y):
    if not context.window:
        return None, None
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW' and region.x <= x < region.x + region.width and region.y <= y < region.y + region.height:
                    return area, region
    return None, None


class MAX_OT_viewport_label(bpy.types.Operator):
    bl_idname = 'max.viewport_label'
    bl_label = 'Viewport Label Menu'
    bl_description = 'Open the menu for the viewport label under the pointer'

    def invoke(self, context, event):
        from . import overlay
        area, region = region_at(context, event.mouse_x, event.mouse_y)
        if area is None or not overlay._visible(context):
            return {'PASS_THROUGH'}
        with context.temp_override(area=area, region=region):
            menu = overlay.hit_test(bpy.context, event.mouse_x-region.x, event.mouse_y-region.y)
            if menu:
                self.menu = menu
                self.area = area
                self.region = region
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def modal(self, context, event):
        from . import overlay
        if event.type in {'ESC', 'RIGHTMOUSE'} or overlay._handle is None:
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            try:
                with context.temp_override(area=self.area,region=self.region):
                    if overlay.hit_test(bpy.context,event.mouse_x-self.region.x,event.mouse_y-self.region.y) != self.menu:
                        return {'CANCELLED'}
                    # Open on release. Opening on press lets the same click release
                    # dismiss the popup before the user can choose a command.
                    bpy.ops.wm.call_menu('INVOKE_DEFAULT',name=self.menu)
            except (ReferenceError, RuntimeError):
                return {'CANCELLED'}
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class MAX_OT_viewport_shading(bpy.types.Operator):
    bl_idname = 'max.viewport_shading'
    bl_label = 'Viewport Shading'
    bl_description = 'Set shading for this viewport'
    mode: EnumProperty(items=[(k, n, d) for k, n, d in (
        ('DEFAULT', 'Default Shading', 'Solid lighting and object colours'),
        ('MAPS', 'Shaded with Maps', 'Solid preview with available image textures'),
        ('MATERIALS', 'Materials', 'Material preview'), ('FLAT', 'Flat Color', 'Unlit object colours'),
        ('CLAY', 'Clay', 'One neutral material'), ('WIRE', 'Wireframe', 'Visible mesh edges'),
        ('REALISTIC', 'Realistic', 'Rendered viewport using the scene renderer'),
        ('ACTIVESHADE', 'ActiveShade', 'ActiveShade requires a supported Max renderer'))])

    def execute(self, context):
        space = _space(context)
        if not space:
            self.report({'WARNING'}, 'Choose a viewport first')
            return {'CANCELLED'}
        if self.mode == 'ACTIVESHADE':
            self.report({'WARNING'}, 'ActiveShade is unavailable. Use Realistic for a rendered viewport')
            return {'CANCELLED'}
        s = space.shading
        s.type = {'WIRE': 'WIREFRAME', 'MATERIALS': 'MATERIAL', 'REALISTIC': 'RENDERED'}.get(self.mode, 'SOLID')
        if s.type == 'SOLID':
            s.light = 'FLAT' if self.mode == 'FLAT' else 'STUDIO'
            s.color_type = {'CLAY': 'SINGLE', 'MAPS': 'TEXTURE'}.get(self.mode, 'OBJECT')
            if self.mode == 'CLAY':
                s.single_color = (.65, .65, .65)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class MAX_OT_viewport_quality(bpy.types.Operator):
    bl_idname = 'max.viewport_quality'
    bl_label = 'Viewport Quality'
    bl_description = 'Set supported preview quality for this viewport'
    level: EnumProperty(items=[('STANDARD', 'Standard', 'Solid viewport'),
                              ('PERFORMANCE', 'Performance', 'Solid viewport without shadows or cavity'),
                              ('HIGH', 'High Quality', 'Material preview, not Nitrous')])

    def execute(self, context):
        space = _space(context)
        if not space:
            return {'CANCELLED'}
        s = space.shading
        s.type = 'MATERIAL' if self.level == 'HIGH' else 'SOLID'
        s.show_shadows = self.level != 'PERFORMANCE'
        s.show_cavity = self.level == 'STANDARD'
        return {'FINISHED'}


class MAX_OT_view_camera(bpy.types.Operator):
    bl_idname = 'max.view_camera'
    bl_label = 'View Camera'
    bl_description = 'Look through this scene camera in this viewport'
    name: StringProperty()

    def execute(self, context):
        camera = context.scene.objects.get(self.name)
        if not camera or camera.type != 'CAMERA' or context.region_data is None:
            self.report({'WARNING'}, 'Camera is unavailable in this viewport')
            return {'CANCELLED'}
        context.space_data.use_local_camera = True
        context.space_data.camera = camera
        context.region_data.view_perspective = 'CAMERA'
        return {'FINISHED'}


class MAX_OT_viewport_direction(bpy.types.Operator):
    bl_idname = 'max.viewport_direction'
    bl_label = 'Point of View'
    bl_description = 'Change only the current viewport direction'
    direction: EnumProperty(items=[(v, v.title(), '') for v in
                                  ('TOP', 'BOTTOM', 'FRONT', 'BACK', 'LEFT', 'RIGHT', 'PERSP', 'USER')])

    def execute(self, context):
        if not context.region_data:
            return {'CANCELLED'}
        if self.direction in {'PERSP', 'USER'}:
            context.region_data.view_perspective = 'PERSP' if self.direction == 'PERSP' else 'ORTHO'
        else:
            bpy.ops.view3d.view_axis(type=self.direction, align_active=False)
        return {'FINISHED'}


class MAX_OT_viewport_configure(bpy.types.Operator):
    bl_idname = 'max.viewport_configure'
    bl_label = 'Viewport Configuration'
    bl_description = 'Configure this viewport display, safe frames and Home Grid'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        space = _space(context)
        if not space:
            self.layout.label(text='Choose a viewport first')
            return
        for title, fields in (
            ('Visual Style', ((space.overlay, 'show_wireframes', 'Edged Faces'),
                              (space.overlay, 'show_stats', 'Statistics'))),
            ('Display', ((space.overlay, 'show_floor', 'Home Grid'),
                         (space, 'show_region_ui', 'Command Panel'))),
        ):
            box = self.layout.box()
            box.label(text=title)
            for owner, prop, label in fields:
                box.prop(owner, prop, text=label)
        camera = space.camera or context.scene.camera
        if camera:
            self.layout.prop(camera.data, 'show_safe_areas', text='Safe Frames')
        from . import get_prefs
        prefs = get_prefs()
        if prefs:
            self.layout.prop(prefs, 'show_viewcube', text='ViewCube')
            grid = self.layout.box()
            grid.label(text='Home Grid')
            grid.prop(prefs.snap_settings, 'grid_spacing', text='Grid Spacing')
            grid.prop(prefs.snap_settings, 'major_lines', text='Major Lines every Nth Grid Line')
        self.layout.label(text='Viewport renderer and grid extent differ from Nitrous', icon='INFO')

    def execute(self, context):
        return {'FINISHED'}


class MAX_MT_vp_general(bpy.types.Menu):
    bl_label = '[+]'

    def draw(self, context):
        l, space = self.layout, _space(context)
        if not space:
            return
        l.prop(space.overlay, 'show_floor', text='Show Grids')
        l.prop(space.overlay, 'show_stats', text='Statistics')
        camera = space.camera or context.scene.camera
        row = l.row()
        row.enabled = camera is not None
        if camera:
            row.prop(camera.data, 'show_safe_areas', text='Show Safe Frames')
        else:
            row.label(text='Show Safe Frames (camera view required)')
        from . import get_prefs
        prefs = get_prefs()
        if prefs:
            l.prop(prefs, 'show_viewcube', text='ViewCube')
        for menu, label in (('MAX_MT_viewcube', 'ViewCube'), ('MAX_MT_xview', 'xView')):
            if hasattr(bpy.types, menu):
                l.menu(menu, text=label)
        l.separator()
        l.operator('max.viewport_configure', text='Configure Viewports...')


class MAX_MT_vp_point_of_view(bpy.types.Menu):
    bl_label = 'Point of View'

    def draw(self, context):
        for direction in ('TOP', 'BOTTOM', 'FRONT', 'BACK', 'LEFT', 'RIGHT', 'PERSP', 'USER'):
            self.layout.operator('max.viewport_direction', text={'PERSP': 'Perspective'}.get(direction, direction.title())).direction = direction
        self.layout.separator()
        cameras = [ob for ob in context.scene.objects if ob.type == 'CAMERA']
        for camera in cameras:
            self.layout.operator('max.view_camera', text=camera.name).name = camera.name
        if not cameras:
            row = self.layout.row()
            row.enabled = False
            row.label(text='No scene cameras')


class MAX_MT_vp_quality(bpy.types.Menu):
    bl_label = 'Viewport Quality'

    def draw(self, context):
        for value, label in (('STANDARD', 'Standard'), ('PERFORMANCE', 'Performance'), ('HIGH', 'High Quality')):
            self.layout.operator('max.viewport_quality', text=label).level = value


class MAX_MT_vp_shading(bpy.types.Menu):
    bl_label = 'Viewport Shading'

    def draw(self, context):
        for value, label in (('DEFAULT', 'Default Shading'), ('MAPS', 'Shaded with Maps'),
                             ('MATERIALS', 'Materials'), ('FLAT', 'Flat Color'), ('CLAY', 'Clay'),
                             ('WIRE', 'Wireframe'), ('REALISTIC', 'Realistic')):
            self.layout.operator('max.viewport_shading', text=label).mode = value
        row = self.layout.row()
        row.enabled = False
        row.operator('max.viewport_shading', text='ActiveShade (renderer unavailable)').mode = 'ACTIVESHADE'
        space = _space(context)
        if space:
            self.layout.prop(space.overlay, 'show_wireframes', text='Edged Faces')


classes = (MAX_OT_viewport_label, MAX_OT_viewport_shading, MAX_OT_viewport_quality,
           MAX_OT_view_camera, MAX_OT_viewport_direction, MAX_OT_viewport_configure,
           MAX_MT_vp_general, MAX_MT_vp_point_of_view, MAX_MT_vp_quality, MAX_MT_vp_shading)
