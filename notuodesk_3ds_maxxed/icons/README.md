# Original Max-style icons

These SVGs were drawn from scratch for NotuoDesk 3ds Maxxed. They use familiar
modeling symbols, light grey strokes, transparent backgrounds and sparse accent
colors. Modify has a curved segment in a cyan control cage. Render has a teapot.
The color choices belong to this set and are not measured Autodesk theme values.

Extended Primitive artwork covers Hedra, Torus Knot, ChamferBox, ChamferCyl,
OilTank, Capsule, Spindle, L-Ext, Gengon, C-Ext and Prism. OilTank has shallow
convex caps, Capsule has hemispherical caps, and Spindle has pointed caps.
These are original drawings using the same strokes as Box, Cylinder and Cone.

License for every SVG and PNG in this directory is GPL-3.0-or-later, like the
add-on. See the repository's LICENSE. Every SVG also carries the SPDX identifier.

## Provenance

No Autodesk artwork was copied, traced, extracted or embedded in these assets.
Official Help images were downloaded into the external review sandbox for
visual study. No Max installation files were read. The supplied reference pack
and those images informed symbols and placement. Neither ships in the add-on.

Visual references in the external `max-ui-reference/images/` pack were
`interface-overview.png`, `create-primitives.png`, `edit-poly-stack.png` and
`quad-default-2026.png`. The matching text references were `overall-layout.md`,
`create-panel.md`, `modify-panel.md`, `quad-menus.md`, `dialogs.md` and
`nathan-setup.md`.

The SVG paths, circles, ellipses and rectangles are the editable source. Their
16 by 16 coordinate system uses strokes near one unit wide. Numerals on snap
icons are original paths. Sources contain no linked images, fonts or external
resources. PNGs are transparent RGBA renders at 32px and 64px (`@2x`).

## Rebuild

From the repository root on Reborn:

```powershell
uv pip install --python C:/Users/thelo/.local/venvs/data/Scripts/python.exe resvg-py==0.5.0 Pillow
& C:/Users/thelo/.local/venvs/data/Scripts/python.exe tools/build_icons.py --contact-sheet icons-contact.png
```

`tools/draw_max_icons_v2.py` authors the SVG family and `src/catalog.json`.
The catalog gives every asset a Max placement, presentation, visual metaphor
and Autodesk 2026 reference URL. `tools/preview_max_icons_v2.py --out <sandbox>`
compares these drawings with a frozen pre-change `<sandbox>/baseline` folder.
It renders native 16, 20 and 32px sizes and 24, 30 and 48px for 150% scaling.

The renderer reads only the SVG sources. Pillow is needed only for the optional
contact sheet. Neither dependency ships with the add-on or runs inside Blender.

`max_icons.py` owns one `bpy.utils.previews` collection. Registration loads 64px
PNGs, then tries 32px when a 64px PNG is missing. Repeated loader registration
reuses the collection. Unregister removes it. `icon(name)` returns an icon ID.
`ui(name, fallback)` chooses custom `icon_value` or the previous Blender icon.
Command Panel enums receive their custom icon IDs when the properties register.
The loader fills icon pixels before the first draw to avoid transparent lazy
thumbnails at GUI startup. The icon and larger preview both retain the source
resolution for UI scaling.

## Verify in an isolated Blender profile

Never use the real Blender profile for these checks. Create `scripts/addons`,
`config` and `ext` under a disposable directory and junction the add-on package
into its `scripts/addons/notuodesk_3ds_maxxed` directory. Then run:

```powershell
$env:BLENDER_USER_SCRIPTS='C:/Users/thelo/.claudework/maxxed-review/sb-icons/scripts'
$env:BLENDER_USER_CONFIG='C:/Users/thelo/.claudework/maxxed-review/sb-icons/config'
$env:BLENDER_USER_EXTENSIONS='C:/Users/thelo/.claudework/maxxed-review/sb-icons/ext'
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/test_max_icons.py
```

The test checks the required set, literal and dynamic UI references, PNG sizes,
decoded preview pixels, missing PNG fallbacks and three complete add-on reloads.
It checks Blender's diagnostic collection registry for leaks. Background Blender
does not allocate GUI icon IDs. Positive IDs and visible drawing need a GUI run.

## Scope

The set has 272 drawings, including all 125 previous names. It includes assets
for Max controls that this add-on does not yet display.
No new controls or tool behavior are introduced. The existing quad menus have
no built-in icon arguments to replace. Material previews remain live Blender
previews. Blender's native material preview-type, viewport shading and overlay
buttons retain their built-in enum icons.

Move uses a solid four-way cross. Create categories use Max's disc, overlapping
shapes, bulb, camera and set-square metaphors. Each sub-object icon has the same
small mesh with a different component highlighted. Modifier visibility uses eyes.
Settings buttons use inset squares. Snaps use large numerals with a small gold
magnet at the upper right. These are original drawings, not pixel copies.

Command Panel tabs, categories, sub-object buttons, toolbar tools, snap toggles
and existing stack tools remain icon-only. Icon tooltips give the Max name and
an active configured shortcut when one exists. Create object buttons, Loft,
PlanePlus, Constraints, viewport labels and Editable Poly commands keep text.
Auto Key and Set Key mode controls keep text. Named stack rows keep icon and text.
The catalog marks reserved drawings for text-only spots so integration does not
add decorative icons to Max's text controls.

`max_icons.CADDY_FIELDS` maps pending `poly_caddies` field keys to the `caddy_*`
assets. These include the branch's kind names and field names. The caddy branch
must use these assets in its GPU draw routine. Its numeric values stay visible,
and its field names move into hover titles. That branch is not merged here.
The `constraint_*`, `symmetry*` and `ops.transform.*` drawings are ready for
their feature integrator. WorkSpaceTool `bl_icon` requires Blender's tool-icon
format or a custom draw route. A preview PNG does not replace its `.dat` file.
This branch changes toolbar previews, not unmerged gizmo drawing code.

`show_end_result`, `pin_stack` and `configure_modifier_sets` are assets for
controls not yet implemented here. No inactive asset creates a new control.
