"""Compare original caddy SVGs with frozen old icons and external Max references.

python tools/preview_caddy_icons.py --sandbox <sb-caddy-icons> [--live]
The reference images stay outside the repo. They never enter runtime assets.
"""
import argparse
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import resvg_py

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT/'notuodesk_3ds_maxxed/icons'
# Full caddy images downloaded from the corresponding Autodesk 2026 Help page.
REFERENCES = {'extrude':'extrude-05.png', 'chamfer':'chamfer-09.png',
    'connect':'connect-07.png', 'bevel':'bevel-06.png', 'inset':'inset-05.png',
    'bridge':'bridge-07.png', 'weld':'weld-06.png', 'tessellate':'tessellate-04.png',
    'msmooth':'smooth-04.png', 'relax':'relax-04.png', 'outline':'poly_face-08.png'}
OLD = {'extrude_height':'height', 'chamfer_amount':'chamfer',
       'inset_individual':'type_group', 'tessellate_tessellate_type':'type_edge'}
# Measured control bounds, excluding the documentation image's outer padding.
# Chamfer's last antialiased footer row is dark. Its logical disc is 22px high.
REFERENCE_BOUNDS = {'extrude':(5,5,108,150),'chamfer':(10,9,181,266),
    'connect':(4,5,85,133),'bevel':(9,6,80,179),'inset':(4,3,80,104),
    'bridge':(5,6,155,162),'weld':(4,5,103,99),'tessellate':(3,4,80,104),
    'msmooth':(3,4,95,104),'relax':(3,3,95,133)}
# Prefer Autodesk's isolated setting image when it supplies one. This avoids
# cutting through neighbouring pills in tightly packed full-caddy screenshots.
FIELD_REFS = {
    'extrude': {'extrusion_type':6,'height':9,'local_bias':10},
    'chamfer': {'amount':11,'segments':12,'tension':13,'open':17,
        'chamfer_depth':13,'end_bias':15,'radial_bias':16,'invert_open':18,
        'chamfer_smooth':19,'smooth_type':20,'smooth_threshold':21},
    'connect': {'segments':9,'pinch':10,'slide':11},
    'bevel': {'bevel_type':7,'height':10,'amount':11,'local_bias':12},
    'inset': {'individual':7,'amount':9},
    'bridge': {'segments':9,'taper':10,'bias':11,'smooth':12,'twist1':13,'twist2':14,
               'bridge_selection':15,'pick1':17,'pick2':18,'pick_cursor':17},
    'weld': {'threshold':8},
    'tessellate': {'tessellate_type':6,'tess_tension':8},
    'msmooth': {'smoothness':6,'separate_smoothing':7,'separate_materials':8},
    'relax': {'relax':6,'iterations':7,'hold_boundary':8,'hold_outer':9},
}
# Crop the actual setting from its caddy. Outline has no published caddy image.
ROWS = {
    'extrude': {'extrusion_type':(2,44,53,70),'height':(2,73,83,99),'local_bias':(2,103,83,129)},
    'chamfer': {'amount':(10,79,81,101),'segments':(10,108,81,130),'tension':(10,137,81,159),
        'open':(10,195,58,217),'chamfer_miter':(10,50,58,72),
        'chamfer_depth':(10,137,81,159),'end_bias':(10,166,81,188),'radial_bias':(90,166,161,188),
        'invert_open':(65,195,113,217),'chamfer_smooth':(10,224,58,246),
        'smooth_type':(65,224,113,246),'smooth_threshold':(120,224,191,246)},
    'connect': {'segments':(3,28,88,54),'pinch':(3,59,88,85),'slide':(3,90,88,116)},
    'bevel': {'bevel_type':(4,41,56,65),'height':(4,72,80,96),'amount':(4,102,80,126),'local_bias':(4,132,80,156)},
    'inset': {'individual':(2,26,48,51),'amount':(2,55,82,81)},
    'bridge': {'segments':(2,25,78,50),'taper':(85,25,160,50),'bias':(2,54,78,79),'smooth':(85,54,160,79),
               'twist1':(2,83,78,108),'twist2':(85,83,160,108),'bridge_selection':(2,113,50,138),
               'pick1':(85,113,160,138),'pick2':(48,113,86,138),'pick_cursor':(105,113,130,138)},
    'weld': {'threshold':(2,26,108,53),'weld_counts':(2,57,108,80)},
    'tessellate': {'tessellate_type':(2,25,50,52),'tess_tension':(2,57,83,82)},
    'msmooth': {'smoothness':(2,26,98,53),'separate_smoothing':(2,57,50,83),'separate_materials':(52,57,100,83)},
    'relax': {'relax':(2,27,98,53),'iterations':(2,57,98,83),'hold_boundary':(2,87,50,113),'hold_outer':(52,87,100,113)},
}


def split_name(name):
    op, key = name.removeprefix('caddy_').split('_', 1)
    for prefix in ('extrusion_type','bevel_type','individual','tessellate_type'):
        if key.startswith(prefix):
            return op, prefix
    return op, key


def old_name(name):
    op, key = split_name(name)
    if key == 'pick_cursor':
        return 'caddy_pick'
    if key in ('extrusion_type','bevel_type'):
        value = name.rsplit('_',1)[-1]
        return 'caddy_type_'+(value if value in ('group','local','polygon') else 'group')
    if key == 'individual':
        return 'caddy_type_'+('polygon' if name.endswith('_polygon') else 'group')
    if key == 'tessellate_type':
        return 'caddy_type_'+('face' if name.endswith('_face') else 'edge')
    return 'caddy_'+OLD.get(op+'_'+key,key)


def render(source, size):
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(source),width=size,height=size,
                                                     skip_system_fonts=True))).convert('RGBA')


def live_comparisons(sandbox, tag=''):
    manifest_path=sandbox/'out/caddy-icons-gallery.json'
    if not manifest_path.is_file():
        return
    rows=json.loads(manifest_path.read_text())
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
    small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',13)
    evidence=[]
    footprints=[]
    for op,reference in REFERENCES.items():
        captured=[]
        for requested in (1.0,1.5):
            row=next(r for r in rows if r['action']==op.upper() and r['requested_scale']==requested)
            assert abs(row['scale']-requested)<.03, 'Capture must use effective 100% / 150% UI scale'
            source=max((sandbox/'out').glob('*-icons-'+op+'-'+str(round(requested*100))+'.png'),
                       key=lambda p:p.stat().st_mtime_ns)
            im=Image.open(source).convert('RGB')
            x,y=row['x'],im.height-row['y']
            crop=im.crop((int(x-8*requested),int(y-2*requested),
                          int(x+max(row['width'],row['title_width'])+8*requested),
                          int(y+row['height']+12*requested)))
            # Both live panels and the reference use the same total 3x scale.
            crop=crop.resize((round(crop.width*3/requested),round(crop.height*3/requested)),Image.Resampling.NEAREST)
            captured.append((row,source,crop))
        max_image=Image.open(sandbox/'references'/reference).convert('RGBA')
        if op in REFERENCE_BOUNDS:
            rx,ry,rw,rh=REFERENCE_BOUNDS[op]
            normalized=Image.new('RGBA',(rw+16,rh+14),max_image.getpixel((0,0)))
            normalized.paste(max_image,(8-rx,2-ry))
            max_image=normalized
        for row,source,crop in captured:
            factor=row['scale']
            actual=[math.ceil(row['width']),math.ceil(row['height'])]
            target=([math.ceil(REFERENCE_BOUNDS[op][2]*factor),math.ceil(REFERENCE_BOUNDS[op][3]*factor)]
                    if op in REFERENCE_BOUNDS else None)
            if target is not None:
                assert actual==target,(op,factor,actual,target)
            footprints.append(dict(operation=op,scale=factor,live_pixels=actual,max_pixels=target,
                measurement='Enclosing control bounds, no documentation padding or hover tooltip',
                reference=reference,source=str(source)))
        max_large=max_image.resize((max_image.width*3,max_image.height*3),Image.Resampling.NEAREST)
        dark_footer=Image.open(sandbox/'references/extrude-05.png').convert('RGBA').crop((0,132,88,158))
        dark_footer=dark_footer.resize((264,78),Image.Resampling.NEAREST)
        widths=[captured[0][2].width,captured[1][2].width,max_large.width]
        height=max(crop.height for _,_,crop in captured)
        height=max(height,max_large.height)+240
        sheet=Image.new('RGB',(sum(widths)+90,height),'#303437');d=ImageDraw.Draw(sheet)
        d.text((15,12),op.title()+' | Blender live caddy beside Autodesk 2026 Help',font=font,fill='white')
        x=15
        for index,(row,source,crop) in enumerate(captured):
            d.text((x,47),'Live '+str(round(row['scale']*100))+'% (normalized 3x)',font=small,fill='#d0d7dc')
            sheet.paste(crop,(x,77));x+=widths[index]+20
        label='Max caddy (3x nearest)' if op!='outline' else 'Max Outline example (3x)'
        d.text((x,47),label,font=small,fill='#d0d7dc');sheet.paste(max_large,(x,77),max_large)
        d.text((15,height-126),'Footer target: Max 2026 dark theme (Extrude)',font=small,fill='#d0d7dc')
        sheet.paste(dark_footer,(15,height-102),dark_footer)
        if op=='outline':
            d.text((15,height-34),'Autodesk publishes a boundary example, not an Outline caddy image. Caddy chrome remains unverified.',font=small,fill='#f3c37c')
        path=sandbox/('compare-'+op+tag+'.png');sheet.save(path)
        if tag:
            sheet.save(sandbox/('compare-'+op+'.png'))
        evidence.append(dict(operation=op,comparison=str(path),reference=reference,
                             live=[str(source) for _,source,_ in captured]))
        print('COMPARE',path,flush=True)
    (sandbox/'live-comparison-index.json').write_text(json.dumps(evidence,indent=2)+'\n')
    (sandbox/'round3-footprints.json').write_text(json.dumps(footprints,indent=2)+'\n')
    lines=['| Caddy | Live 100% | Max 100% | Live 150% | Max 150% |',
           '|---|---|---|---|---|']
    def dimensions(value):
        return 'Unverified' if value is None else ' x '.join(map(str,value))
    for op in REFERENCES:
        first,second=[r for r in footprints if r['operation']==op]
        lines.append('| '+op+' | '+' | '.join(dimensions(v) for v in
                     [first['live_pixels'],first['max_pixels'],second['live_pixels'],second['max_pixels']])+' |')
    (sandbox/'round3-footprints.md').write_text('\n'.join(lines)+'\n')


def main(sandbox, include_live=False, tag=''):
    catalog=json.loads((ICONS/'src/catalog.json').read_text())
    names=sorted(row['name'] for row in catalog['icons'] if
        row['section']=='caddies' and row['note'].startswith('Original shaded pictogram.'))
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',13)
    small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',11)
    manifest=[]
    pages=[]
    for start in range(0,len(names),16):
        batch=names[start:start+16]
        sheet=Image.new('RGB',(1160,90+len(batch)*100),'#303437'); d=ImageDraw.Draw(sheet)
        d.text((16,10),'Caddy icons | old beside original redraw | Autodesk 2026 setting crop',font=font,fill='white')
        d.text((16,34),'Native 16 / 20 / 32 px and 150% (24 / 30 / 48 px). Reference pixels never ship.',font=font,fill='#b6c0c5')
        d.text((320,62),'Each pair: old (left), new (right)',font=small,fill='white')
        d.text((870,62),'Max setting / caddy',font=small,fill='white')
        for i,name in enumerate(batch):
            y=90+i*100;op,key=split_name(name);old=old_name(name)
            d.rectangle((0,y,1159,y+99),outline='#485158')
            d.text((10,y+7),name,font=small,fill='white')
            d.text((10,y+28),'old '+old,font=small,fill='#b4bdc3')
            x=320
            for index,size in enumerate((16,20,32,24,30,48)):
                # Same medium-grey pill background as the actual caddies.
                for dx,src in ((0,sandbox/'baseline/src'/(old+'.svg')),(size+6,ICONS/'src'/(name+'.svg'))):
                    d.rectangle((x+dx-2,y+33,x+dx+size+1,y+33+size),fill='#93999c')
                    if src.is_file() and not (dx and op=='msmooth' and key in {'separate_smoothing','separate_materials'}):
                        tile=render(src,size);sheet.paste(tile,(x+dx,y+33),tile)
                d.text((x,y+9),str(size)+'px',font=small,fill='#c6ced2')
                x += size*2+16
            ref=Image.open(sandbox/'references'/REFERENCES[op]).convert('RGBA')
            if op=='extrude' and key=='base_width':
                ref=Image.open(sandbox/'references/extrude_vertex-07.png').convert('RGBA')
                crop=ref.crop((2,54,90,81))
            elif op=='outline':
                crop=ref.copy();crop.thumbnail((130,68))
                d.text((870,y+78),'No Max caddy image published',font=small,fill='#f3c37c')
            elif key in {'bridge_adjacent','reverse_triangulation'}:
                ref=Image.open(sandbox/'references/bridge_edges-06.png').convert('RGBA')
                crop=ref.copy();crop.thumbnail((130,68))
            else:
                crop=ref.crop(ROWS[op][key]);crop.thumbnail((200,60))
                ref_prefix='smooth' if op=='msmooth' else op
                if key in FIELD_REFS.get(op,{}):
                    ref_file=ref_prefix+'-'+str(FIELD_REFS[op][key]).zfill(2)+'.png'
                    crop=Image.open(sandbox/'references'/ref_file).convert('RGBA')
                    crop.thumbnail((200,60))
                choice=name.rsplit('_',1)[-1]
                mode_refs={'extrude':{'group':6,'local':7,'polygon':8},
                           'bevel':{'group':7,'local':8,'polygon':9},
                           'inset':{'group':7,'polygon':8},
                           'tessellate':{'edge':6,'face':7}}
                if key in ('extrusion_type','bevel_type','individual','tessellate_type') and choice in mode_refs.get(op,{}):
                    crop=Image.open(sandbox/'references'/(op+'-'+str(mode_refs[op][choice]).zfill(2)+'.png')).convert('RGBA')
                    crop.thumbnail((200,60))
            sheet.paste(crop,(875,y+15),crop)
            if op=='msmooth' and key in {'separate_smoothing','separate_materials'}:
                d.text((320,y+86),'Blank before the check mark in Max. Reserved SVG is not drawn.',font=small,fill='#f3c37c')
            manifest.append(dict(name=name,old=old,reference=REFERENCES[op],field=key))
        stem='caddy-icons-sheet' if not pages else 'caddy-icons-sheet-'+str(len(pages)+1)
        path=sandbox/(stem+tag+'.png')
        sheet.save(path);pages.append(path)
        if tag:
            sheet.save(sandbox/(stem+'.png'))
        print('SHEET',path,flush=True)
    (sandbox/'icon-comparison-index.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('CADDY SHEETS',len(names),'new drawings in',len(pages),'sheets',flush=True)
    if include_live:
        live_comparisons(sandbox,tag)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sandbox',type=Path,required=True)
    parser.add_argument('--live',action='store_true',help='Also compare the completed GUI icon tour')
    parser.add_argument('--tag',default='',help='Unique render suffix, also refresh the standard comparison filenames')
    args=parser.parse_args()
    main(args.sandbox,args.live,args.tag)
