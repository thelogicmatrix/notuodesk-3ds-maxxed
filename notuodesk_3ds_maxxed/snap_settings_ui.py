"""Modeless Grid and Snap Settings drawing in a floating viewport region."""
import time
import bpy
from .max_ui_draw import Canvas, BACKGROUND, TEXT, DISABLED, HEADER, EDGE

_dialogs = {}


def close_all():
    for dialog in list(_dialogs.values()):
        dialog.close()


class Dialog:
    width, height = 404, 392

    def __init__(self, context):
        self.window, self.area, self.region = context.window, context.area, context.region
        self.key = self.window.as_pointer()
        self.scale = context.preferences.system.ui_scale
        self.x, self.top = 16, self.region.height-16
        self.mouse = (-100, -100)
        self.edit = None
        self.buffer = ''
        self.selected = False
        self.drag = None
        self.closed = False
        self.hover_since = time.monotonic()
        self.controls = []
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), 'WINDOW', 'POST_PIXEL')
        _dialogs[self.key] = self

    def layout(self):
        from . import snaps
        s = snaps.settings(bpy.context)
        self.controls = []
        # kind, property/action, value, x, y, width, height, label, enabled, tooltip
        def add(kind, key, x,y,w,h,label='',enabled=True,value=None,tip=''):
            self.controls.append((kind,key,value,x,y,w,h,label,enabled,tip))
        add('close','close',370,5,28,24,'')
        x = 4
        for key,label,w in [('SNAPS','Snaps',49),('OPTIONS','Options',58),('HOME','Home Grid',73),('USER','User Grids',73)]:
            add('tab','tab',x,40,w,25,label,value=key)
            x += w
        if s.tab == 'SNAPS':
            add('combo','standard',16,78,369,23,'Standard')
            for col, items in enumerate((snaps.TYPES[:6],snaps.TYPES[6:])):
                for row,(key,label) in enumerate(items):
                    add('snap',key,24+col*188,116+row*30,180,23,label,key!='tangent',
                        tip=s.bl_rna.properties[key].description)
            add('label','override',20,318,235,22,'Override OFF' if s.override=='NONE' else dict(snaps.TYPES).get(s.override,'None'))
            add('button','clear',288,315,92,25,'Clear All')
        elif s.tab == 'OPTIONS':
            add('group','marker_group',15,72,373,45,'Marker')
            add('bool','marker',24,92,93,20,'Display')
            add('number','marker_size',168,92,72,19,'Size:',tip='Size of the snap hit point in screen pixels')
            add('label','pixels',245,92,60,20,'(pixels)')
            add('group','general_group',15,126,373,135,'General')
            for i,(key,label,unit) in enumerate([('preview_radius','Snap Preview Radius:','(pixels)'),
                                               ('snap_radius','Snap Radius:','(pixels)'),
                                               ('angle','Angle:','(deg)'),('percent','Percent:','(%)')]):
                add('number',key,168,142+i*23,72,19,label)
                add('label',key+'_unit',245,142+i*23,65,20,unit)
            add('bool','snap_frozen',24,236,340,20,'Snap to frozen objects')
            add('group','translation_group',15,270,373,47,'Translation')
            add('bool','axis_constraints',24,287,176,20,'Enable Axis Constraints')
            add('bool','rubber_band',204,287,175,20,'Display rubber band')
            add('group','shape_group',15,330,373,49,'Shape Creation')
            add('bool','shape_angle',24,346,247,20,'Enable Shape Angle Constraints',False,
                tip='Shape angle constraints need Line tool integration')
            add('label','shape_value',278,346,70,20,'15.0',False)
            add('label','degrees',351,346,30,20,'(deg)',False)
        elif s.tab == 'HOME':
            add('group','dimensions_group',44,75,316,88,'Grid Dimensions')
            for i,(key,label) in enumerate([('grid_spacing','Grid Spacing:'),
                                          ('major_lines','Major Lines every Nth Grid Line:'),
                                          ('grid_extent','Perspective View Grid Extent:')]):
                add('number',key,259,88+i*24,83,19,label,key!='grid_extent',
                    tip='Blender controls visible grid extent' if key=='grid_extent' else '')
            for i,(key,label) in enumerate([('inhibit_subdivision','Inhibit Grid Subdivision Below Grid Spacing'),
                                          ('inhibit_resize','Inhibit Perspective View Grid Resize')]):
                add('bool',key,46,175+i*24,346,20,label,False,
                    tip='Blender owns adaptive grid subdivision and resize')
            add('group','update_group',44,230,316,50,'Dynamic Update')
            for key,label,x in [('ACTIVE','Active Viewport',60),('ALL','All Viewports',211)]:
                add('radio','grid_update',x,250,140,22,label,False,value=key,
                    tip='Blender updates all viewports immediately')
        else:
            add('group','automation_group',50,77,300,54,'Grid object automation')
            add('bool','activate_grids',63,96,280,22,'Activate grids when created',False,
                tip='User grid helper objects are not available')
            add('group','autogrid_group',50,141,300,77,'AutoGrid')
            add('label','alignment',62,161,200,20,'Alignment:')
            for key,label,x in [('WORLD','World space',63),('OBJECT','Object space',201)]:
                add('radio','autogrid_space',x,187,130,22,label,False,value=key,
                    tip='AutoGrid is not available')

    def hit(self, x, y):
        self.layout()
        x, y = (x-self.x)/self.scale, (self.top-y)/self.scale
        return next((c for c in reversed(self.controls) if c[0] not in {'label','group'}
                     and c[3] <= x < c[3]+c[5] and c[4] <= y < c[4]+c[6]),None)

    def close(self):
        if not self.closed:
            self.closed = True
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            _dialogs.pop(self.key,None)
            from . import snaps
            snaps._settings_windows.discard(self.key)
            try:
                self.area.tag_redraw()
            except ReferenceError:
                pass

    def change_number(self, context, key, value):
        from . import snaps
        s = snaps.settings(context)
        p = s.bl_rna.properties[key]
        try:
            number = float(value)
            if not __import__('math').isfinite(number):
                return
            value = max(p.hard_min,min(p.hard_max,number))
            setattr(s,key,int(round(value)) if p.type=='INT' else value)
            snaps._redraw(context)
        except ValueError:
            pass

    def commit(self, context):
        if self.edit:
            self.change_number(context,self.edit,self.buffer)
            self.edit = None

    def event(self, context, event):
        from . import snaps
        if context.window.as_pointer()!=self.key:
            return {'PASS_THROUGH'}
        x,y = event.mouse_x-self.region.x,event.mouse_y-self.region.y
        if (x,y)!=self.mouse:
            self.hover_since = time.monotonic()
            self.mouse = (x,y)
        hit = self.hit(x,y)
        s = snaps.settings(context)
        if self.drag and self.drag[0]=='title':
            _,mx,my,left,top=self.drag
            if event.type=='MOUSEMOVE':
                self.x=max(0,min(self.region.width-self.width*self.scale,left+x-mx))
                self.top=max(self.height*self.scale,min(self.region.height,top+y-my))
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.drag=None
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if self.drag:
            key,start_y,value = self.drag
            if event.type=='MOUSEMOVE':
                p=s.bl_rna.properties[key]
                step=1 if p.type=='INT' else .1
                self.change_number(context,key,value+(y-start_y)*step)
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.drag = None
            return {'RUNNING_MODAL'}
        if self.edit and event.value=='PRESS':
            if event.type in {'RET','NUMPAD_ENTER','TAB'}:
                self.commit(context)
            elif event.type=='ESC':
                self.edit=None
            elif event.type=='A' and event.ctrl:
                self.selected=True
            elif event.type in {'BACK_SPACE','DEL'}:
                self.buffer='' if self.selected else self.buffer[:-1]
                self.selected=False
            elif event.ascii and event.ascii in '0123456789.-+eE':
                self.buffer=('' if self.selected else self.buffer)+event.ascii
                self.selected=False
            if event.type!='LEFTMOUSE':
                return {'RUNNING_MODAL'}
        in_card=(self.x<=x<self.x+self.width*self.scale and self.top-self.height*self.scale<=y<self.top)
        if not in_card and not self.edit:
            return {'PASS_THROUGH'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            self.commit(context)
            if hit is None and self.top-36*self.scale<=y<=self.top:
                self.drag=('title',x,y,self.x,self.top)
            if hit and hit[8]:
                kind,key,value,xx,yy,w,h,label,enabled,tip=hit
                if kind=='close':
                    bpy.ops.max.snap_settings_close()
                    return {'FINISHED'}
                if kind=='tab':
                    s.tab=value
                elif kind=='bool' or kind=='snap':
                    setattr(s,key,not getattr(s,key))
                elif kind=='radio':
                    setattr(s,key,value)
                elif kind=='button':
                    bpy.ops.max.snap_clear()
                elif kind=='number':
                    if (x-self.x)/self.scale>xx+w-12:
                        step=1 if s.bl_rna.properties[key].type=='INT' else .1
                        sign=1 if (self.top-y)/self.scale<yy+h/2 else -1
                        self.change_number(context,key,getattr(s,key)+step*sign)
                        self.drag=(key,y,getattr(s,key))
                    else:
                        self.edit=key
                        self.buffer=f'{getattr(s,key):g}'
                        self.selected=True
                snaps._redraw(context)
        if event.type=='ESC' and event.value=='PRESS':
            bpy.ops.max.snap_settings_close()
            return {'FINISHED'}
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def draw(self):
        if self.closed or bpy.context.window.as_pointer()!=self.key or bpy.context.region!=self.region:
            return
        import gpu
        from . import snaps,max_icons
        self.layout()
        s=snaps.settings(bpy.context)
        self.scale=bpy.context.preferences.system.ui_scale
        c=Canvas(self.x,self.top,self.scale)
        gpu.state.blend_set('ALPHA')
        c.rect(0,0,self.width,self.height)
        c.border(0,0,self.width,self.height)
        c.rect(0,0,self.width,36,HEADER)
        c.text(12,10,'Grid and Snap Settings',size=14)
        c.rect(0,65,self.width,1,EDGE)
        hover=self.hit(*self.mouse)
        for control in self.controls:
            kind,key,value,x,y,w,h,label,enabled,tip=control
            color=TEXT if enabled else DISABLED
            if kind=='group':
                c.border(x,y,w,h,(.21,.21,.21,1))
                import blf
                blf.size(c.font,12*self.scale)
                tw=blf.dimensions(c.font,label)[0]/self.scale
                c.rect(x+6,y-6,tw+8,14)
                c.text(x+8,y-8,label)
            elif kind=='tab':
                c.rect(x,y,w,h,BACKGROUND if s.tab==value else HEADER)
                c.border(x,y,w,h)
                c.text(x,y+3,label,size=12,align='CENTER',width=w)
            elif kind=='close':
                c.line((x+8,y+7),(x+20,y+19))
                c.line((x+20,y+7),(x+8,y+19))
            elif kind in {'snap','bool','radio'}:
                if kind=='radio':
                    import math
                    c.polygon([(x+7+7*math.cos(i*math.tau/24),y+10+7*math.sin(i*math.tau/24)) for i in range(24)],DISABLED)
                    if getattr(s,key)==value:
                        c.polygon([(x+7+4*math.cos(i*math.tau/24),y+10+4*math.sin(i*math.tau/24)) for i in range(24)],TEXT)
                else:
                    c.rect(x,y+3,14,14,(.36,.36,.36,1))
                    c.border(x,y+3,14,14,(.22,.22,.22,1))
                    if getattr(s,key):c.tick(x+3,y+6,color)
                if kind=='snap':
                    max_icons.draw('snap_type_'+key,self.x+(x+30)*self.scale,self.top-(y+10)*self.scale,20*self.scale)
                c.text(x+(46 if kind=='snap' else 20),y+2,label,color)
            elif kind=='number':
                if s.tab=='OPTIONS' and key!='marker_size':
                    c.text(24,y,label,color)
                else:
                    c.text(x-255,y,label,color,align='RIGHT',width=251)
                c.rect(x,y,w,h,(.34,.34,.34,1))
                text=self.buffer if self.edit==key else (str(getattr(s,key)) if s.bl_rna.properties[key].type=='INT' else f'{getattr(s,key):.1f}')
                if self.edit==key and self.selected:c.rect(x+1,y+1,w-14,h-2,(.2,.35,.5,1))
                c.text(x+3,y,text,color)
                c.rect(x+w-12,y,12,h,(.39,.39,.39,1))
                c.arrow(x+w-10,y+3,'UP',color)
                c.arrow(x+w-10,y+12,'DOWN',color)
            elif kind=='button' or kind=='combo':
                c.rect(x,y,w,h,(.34,.34,.34,1))
                c.border(x,y,w,h,(.2,.2,.2,1))
                c.text(x+5,y+4,label,color,align='CENTER' if kind=='button' else 'LEFT',width=w-10)
                if kind=='combo':c.arrow(x+w-14,y+9,'DOWN')
            else:
                c.text(x,y,label,color)
        if hover and hover[9] and time.monotonic()-self.hover_since>.7:
            tip=hover[9]
            c.rect(8,360,self.width-16,28,(.16,.16,.16,1))
            c.text(14,365,tip,size=10)
        gpu.state.blend_set('NONE')


class MAX_OT_snap_settings_events(bpy.types.Operator):
    bl_idname='max.snap_settings_events'
    bl_label='Grid and Snap Settings Events'
    bl_options={'INTERNAL'}

    def invoke(self,context,event):
        self.dialog=Dialog(context)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        from . import snaps
        live = any(area == self.dialog.area for area in context.window.screen.areas) and self.dialog.area.type == 'VIEW_3D'
        if self.dialog.closed or self.dialog.key not in snaps._settings_windows or not live:
            self.dialog.close()
            return {'FINISHED', 'PASS_THROUGH'}
        return self.dialog.event(context,event)

    def cancel(self,context):
        self.dialog.close()
