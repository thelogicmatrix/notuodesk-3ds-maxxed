# Original Max-style icons

These SVGs were drawn from scratch for NotuoDesk 3ds Maxxed. They use familiar
modeling symbols, light grey strokes, transparent backgrounds and sparse accent
colors. The Modify tab has a colored arch. The Render buttons have a teapot.
The color choices belong to this set and are not measured Autodesk theme values.

License for every SVG and PNG in this directory is GPL-3.0-or-later, like the
add-on. See the repository's LICENSE. Every SVG also carries the SPDX identifier.

## Provenance

No Autodesk icon file was downloaded, copied, traced, extracted or embedded.
No Max installation files were read. The supplied reference pack was inspected
only for symbols and placement. It is not included in this directory.

Visual references in the external `max-ui-reference/images/` pack were
`interface-overview.png`, `create-primitives.png`, `edit-poly-stack.png` and
`quad-default-2026.png`. The matching text references were `overall-layout.md`,
`create-panel.md`, `modify-panel.md`, `quad-menus.md`, `dialogs.md` and
`nathan-setup.md`.

The SVG paths, circles, ellipses and rectangles are the editable source. Their
32 by 32 coordinate system uses strokes near two units wide. Numerals on snap
icons are original paths. Sources contain no linked images, fonts or external
resources. PNGs are transparent RGBA renders at 32px and 64px (`@2x`).

## Rebuild

From the repository root on Reborn:

```powershell
uv pip install --python C:/Users/thelo/.local/venvs/data/Scripts/python.exe resvg-py==0.5.0 Pillow
& C:/Users/thelo/.local/venvs/data/Scripts/python.exe tools/build_icons.py --contact-sheet icons-contact.png
```

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

The set includes icons for Max controls that this add-on does not yet display.
No new controls or tool behavior are introduced. The existing quad menus have
no built-in icon arguments to replace. Material previews remain live Blender
previews. Blender's native material preview-type, viewport shading and overlay
buttons retain their built-in enum icons.
