"""Explicit Max layers over collections. Ordinary collections remain ordinary."""
import json
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

MARKER = "max_layer_id"
STATE = "max_layer_restore"


def _collections(scene):
    found = set()
    pending = list(scene.collection.children)
    while pending:
        collection = pending.pop()
        if collection in found:
            continue
        found.add(collection)
        pending.extend(collection.children)
    return found


def catalogue(scene):
    return sorted((c for c in _collections(scene) if c.get(MARKER)),
                  key=lambda c: (label(c).casefold(), c[MARKER]))


def label(layer):
    return layer.get("max_layer_name", layer.name) if layer else "0"


def membership(scene, obj):
    """For externally multi-linked objects, the first sorted managed layer wins."""
    return next((layer for layer in catalogue(scene) if obj.name in layer.objects), None)


def _writable(item):
    if item.library and not item.override_library:
        raise ValueError("Linked data is read-only. Make a local copy first")


def _check_layer(scene, layer):
    if layer not in catalogue(scene):
        raise ValueError("This is not a Max layer in this scene")
    _writable(layer)
    if any(s != scene and layer in _collections(s) for s in bpy.data.scenes):
        raise ValueError("This layer is shared with another scene")


def create(scene, name):
    name = name.strip()
    if not name or name == "0" or any(label(c) == name for c in catalogue(scene)):
        raise ValueError("Choose an unused layer name other than 0")
    layer = bpy.data.collections.new("Layer." + name)
    layer[MARKER] = uuid.uuid4().hex
    layer["max_layer_name"] = name
    layer["max_layer_hidden"] = False
    layer["max_layer_frozen"] = False
    scene.collection.children.link(layer)
    return layer


def _hidden_states(scene, obj):
    return {v.name: obj.hide_get(view_layer=v) for v in scene.view_layers
            if obj.name in v.objects}


def _restore(scene, obj):
    from . import freezing
    state = json.loads(obj.get(STATE, "{}"))
    for name, hidden in state.get("hidden", {}).items():
        view = scene.view_layers.get(name)
        if view and obj.name in view.objects:
            obj.hide_set(hidden, view_layer=view)
    if "frozen" in state:
        (freezing.freeze if state["frozen"] else freezing.unfreeze)(obj, scene)
    if STATE in obj:
        del obj[STATE]


def _apply(scene, obj, layer):
    from . import freezing
    state = json.loads(obj.get(STATE, "{}"))
    if state and state.get("layer") != layer[MARKER]:
        _restore(scene, obj)
        state = {}
    state["layer"] = layer[MARKER]
    hidden = layer.get("max_layer_hidden", False)
    frozen = layer.get("max_layer_frozen", False)
    if hidden:
        state.setdefault("hidden", _hidden_states(scene, obj))
        for view in scene.view_layers:
            if obj.name in view.objects:
                obj.hide_set(True, view_layer=view)
    elif "hidden" in state:
        for name, value in state.pop("hidden").items():
            view = scene.view_layers.get(name)
            if view and obj.name in view.objects:
                obj.hide_set(value, view_layer=view)
    if frozen:
        state.setdefault("frozen", bool(obj.max_frozen))
        freezing.freeze(obj, scene)
    elif "frozen" in state:
        (freezing.freeze if state.pop("frozen") else freezing.unfreeze)(obj, scene)
    if len(state) > 1:
        obj[STATE] = json.dumps(state)
    elif STATE in obj:
        del obj[STATE]


def assign(scene, objects, layer=None):
    objects = list(objects)
    if layer:
        _check_layer(scene, layer)
    for obj in objects:
        _writable(obj)
        if obj.name not in scene.objects:
            raise ValueError("Object is no longer in this scene")
        for old in catalogue(scene):
            if obj.name in old.objects:
                _check_layer(scene, old)
    for obj in objects:
        _restore(scene, obj)
        # Link first so moving the only membership cannot orphan the object.
        if layer and obj.name not in layer.objects:
            layer.objects.link(obj)
        if not layer and obj.name not in scene.collection.objects:
            scene.collection.objects.link(obj)
        for old in catalogue(scene):
            if old != layer and obj.name in old.objects:
                old.objects.unlink(obj)
        bpy.context.view_layer.update()
        if layer:
            _apply(scene, obj, layer)


def _set_state(scene, layer, field, value):
    _check_layer(scene, layer)
    for obj in layer.objects:
        _writable(obj)
        if sum(obj.name in candidate.objects for candidate in catalogue(scene)) > 1:
            raise ValueError("Assign this object to one Max layer before changing layer state")
    layer[field] = bool(value)
    for obj in layer.objects:
        _apply(scene, obj, layer)


def set_hidden(scene, layer, hidden):
    _set_state(scene, layer, "max_layer_hidden", hidden)


def set_frozen(scene, layer, frozen):
    _set_state(scene, layer, "max_layer_frozen", frozen)


def remove(scene, layer):
    _check_layer(scene, layer)
    if layer.children:
        raise ValueError("Move nested collections out before deleting this layer")
    assign(scene, list(layer.objects), None)
    bpy.data.collections.remove(layer)


class MAX_OT_layer_action(bpy.types.Operator):
    """Manage Max layers without changing object groups or hierarchy"""
    bl_idname = "max.layer_action"
    bl_label = "Layer"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(items=[(v, n, "") for v, n in (
        ("CREATE", "New Layer"), ("ASSIGN", "Move Selection to Layer"),
        ("REMOVE", "Delete Layer"), ("HIDE", "Hide Layer"), ("FREEZE", "Freeze Layer"), ("RENAME", "Rename Layer"))])
    layer_id: StringProperty()
    name: StringProperty(name="Name", default="Layer001")
    value: BoolProperty(default=True)

    def invoke(self, context, event):
        if self.action in {"CREATE", "RENAME"}:
            if self.action == "RENAME":
                layer = next((c for c in catalogue(context.scene) if c[MARKER] == self.layer_id), None)
                self.name = label(layer)
            return context.window_manager.invoke_props_dialog(self, width=280)
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "name")

    def execute(self, context):
        layer = next((c for c in catalogue(context.scene) if c[MARKER] == self.layer_id), None)
        try:
            if self.layer_id and layer is None:
                raise ValueError("The layer is no longer in this scene")
            if self.action == "CREATE":
                create(context.scene, self.name)
            elif self.action == "ASSIGN":
                assign(context.scene, context.selected_objects, layer)
            elif self.action == "REMOVE":
                remove(context.scene, layer)
            elif self.action == "HIDE":
                set_hidden(context.scene, layer, self.value)
            elif self.action == "FREEZE":
                set_frozen(context.scene, layer, self.value)
            elif self.action == "RENAME":
                _check_layer(context.scene, layer)
                name = self.name.strip()
                if not name or name == "0" or any(label(c) == name for c in catalogue(context.scene) if c != layer):
                    raise ValueError("Choose an unused layer name other than 0")
                layer["max_layer_name"] = name
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


def draw_layers(layout, context):
    layout.operator("max.layer_action", text="New Layer", icon='ADD').action = "CREATE"
    for layer in catalogue(context.scene):
        row = layout.row(align=True)
        row.label(text=label(layer))
        for action, glyph, field in (("HIDE", 'HIDE_ON' if layer.get('max_layer_hidden') else 'HIDE_OFF', "max_layer_hidden"),
                                     ("FREEZE", 'LOCKED' if layer.get('max_layer_frozen') else 'UNLOCKED', "max_layer_frozen")):
            op = row.operator("max.layer_action", text='', icon=glyph, emboss=False, depress=bool(layer.get(field)))
            op.action, op.layer_id, op.value = action, layer[MARKER], not layer.get(field, False)
        op = row.operator("max.layer_action", text="", icon='FORWARD')
        op.action, op.layer_id = "ASSIGN", layer[MARKER]
        op = row.operator("max.layer_action", text="", icon='TRASH')
        op.action, op.layer_id = "REMOVE", layer[MARKER]
        op = row.operator("max.layer_action", text="", icon='GREASEPENCIL')
        op.action, op.layer_id = "RENAME", layer[MARKER]
    layout.operator("max.layer_action", text="Move Selection to Layer 0").action = "ASSIGN"


class MAX_OT_layer_dialog(bpy.types.Operator):
    """Manage all Max layers and selected object membership"""
    bl_idname = "max.layer_dialog"
    bl_label = "Layer Explorer"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=720)

    def draw(self, context):
        draw_layers(self.layout, context)

    def execute(self, context):
        return {"FINISHED"}


classes = (MAX_OT_layer_action, MAX_OT_layer_dialog)
_installed = False


def install():
    global _installed
    if not _installed:
        for cls in classes:
            bpy.utils.register_class(cls)
        _installed = True


def uninstall():
    global _installed
    if _installed:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        _installed = False
