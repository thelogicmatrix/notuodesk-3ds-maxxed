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
        self.row = 16 * self.scale
        self.width = 165 * self.scale
        self.left = max(1, min(event.mouse_x - self.region.x, self.region.width - 264*self.scale-1))
        self.top = min(self.region.height-1, max(194*self.scale+1, event.mouse_y-self.region.y+19*self.scale))
        self.subleft = self.left+245*self.scale if self.left+405*self.scale < self.region.width else max(1,self.left-160*self.scale)
        self.subtop = self.top-16*self.scale
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.paint, (), "WINDOW", "POST_PIXEL")
        _instances.append(self)
        snaps._quad_open = True
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def entries(self):
        from . import snaps
        s = snaps.settings(bpy.context)
        # x, y, width, height, key, caption, enabled, header, submenu
        return [
            (0,19,165,16,'settings','Grid and Snap Settings...',True,False,False),
            (0,35,165,16,'snap_frozen','Snaps To Frozen Objects',True,False,False),
            (0,51,165,17,'axis_constraints','Snaps Use Axis Constraints',True,False,False),
            (0,68,165,15,'options_header','snap options',False,True,False),
            (165,0,79,18,'nurbs','NURBS',False,False,True),
            (165,18,79,17,'standard','Standard',True,False,True),
            (165,35,79,16,'OFF','None',bpy.context.scene.tool_settings.use_snap,False,False),
            (165,51,79,17,'LAST',dict(snaps.TYPES).get(s.last_override,'Last'),s.last_override!='NONE',False,False),
            (165,68,79,15,'override_header','snap override',False,True,False),
            (165,83,99,15,'toggles_header','snap toggles',False,True,False),
        ] + [(165,98+i*16,99,16,k,dict(snaps.TYPES)[k],True,False,False)
             for i,k in enumerate(('grid_points','pivot','vertex','midpoint','edge','face'))]

    def action_center(self, key):
        x,y,w,h,*_ = next(row for row in self.entries() if row[4] == key)
        return self.left+(x+w/2)*self.scale, self.top-(y+h/2)*self.scale

    def hit(self, x, y):
        from . import snaps
        if self.submenu and self.subleft <= x < self.subleft+160*self.scale:
            index = int((self.subtop-y)//self.row)
            if 0 <= index < len(snaps.TYPES) and y <= self.subtop:
                k,_ = snaps.TYPES[index]
                return ('override',k) if k != 'tangent' else None
        lx, ly = (x-self.left)/self.scale, (self.top-y)/self.scale
        for xx, yy, w, h, key, label, enabled, header, arrow in self.entries():
            if enabled and xx <= lx < xx+w and yy <= ly < yy+h:
                return ('action',key)
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
        import gpu
        from . import snaps
        from .max_ui_draw import Canvas, EDGE
        gpu.state.blend_set('ALPHA')
        c = Canvas(self.left,self.top,self.scale,'arial')
        s = snaps.settings(bpy.context)
        hover = self.hit(*self.mouse)
        toggles = {'snap_frozen','axis_constraints','grid_points','pivot','vertex','midpoint','edge','face'}
        for x,y,w,h,key,label,enabled,header,arrow in self.entries():
            c.menu_row(x,y,w,label,enabled=enabled,header=header,arrow=arrow,
                       checked=key in toggles and getattr(s,key),hover=hover==('action',key),height=h,
                       align='LEFT' if key=='options_header' else 'CENTER' if x==0 else None)
        for x,y,w,h in ((0,19,165,64),(165,0,79,83),(165,83,99,111)):
            c.border(x,y,w,h,EDGE)
        c.rect(165,35,79,1,EDGE)
        if self.submenu:
            c = Canvas(self.subleft,self.subtop,self.scale,'arial')
            for i,(key,label) in enumerate(snaps.TYPES):
                c.menu_row(0,i*16,160,label,enabled=key!='tangent',hover=hover==('override',key))
            c.border(0,0,160,len(snaps.TYPES)*16)
        gpu.state.blend_set('NONE')
