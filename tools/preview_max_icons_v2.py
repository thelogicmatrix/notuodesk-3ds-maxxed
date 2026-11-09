"""Render side-by-side review sheets. Never writes runtime PNG files.

python tools/preview_max_icons_v2.py --out <sandbox>
Dependencies are the existing resvg-py and Pillow build tools.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
from collections import Counter
import hashlib
import html
import io
import json
from pathlib import Path
import shutil
import textwrap
import xml.etree.ElementTree as ET

import resvg_py
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / 'notuodesk_3ds_maxxed/icons'
SOURCES = ICONS / 'src'
PACK = Path('C:/Users/thelo/.claudework/maxxed-review/max-ui-reference')
FONT = 'C:/Windows/Fonts/consola.ttf'
SECTIONS = {
    'toolbar': 'Main toolbar', 'command_panel': 'Command Panel and stack',
    'create_objects': 'Create object types', 'material': 'Material tools',
    'editable_poly': 'Editable Poly commands', 'caddies': 'Caddy fields and choices',
    'navigation': 'Viewport navigation and time', 'features': 'Pending feature tools',
}

def render(path, size):
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(path),width=size,height=size,
                                                   skip_system_fonts=True))).convert('RGBA')

def main(out):
    out.mkdir(parents=True, exist_ok=True)
    baseline = out / 'baseline'
    baseline.mkdir(exist_ok=True)
    catalog = json.loads((SOURCES / 'catalog.json').read_text(encoding='utf-8'))
    # Baseline was frozen before integration. Never replace it on a rebuild.
    if not any(baseline.glob('*.svg')):
        raise RuntimeError('Supply the pre-change baseline SVGs in <out>/baseline first')
    fonts = {s:ImageFont.truetype(FONT,s) for s in (12,13,14,15,20)}
    refs = catalog['references']
    rows = catalog['icons']
    source_hashes = {}
    for row in rows:
        src = SOURCES / (row['name']+'.svg')
        tree = ET.parse(src)
        assert tree.getroot().get('viewBox') == '0 0 16 16', src
        assert not any(x.tag.split('}')[-1] in {'image','text','script','foreignObject'} for x in tree.iter()),src
        assert 'SPDX-License-Identifier: GPL-3.0-or-later' in src.read_text()
        source_hashes[row['name']] = hashlib.sha256(src.read_bytes()).hexdigest()
    pages=[]
    for section,title in SECTIONS.items():
        group=[r for r in rows if r['section']==section]
        for start in range(0,len(group),28):
            batch=group[start:start+28]
            num=len(pages)+1
            filename='contact-sheet-v1'+('' if num==1 else '-'+str(num).zfill(2))+'.png'
            im=Image.new('RGB',(1480,150+len(batch)*96),'#444444')
            d=ImageDraw.Draw(im)
            d.text((18,12),f'{num:02d}  {title} | original Max-inspired drawings',font=fonts[20],fill='#eeeeee')
            d.text((18,44),'Current and new at native 16 / 20 / 32 px. New at 150% = 24 / 30 / 48 px.',font=fonts[14],fill='#dddddd')
            d.text((18,66),'Background #444444 sampled from the supplied Autodesk overview. Accent RGB is an authored approximation.',font=fonts[12],fill='#bbbbbb')
            d.text((18,86),'TEXT ONLY means keep Max\'s text, not permission to add this reserved pictogram. Source URLs are in contact-sheet-index.md.',font=fonts[12],fill='#e9c77a')
            for x,label in [(18,'Asset / Max placement'),(282,'Current'),(445,'New'),(620,'New at 150%'),(875,'Max idea / evidence')]:
                d.text((x,119),label,font=fonts[14],fill='#ffffff')
            for i,row in enumerate(batch):
                y=150+i*96
                d.line((12,y,1468,y),fill='#606060')
                n=row['name']
                d.text((18,y+10),n,font=fonts[14],fill='#ffffff')
                mode=row['presentation'].upper()
                d.text((18,y+33),mode,font=fonts[12],fill='#e9c77a' if mode=='TEXT-ONLY' else '#9dd6d9')
                for j,line in enumerate(textwrap.wrap(row['spot'],31)[:2]):
                    d.text((18,y+53+j*15),line,font=fonts[12],fill='#cccccc')
                src=SOURCES/(n+'.svg')
                old=baseline/(n+'.svg')
                for label,xs,ss,target in [('old',(284,327,374),(16,20,32),old),('new',(447,490,537),(16,20,32),src),('scale',(621,673,733),(24,30,48),src)]:
                    if not target.exists():
                        d.text((xs[0],y+27),'No prior SVG',font=fonts[12],fill='#b4b4b4')
                        d.text((xs[0],y+44),'text / built-in',font=fonts[12],fill='#b4b4b4')
                        continue
                    for x,size in zip(xs,ss):
                        tile=render(target,size)
                        assert tile.getbbox(),(n,size)
                        im.paste(tile,(x,y+9+(48-size)//2),tile)
                        d.text((x,y+67),str(size),font=fonts[12],fill='#bbbbbb')
                for j,line in enumerate(textwrap.wrap(row['idea'],66)[:2]):
                    d.text((875,y+10+j*17),line,font=fonts[13],fill='#eeeeee')
                d.text((875,y+51),'Reference '+row['reference'],font=fonts[12],fill='#9dd6d9')
                evidence=refs[row['reference']]['evidence']
                d.text((875,y+69),textwrap.shorten(evidence,75,placeholder='...'),font=fonts[12],fill='#bbbbbb')
                row['sheet']=filename
            im.save(out/filename)
            pages.append(filename)
            print('SHEET',filename,len(batch),'assets',flush=True)
    header=['# Max 2026 icon comparison index','',
        'Review date 2026-11-10. Original GPL-3.0-or-later drawings, authored without tracing or embedding Autodesk artwork. '+
        'The Autodesk images are external reference evidence only. The existing 125 SVGs are frozen in this sandbox\'s baseline folder.', '',
        'Every asset has a primary placement classification below. A symbol can have another presentation in a different location. '+
        'Main toolbar and menu reuse does not make the menu icon-only. Max quad command names stay text, with a small settings or '+
        'Transform Type-In square where Max shows one. Create Object Type buttons stay text. Active viewport labels stay text.', '',
        'The 2026 Help sometimes reuses older screenshots. These citations prove the published metaphor and placement, not a measured '+
        'stock 2026 theme. Colours other than the sampled background are authored approximations. Reserved drawings for text-only '+
        'controls are not claimed to be stock Max icons.', '',
        '## Contact sheets','']
    header += [f'- [{p}]({p})' for p in pages]
    header += ['', '## Source index', '']
    for key,ref in refs.items():
        header += [f'- `{key}` [Autodesk 2026]({ref["url"]}). Evidence `{ref["evidence"]}`.']
    header += ['', '## Every asset', '', '| Asset | Sheet | Max presentation at this spot | Spot | Visual idea | Source | Integration note |',
               '|---|---|---|---|---|---|---|']
    for r in rows:
        ref=refs[r['reference']]
        header.append(f'| `{r["name"]}` | [{r["sheet"]}]({r["sheet"]}) | {r["presentation"]} | {r["spot"]} | {r["idea"]} | [{r["reference"]}]({ref["url"]}), `{ref["evidence"]}` | {r["note"]} |')
    (out/'contact-sheet-index.md').write_text('\n'.join(header)+'\n',encoding='utf-8')
    (out/'contact-sheet-index.json').write_text(json.dumps(catalog,indent=2)+'\n',encoding='utf-8')
    (out/'source-hashes.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
    verify=dict(svg_count=len(rows),baseline_count=len(list(baseline.glob('*.svg'))),
                sheets=pages,presentation=dict(Counter(r['presentation'] for r in rows)),
                render_sizes=[16,20,32,24,30,48],external_images_in_svg=0)
    (out/'artwork-verification.json').write_text(json.dumps(verify,indent=2)+'\n')
    print('ARTWORK PASS',json.dumps(verify),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
