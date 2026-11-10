"""One object hierarchy and selection model for Explorer and scene dialogs."""
from dataclasses import dataclass
import fnmatch

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, StringProperty
from . import freezing, max_layers


@dataclass
class SceneRow:
    obj: object
    depth: int
    matches: bool


def set_expanded(obj, value):
    obj["max_explorer_collapsed"] = not value


def scene_rows(context, search=""):
    objects = list(context.scene.objects)
    names = {obj.name: obj for obj in objects}
    children = {}
    for obj in objects:
        parent = obj.parent if obj.parent and obj.parent.name in names else None
        children.setdefault(parent, []).append(obj)
    pattern = search.strip().casefold()
    matching = {obj for obj in objects if not pattern or
                (fnmatch.fnmatchcase(obj.name.casefold(), pattern) if any(c in pattern for c in "*?[")
                 else pattern in obj.name.casefold())}
    included = set(matching)
    for obj in matching:
        parent = obj.parent
        while parent and parent.name in names and parent not in included:
            included.add(parent)
            parent = parent.parent
    rows, seen = [], set()

    def visit(obj, depth):
        if obj in seen or obj not in included:
            return
        seen.add(obj)
        rows.append(SceneRow(obj, depth, obj in matching))
        if pattern or not obj.get("max_explorer_collapsed", False):
            for child in sorted(children.get(obj, []), key=lambda o: o.name.casefold()):
                visit(child, depth + 1)
    for root in sorted(children.get(None, []), key=lambda o: o.name.casefold()):
        visit(root, 0)
    return rows


def select_objects(context, objects, extend=False):
    objects = list(objects)
    if context.mode != "OBJECT":
        raise ValueError("Finish the current sub-object operation before selecting objects")
    if not extend:
        for obj in context.view_layer.objects:
            obj.select_set(False)
    selected = []
    for obj in objects:
        if (obj.name in context.view_layer.objects and obj.visible_get(view_layer=context.view_layer)
                and not obj.hide_select and not obj.max_frozen):
            obj.select_set(True)
            selected.append(obj)
    context.view_layer.objects.active = selected[-1] if selected else None
    return selected


def set_hidden(context, objects, value):
    objects = list(objects)
    for obj in objects:
        max_layers._writable(obj)
        layer = max_layers.membership(context.scene, obj)
        if not value and layer and layer.get("max_layer_hidden"):
            raise ValueError("Unhide the object's layer first")
    for obj in objects:
        if obj.name in context.view_layer.objects:
            obj.hide_set(value, view_layer=context.view_layer)


def set_frozen(context, objects, value):
    objects = list(objects)
    for obj in objects:
        max_layers._writable(obj)
        layer = max_layers.membership(context.scene, obj)
        if not value and layer and layer.get("max_layer_frozen"):
            raise ValueError("Unfreeze the object's layer first")
    for obj in objects:
        (freezing.freeze if value else freezing.unfreeze)(obj, context.scene)


def reparent(context, objects, target=None):
    objects = list(objects)
    if target and target.name not in context.scene.objects:
        raise ValueError("Target is no longer in this scene")
    for obj in objects:
        max_layers._writable(obj)
        parent = target
        while parent:
            if parent == obj:
                raise ValueError("A hierarchy cannot contain a cycle")
            parent = parent.parent
    matrices = {obj: obj.matrix_world.copy() for obj in objects}
    for obj in objects:
        obj.parent = target
        obj.matrix_world = matrices[obj]
    context.view_layer.update()


class SelectionDraft:
    """A dialog edits a draft. Cancel never writes scene selection."""
    def __init__(self, context):
        self.context = context
        self.objects = set(context.selected_objects)
        self.closed = False

    def toggle(self, obj):
        if self.closed:
            return
        if obj in self.objects:
            self.objects.remove(obj)
        else:
            self.objects.add(obj)

    def accept(self):
        if self.closed:
            return []
        self.closed = True
        alive = set(self.context.scene.objects)
        return select_objects(self.context, [obj for obj in alive if obj in self.objects])

    def cancel(self):
        self.closed = True


class MAX_OT_explorer_action(bpy.types.Operator):
    """Select, hide, freeze, rename or expand an object in Scene Explorer"""
    bl_idname = "max.explorer_action"
    bl_label = "Scene Explorer"
    bl_options = {"REGISTER", "UNDO"}
    action: EnumProperty(items=[(v, v.title(), "") for v in
                               ("SELECT", "HIDE", "FREEZE", "EXPAND", "RENAME", "SEARCH", "CLEAR")])
    object_name: StringProperty()
    name: StringProperty(name="Name")
    extend: BoolProperty(default=False)
    value: BoolProperty(default=True)

    def invoke(self, context, event):
        if self.action in {"RENAME", "SEARCH"}:
            self.name = self.object_name if self.action == "RENAME" else context.window_manager.max_explorer_search
            return context.window_manager.invoke_props_dialog(self, width=320)
        self.extend = self.extend or event.ctrl or event.shift
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "name", text="Search" if self.action == "SEARCH" else "Name")

    def execute(self, context):
        if self.action in {"SEARCH", "CLEAR"}:
            context.window_manager.max_explorer_search = self.name if self.action == "SEARCH" else ""
            return {"FINISHED"}
        obj = context.scene.objects.get(self.object_name)
        if not obj:
            return {"CANCELLED"}
        try:
            if self.action == "SELECT":
                if self.extend and obj.select_get():
                    obj.select_set(False)
                else:
                    select_objects(context, [obj], self.extend)
            elif self.action == "HIDE":
                set_hidden(context, [obj], self.value)
            elif self.action == "FREEZE":
                set_frozen(context, [obj], self.value)
            elif self.action == "EXPAND":
                set_expanded(obj, self.value)
            elif self.action == "RENAME":
                max_layers._writable(obj)
                if self.name.strip():
                    obj.name = self.name.strip()
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        for area in context.screen.areas if context.screen else []:
            area.tag_redraw()
        return {"FINISHED"}


class MAX_OT_scene_selection_dialog(bpy.types.Operator):
    """Select or hide objects by name using the shared scene hierarchy"""
    bl_idname = "max.scene_selection_dialog"
    bl_label = "Select From Scene"
    bl_options = {"REGISTER", "UNDO"}
    search: StringProperty(name="Search")
    hide: BoolProperty(default=False, options={"HIDDEN"})

    def invoke(self, context, event):
        self._draft = SelectionDraft(context)
        self._chosen = self._draft.objects
        self._token = id(self)
        _drafts[self._token] = self
        return context.window_manager.invoke_props_dialog(self, width=500,
                                                         title="Hide by Name" if self.hide else self.bl_label)

    def draw(self, context):
        self.layout.prop(self, "search")
        for entry in scene_rows(context, self.search):
            row = self.layout.row(align=True)
            row.label(text="    " * entry.depth)
            op = row.operator("max.scene_selection_toggle", text=entry.obj.name,
                              icon="CHECKBOX_HLT" if entry.obj in self._chosen else "CHECKBOX_DEHLT",
                              emboss=False)
            op.token, op.object_name = str(self._token), entry.obj.name

    def execute(self, context):
        chosen = getattr(self, "_chosen", set())
        objects = [obj for obj in context.scene.objects if obj in chosen]
        try:
            if self.hide:
                set_hidden(context, objects, True)
            else:
                select_objects(context, objects)
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        finally:
            self.cancel(context)
        return {"FINISHED"}

    def cancel(self, context):
        if hasattr(self, "_draft"):
            self._draft.cancel()
        _drafts.pop(getattr(self, "_token", None), None)


class MAX_OT_scene_selection_toggle(bpy.types.Operator):
    """Include or remove a scene object from the pending selection"""
    bl_idname = "max.scene_selection_toggle"
    bl_label = "Select Object"
    token: StringProperty()
    object_name: StringProperty()

    def execute(self, context):
        draft = _drafts.get(int(self.token or 0))
        if not draft:
            return {"CANCELLED"}
        obj = context.scene.objects.get(self.object_name)
        if not obj:
            return {"CANCELLED"}
        draft._draft.toggle(obj)
        return {"FINISHED"}


def draw_explorer(layout, context):
    row = layout.row(align=True)
    row.prop(context.window_manager, "max_explorer_search", text="", icon='VIEWZOOM')
    row.operator("max.explorer_action", text="", icon='X').action = "CLEAR"
    row.operator('max.layer_dialog', text='', icon='OUTLINER_COLLECTION')
    header = layout.row(align=True)
    header.label(text='Name')
    header.label(text='Hidden')
    header.label(text='Frozen')
    for entry in scene_rows(context, context.window_manager.max_explorer_search):
        obj = entry.obj
        row = layout.row(align=True)
        row.label(text="    " * entry.depth)
        op = row.operator("max.explorer_action", text="", icon="TRIA_RIGHT" if obj.get("max_explorer_collapsed") else "TRIA_DOWN", emboss=False)
        op.action, op.object_name, op.value = "EXPAND", obj.name, bool(obj.get("max_explorer_collapsed"))
        object_icon = {'MESH': 'OUTLINER_OB_MESH', 'CURVE': 'OUTLINER_OB_CURVE',
                       'CAMERA': 'OUTLINER_OB_CAMERA', 'LIGHT': 'OUTLINER_OB_LIGHT'}.get(obj.type, 'OBJECT_DATA')
        op = row.operator("max.explorer_action", text=obj.name, icon=object_icon,
                          emboss=False, depress=obj.select_get())
        op.action, op.object_name = "SELECT", obj.name
        for action, glyph, state in (("HIDE", 'HIDE_ON' if obj.hide_get() else 'HIDE_OFF', obj.hide_get()),
                                      ("FREEZE", 'LOCKED' if obj.max_frozen else 'UNLOCKED', obj.max_frozen)):
            op = row.operator("max.explorer_action", text='', icon=glyph, emboss=False, depress=state)
            op.action, op.object_name, op.value = action, obj.name, not state
        op = row.operator("max.explorer_action", text="", icon='GREASEPENCIL')
        op.action, op.object_name = "RENAME", obj.name
    max_layers.draw_layers(layout.box(), context)


def draw_docked(host, context, width, height, scale, rect, text, line, op):
    """Compact name table. The overview proves columns, not toolbar glyph detail."""
    import blf
    import gpu
    from . import max_icons
    s = scale
    font = 12*s

    def caption(x, y, value, available, color=(.87, .87, .87, 1)):
        blf.size(0, font)
        while value and blf.dimensions(0, value)[0] > available:
            value = value[:-1]
        text(x, y, value, round(font), color)

    def icon(x, y, art, callback, active=False, size=22):
        if active:
            rect(x, y, size*s, size*s, (.28, .39, .49, 1))
        gpu.state.blend_set('ALPHA')
        max_icons.draw(art, x+size*s/2, y+size*s/2, 16*s)
        if callback:
            host.hits.append(((x, y, x+size*s, y+size*s), callback))

    y = height-65*s
    search_width = max(24*s, width-62*s)
    rect(7*s, y, search_width, 21*s, (.24, .24, .24, 1))
    caption(12*s, y+5*s, context.window_manager.max_explorer_search,
            search_width-10*s)
    host.hits.append(((7*s, y, 7*s+search_width, y+21*s),
                      op('max.explorer_action', action='SEARCH')))
    icon(width-51*s, y, 'remove_modifier', op('max.explorer_action', action='CLEAR'))
    icon(width-28*s, y, 'select_by_name', op('max.scene_selection_dialog'))
    y -= 24*s
    hidden_x, frozen_x = width-98*s, width-51*s
    rect(6*s, y, width-12*s, 21*s, (.22, .22, .22, 1))
    caption(12*s, y+5*s, 'Name', max(0, hidden_x-16*s))
    caption(hidden_x, y+5*s, 'Hidden', 44*s)
    caption(frozen_x, y+5*s, 'Frozen', 44*s)
    rows = scene_rows(context, context.window_manager.max_explorer_search)
    capacity = max(1, int((y-44*s)/(21*s)))
    host.scroll = min(host.scroll, max(0, len(rows)-capacity))
    for index, entry in enumerate(rows[host.scroll:host.scroll+capacity]):
        y -= 21*s
        obj = entry.obj
        rect(6*s, y, width-12*s, 21*s,
             (.27, .39, .49, 1) if obj.select_get() else
             ((.31, .31, .31, 1) if index % 2 else (.29, .29, .29, 1)))
        x = min(9*s+entry.depth*12*s, max(9*s, hidden_x-58*s))
        if obj.children:
            collapsed = bool(obj.get('max_explorer_collapsed'))
            caption(x, y+5*s, '+' if collapsed else '-', 12*s)
            host.hits.append(((x, y, x+12*s, y+21*s),
                             op('max.explorer_action', action='EXPAND',
                                object_name=obj.name, value=collapsed)))
        x += 12*s
        art = {'MESH': 'box', 'CURVE': 'line', 'LIGHT': 'lights',
               'CAMERA': 'cameras', 'EMPTY': 'select_object'}.get(obj.type, 'select_object')
        gpu.state.blend_set('ALPHA')
        max_icons.draw(art, x+8*s, y+10*s, 14*s)
        caption(x+19*s, y+5*s, obj.name, max(0, hidden_x-x-22*s))
        host.hits.append(((x, y, hidden_x, y+21*s),
                          op('max.explorer_action', action='SELECT', object_name=obj.name)))
        icon(hidden_x, y, 'bulb_off' if obj.hide_get() else 'bulb_on',
             op('max.explorer_action', action='HIDE', object_name=obj.name,
                value=not obj.hide_get()), size=20)
        icon(frozen_x, y, 'freeze',
             op('max.explorer_action', action='FREEZE', object_name=obj.name,
                value=not obj.max_frozen), obj.max_frozen, size=20)
    line((hidden_x-2*s, 40*s), (hidden_x-2*s, height-68*s), (.21, .21, .21, 1))
    line((frozen_x-2*s, 40*s), (frozen_x-2*s, height-68*s), (.21, .21, .21, 1))
    tools = [('select_by_name', op('max.scene_selection_dialog')),
             ('hide_sel', op('max.scene_selection_dialog', hide=True)),
             ('layer_explorer', op('max.layer_dialog')),
             ('move', op('max.layer_action', action='ASSIGN'))]
    if context.active_object:
        tools.append(('edit_mode', op('max.explorer_action', action='RENAME',
                                   object_name=context.active_object.name)))
    for index, (art, callback) in enumerate(tools):
        icon((8+24*index)*s, 10*s, art, callback)


classes = (MAX_OT_explorer_action, MAX_OT_scene_selection_toggle, MAX_OT_scene_selection_dialog)
_drafts = {}
_installed = False


@persistent
def _clear_drafts(*_):
    for draft in list(_drafts.values()):
        draft.cancel(bpy.context)
    _drafts.clear()


def install():
    global _installed
    if not _installed:
        bpy.types.WindowManager.max_explorer_search = StringProperty(default="", options={"SKIP_SAVE"})
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.app.handlers.load_pre.append(_clear_drafts)
        _installed = True


def uninstall():
    global _installed
    _clear_drafts()
    if _installed:
        bpy.app.handlers.load_pre.remove(_clear_drafts)
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        del bpy.types.WindowManager.max_explorer_search
        _installed = False
