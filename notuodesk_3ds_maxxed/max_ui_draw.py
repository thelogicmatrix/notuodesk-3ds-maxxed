"""Compact Max menu/dialog drawing. Coordinates run down from the top left.

Shared drawing only. The invoking operator owns input and lifetime. W2.D can
reuse Canvas and menu_row without adopting the snap tool's event listener.
"""
from pathlib import Path

_fonts = {}
BACKGROUND = (.26, .26, .26, 1)
TEXT = (.9, .9, .9, 1)
DISABLED = (.53, .53, .53, 1)
HEADER = (.20, .20, .20, 1)
EDGE = (.10, .10, .10, 1)
HOVER = (.24, .40, .55, 1)


class Canvas:
    def __init__(self, x, top, scale=1, font='segoeui'):
        import gpu
        import blf
        self.x, self.top, self.scale = x, top, scale
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        if font not in _fonts:
            path = Path('C:/Windows/Fonts') / (font+'.ttf')
            _fonts[font] = blf.load(str(path)) if path.is_file() else 0
        self.font = _fonts[font]

    def polygon(self, points, color):
        from gpu_extras.batch import batch_for_shader
        coords = [(self.x+x*self.scale, self.top-y*self.scale) for x, y in points]
        self.shader.bind()
        self.shader.uniform_float('color', color)
        batch_for_shader(self.shader, 'TRI_FAN', {'pos': coords}).draw(self.shader)

    def rect(self, x, y, w, h, color=BACKGROUND):
        self.polygon(((x,y), (x+w,y), (x+w,y+h), (x,y+h)), color)

    def border(self, x, y, w, h, color=EDGE):
        self.rect(x,y,w,1,color)
        self.rect(x,y+h-1,w,1,color)
        self.rect(x,y,1,h,color)
        self.rect(x+w-1,y,1,h,color)

    def text(self, x, y, label, color=TEXT, size=12, align='LEFT', width=0):
        import blf
        blf.size(self.font, size*self.scale)
        blf.color(self.font, *color)
        w = blf.dimensions(self.font, label)[0]/self.scale
        if align == 'RIGHT':
            x += width-w
        elif align == 'CENTER':
            x += (width-w)/2
        blf.position(self.font, self.x+x*self.scale, self.top-(y+size)*self.scale, 0)
        blf.draw(self.font, label)

    def line(self, a, b, color=TEXT, width=1):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = (dx*dx+dy*dy)**.5
        if not length:
            return
        nx, ny = -dy/length*width/2, dx/length*width/2
        self.polygon(((a[0]+nx,a[1]+ny),(a[0]-nx,a[1]-ny),
                      (b[0]-nx,b[1]-ny),(b[0]+nx,b[1]+ny)), color)

    def tick(self, x, y, color=TEXT):
        self.line((x,y+4), (x+3,y+7), color)
        self.line((x+3,y+7), (x+8,y), color)

    def arrow(self, x, y, direction='RIGHT', color=TEXT):
        points = {'RIGHT': ((0,0),(4,4),(0,8)), 'DOWN': ((0,0),(8,0),(4,4)),
                  'UP': ((0,4),(8,4),(4,0))}[direction]
        self.polygon([(x+a,y+b) for a,b in points], color)

    def menu_row(self, x, y, width, label, *, enabled=True, checked=False,
                 header=False, arrow=False, hover=False, height=16, align=None):
        self.rect(x, y, width, height, HEADER if header else HOVER if hover else BACKGROUND)
        if header:
            self.border(x,y,width,height)
        color = TEXT if enabled or header else DISABLED
        self.text(x+4 if header or align=='CENTER' else x+14,y+1,label,color,10,
                  align=align or ('RIGHT' if header else 'LEFT'),width=width-8)
        if checked:
            self.tick(x+4,y+4,color)
        if arrow:
            self.arrow(x+width-10,y+4,color=color)
