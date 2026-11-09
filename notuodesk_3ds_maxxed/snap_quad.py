"""Snap quad with a modal lifetime independent of Blender's popup stack."""

import bpy

_instances = []


def close_all():
    for menu in list(_instances):
        menu.close()


class MAX_OT_snap_quad(bpy.types.Operator):
    """Choose a one-shot snap override without ending the current tool"""
    bl_idname = "max.snap_quad"
    bl_label = "Snaps"
    bl_options = {"INTERNAL", "BLOCKING"}

    def invoke(self, context, event):
        from . import snaps
        from .create import region_under_mouse
        self.area, self.region = region_under_mouse(context, event.mouse_x, event.mouse_y)
        if self.region is None:
            return {"CANCELLED"}
        close_all()
        self.closed = False
        self.submenu = False
        self.mouse = (-1, -1)
        self.scale = context.preferences.system.ui_scale
        self.row = 24 * self.scale
        self.width = 240 * self.scale
        self.left = max(0, min(event.mouse_x - self.region.x, self.region.width - 2 * self.width))
        self.top = min(self.region.height - 8, max(13 * self.row + 8, event.mouse_y - self.region.y + self.row))
        self.subleft = self.left + 2 * self.width if self.left + 3 * self.width <= self.region.width else max(0, self.left - self.width)
        self.subtop = min(self.region.height - 8, max(12 * self.row + 8, self.top - self.row))
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.paint, (), "WINDOW", "POST_PIXEL")
        _instances.append(self)
        snaps._quad_open = True
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def entries(self):
        from . import snaps
        s = snaps.settings(bpy.context)
        return [
            (0, 0, "settings", "Grid and Snap Settings...", True),
            (0, 1, "snap_frozen", "Snaps To Frozen Objects", True),
            (0, 2, "axis_constraints", "Snaps Use Axis Constraints", True),
            (0, 3, "label", "snap options", False),
            (1, 0, "label", "NURBS (not available)", False),
            (1, 1, "standard", "Standard >", True),
            (1, 2, "OFF", "None", bpy.context.scene.tool_settings.use_snap),
            (1, 3, "LAST", "Last: " + dict(snaps.TYPES).get(s.last_override, "None"), s.last_override != "NONE"),
            (1, 4, "label", "snap override", False),
            (1, 6, "label", "snap toggles", False),
        ] + [(1, i + 7, k, dict(snaps.TYPES)[k], True)
             for i, k in enumerate(("grid_points", "pivot", "vertex", "midpoint", "edge", "face"))]

    def hit(self, x, y):
        from . import snaps
        if self.submenu and self.subleft <= x < self.subleft + self.width:
            index = int((self.subtop - y) // self.row)
            if 0 <= index < len(snaps.TYPES) and y <= self.subtop:
                k, _ = snaps.TYPES[index]
                return ("override", k) if k != "tangent" else None
        for col, row, key, label, enabled in self.entries():
            if enabled and self.left + col * self.width <= x < self.left + (col + 1) * self.width and self.top - (row + 1) * self.row <= y < self.top - row * self.row:
                return ("action", key)
        return None

    def close(self):
        from . import snaps
        if self.closed:
            return
        self.closed = True
        snaps._quad_open = False
        bpy.types.SpaceView3D.draw_handler_remove(self.handle, "WINDOW")
        if self in _instances:
            _instances.remove(self)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def modal(self, context, event):
        from . import snaps
        if self.closed or not snaps._quad_open:
            self.close()
            return {"FINISHED"}
        x, y = event.mouse_x - self.region.x, event.mouse_y - self.region.y
        self.mouse = (x, y)
        hit = self.hit(x, y)
        if hit == ("action", "standard"):
            self.submenu = True
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self.close()
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if hit is None:
                self.close()
                return {"CANCELLED"}
            action, key = hit
            if key == "standard":
                self.submenu = True
            elif action == "override" or key in {"OFF", "LAST"}:
                self.close()
                bpy.ops.max.snap_override(kind=key)
                return {"FINISHED"}
            elif key == "settings":
                self.close()
                with context.temp_override(area=self.area, region=self.region):
                    bpy.ops.max.snap_settings("INVOKE_DEFAULT")
                return {"FINISHED"}
            else:
                s = snaps.settings(context)
                setattr(s, key, not getattr(s, key))
                self.close()
                return {"FINISHED"}
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self.close()

    def paint(self):
        if self.closed or bpy.context.region.as_pointer() != self.region.as_pointer():
            return
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
        from . import snaps
        theme = bpy.context.preferences.themes[0].user_interface.wcol_menu
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        def rect(x, y, w, h, color):
            shader.bind()
            shader.uniform_float("color", tuple(color[:3]) + (1,))
            batch_for_shader(shader, "TRIS", {"pos": ((x,y),(x+w,y),(x+w,y-h),(x,y),(x+w,y-h),(x,y-h))}).draw(shader)

        def text(x, y, label, enabled=True):
            values = theme.text[:3]
            color = tuple(c / 255 for c in values) if max(values) > 1 else tuple(values)
            blf.size(0, int(12 * self.scale))
            blf.color(0, *(color if enabled else tuple(c * .5 for c in color)), 1)
            blf.position(0, x + 8 * self.scale, y - 17 * self.scale, 0)
            blf.draw(0, label)

        gpu.state.blend_set("ALPHA")
        s = snaps.settings(bpy.context)
        for col, height in ((0, 4), (1, 13)):
            rect(self.left + col*self.width, self.top, self.width, height*self.row, theme.inner)
        hover = self.hit(*self.mouse)
        for col, row, key, label, enabled in self.entries():
            x, y = self.left + col*self.width, self.top - row*self.row
            if hover == ("action", key):
                rect(x, y, self.width, self.row, theme.inner_sel)
            if key in {"snap_frozen", "axis_constraints", "grid_points", "pivot", "vertex", "midpoint", "edge", "face"}:
                size = 12 * self.scale
                bx, by = x + 7 * self.scale, y - 6 * self.scale
                rect(bx, by, size, size, theme.outline)
                rect(bx + self.scale, by - self.scale, size - 2*self.scale, size - 2*self.scale, theme.inner)
                if getattr(s, key):
                    shader.bind()
                    values = theme.text[:3]
                    color = tuple(c / 255 for c in values) if max(values) > 1 else tuple(values)
                    shader.uniform_float("color", color + (1,))
                    points = ((bx+2*self.scale,by-6*self.scale),(bx+5*self.scale,by-9*self.scale),
                              (bx+5*self.scale,by-9*self.scale),(bx+10*self.scale,by-3*self.scale))
                    batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)
                x += 20 * self.scale
            text(x, y, label, enabled)
        if self.submenu:
            rect(self.subleft, self.subtop, self.width, len(snaps.TYPES)*self.row, theme.inner)
            for i, (key, label) in enumerate(snaps.TYPES):
                y = self.subtop - i*self.row
                if hover == ("override", key):
                    rect(self.subleft, y, self.width, self.row, theme.inner_sel)
                text(self.subleft, y, label, key != "tangent")
        gpu.state.blend_set("NONE")
