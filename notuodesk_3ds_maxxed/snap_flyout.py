"""Three compact snap mode buttons, without Blender's minimum menu width."""
import time
import bpy

_active = []
MODES = (('2D','snap_2d'),('2_5D','snap_25d'),('3D','snap_3d'))


def close_all():
    for item in list(_active):
        item.close()


class Flyout:
    # The downloaded 2026 image is 37x113. Its stale HTML says 37x97.
    width, height, row_height = 37, 113, 38

    def __init__(self, context, event):
        from . import snaps
        self.window, self.area = context.window, context.area
        regions=[r for r in self.area.regions if r.type=='WINDOW' and r.x<=event.mouse_x<r.x+r.width]
        self.region=max(regions,key=lambda r:r.y+r.height)
        self.scale=context.preferences.system.ui_scale
        self.left=max(0,min(self.region.width-self.width*self.scale,event.mouse_x-self.region.x-self.width*self.scale/2))
        self.top=self.region.height
        self.mouse=(event.mouse_x,event.mouse_y)
        self.started=time.monotonic()
        self.generation=snaps._guard_generation
        self.open=False
        self.closed=False
        self.handle=None
        self.timer=context.window_manager.event_timer_add(.05,window=self.window)
        _active.append(self)

    def hit(self):
        x,y=self.mouse[0]-self.region.x,self.mouse[1]-self.region.y
        index=int((self.top-y)//(self.row_height*self.scale))
        return index if self.left<=x<self.left+self.width*self.scale and 0<=index<3 and self.top-self.height*self.scale<y<=self.top else None

    def close(self):
        if self.closed:return
        self.closed=True
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW')
        bpy.context.window_manager.event_timer_remove(self.timer)
        if self in _active:_active.remove(self)
        try:self.area.tag_redraw()
        except ReferenceError:pass

    def modal(self, context, event):
        from . import snaps
        if self.closed or self.generation!=snaps._guard_generation:
            self.close()
            return {'CANCELLED'}
        if event.type!='TIMER':self.mouse=(event.mouse_x,event.mouse_y)
        if event.type=='TIMER' and not self.open and time.monotonic()-self.started>.3:
            self.open=True
            self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw,(),'WINDOW','POST_PIXEL')
        if event.type in {'RIGHTMOUSE','ESC'} and event.value=='PRESS':
            self.close()
            return {'CANCELLED'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            if not self.open:
                self.close()
                snaps.toggle(context,'SNAP')
                return {'FINISHED'}
            index=self.hit()
            if index is not None:
                snaps.settings(context).mode=MODES[index][0]
                self.close()
                snaps._redraw(context)
                return {'FINISHED'}
            self.close()
            return {'CANCELLED'}
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def draw(self):
        if self.closed or bpy.context.region!=self.region:return
        import gpu
        from . import max_icons,snaps
        from .max_ui_draw import Canvas,HEADER,HOVER
        c=Canvas(self.left,self.top,self.scale)
        gpu.state.blend_set('ALPHA')
        c.rect(0,0,self.width,self.height,HEADER)
        for i,(mode,icon) in enumerate(MODES):
            top=i*self.row_height
            height=min(self.row_height,self.height-top)
            if i==self.hit():c.rect(1,top+1,self.width-2,height-2,HOVER)
            max_icons.draw(icon,self.left+self.width*self.scale/2,self.top-(top+height/2)*self.scale,32*self.scale)
            c.border(0,top,self.width,height)
        c.border(0,0,self.width,self.height)
        gpu.state.blend_set('NONE')
