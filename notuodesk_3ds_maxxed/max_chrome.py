"""Explicit, reversible installation of Maxxed workspace chrome for the wave-2 host."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty
from . import max_status, max_timeline, max_toolbar, overlay, theme

_installed = False
_originals = []
_keys = []
_layout_changes = []
_timeline_areas = {}
_quad_changes = {}
_pointers = {}
_menus = None
_explorer_layout = None
_command_panel_layout = None


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
        if not active(context) or event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        from . import viewport_menus
        area, region = viewport_menus.region_at(context, event.mouse_x, event.mouse_y)
        if area is None:
            return {'PASS_THROUGH'}
        with context.temp_override(area=area, region=region):
            ctx = bpy.context
            if timeline_area(area) and event.mouse_y-region.y >= 22*ctx.preferences.system.ui_scale:
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
        max_toolbar.draw(self.layout, context)


def _draw_status(self, context):
    max_status.draw(self.layout, context)


def _draw_time(self, context):
    max_timeline.draw_controls(self.layout, context)


def _draw_top(self, context):
    if context.region.alignment == 'RIGHT':
        return
    row = self.layout.row(align=True)
    row.menu('MAX_MT_chrome_application', text='Maxxed')
    if _menus:
        _menus(row, context)
    row.menu('MAX_MT_chrome_layouts', text='3ds Max')


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


def _use_timeline_host(area):
    area.type = 'VIEW_3D'
    space = area.spaces.active
    space.overlay.show_overlays = False
    space.show_gizmo = False
    space.show_region_ui = False
    space.show_region_toolbar = False
    space.show_region_tool_header = False


def _adopt_timelines(screen):
    for area in screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            _timeline_areas[area.as_pointer()] = (area, area.type, area.ui_type)
            _use_timeline_host(area)


def apply_layout(context, quad=False):
    """Explicitly configure this screen, preserving scene range, FPS, units and data."""
    _set(context.workspace, 'name', '3ds Max')
    _adopt_timelines(context.screen)
    for area in context.screen.areas:
        if timeline_area(area):
            area.tag_redraw()
            continue
        if area.type == 'VIEW_3D':
            space = area.spaces.active
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
    _quad_changes.clear()
    max_status.clear()
    if _installed:
        for window in bpy.context.window_manager.windows:
            if window.workspace.name == '3ds Max':
                _adopt_timelines(window.screen)
        max_timeline.unregister()
        max_timeline.register()
        if not bpy.app.background and not bpy.app.timers.is_registered(_start_pointers):
            bpy.app.timers.register(_start_pointers, first_interval=.1)


@persistent
def _before_save(_):
    # Save real Timeline editor types. There is no second saved time-range or
    # layout marker, and a saved file opens normally even without this add-on.
    for area, original_type, original_ui in _timeline_areas.values():
        try:
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
    global _installed, _menus, _explorer_layout, _command_panel_layout
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
    _replace(bpy.types.VIEW3D_HT_header, _draw_header)
    _replace(bpy.types.STATUSBAR_HT_header, _draw_status)
    _replace(bpy.types.DOPESHEET_HT_header, _draw_time,
             lambda ctx: active(ctx) and ctx.space_data.mode == 'TIMELINE')
    _replace(bpy.types.TOPBAR_HT_upper_bar, _draw_top)
    _installed = True
    if not bpy.app.background:
        bpy.app.timers.register(_start_pointers, first_interval=.1)
    max_timeline.register()
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
    global _installed, _menus, _explorer_layout, _command_panel_layout
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
    if _load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load)
    for handlers, callback in ((bpy.app.handlers.save_pre, _before_save), (bpy.app.handlers.save_post, _after_save)):
        if callback in handlers:
            handlers.remove(callback)
    max_timeline.unregister()
    overlay.unregister()
    max_status.clear()
    max_status.configure()
    max_toolbar.configure()
    _menus = _explorer_layout = _command_panel_layout = None
    theme.restore()
    # Retain saved Scene.max_chrome_sets ID data across disable and re-enable.
    del bpy.types.WindowManager.max_chrome_offset
    del bpy.types.WindowManager.max_chrome_crossing
    del bpy.types.Scene.max_chrome_sets
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


register = install
unregister = uninstall
classes = (*max_toolbar.classes, *max_status.classes, *max_timeline.classes,
           MAX_OT_chrome_pointer, MAX_OT_chrome_layout, MAX_OT_chrome_theme, MAX_MT_chrome_application, MAX_MT_chrome_layouts)
