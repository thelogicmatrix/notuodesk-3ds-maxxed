"""Explicit, reversible installation of Maxxed workspace chrome for the wave-2 host."""
import bpy
import blf
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatVectorProperty
from . import max_status, max_timeline, max_toolbar, overlay, theme

_installed = False
_originals = []
_keys = []
_layout_changes = []
_timeline_areas = {}
_timeline_original_heights = {}
_timeline_resize_jobs = {}
_quad_changes = {}
_pointers = {}
_menus = None
_explorer_layout = None
_command_panel_layout = None
_region_overlap = None
_label_callbacks = None


def _label_regions(context):
    region = context.region
    if not region or region.type != 'WINDOW' or context.area.type != 'VIEW_3D':
        return []
    scale = max(.5, context.preferences.system.ui_scale)
    face = max_timeline.font()
    blf.size(face, round(10*scale))
    shading = context.space_data.shading
    quality = ('High Quality' if shading.type in {'MATERIAL', 'RENDERED'} else
               'Performance' if not shading.show_shadows and not shading.show_cavity else 'Standard')
    labels = [('MAX_MT_vp_general', '+'), ('MAX_MT_vp_point_of_view', overlay.view_name(context)),
              ('MAX_MT_vp_quality', quality), ('MAX_MT_vp_shading', overlay.shading_name(context.space_data))]
    x, y = 4*scale, region.height-14*scale
    result = []
    for menu, caption in labels:
        text = '['+caption+(' ' if caption != '+' else '')+']'
        width = blf.dimensions(face, text)[0]+2*scale
        if x+width > region.width-4*scale:
            break
        result.append((menu, text, (x, y-2*scale, x+width, y+11*scale)))
        x += width
    return result


def _draw_labels():
    context = bpy.context
    if context.area.type != 'VIEW_3D' or not overlay._visible(context):
        return
    entries = _label_regions(context)
    keys = ('PLUS', 'VIEW', 'QUALITY', 'SHADING')
    overlay.label_rects[context.region.as_pointer()] = [(key, *rect) for key, (_, _, rect) in zip(keys, entries)]
    for _, caption, (x, y, _, _) in entries:
        max_timeline._text(x, y+2*context.preferences.system.ui_scale, caption,
                           round(10*context.preferences.system.ui_scale), (.72,.72,.72,1))


class MAX_OT_chrome_pointer(bpy.types.Operator):
    bl_idname = 'max.chrome_pointer'
    bl_label = 'Maxxed Chrome Pointer'
    bl_description = 'Route clicks only inside Maxxed viewport labels and the time slider'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self.window_id = context.window.as_pointer()
        if self.window_id in _pointers:
            return {'CANCELLED'}
        _pointers[self.window_id] = self
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _installed or _pointers.get(self.window_id) != self:
            if _pointers.get(self.window_id) == self:
                _pointers.pop(self.window_id, None)
            return {'CANCELLED'}
        if not active(context):
            return {'PASS_THROUGH'}
        if max_toolbar.pointer(context, event):
            return {'RUNNING_MODAL'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        from . import viewport_menus
        area, region = viewport_menus.region_at(context, event.mouse_x, event.mouse_y)
        if area is None:
            return {'PASS_THROUGH'}
        with context.temp_override(area=area, region=region):
            ctx = bpy.context
            if timeline_area(area):
                bpy.ops.max.chrome_scrub('INVOKE_DEFAULT')
                return {'RUNNING_MODAL'}
            if overlay._visible(ctx) and overlay.hit_test(ctx, event.mouse_x-region.x, event.mouse_y-region.y):
                bpy.ops.max.viewport_label('INVOKE_DEFAULT')
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


def attach_window(context):
    """Attach UI hit routing to a newly opened window, once. Used by W2.E windows."""
    if not bpy.app.background and _installed and context.window and context.window.as_pointer() not in _pointers:
        bpy.ops.max.chrome_pointer('INVOKE_DEFAULT')


def _start_pointers():
    if _installed:
        for window in bpy.context.window_manager.windows:
            with bpy.context.temp_override(window=window):
                attach_window(bpy.context)
    return None


def active(context):
    return _installed and context.workspace is not None and context.workspace.name == '3ds Max'


def _draw_header(self, context):
    if timeline_area(context.area):
        max_timeline.draw_controls(self.layout, context)
    else:
        # Header pixels and hit rectangles come from the same reference cells.
        self.layout.separator()


def _draw_status(self, context):
    max_status.draw(self.layout, context)


def _draw_time(self, context):
    max_timeline.draw_controls(self.layout, context)


def _draw_top(self, context):
    if context.region.alignment == 'RIGHT':
        row = self.layout.row(align=True)
        row.label(text='Workspaces:')
        row.menu('MAX_MT_chrome_layouts', text='Default')
        return
    row = self.layout.row(align=True)
    if _menus:
        _menus(row, context)


def _replace(cls, callback, predicate=active):
    original = cls.draw
    def draw(self, context):
        if predicate(context):
            return callback(self, context)
        return original(self, context)
    _originals.append((cls, original, draw))
    cls.draw = draw


def _set(owner, name, value):
    if not any(item[0] == owner and item[1] == name for item in _layout_changes):
        _layout_changes.append((owner, name, getattr(owner, name)))
    setattr(owner, name, value)


def timeline_area(area):
    return area is not None and area.as_pointer() in _timeline_areas


def _area_window(area):
    return next((window for window in bpy.context.window_manager.windows
                 if area in tuple(window.screen.areas)), None)


def _resize_tick():
    # Native area geometry updates on the next redraw. A successful operator
    # return is not proof that the requested size was applied.
    for key, (area, requested, attempts, restoring) in list(_timeline_resize_jobs.items()):
        try:
            target = requested if requested is not None else round(64*bpy.context.preferences.system.ui_scale)
            window = _area_window(area)
            if window is None or abs(area.height-target) <= 1:
                _timeline_resize_jobs.pop(key, None)
                if restoring:
                    _timeline_original_heights.pop(key, None)
                continue
            if attempts >= 30:
                _timeline_resize_jobs.pop(key, None)
                print('[Maxxed] Timeline resize unavailable in the active screen context')
                continue
            _timeline_resize_jobs[key] = area, requested, attempts+1, restoring
            with bpy.context.temp_override(window=window, area=area, region=None):
                if bpy.ops.screen.area_move.poll():
                    bpy.ops.screen.area_move(x=area.x+area.width//2, y=area.y+area.height,
                                             delta=target-area.height)
        except (ReferenceError, RuntimeError):
            _timeline_resize_jobs.pop(key, None)
    return .1 if _timeline_resize_jobs else None


def _size_timeline(area, height=None, restoring=False):
    key = area.as_pointer()
    if not restoring:
        _timeline_original_heights.setdefault(key, (area, area.height))
    _timeline_resize_jobs[key] = area, height, 0, restoring
    if not bpy.app.background and not bpy.app.timers.is_registered(_resize_tick):
        bpy.app.timers.register(_resize_tick, first_interval=.1)


def _use_timeline_host(area):
    window = _area_window(area)
    if window is None:
        return
    # Another save handler may have closed the window that invoked the save.
    with bpy.context.temp_override(window=window, area=area):
        area.type = 'VIEW_3D'
        space = area.spaces.active
        space.overlay.show_overlays = False
        space.show_gizmo = False
        space.show_region_ui = False
        space.show_region_toolbar = False
        space.show_region_tool_header = False
        header = next((r for r in area.regions if r.type == 'HEADER'), None)
        if header and header.alignment != 'BOTTOM':
            with bpy.context.temp_override(region=header):
                bpy.ops.screen.region_flip()
    _size_timeline(area)


def _adopt_timelines(screen):
    for area in screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            _timeline_areas[area.as_pointer()] = (area, area.type, area.ui_type)
            _use_timeline_host(area)


def apply_layout(context, quad=False):
    """Explicitly configure this screen, preserving scene range, FPS, units and data."""
    global _region_overlap
    if _region_overlap is None:
        _region_overlap = context.preferences.system.use_region_overlap
    context.preferences.system.use_region_overlap = False
    _set(context.workspace, 'name', '3ds Max')
    _adopt_timelines(context.screen)
    for area in context.screen.areas:
        if timeline_area(area):
            _size_timeline(area)
            area.tag_redraw()
            continue
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            _set(space.overlay, 'show_text', False)
            _set(space, 'show_region_toolbar', False)
            _set(space, 'show_region_tool_header', False)
            _set(space, 'show_region_ui', True)
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            _quad_changes.setdefault(area.as_pointer(), (area, bool(space.region_quadviews)))
            if region and bool(space.region_quadviews) != quad:
                with context.temp_override(area=area, region=region):
                    bpy.ops.screen.region_quadview()
            if not quad:
                _set(space.region_3d, 'view_perspective', 'PERSP')
        area.tag_redraw()
    # W1.5 owns Scene Explorer and W2.B owns the Command Panel category filter.
    # No empty editor is substituted for either while those providers are absent.
    if _explorer_layout:
        _explorer_layout(context)
    if _command_panel_layout:
        _command_panel_layout(context)


@persistent
def _load(_):
    max_toolbar.cancel_pending()
    _pointers.clear()
    _layout_changes.clear()  # Old screen references must never be restored into a new file.
    _timeline_areas.clear()
    _timeline_original_heights.clear()
    _timeline_resize_jobs.clear()
    _quad_changes.clear()
    max_status.clear()
    if _installed:
        for window in bpy.context.window_manager.windows:
            if window.workspace.name == '3ds Max':
                _adopt_timelines(window.screen)
        max_timeline.unregister()
        max_timeline.register()
        # Windows already exist at load_post. Routing needs only a window, so
        # restore it before another persistent timer can observe the loaded UI.
        _start_pointers()


@persistent
def _before_save(_):
    # Save real Timeline editor types. There is no second saved time-range or
    # layout marker, and a saved file opens normally even without this add-on.
    for area, original_type, original_ui in _timeline_areas.values():
        try:
            window = _area_window(area)
            if window:
                with bpy.context.temp_override(window=window, area=area):
                    area.type = original_type
                    area.ui_type = original_ui
        except (ReferenceError, RuntimeError):
            pass


@persistent
def _after_save(_):
    for area, _, _ in _timeline_areas.values():
        try:
            _use_timeline_host(area)
        except (ReferenceError, RuntimeError):
            pass


class MAX_OT_chrome_layout(bpy.types.Operator):
    bl_idname = 'max.chrome_layout'
    bl_label = 'Maxxed Workspace Layout'
    bl_description = 'Explicitly apply a single Perspective viewport or a four-view layout'
    quad: BoolProperty(default=False)

    def execute(self, context):
        apply_layout(context, self.quad)
        return {'FINISHED'}


class MAX_OT_chrome_theme(bpy.types.Operator):
    bl_idname = 'max.chrome_theme'
    bl_label = 'Maxxed Appearance'
    bl_description = 'Apply the Maxxed appearance or restore settings saved by Apply'
    restore: BoolProperty(default=False)

    def execute(self, context):
        theme.restore(context) if self.restore else theme.apply(context)
        return {'FINISHED'}


class MAX_MT_chrome_application(bpy.types.Menu):
    bl_label = 'Maxxed'

    def draw(self, context):
        self.layout.operator('max.chrome_theme', text='Apply Maxxed Appearance').restore = False
        self.layout.operator('max.chrome_theme', text='Restore Appearance').restore = True
        self.layout.separator()
        self.layout.operator('wm.splash_about', text='About Blender / Maxxed Backend')


class MAX_MT_chrome_layouts(bpy.types.Menu):
    bl_label = 'Maxxed Layouts'

    def draw(self, context):
        self.layout.operator('max.chrome_layout', text='Single Perspective').quad = False
        self.layout.operator('max.chrome_layout', text='Four Viewports').quad = True


def install(*, feedback=None, read_transform=None, write_transform=None, commands=None,
            draw_menus=None, apply_explorer=None, apply_command_panel=None):
    """Install once after shared RNA/classes. Does not apply a layout or theme implicitly."""
    global _installed, _menus, _explorer_layout, _command_panel_layout, _label_callbacks
    if _installed:
        return
    _menus, _explorer_layout, _command_panel_layout = draw_menus, apply_explorer, apply_command_panel
    max_status.configure(feedback=feedback, reader=read_transform, writer=write_transform)
    max_toolbar.configure(commands)
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.max_chrome_sets = CollectionProperty(type=max_toolbar.MAX_PG_chrome_set)
    bpy.types.WindowManager.max_chrome_offset = BoolProperty(name='Absolute / Offset', default=False, options={'SKIP_SAVE'})
    bpy.types.WindowManager.max_chrome_crossing = BoolProperty(name='Window / Crossing', default=False, options={'SKIP_SAVE'},
        description='Crossing intersects projected object bounds. Window encloses them. Applies to rectangular object selection')
    bpy.types.WindowManager.max_chrome_filter = EnumProperty(name='Selection Filter',
        items=[('ALL', 'All', 'Select all supported object types')], options={'SKIP_SAVE'})
    bpy.types.WindowManager.max_chrome_set = EnumProperty(name='Named Selection Sets',
        items=max_toolbar.set_items, update=max_toolbar.recall_set, options={'SKIP_SAVE'})
    for field, subtype, unit in (('position', 'TRANSLATION', 'LENGTH'),
                                 ('rotation', 'EULER', 'ROTATION'), ('scale', 'NONE', 'NONE')):
        setattr(bpy.types.WindowManager, 'max_chrome_' + field,
                FloatVectorProperty(name=field.title(), size=3, subtype=subtype, unit=unit,
                                    precision=3, step=10, get=max_status.get_values,
                                    set=max_status.set_values, options={'SKIP_SAVE'}))
    _replace(bpy.types.VIEW3D_HT_header, _draw_header)
    _replace(bpy.types.STATUSBAR_HT_header, _draw_status)
    _replace(bpy.types.DOPESHEET_HT_header, _draw_time,
             lambda ctx: active(ctx) and ctx.space_data.mode == 'TIMELINE')
    _replace(bpy.types.TOPBAR_HT_upper_bar, _draw_top)
    _installed = True
    _label_callbacks = overlay.label_regions, overlay.draw_labels
    overlay.label_regions, overlay.draw_labels = _label_regions, _draw_labels
    if not bpy.app.background:
        bpy.app.timers.register(_start_pointers, first_interval=.1)
    max_timeline.register()
    max_toolbar.install_drawing()
    overlay.register()
    bpy.app.handlers.load_post.append(_load)
    bpy.app.handlers.save_pre.append(_before_save)
    bpy.app.handlers.save_post.append(_after_save)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        for name, space_type, operator in (('3D View', 'VIEW_3D', 'max.viewport_label'),
                                           ('3D View', 'VIEW_3D', 'max.chrome_scrub'),
                                           ('Object Mode', 'EMPTY', 'max.viewport_label'),
                                           ('Object Mode', 'EMPTY', 'max.chrome_scrub'),
                                           ('Mesh', 'EMPTY', 'max.viewport_label'),
                                           ('Mesh', 'EMPTY', 'max.chrome_scrub'),
                                           ('Dopesheet', 'DOPESHEET_EDITOR', 'max.chrome_scrub')):
            keymap = config.keymaps.new(name=name, space_type=space_type)
            item = keymap.keymap_items.new(operator, 'LEFTMOUSE', 'PRESS', head=True)
            _keys.append((keymap, item))


def uninstall():
    """Restore only callbacks still owned here, and discard all screen/window state."""
    global _installed, _menus, _explorer_layout, _command_panel_layout, _region_overlap, _label_callbacks
    if not _installed:
        return
    _installed = False
    if bpy.app.timers.is_registered(_start_pointers):
        bpy.app.timers.unregister(_start_pointers)
    _pointers.clear()
    max_toolbar.cancel_pending()
    for keymap, item in _keys:
        keymap.keymap_items.remove(item)
    _keys.clear()
    for cls, original, ours in reversed(_originals):
        if cls.draw is ours:
            cls.draw = original
    _originals.clear()
    for area, was_quad in _quad_changes.values():
        try:
            window = next((w for w in bpy.context.window_manager.windows if area in tuple(w.screen.areas)), None)
            if window and area.type == 'VIEW_3D' and bool(area.spaces.active.region_quadviews) != was_quad:
                region = next(r for r in area.regions if r.type == 'WINDOW')
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.screen.region_quadview()
        except (ReferenceError, RuntimeError, StopIteration):
            pass
    _quad_changes.clear()
    for area, height in list(_timeline_original_heights.values()):
        try:
            _size_timeline(area, height, restoring=True)
        except ReferenceError:
            pass
    for area, original_type, original_ui in _timeline_areas.values():
        try:
            area.type = original_type
            area.ui_type = original_ui
        except (ReferenceError, RuntimeError):
            pass
    _timeline_areas.clear()
    for owner, name, value in reversed(_layout_changes):
        try:
            setattr(owner, name, value)
        except (ReferenceError, RuntimeError, AttributeError):
            pass
    _layout_changes.clear()
    if _region_overlap is not None:
        bpy.context.preferences.system.use_region_overlap = _region_overlap
        _region_overlap = None
    if _load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load)
    for handlers, callback in ((bpy.app.handlers.save_pre, _before_save), (bpy.app.handlers.save_post, _after_save)):
        if callback in handlers:
            handlers.remove(callback)
    max_timeline.unregister()
    max_toolbar.remove_drawing()
    overlay.unregister()
    if _label_callbacks:
        if overlay.label_regions is _label_regions:
            overlay.label_regions = _label_callbacks[0]
        if overlay.draw_labels is _draw_labels:
            overlay.draw_labels = _label_callbacks[1]
        _label_callbacks = None
    max_status.clear()
    max_status.configure()
    max_toolbar.configure()
    _menus = _explorer_layout = _command_panel_layout = None
    theme.restore()
    # Retain saved Scene.max_chrome_sets ID data across disable and re-enable.
    del bpy.types.WindowManager.max_chrome_offset
    del bpy.types.WindowManager.max_chrome_crossing
    del bpy.types.WindowManager.max_chrome_filter
    del bpy.types.WindowManager.max_chrome_set
    for field in ('position', 'rotation', 'scale'):
        delattr(bpy.types.WindowManager, 'max_chrome_' + field)
    del bpy.types.Scene.max_chrome_sets
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


register = install
unregister = uninstall
classes = (*max_toolbar.classes, *max_status.classes, *max_timeline.classes,
           MAX_OT_chrome_pointer, MAX_OT_chrome_layout, MAX_OT_chrome_theme, MAX_MT_chrome_application, MAX_MT_chrome_layouts)
