"""Reversible Maxxed appearance. Palette values are an independent approximation."""
import bpy

_changes = {}


def _remember(owner, name, value):
    """Record the first value, even when Apply is used more than once."""
    if not hasattr(owner, name):
        return
    key = (owner.as_pointer(), owner.bl_rna.identifier, name)
    if key not in _changes:
        previous = getattr(owner, name)
        if not isinstance(previous, (str, bool, int, float)):
            previous = tuple(previous)
        _changes[key] = previous
    try:
        setattr(owner, name, value)
    except (TypeError, ValueError, AttributeError):
        # Optional theme fields differ between supported Blender releases.
        pass


def apply(context=None):
    """Apply only owned colours, navigation and ordinary viewport visibility."""
    context = context or bpy.context
    prefs = context.preferences
    for owner, name, value in (
        (prefs.view, 'show_splash', False),
        (prefs.view, 'show_tooltips_python', False),
        (prefs.view, 'show_statusbar_version', False),
        (prefs.inputs, 'use_emulate_3_button_mouse', True),
        (prefs.inputs, 'view_rotate_method', 'TURNTABLE'),
        (prefs.inputs, 'use_rotate_around_active', True),
        (prefs.inputs, 'use_zoom_to_mouse', True),
    ):
        _remember(owner, name, value)
    if prefs.themes:
        theme = prefs.themes[0]
        view = theme.view_3d
        for name, value in {
            'object_selected': (.08, .72, .88),
            'object_active': (.08, .72, .88),
            'wire_edit': (.24, .24, .24),
            'vertex': (.22, .48, .82),
            'vertex_select': (1., .12, .08),
            'edge_select': (1., .12, .08),
            'face_select': (1., .12, .08, .15),
            'face_dot': (1., .12, .08),
            'vertex_size': 4,
            'grid': (.27, .27, .27),
        }.items():
            _remember(view, name, value)
        for section in ('view_3d', 'properties', 'outliner', 'dopesheet_editor'):
            space = getattr(theme, section, None)
            space = getattr(space, 'space', None)
            if space:
                for name, value in {'back': (.16, .16, .16),
                                    'header': (.20, .20, .20, 1.),
                                    'text': (.85, .85, .85),
                                    'text_hi': (1., 1., 1.)}.items():
                    _remember(space, name, value)
        ui = theme.user_interface
        for name in ('wcol_regular', 'wcol_tool', 'wcol_num', 'wcol_text', 'wcol_menu'):
            widget = getattr(ui, name, None)
            if widget:
                _remember(widget, 'inner', (.25, .25, .25, 1.))
                _remember(widget, 'inner_sel', (.16, .40, .60, 1.))
                _remember(widget, 'text', (.88, .88, .88, 1.))
        # mode_feedback owns the stack state. Its active row needs the yellow
        # list-selection category while ordinary tool buttons stay blue.
        _remember(ui.wcol_list_item, 'inner_sel', (1., .85, .0, 1.))
        _remember(ui.wcol_list_item, 'text_sel', (0., 0., 0., 1.))
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                _remember(space.overlay, 'show_cursor', False)
                _remember(space.overlay, 'show_text', False)
                _remember(space, 'show_region_toolbar', False)
                _remember(space.shading, 'background_type', 'VIEWPORT')
                _remember(space.shading, 'background_color', (.035, .035, .035))
                _remember(space.shading, 'show_object_outline', True)
                area.tag_redraw()


def _live_owners(context):
    """Resolve current preference and viewport structs, never cached RNA owners."""
    prefs = context.preferences
    yield prefs.view
    yield prefs.inputs
    for palette in prefs.themes:
        yield palette.view_3d
        for section in ('view_3d', 'properties', 'outliner', 'dopesheet_editor'):
            yield getattr(palette, section).space
        for name in ('wcol_regular', 'wcol_tool', 'wcol_num', 'wcol_text', 'wcol_menu', 'wcol_list_item'):
            yield getattr(palette.user_interface, name)
    for workspace in bpy.data.workspaces:
        for screen in workspace.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        yield space
                        yield space.overlay
                        yield space.shading


def restore(context=None):
    """Restore surviving settings. Reloaded preferences and closed spaces are new owners."""
    context = context or bpy.context
    owners = {(owner.as_pointer(), owner.bl_rna.identifier): owner for owner in _live_owners(context)}
    for (pointer, kind, name), value in reversed(list(_changes.items())):
        owner = owners.get((pointer, kind))
        if owner is None:
            continue
        try:
            setattr(owner, name, value)
        except (RuntimeError, TypeError, AttributeError):
            pass
    _changes.clear()
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


apply_theme = apply
restore_theme = restore
apply_prefs = apply
restore_prefs = restore
reset_theme = restore
classes = ()


def register():
    """Appearance is explicit. Enabling alone does not change preferences."""


def unregister():
    restore()
