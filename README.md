# NotuoDesk 3ds Maxxed

A Blender add-on (Blender 4.2+, tested on 5.2.3 LTS) that makes Blender look and work like Autodesk 3ds Max. It's aimed at people who know both apps.

![3ds Max layout in Blender: quad viewports, Command Panel, Editable Poly](docs/quad-editpoly.png)

![Animated Melt modifier at frame 60](docs/melt-animation.png)

## Install

1. In Blender, open **Edit › Preferences › Get Extensions**, click the **⌄** menu (top right), then **Install from Disk…**
2. Pick `notuodesk_3ds_maxxed-1.8.0.zip` (download it from this repo's **Releases** page).
3. On first enable, the add-on applies the 3ds Max theme and adds a **3ds Max** workspace with one viewport, then switches you to it. Alt+W toggles the optional four-view layout.

To reset a rearranged layout, choose **Customize › Apply 3ds Max Look**. It rebuilds the "3ds Max" workspace from scratch.

To go back to normal Blender, choose **Customize › Restore Blender Look**, or turn the add-on off. Turning it off removes every hotkey and menu change. The theme stays as it is until you restore it.

## What you get

The 3ds Max workspace hides Blender's 3D cursor in every viewport, including new viewports and saved layouts. It keeps the active scene's cursor at the world origin. Shift+right-click cannot place or drag it. Shapes, helpers, lights, cameras and V-Ray objects start at the origin without reading the cursor. Primitive mouse creation still uses the point you click on the construction grid.

Mode feedback follows the current tool and selection level. Select Object and Move, Rotate, Scale and Select and Link press their Main Toolbar buttons. The expanded Editable Poly stack marks the active level in yellow and puts its icon beside the base entry. The Selection rollout and quad menu show the same level. Border and Element remain distinct after Undo, Redo and saving and reopening the file. Click the active level, the base entry, press 6 or Ctrl+B to return to Object. Switching Command Panel tabs also leaves sub-object mode. Move, Rotate and Scale stay active when changing mesh levels. In quad view, the feedback cursor appears only in the viewport under the mouse.

Selected objects have white edged faces and white wireframe selection. Press J for optional white selection brackets in shaded views. Brackets start off, as in Max 2026. Sub-object mode removes the object brackets and uses red vertices, edges or polygons with blue unselected vertices. The status bar shows the selection count and a prompt for the current tool. Hovering a selectable object changes the cursor. Select and Link stays active while you drag children onto a parent, with a dashed link line.

| 3ds Max | In Blender |
|---|---|
| Menu bar: File, Edit, Tools, Group, Views, Create, Modifiers, Animation, Graph Editors, Rendering, Customize, Scripting, Help | Replaces Blender's top menus. Blender's own menus are still there as sub-menus |
| Workspaces dropdown | Top right, replaces the workspace tabs |
| Main Toolbar | Viewport header: undo/redo, link/unlink, select by name, region select, move/rotate/scale, reference coordinate system, pivot, snaps, mirror, align, editors, render |
| Scene Explorer | Outliner on the left |
| One viewport, optional Top, Front, Left and Perspective quads | Alt+W toggles quad view. Clickable `[+] [Top] [Standard] [Edged Faces]` labels, like Max:<br>**[+]** maximize, grid, ViewCube, statistics<br>**[Perspective]** Top / Front / Left… and your cameras<br>**[Standard]** High Quality / Standard / Performance, shadows and AO<br>**[Default Shading]** Default Shading, Shaded Materials with Maps, Flat Color, Clay, Wireframe Override, Realistic, ActiveShade, Edged Faces, See-Through |
| ViewCube | Shaded, labelled cube in each viewport of the 3ds Max workspace, with a compass and Home. Click faces, edges or corners, drag to orbit, or drag the compass to turn around the vertical axis. Right-click for Home, projection, Front and configuration. Orthographic face views have adjacent-view and roll arrows |
| Command Panel: Create, Modify, Hierarchy, Motion, Display, Utilities | Right sidebar with collapsible rollouts |
| Click-drag creation (base first, then height) | Box, Cone, Sphere, GeoSphere, Cylinder, Tube, Torus, Pyramid, Plane. Right-click stops creating |
| Keyboard Entry and Creation Method | Type grid coordinates and dimensions, then click Create. Choose Edge / Center, Cube / Box, Base/Apex / Center or Rectangle / Square for mouse creation |
| Parametric primitives | Box and the other primitives keep live **Parameters** until you explicitly convert to Editable Poly. Keys 1-5 and Tab leave an unconverted primitive at Object level |
| Modifier List and stack | About 60 modifiers under their Max names (see below). Newest is on top, with a visibility toggle per modifier |
| Editable Poly | Selection, Edit Vertices/Edges/Borders/Polygons/Elements and Edit Geometry rollouts |
| Cut and SwiftLoop | Hover previews and click-to-commit cuts and loops. Right-click ends the tool |
| Quad menus | Right-click (display / tools / transform) and Ctrl+right-click (modeling) |
| xView | Views and viewport-label menus, green mesh highlights, result counts and Select Results |
| Status bar | "1 Object Selected", X/Y/Z type-in, Grid, Auto Key, Set Key |
| Look | Max dark UI, cyan selection outline, red sub-object selection, blue vertices, random object colors, names like Box001 |

The icon family follows the visual ideas in Autodesk's 3ds Max 2026 Help.
Move is a four-way arrow, Modify is a curved segment in a control cage, snaps
use a numeral and magnet, and sub-object buttons highlight part of a small mesh.
The 336 original GPL SVGs have transparent 32px and 64px renders. Toolbar and
Command Panel buttons use icons where Max does. Create, Editable Poly commands,
viewport labels and Auto Key retain text. Hover a tool for its name and assigned
shortcut. Artwork references and field mappings are in `icons/README.md`
inside the add-on package.

The caddy pictograms follow each field's Max 2026 symbol. Height uses a rectangle
and height bar. Bridge uses a tapered prism, flared bell and numbered hourglasses.
Its pick buttons have flat polygon grids and round pick cursors. Mode icons change
with the choice. MeshSmooth's separation pills show their smoothing and material icons.
The drawings use original SVG paths and shaded faces.
Value pills have rounded ends, the title has a drag grip, and the round footer
buttons have one disc each. Missing field artwork falls back to the generic set.
The caddies use the measured Max control sizes and row breaks. At 100% scale,
pills are 22 pixels high with 7-pixel gaps. Bridge is 155 pixels wide. The footer
buttons are 22 pixels across on 29-pixel centres. Titles and values use Tahoma
when Windows supplies it. Other systems use Blender's font.

## Creating primitives from the keyboard

In **Create > Geometry > Standard Primitives**, pick a primitive and open **Keyboard Entry**. Enter X, Y, Z and its dimensions, then click **Create**. X, Y and Z follow the active viewport's construction grid. For Box, Cone, Cylinder, Tube and Pyramid they place the centre of the base. For Sphere, GeoSphere, Torus and Plane they place the centre.

The rollout starts closed. Each type keeps its own values between creations and when you save the scene. New objects keep editable parameters and the default segment counts. **Creation Method** controls mouse creation only. GeoSphere calls its diameter method **Diameter**, as Max does. **Cube** creates equal sides in one drag.

Tube accepts its radii in either order. Set the inner radius to zero for a solid cylinder that keeps editable Tube parameters. Equal Tube radii and a zero Torus Radius 2 are rejected before creating an object. Cone accepts either end radius at zero. A Torus with Radius 1 at zero becomes a sphere. Horn and spindle tori keep their touching or intersecting shape without collapsed edges at the axis.

The Create rollouts follow Max's order: Object Type, Name and Color, Creation Method, Keyboard Entry, Parameters. Creation Method uses a row of radio buttons. Keyboard Entry has compact labelled spinners, with coordinates above dimensions and a full-width Create button. Numbers use the scene's display units.
## PlanePlus reference images

Choose **Create > Geometry > JokerMartini > PlanePlus** and click-drag in a viewport. Right-click stops creating. Hold Ctrl for a vertical plane, Shift for a square, or Alt to put the pivot at [0,0,0].

Creation follows the viewport's construction grid. Front and Right views keep the plane facing the view, including with Ctrl held. Copy clones keep their own image and opacity settings when edited.

In **Parameters**, pick an image. Width and Length fit its aspect ratio. **Uniform** locks the proportions while you resize. Choose Left, Center or Right for the pivot, or use **More** for the other corners and edge centers. Horizontal and Vertical change the plane's orientation. **Enable Image** hides or shows the bitmap, and **Opacity** controls its transparency.

The image stays unlit in the default Solid viewport. An image draw handler supplies the viewport display, including opacity. A UV-mapped emission material supplies the rendered surface. Width, Length and the other parameters stay editable in Create and Modify until you convert to Editable Poly.

**Freeze** keeps the image visible and locks selection and snapping. PlanePlus starts with **Show Frozen in Gray** off. Other objects start with it on. Change it in **Object Properties** or **Display > Display Properties**. **Display > Freeze** and the right-click Display quadrant also have Freeze Selection, Unfreeze All, Unfreeze by Name and Unfreeze by Hit. Right-click leaves Unfreeze by Hit.

Parameter edits to gray-frozen primitives survive unfreezing. Unfreeze by Hit uses Blender's viewport picking for mesh surfaces, wire edges, curves, helper display lines and light/camera icons. It keeps the previous selection, active object and unrelated selection locks.
The Command Panel tabs, Create categories, sub-object levels, modifier stack and
Main Toolbar use original Max-style icons. The Material Editor control icons and
Create-menu object icons use the same set. Missing artwork falls back to Blender's
icons. The set includes artwork for all 11 supported Extended Primitives.
Material sample slots still show their real material previews.

## Shift-drag cloning

With Move (W), Rotate (E) or Scale (R) active, hold Shift and drag a gizmo handle or the selected geometry. The original stays put. Release to open **Clone Options** with **Copy**, **Instance**, **Reference**, **Number of Copies** and **Name**. Extra copies repeat the same move, rotation or scale. The dialog remembers your choices during the Blender session.

**Copy** gives each clone its own mesh. **Instance** shares the mesh. **Reference** shares the mesh and keeps a separate modifier stack. The **Controller** choices become available when the selection includes a parent and its child. Copy duplicates animation actions. Instance links child transform channels to the original with drivers.

In Editable Poly, Shift-drag extends open **Edges** and **Borders** without a dialog. **Vertex**, **Polygon** and **Element** selections open **Clone Part of Mesh**. Choose **Clone To Object**, with a name, or **Clone To Element**. Right-click or Esc cancels a drag. Cancel in either dialog removes the preview. Undo removes the whole clone operation. Ctrl+V still clones in place.

Only meshes with selected geometry contribute clones in multi-object Edit Mode. Undo, leaving Edit Mode, deleting a source or preview, and disabling the add-on cancel interrupted clones safely. The release dialogs open after the drag operator has finished.

## Editable Poly

The Modify tab has Max's Selection, Soft Selection, Edit Vertices, Edit Edges,
Edit Borders, Edit Polygons, Edit Elements and Edit Geometry rollouts. Material
IDs, the 32 Smoothing Groups and Vertex Colors appear at Polygon and Element
levels. Subdivision Surface, Subdivision Displacement and Paint Deformation are
available at every level. Unmapped controls remain visible and disabled. Adding
Edit Poly still edits the base mesh.

The small settings button beside an operation opens a floating viewport caddy
for Extrude, Chamfer, Connect, Bevel, Inset, Outline, Bridge, Weld, Tessellate,
MSmooth and Relax. Shift-click the main button to open its caddy too, except
Outline. Drag a spinner's icon vertically or click its value and type. Changes
preview from the original mesh, so adjusting an amount never repeats the operation.
Choice arrows open dropdowns. Drag the title to move the caddy.
Select another part of the mesh while the caddy stays open. It removes the
temporary preview before selecting, then previews once on the new selection.
Sub-object keys rebuild the controls for the new level. A level key that leaves
sub-object mode cancels the current preview. Ctrl+A, Ctrl+D and Ctrl+I select
all, none and inverse.

The bottom buttons are OK, Apply and Continue, and Cancel. Enter accepts. Ctrl+Enter
applies and previews another iteration. Right-click or Esc cancels the current
preview and keeps earlier Apply and Continue operations. Each accepted operation
has one undo step. While typing, Enter accepts the number and leaves the caddy open.
Ctrl+Z restores the previous completed value edit. Ctrl+Shift+Z redoes it.
Arrow keys, Home, End, Delete, Shift selection and clipboard shortcuts work in
numeric fields. Right-click an idle spinner's arrows to reset its value.
Right-click during a drag restores the starting value. Right-click elsewhere cancels.
The main button reuses the accepted values for that operation and sub-object
level. Values live in the scene and are saved in the blend file. Detach, Create
Shape and Slice Plane keep their separate dialogs.

Fresh caddy distances use one Max world unit per Blender unit. This is a numeric
mapping, without assuming meters or inches. Extrude and Bevel heights start at
10, Bevel and Outline amounts at -1, Chamfer and Inset at 1, and Weld at 0.1.
Extrusion Base Width shows 3 but remains disabled. Relax starts with one iteration.
Stored values take priority over fresh defaults. Tessellate has its own signed
Tension, starting at zero for flat subdivision. Negative values pull new vertices
inward and positive values push them outward. Chamfer Tension stays separate.

Chamfer has the 2026 Mitering choices, Depth or Tension, End Bias, Radial Bias,
Open, Invert Open and smoothing controls. Uniform is the fresh miter default.
Depth starts at 0.5, End Bias at 0.5, Radial Bias at 0, and Smooth at 30 degrees
for the entire object. The bevel uses Blender's offset or width mode, profile,
outer and inner miters, normal hardening and overlap clamp. Open and Invert
keep complementary sets of faces. Every change previews from the original mesh.
Bridge Smooth displays radians, as in the Max caddy. Its stored degree values
stay compatible with existing files.

Material IDs use Blender's material slots, numbered from 1. Smoothing groups use
the face attribute `max_smoothing_group`, including group 32. Faces that share a
group have smooth common edges. Other edges become sharp. Auto Smooth assigns
groups by face angle. Crease writes Blender's native vertex or edge crease.
Use NURMS Subdivision adds a native Subdivision Surface modifier. Smooth Result
backs up and restores face shading, as TurboSmooth does.

Ring and Loop have shift arrows. At Border level, Select Open Edges finds the
mesh boundaries. Quad Cap and Loop Regularizer appear when their companion
operators are installed. Disabled controls explain the Blender limitation in
their tooltip.

Target Weld works from the panel and quad menu at Vertex, Edge and Border levels.
Start with one selected source, or click a source in the viewport. Move without
holding a button, then click a valid target. The dashed line follows the mouse
and an outlined pick cross appears over valid targets. Target Weld draws its
own pointer while it owns the viewport. The normal pick arrow returns away
from targets, and the system pointer returns outside the viewport. Vertices must
share an edge. Edges
must each have one polygon attached, and the weld must preserve valid topology.
The source moves onto the target's exact position. Keep welding until you
right-click in the viewport or click Target Weld again. Invalid targets explain
the restriction in the status bar.

Ctrl+Shift+W starts Target Weld. Undo, Redo and file load end it before Blender
replaces the edit mesh. Each weld has one undo step. Right-click and disabling
the add-on remove its viewport line and active state.

QuickSlice uses two clicks. Click the start, move without holding a button,
then click the endpoint. Keep slicing until right-click or click QuickSlice
again. Polygon and Element levels affect selected visible polygons and retain
the new polygons in the selection. Split uses the Slice Plane setting.
Object-level QuickSlice affects the object and returns to Object level on exit.
Cut also works at Object level. The panel and quad menu call `max.cut`.
Alt+C starts the same tool. Right-click ends the chain, then right-click again
to leave Cut and return to Object level.

Imported `.hsx` settings shortcuts use the same caddies and stored values as
the panel. When the import module is present, its settings registration uses
the compatibility adapter without changing imported assignments or storage.

Delete Isolated Vertices is a checkbox, on by default. Delete and Remove clean
up vertices that have no polygons when it is on. Remove Isolated Vertices at
Vertex level remains a separate command. Slice at Polygon and Element levels
cuts only selected, visible polygons. By Polygon Extrude keeps the new tops
selected. Smoothing Groups has its own Clear Selection checkbox.

Headless checks run with an isolated Blender profile:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/test_editable_poly_panel.py
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/test_editable_poly_rework.py
```

Set `BLENDER_USER_SCRIPTS`, `BLENDER_USER_CONFIG` and `BLENDER_USER_EXTENSIONS`
to your test profile first. Its scripts/addons directory must contain this add-on.

## Compact Material Editor (M)

<img src="docs/material-editor.png" width="207" align="right" alt="Compact Material Editor">

Press **M**, or choose **Rendering › Material Editor**. It opens as a narrow floating window, like 3ds Max's Compact Material Editor.

- **Sample slots:** 6, 15 or 24 slots, or **All**, chosen under Options. A dot marks materials that are used in the scene. **+ New Slot** adds more slots, with no 24-slot limit. **Utils › Get All Scene Materials** loads every material used in the scene, adding slots as needed.
- **Drag and drop:** click a slot's hand icon, or **Drag**, then click an object in any viewport.
  - **Plain click:** replaces the object's material, as in Max.
  - **Object is part of a selection:** assigns to every selected object.
  - **Edit Mode:** assigns to the selected faces.
  - **Ctrl+click:** replaces only the material on the part you clicked.
  - **Shift+click:** keeps dropping. Right-click or Esc to stop.
  - *Blender doesn't let add-on buttons start a true mouse drag, so it works as pick-up-and-click.*
- **Side toolbar:** preview type (sphere, cube, flat, cloth…), **Select by Material**, and options.
- **Bottom toolbar:** Get Material, **Assign Material to Selection**, Reset Map/Mtl to Default Settings, Make Material Copy, **Put to Library** (Asset Browser), Material ID Channel, and Show Shaded Material in Viewport.
- **Pick Material from Object:** an eyedropper. Click any object, or one face of a multi-material object.
- **Material type:** Standard, VRayMtl or Physical.
- **Rollouts:**
  - **Shader Basic Parameters:** Blinn, Phong, Metal, Anisotropic, Oren-Nayar-Blinn, Translucent and Multi-Layer, plus Wire, 2-Sided and Faceted.
  - **Blinn Basic Parameters:** Ambient (locked), Diffuse, Specular, Self-Illumination, Opacity, Specular Level, Glossiness and Soften.
  - **Extended Parameters.**
  - **Maps:** per-channel on/off and a bitmap button for Diffuse, Specular, Glossiness, Self-Illum, Opacity, Bump (with amount), Reflection, Refraction and Displacement.
- **New materials** start with 3ds Max's defaults: grey 150, Specular Level 0, Glossiness 10.
- **Real materials:** every value drives the material's Principled BSDF directly, so it renders the same in EEVEE, Cycles, and V-Ray (after conversion).
- **Slate view:** the node canvas behind the panel acts as the Slate editor and shows the active slot's material.

<br clear="right">

## Extended Primitives

Choose **Create > Geometry > Extended Primitives** in the Command Panel. It has Hedra, ChamferBox, OilTank, Spindle, Gengon, Prism, Torus Knot, ChamferCyl, Capsule, L-Ext and C-Ext.

Drag the footprint, release, then click to set height. ChamferBox, ChamferCyl and Gengon have a final Fillet step. OilTank and Spindle finish with Cap Height. L-Ext and C-Ext finish with wall width. Hedra needs only the radius drag. Torus Knot uses its second step for Cross Section Radius. Prism starts with an isosceles triangle. The tool stays active for the next object until you right-click.

The objects keep their parameters in **Create > Parameters** and **Modify > Parameters**, including segment counts, Smooth and Generate Mapping Coords. Use **Convert To > Convert to Editable Poly** in the quad menu or the base stack entry's right-click menu to bake the object. Nathan.hsx maps Ctrl+Alt+E to the same conversion. OilTank, Spindle and Capsule have Overall/Centers height options. Torus Knot has Knot/Circle base curves, winding numbers, warp, eccentricity, twist and lumps.

Object Type follows Max's button order. Parameters use compact labelled fields. Prism limits impossible side lengths to a valid triangle and shows the corrected lengths in Parameters.

Parameter names and segment defaults follow [Autodesk's Extended Primitives reference](https://help.autodesk.com/cloudhelp/2015/ENU/3DSMax/files/GUID-BF868DCF-12E3-431C-A73B-C16C0FD67C98.htm). Types whose Max constructor starts with zero dimensions start at one Blender unit here. ChamferBox, Capsule, Hedra and Prism keep their documented nonzero dimensions. Click-drag creation replaces these dimensions with the size you draw.

## Symmetry

Choose **Modifier List > Symmetry** in the Modify panel. Its Parameters rollout has **Planar** and **Radial** types. Planar supports X, Y and Z together, with Flip per axis. Radial repeats a segment around X, Y or Z, with **Count**, **Mirror Symmetry** and **Flip**. Mirror Symmetry reflects half of each segment so its adjacent boundaries match. Slice Along Mirror and Weld Seam start on. Both Threshold fields start at **0.01 object-space Blender units**, matching Autodesk's 2026 rollout image. Use Proximity Weld starts off. No physical unit conversion is applied.

Expand Symmetry in the stack and click **Mirror**. Press **W** to move or **E** to rotate its yellow mirror plane with the viewport gizmo. Click Symmetry or Editable Poly to return to the mesh. The original mesh stays editable at Vertex, Edge, Border, Polygon and Element levels, with the symmetric result visible. Align to Face picks a surface point and normal. Pick Object copies a reference object's current transform. Reset Gizmo restores the object's local origin and axes. Right-click cancels picking.

Saved Geometry Nodes supply the geometry. Exact Boolean cuts mark seam boundaries, remove construction caps and reflect or rotate the segment. Default welding joins the marked boundaries. Proximity welding also accepts nearby vertices in the seam band, without merging thin faces elsewhere on the source. Each Symmetry has an independent, parented centre helper in the hidden-from-render `.3ds Maxxed Symmetry` collection. Helpers stay hidden and unselectable except while editing Mirror. A lost helper recovers from the saved plane record. Removing, applying or converting the modifier removes its helper. Convert to Editable Poly also works from Mirror level. Save/reload and undo retain the centre and parameters. Disabling the add-on keeps its native scene dependencies and evaluated geometry. Re-enabling restores the UI without making duplicate helpers. Older Symmetry scenes upgrade while retaining their plane and proximity weld setting.

Reference: [Autodesk 3ds Max 2026 Symmetry](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Modifiers/files/GUID-EB0B7B9B-117D-4CC3-A966-A3E007E0C68A.htm).

Cut welding adjusts its numerical tolerance to the coordinates in the Mirror frame, up to the Weld Threshold. It still selects only marked seam vertices. Geometry wholly inside a retained half-space skips the Boolean cut, so editing an open segment does not repeatedly intersect it with a solid cutter. Moving geometry across the plane uses the cut again. Saved node graphs upgrade with their centre and parameters intact.

## Poly tools and pivots

- **Quad Cap:** in Edit Poly at Border level, next to Cap, or in the modeling quad menu. Select the border edges or just one edge of a hole. It fills each selected hole with a quad grid and chooses the grid corners from the border angles. An odd edge count uses triangles and quads, with a warning.
- **Edge Loop Regularizer:** in Edit Sub-Object at Edge or Border level, or in the modeling quad menu. The default is **Circle**, like rapidTools' round-loop command. It handles separate loops and open arcs together. The redo panel has **Even Spacing** along the existing polyline and **Strength**. Even Spacing keeps open endpoints fixed. Circle fits a plane and circle, then spaces vertices by angle. Straight chains use Even Spacing.
- **Auto Pivot on Create:** choose **Off**, **Bottom** or **Center** in the add-on preferences. Off is the default. It runs when you finish an add-on standard or extended primitive, Keyboard Entry creation, or spline, including Line and Text. Bottom uses the bottom center of the world bounding box. Center uses its center. Lights, cameras, helpers, imports, duplicates and Blender's own Add menu keep their usual pivots. **Hierarchy > Adjust Pivot** also has **Pivot to Bottom** and **Pivot to Center** for selected meshes and splines. Primitive parameter edits retain the pivot offset, without recentering after each edit.

These tools follow the public descriptions of [rapidTools](https://rapidmxs.com/store/rapidtools/) and [AutoPivot](https://www.scriptspot.com/3ds-max/scripts/autopivot). The original scripts do not run inside Blender.

Creation tools call `poly_tools.finalize_new_object(context, ob)` after setting the final geometry and transform, before recording creation undo. Standard and extended primitives, Keyboard Entry, Shapes, finished Lines and Loft share this function. Loft keeps its live skin through an origin-compensation modifier. It never runs during previews.

PlanePlus keeps its own Pivot setting and bypasses Auto Pivot on Create.
## xView

Choose **Views > xView**, **[+] > xView** or **[Standard] > xView**. One check runs at a time. **Show Statistics (7)** stays independent.

xView checks Face Orientation, Overlapping Faces, Open Edges, Multiple Edges, Isolated Vertices, Overlapping Vertices, T-Vertices, Missing UVW Coordinates, Flipped UVW Faces and Overlapped UVW Faces. Green points, lines or faces mark the results in Object mode and Edit Poly. Selected sub-objects keep their normal selection colour.

Click the centred, bracketed viewport result to open the menu. **Select Results** enters the matching Edit Poly level and selects the flagged elements. **Hide** turns off the check. **Click Here To Configure** opens the Tolerance dialog for overlapping vertices or overlapping faces. With Auto Update off, **Click Here To Update** refreshes without changing mode or selection.

**Selected Only**, **See-Through** and **Auto Update** start on. **Display On Top** starts off. Overlapping Vertices and Overlapping Faces each store their own tolerance, initially **0.01 Blender world units**. This maps one Blender world unit to one Max system unit, without assigning a physical unit. The default comes from Autodesk's 2026 SDK.

Checks run in cancellable timer jobs with an 8 ms work budget. The previous result stays visible with an Updating message while a checked mesh changes. New results can appear in pieces. Results belong to their scene and view layer. Unrelated object edits do not rerun the check.

## Opening 3ds Max files

![A 3ds Max 2015 character opened with File › Open 3ds Max File](docs/open-max-file.png)

`.max` is a closed Autodesk format. 3ds Maxxed reads it through the open-source [Import Autodesk MAX (.max)](https://extensions.blender.org/add-ons/io-scene-max/) extension (GPL, [source](https://github.com/nrgsille76/io_scene_max)). If it isn't installed, **File › Import › Install .max Reader…** installs it.

- **File › Open 3ds Max File…** opens the file into a new scene, so nothing in your current scene is overwritten.
- **File › Import › Merge 3ds Max File** adds a file's objects to the current scene. You can also drag a `.max` file onto the viewport.
- **System Units:** pick the unit the file was made in. The default is Inches, 3ds Max's US default. The reader ignores units, so without this setting scenes come in at the wrong scale.
- **Materials:** names are cleaned up (`04 - Default` instead of `04___Default_C:\Users\…\pipe_bowl`), and the materials can be edited in **Modify › Material** using V-Ray parameter names.
- **Hierarchy and smoothing:** unit conversion scales the imported hierarchy once. With reader 1.9.2, matching source face masks become smooth faces and sharp edges. Original masks stay in the mesh's `max_smoothing_group` face attribute. Unsupported source nodes produce a warning.
- **Textures:** bitmaps are searched for next to the `.max` file and in its subfolders, in any image format. Missing files are listed like Max's *Missing External Files*. Point **File › External Data › Relink 3ds Max Textures…** at the folder where they are. It also repairs missing image files in FBX materials and matches renamed copies like `Name (1).png`. To pick a file for one material directly, use **Modify › Material › Load Bitmap…**.

**What the reader supports:** meshes (Editable Poly/Mesh), primitives, UVs, Standard / Physical / V-Ray / Corona materials, and helpers. It handles uncompressed files from any version, and compressed files up to 3ds Max 2023. **Not supported:** animation, complete modifier results (the base mesh can differ from the evaluated scene), splines, lights, cameras and rigs.

**For full scenes, use FBX:** run [`tools/max_to_blender.ms`](tools/max_to_blender.ms) inside 3ds Max (*Scripting › Run Script*). It exports the open scene, or a whole folder of `.max` files, to FBX. Then use **File › Import › FBX from 3ds Max** in Blender, which keeps animation, skinning, cameras and lights, and turns TurboSmooth into subdivision. *(I haven't been able to test the MAXScript, since 3ds Max isn't available here.)*

### Sending a scene back to 3ds Max

Choose **File › Export › 3ds Max Scene (FBX)...**. **Export Selected (3ds Max FBX)...** is in File, File › Export and Customize.

- **System Units:** shares the last `.max` import setting, initially Inches. FBX import remembers units from the file. Export writes the chosen units into FBX without changing the scene's scale. Both directions use Z-up coordinates, with FBX import reading the file's axis metadata.
- Export always applies modifiers and writes the viewport-evaluated geometry at the current frame, including the current pose. The earlier Keep Editable option was removed because it changed geometry and was not needed for FBX export to Max. Source meshes and modifiers stay editable in Blender. Hidden export objects and collections are temporarily enabled, then restored on success or failure.
- **Embed Media:** packs image files used by supported FBX materials into the FBX. Names, object origins, exported parent links, cameras and lights use Blender's native FBX exporter. **Animation** bakes transform animation over the scene frame range. Mesh deformation stays at the exported frame, with no skin binding or subdivision attributes.
- **Smoothing:** exports face smoothing groups where Blender supports them, or face smoothing and explicit normals on older versions. FBX material names stay unchanged.

Tested in Blender 5.0.1 with 17 copied `.max` scenes and a Max-exported FBX. The FBX round trip preserved names, transforms, scale, normals and smoothing. There is no Max-side validation yet. See [the interchange validation report](docs/max-interchange-validation.md) for the per-scene results and commands.
## Loft

Select a spline, then choose **Create > Geometry > Compound Objects > Loft**.
Use **Get Shape** with a selected path, or **Get Path** with a selected shape.
Click the other spline in a viewport. Right-click or Esc cancels picking.
Only single Poly or Bezier splines can be picked.

- **Instance** is the default. Point edits, source scale and spline modifier changes update the Loft. Path and profile deformers keep their stack order.
- **Copy** uses independent, hidden copies. **Move** hides the sources in the viewport and render.
- **Skin Parameters** has separate start/end caps, Shape Steps, Path Steps, Adaptive Path Steps, Contour, Banking and Flip Normals. Steps add points between the source vertices.
- **Surface Parameters** has Smooth Length and Smooth Width. Either one turns on smooth shading.
- **Path Parameters > Path %** sets the level for the next Get Shape. One profile fills the whole path. Get Shape replaces it. Adaptive Path Steps adds a division at that level.
- **Deformations** has linear start/end Scale percentages and Twist in degrees.

The Loft is a mesh with a Geometry Nodes modifier. Hidden spline copies evaluate the source modifiers without native bevel, extrusion or Line's rendering conversion. Object Info reads those modified splines and Curve to Mesh builds the skin. Source rendering stays unchanged. Get Shape creates it at the path. Get Path aligns the path's first tangent to the selected shape's local Z axis.

Mixed Geometry Nodes and native deformers work in either stack order. Loft converts curves to wire geometry before native deformers and restores curves before Geometry Nodes. Empty results, surface meshes and multiple splines show an error in the Loft rollout. Deleting a Loft removes its hidden helpers. Undo restores them, and removing the Loft from one scene preserves them while another scene still uses it.

## Modifiers

### TurboSmooth

![TurboSmooth on the Captain](docs/turbosmooth.png)

TurboSmooth is in the Modifier List, the quad menus (right-click and Ctrl+right-click) and the Command Panel. It uses 3ds Max's parameters:
- **Main:** Iterations (default 1), Render Iters, Isoline Display, Explicit Normals.
- **Surface Parameters:** Smooth Result, and Separate by **Materials** / **Smoothing Groups**. These keep material borders and sharp edges crisp by creasing them.
- **Update Options:** Always / When Rendering. When Rendering keeps the viewport light.

Underneath it's Blender's native Subdivision Surface, so it keeps GPU subdivision in the viewport.


**Built for this add-on** (Geometry Nodes, because Blender has no equivalent):
**Melt** (Amount, % of Melt Spread, Solidity with Ice/Glass/Jelly/Plastic presets, Irregularity, Drip Size, Seed, Flip Axis). Click **Animate Melt** to keyframe it from solid to puddle over a frame range, or key Amount yourself with Auto Key (N), the key button, or right-click › Insert Keyframe, **Skew**, **Squeeze**, **Slice**, **Noise**, **Push**, **Spherify**.

**FFD 2x2x2 / 3x3x3 / 4x4x4 / FFD Box** create an orange cage fitted to the object, with 3ds Max's FFD parameters:
- **Sub-Object:** **Control Points** (edit the cage), **Lattice** (move, rotate or scale it), **Back to Object**.
- **Set Number of Points:** L × W × H.
- **Display:** Lattice, In Front.
- **Deform:** **Only In Volume** / **All Vertices** with **Falloff**, plus Interpolation (B-Spline, Catmull-Rom, Cardinal, Linear) and Strength.
- **Control Points:** **Reset**, **Animate All** (keys every point), **Conform to Shape** (Inside / Outside Points, Offset).
- **Fit to Object** and **Update Volume.** Run Update Volume after moving the cage when using Only In Volume or Falloff.

**Modifier List:** type to search and press Enter. The list stays open until you choose. The ≡ button opens a compact menu of categories.

**Mapped to Blender's own modifiers:** Edit Poly, Symmetry, Mirror, Vertex Weld, ProOptimizer, Optimize, MultiRes, Turn to Mesh, Delete Mesh, Smooth, Edit Normals, Weighted Normals, Retopology, Quadify Mesh, TurboSmooth, MeshSmooth, OpenSubdiv, Tessellate, Subdivide, HSDS, Shell, Chamfer, Array, Boolean, ProBoolean, Lattice, Skin, Displace, Bend, Twist, Taper, Stretch, Relax, Smooth Deform, Wave, Ripple, Affect Region, Shrink Wrap, Conform, Path Deform, Skin Wrap, Skin Morph, Skin (bones), Linked XForm, UVW Map, Unwrap UVW, UVW XForm, Extrude, Lathe, Sweep, Cloth, Flex, Point Cache, Particle Flow, Hair and Fur, and Ocean.

## V-Ray

- **If Chaos V-Ray for Blender is installed** (there is a free Community Edition), it's detected automatically. **Rendering › V-Ray › Renderer: V-Ray** makes it the active renderer, and the same menu lists V-Ray's own tools.
- **Without V-Ray installed**, you still get the V-Ray workflow, rendered in Cycles:
  - **VRayMtl**: Default, Glossy Plastic, Brushed Metal, Chrome, Glass, Car Paint, VRayLightMtl. Edit it in Modify › Material using V-Ray parameter names (Diffuse, Reflect, Refl. Glossiness, Metalness, Fresnel IOR, Refract, Opacity, Coat, Self-Illumination).
  - **VRayLight**: Plane, Disc, Sphere, Dome (choose an HDRI), plus VRaySun with VRaySky, and VRayIES.
  - **VRayPhysicalCamera**: film gate, focal length, F-number, shutter speed and ISO drive scene exposure. f/8, 1/200 s and ISO 100 count as 0 EV.
  - **VRayPlane**: an effectively infinite ground plane.
  - **Quality presets** (Draft, Medium, High, Very High) use progressive sampling with a noise limit and the denoiser.
- These objects are standard Blender lights, cameras and Principled materials, so V-Ray for Blender's Cycles-to-V-Ray conversion can handle them. I couldn't test that conversion because V-Ray isn't installed on the test machine.

## Line splines

Choose **Create > Shapes > Splines > Line**, then click to place Corner vertices or drag for Bezier handles. **Creation Method** changes the click type (Corner or Smooth) and drag type (Corner, Smooth or Bezier). A preview segment follows the mouse.

Right-click finishes the current spline and leaves Line active for another. Right-click or Esc with no points exits. Click the first vertex and choose **Yes** in **Close spline?** to close it. Cancel continues drawing. Backspace removes the last point. Hold Shift for horizontal or vertical segments on the construction plane. S toggles grid snapping.

**Keyboard Entry** adds points at world X, Y and Z coordinates. **Add Point** continues the current Line, **Close** joins its ends and **Finish** leaves it open. Both need at least two points.

Line's **Creation Method** and **Keyboard Entry** appear only while Line is the chosen Shapes creator. Choosing another shape or switching to Geometry hides them, even with a Line selected. Creation Method uses circle radio buttons. Keyboard Entry, Rendering and Interpolation use compact labelled spinners.

Spline objects have **Rendering** and **Interpolation** rollouts in Create and Modify. Radial Thickness is the diameter. Sides and Angle control the radial cross-section. Enable In Renderer and Enable In Viewport work independently. Blender curves keep the editable vertices, with a Geometry Nodes modifier for the radial mesh. Steps sets subdivisions between vertices. Optimize skips subdivisions on straight segments in the generated mesh.

## Snaps

S toggles positional snaps. The toolbar flyout chooses 2D, 2.5D or 3D. Grid Points is the initial snap type. Grid snapping is magnetic: points stay free outside the 20-pixel Snap Radius. Primitive bases and heights use the same rule, so they no longer jump in whole-unit increments.

W, E and R select the shared Max Move, Rotate and Scale gizmos. Move a box by its corner onto another corner, or move selected Editable Poly vertices onto unselected vertices in the same mesh or another object. Move and Scale retain their magnetic snap base. Rotate uses its Use Center setting and ignores positional snap targets. Snap markers and the rubber band are green during preview and yellow within Snap Radius. Marker Display and Size control the guides in screen pixels. Vertex uses the crosshair shown in Autodesk's viewport illustration. Grid Points uses the Snaps dialog box with a half diagonal to the top-right corner. The other types use their distinct Snaps dialog glyphs. Release commits. Right-click cancels the drag.

Right-click Snaps, Angle Snap or Percent Snap for **Grid and Snap Settings**. Its floating viewport dialog stays open while you edit outside it. Drag the title to move it, or use X to close it. Its Snaps, Options, Home Grid and User Grids tabs use Max's labels. The available targets are Grid Points, Pivot, Perpendicular on straight segments, Bounding Box, Vertex, Endpoint, Edge/Segment, Midpoint, Face, Center Face and Grid Lines. Unsupported settings are greyed out with reasons in tooltips. Snap settings live in the add-on preferences. Right-click Spinner Snap for the General > Spinners settings.

Shift+right-click opens the snap quad, including during a transform or primitive creation. Release the left button, choose an override, then press it again to resume the current drag. Standard chooses a one-shot override. None disables snaps for the next action, and Last repeats the previous override. Alt+S cycles through enabled snap types. The regular checkboxes return after the action. A controls Angle Snap, initially 5 degrees. Ctrl+Shift+P controls Percent Snap, initially 10 percent. Spinner Snap quantizes changed primitive parameter fields in the Command Panel. Grid Spacing and Major Lines map to Blender's grid overlay controls. 2D accepts geometry on the active construction plane and rejects off-plane targets.

## Rotate and transform gizmos

E selects Linear Roll rotation. Drag an axis ring along its tangent, at 0.5 degrees per pixel. The grey outer ring rotates in the screen plane. Drag inside the sphere for free rotation. A turns Angle Snap on or off, including during a drag. Its default increment is 5 degrees. Angle Snap works with S on or off and never pulls the rotation toward a vertex, edge, face or grid point. Percent Snap stays separate.

During an axis drag, a translucent slice shows the direction and amount of rotation. Its colour follows the axis, as in Autodesk's red X example. Complete turns overlap. The live X/Y/Z angle readout follows the stepped angle. The outer screen ring and readout keep Autodesk's proportions at each UI scale. Right-click or Esc restores the starting transform. A completed rotation uses one undo step. Shift-drag opens Clone Options or Clone Part of Mesh.

The transform toolbar offers View, Screen, World, Local, Parent, Grid, Working, Gimbal, Local Aligned and Pick reference systems. Pick accepts a viewport click or H and remembers four objects. Use Center is an icon flyout. Local disables it and uses individual pivots. F12 toggles a floating Rotate Transform Type-In window. Absolute fields and Offset fields update the viewport live. Offset fields reset to zero after each edit. Angle Snap does not round typed values.

Move has long cone arrowheads and connected plane corners. Move and Scale axes carry red, green and blue continuously from the centre. Hovered or locked shafts and labels turn yellow. Arrowheads and Scale point ends keep their axis colours. Move's centre box has a yellow outline. Scale's nested triangle edges carry each axis colour to the midpoint. Its active plane or uniform centre fills with translucent yellow. Only Rotate has a muted centre tripod, with colour on the locked axes. Rotate's rings retain their drawing. The Scale flyout also offers Non-Uniform Scale and Squash. Turn off Uniform 2-Axis Scaling in Gizmos Preferences to scale the two plane axes independently. Picking an axis or plane keeps that constraint for later drags on the selection. F5, F6 and F7 select X, Y and Z. F8 cycles XY, YZ and ZX. Max stores these locks separately for each transform and for Object and sub-object modes. With positional snaps on, Move respects the lock only when Use Axis Constraints in Snaps is on. Plus and minus change the shared gizmo size. X hides or shows all three.

Customize > Gizmos Preferences controls labels, multiple object gizmos, relative tool sizes, plane handles, the Rotate tripod, free rotation, screen handle, pie slice and angle data. Linear Roll remains the default. Circular Crank uses a circular drag and switches to Linear Roll for nearly edge-on rings. Legacy R4 offers axis-directed dragging. Constant keeps reference coordinates across tools. Disabling the add-on cancels live previews, including Shift clones and Edit Mesh changes.

## Hotkeys

| Keys | Action |
|---|---|
| Q / W / E / R | Select / Move / Rotate / Scale |
| MMB / Alt+MMB / Ctrl+Alt+MMB, wheel | Pan / Orbit / Zoom |
| Z / Ctrl+Shift+Z | Zoom Extents Selected / All |
| Alt+W | Maximize viewport toggle |
| T F L B K P U C | Top, Front, Left, Bottom, Back, Perspective, Orthographic, Camera |
| 1 2 3 4 5 (6) | Vertex, Edge, Border, Polygon, Element (exit) |
| H | Select From Scene |
| Ctrl+A / Ctrl+D / Ctrl+I | Select all / none / invert |
| Ctrl+click / Alt+click | Add to / remove from selection |
| F3 / F4 | Wireframe / Edged Faces |
| Alt+X / Alt+Q | See-Through / Isolate Selection |
| G / X / 7 | Grid / Gizmo / Statistics |
| S / A | Snaps / Angle Snap |
| Ctrl+Shift+P | Percent Snap |
| Shift+right-click / Alt+S | Snap quad / Cycle snap override |
| Alt+F3 | Use Axis Constraints in Snaps |
| F5 / F6 / F7 / F8 | X / Y / Z / Cycle plane constraint |
| + / - | Grow / shrink transform gizmos |
| N / K | Auto Key / Set Key |
| Ctrl+V / Ctrl+C | Clone / Camera from view |
| Shift+drag with W / E / R | Clone with Move / Rotate / Scale |
| M / 8 / F10 | Material Editor / Environment / Render Setup |
| Shift+Q / F9 | Render |
| F12 / Ctrl+X | Transform Type-In / Expert Mode |
| O | Adaptive Degradation (lighter viewport for heavy scenes) |
| Shift+E, Ctrl+Shift+E, Ctrl+Shift+C | Extrude, Connect, Chamfer |
| Alt+C / Alt+L / Alt+R | Cut / Loop / Ring |
| Alt+1 | SwiftLoop |
| Backspace / Ctrl+Backspace | Remove / Remove with vertices |
| Ctrl+PgUp / Ctrl+PgDn | Grow / Shrink |
| PgUp / PgDn | Select parent / child |
| , . Home End / | Previous/next frame, first/last frame, play |

You can switch each feature on or off (hotkeys, menu bar, toolbar, status bar, labels, random colors) under **Preferences › Add-ons › NotuoDesk 3ds Maxxed**.

## Cut and SwiftLoop

**Cut (Alt+C):** click a vertex, edge or polygon, then move the mouse and click to commit each segment. The cursor changes over vertices, edges and polygons. Right-click ends the current chain. Right-click again, or press Esc, to leave Cut. Each segment has its own Undo step. Cut works at object level and every sub-object level.

**SwiftLoop (Alt+1):** hover over an edge to preview the loop, then click once to insert it. Keep clicking for more loops. Right-click or Esc leaves the tool.

- **Shift+click:** insert a loop with surface flow.
- **Ctrl+click:** select a loop and enter Edge level.
- **Alt+drag:** slide a selected loop. **Ctrl+Alt+drag** also evens the distances from the bounding loop.
- **Ctrl+Shift+click:** remove a loop and its unused vertices.

The Edit Geometry buttons and quad menus use the same tools. No Enter or Q is needed to commit or leave them. The previous toolbar tool stays selected. Right-click during primitive creation cancels the unfinished primitive. Right-click again stops creating. Esc stops immediately.

Cut and SwiftLoop pick visible polygons behind hidden polygons. Cut keeps endpoint vertices on the picked edge or polygon, even when an unrelated vertex occupies the same position.

## Importing 3ds Max hotkeys

Use **Customize › Import 3ds Max Hotkeys (.hsx)...** to load your Max shortcuts. Imported assignments and unassignments override the add-on's default keys. They stay in the add-on preferences when you save preferences. The preferences show every imported entry and a **Clear Imported Hotkeys** button to restore the defaults. The import reports mapped assignments and lists unsupported actions.

Editable Poly settings shortcuts open the same floating caddies as the panel. Bridge uses **Segments**, starting at 1 with no intermediate ring. Chamfer reuses the panel's last accepted **Amount**, starting at 1. Edge and vertex Extrude settings move the new geometry along averaged adjacent surface normals. Tessellate offers **Edge** and **Face** types. Export Selected opens Blender's FBX exporter with **Selected Objects** on. rapidTools fastBridge and RappaTools3 Inset, Relax and MePoly use the add-on's Bridge, Inset, Relax and Convert to Editable Poly. rapidQCap and fastEdgeLoopRegularizer work when the add-on's Quad Cap and Loop Regularize operators are installed.
**ViewCube.** Alt+Ctrl+V shows or hides it. Alt+Ctrl+H returns Home, as in Max 2026. The chamfered cube has lit faces, bold labels mapped onto the faces, and a broad blue-grey compass band. Face views have inward-pointing adjacent-view arrows and curved roll arrows at the top right. Hover targets turn blue with a yellow outline. It starts smaller than Max's default, at 80% opacity when active and 50% when inactive. Preferences and right-click **Configure** offer Tiny, Small, Normal and Large sizes, inactive opacity up to 70%, Snap to Closest View and Keep Scene Upright. View changes use Blender's Smooth View duration. Set Current View as Home saves the rotation, projection, centre and distance in the scene. Set Current View as Front changes the cube's reference orientation, and Reset Front restores the default. Camera views hide the cube. Turning it off restores Blender's navigation gizmo.

Keep Scene Upright also controls clicked views. Turn it off to carry the current roll into an edge or corner view. Dark text and outlines use slightly higher opacity than the faces so they stay readable over bright viewports. Opening a saved file rebuilds the cube's drawing resources. Files keep each viewport's original navigation gizmo setting, so turning the ViewCube or add-on off after reopening restores that setting.

## Known differences from 3ds Max

- Target Weld uses an outlined selection cross drawn from Autodesk's published
  selection screenshot and an older recorded Target Weld session. The 2026
  Target Weld help supplies no cursor bitmap or pixel dimensions. Exact 2026
  cursor raster parity and rubber-band spacing remain unverified. The existing
  white 5-on/5-off band stays unchanged. [Cursor evidence](docs/target-weld-cursor-reference.md).

- Symmetry uses Blender's exact Boolean and mesh-merge operations. Cut-aware welding uses a coordinate-relative numerical tolerance, limited by Weld Threshold. This is not Autodesk's private vertex-tracking implementation. Unmatched radial boundaries can stay open with Mirror Symmetry off. Blender supplies the spinners and transform gizmos. A helper collection remains visible in the Outliner. Pick Object samples the reference transform once. Radial starts at Count 2, Z and Mirror Symmetry off. Autodesk's 2026 help states X as the general default axis but does not separately explain the switch to Radial. These Radial startup values remain unverified against Max.
- Blender does not expose Max's native cursor artwork or Nitrous selection-preview silhouette. The add-on draws transform/link cursor symbols and yellow hovered mesh edges. Blender draws the native blue selection outline and sub-object dots. Small antialias fringes can remain around the white wireframe overlay. Helper and un-bevelled spline Link targets use their projected origins because Blender's scene ray cast has no pick surface there.
- Blender themes colour list selections globally. The yellow stack-level selection uses that shared list colour. The base entry and toolbar buttons use blue. Symmetry Mirror uses its helper state for the stack, selection count and transform prompt. Edit Poly edits the base mesh.

- Shapes, helpers, lights, cameras and V-Ray objects use the world origin instead of interactive placement. Target lights and cameras keep a preset target offset.
- The cursor policy checks new viewports and scene switches every 0.2 seconds. Other workspaces keep their cursor display settings. A scene shared with the 3ds Max workspace shares its cursor location too.

- Cut adds supporting triangles for endpoints inside a polygon. Concave polygons are triangulated before an interior endpoint is added.
- Cut uses three Blender cursor shapes instead of Max's cursor artwork. Its Undo groups one committed segment per step. Max's exact Undo grouping has not been confirmed.
- SwiftLoop follows quad rings and stops at triangles, n-gons and hidden faces. Shift uses cubic interpolation of surface normals, so its flow can differ from Max's proprietary result. Sliding needs a regular loop with two bounding edges at each vertex.
- Imported hotkeys call Blender equivalents. Relax uses vertex smoothing, including Paint Deform Relax. Edit Poly enters mesh editing through the add-on's existing Edit Poly command. Unassignments affect only this add-on's keys. Unknown actions stay in the imported list but get no binding.
- Caddies keep unavailable Max controls visible and disabled. BMesh bevel has no End Bias or spherical Radial Bias parameter. Chamfer maps the five miter names to Blender's offset/width, grid/cutoff and sharp/arc/patch bevel choices. Corner topology can differ from Max's solver. Bridge Edges shows disabled Bridge Adjacent and Reverse Triangulation because `bridge_edge_loops` has neither parameter. Extrusion Base Width, Local Normal Bias, Connect Pinch/Slide and MeshSmooth's adaptive separation rules remain disabled. Vertex extrusion adds connected vertices and edges, rather than Max's polygon base. Surface normals use equal-weight averages in mesh space, with local Z when no face supplies a normal. Distances use one Max world unit per Blender unit. BLF draws grayscale font edges instead of Windows ClearType subpixel text. Autodesk's Outline topic supplies no caddy image, so its measured visual parity remains unverified.
- Extended Primitives do not include RingWave or Hose. Creation uses the default Corners, Center or Isosceles method. Alternate creation methods and Slice controls are not included.
- Hedra uses reflection-generated polyhedra. Star1, Star2 and axis scaling approximate Max's shapes. Its facet topology and the other primitives' triangulation can differ from Max. OilTank and Spindle use Blender's bevel for Blend.
- Generate Mapping Coords on Extended Primitives uses box projection. It does not reproduce Max's UV layouts. Torus Knot uses whole-number winding, twist, warp and lump counts, and Smooth is an on/off setting. Real-World Map Size and mapping offset/tiling controls are not included.
- Line uses Blender's automatic handles for Smooth vertices, so its curvature can differ from Max. The close prompt uses Blender's Cancel button to keep drawing.
- Spline Adaptive uses a fixed 64 subdivisions per curved segment. Blender does not expose Max's curvature-based adaptive interpolation.

- Quad Cap uses an interpolated grid. It does not reproduce rapidQCap's surface smoothing. Borders too concave or twisted for a grid without folded cells are skipped with a warning. Odd borders cannot be all quads without changing the boundary.
- AutoPivot's original buttons use center-of-mass calculations for meshes and vertex averages for splines. This add-on uses the bounding box and adds an optional creation preference. Moving an origin can change modifiers that depend on that origin, such as Mirror.
- Text stays editable after a pivot move. A protected Geometry Nodes translation handles depth on tilted text. It stays below user modifiers and outside the Max stack, so stack controls cannot disable, remove or reorder it. Conversion to Editable Spline or Editable Poly bakes the translation. Existing Text Pivot Offset modifiers migrate when a file loads or the add-on is enabled.
- The icons are original GPL artwork with Max's visual vocabulary, not Autodesk's icon artwork. Icons are supplied for toolbar and stack controls that this version does not draw, including Pin Stack, Show End Result, Configure Modifier Sets, Bind to Space Warp, Window/Crossing, Spinner Snap, Layer Explorer and Ribbon. This does not add those controls. The modifier's edit-mode toggle has a mesh-and-pencil icon. The Modifier List menu has a list-and-dropdown icon. Blender still draws its own material preview-type buttons and viewport shading and overlay buttons.
- `.max` import is partial. The reader does not import lights, cameras, splines, animation or complete modifier stacks. Source units still need to be chosen. Smoothing recovery uses reader 1.9.2's parsed face data and requires matching topology. Missing textures need the original bitmap files.
- FBX export bakes viewport geometry at the current frame. It does not export editable modifier stacks, subdivision attributes, shape-key animation or skin deformation. Parent-relative shear is baked into mesh vertices and normals to preserve the exported shape, so local mesh coordinates can change. Blender 5.0.1's bundled FBX light importer also fails with Cycles enabled because it references a removed light property. Export still writes lights.
- Loft supports one profile on one Poly or Bezier spline path. NURBS, Text, multiple-spline shapes, and several profiles along a path are not supported. Spline deformers affect the skin, while native bevel, extrusion and Line's rendering conversion do not.
- Loft uses Blender's minimum-twist and Z-up frames for Banking, which can differ from Max. Smooth Length and Smooth Width share Blender's face smoothing. Caps use n-gons rather than Morph or Grid capping.
- Loft Scale and Twist are linear parameters, without Max's deformation graph. Teeter, Bevel and Fit deformations are not implemented. Adaptive Path Steps adds the shape level, without Max's deformation-graph divisions. Loft placement uses the selected spline's initial location and rotation, while source point edits and scale stay live.

- xView checks the evaluated modifier result in Object Mode and the editable cage in Edit Poly, using the active UV map. Select Results is unavailable in Object Mode when a viewport modifier is enabled, because evaluated indices may not identify base-mesh elements. Enter Edit Poly to check and select the cage. Cross-object coincidences are not checked.
- T-Vertices requires three incident edges with faces on both sides, as in Autodesk's 2026 SDK. It has no Tolerance dialog or unwelded near-edge extension. Overlapping Faces also finds edge-only crossings that Max's documented check misses.
- Large xView checks finish over multiple timer ticks. Edits cancel and restart the snapshot, so continuous edits can postpone a finished result. Python scans yield, but Blender's native modifier evaluation and mesh extraction can take longer than the timer budget.

- Editable Poly Constraints work with Select and Move (W), Rotate (E) and Scale
  (R), their gizmos and free drag. Edge chooses original connected edges by
  transform direction before clamping to their endpoints. A straight drag keeps
  its rail. A deliberate direction change can choose another rail. Edge and
  Border selections slide along adjoining unselected edges. Face stays on each
  vertex's original incident polygons, without crossing to other islands or
  walking across adjacent polygons. Normal uses original geometric vertex
  normals. Opposing normals still permit a Push-style move. Each object saves
  its own setting. None restores ordinary transforms. Right-click or Esc
  cancels, and each transform is one undo step.
  Magnetic target snapping runs before Constraints, which keep the final
  position on the original geometry. Each drag restores the snap settings. Rotate and Scale project each vertex's requested displacement
  onto the same frozen edges, polygons or normals. The solver uses BMesh and
  shares repeated Edge calculations on dense selections. It affects the explicit
  selection, without Soft Selection or Preserve UVs correction. Native Blender
  G and tools selected directly from Blender's toolbar bypass these Max tools.
  The rebuilt Max tools use the same geometry hook. See
  [transform integration](docs/poly-constraints-integration.md) for merge details.
- Caddies use a custom viewport overlay with original Max-style artwork, not Autodesk's native
  controls. The icon shapes and spacing differ. Numeric input accepts
  plain numbers in Blender units, without Max unit expressions. Click selection
  and selection shortcuts work on the clean mesh while the caddy stays open.
  Box and lasso selection are not implemented inside a caddy. Numeric undo stays
  local to the caddy until acceptance. Each Apply starts a new value history.
  Caddies support one mesh in Edit mode. Shape-key meshes are rejected before preview.
- Caddies expose the existing operation settings. Chamfer's newer mitering,
  end/radial bias and smoothing controls are not implemented. MSmooth's Separate
  by Smoothing Groups and Materials, and Bridge's pick controls, appear disabled.
  Weld shows total vertex or edge counts before and after its preview.
- Editable Poly's By Vertex click filter, Ignore Backfacing, hover Preview
  Selection and Preserve UVs channel settings are disabled.
  By Angle expands the current face selection with a separate button.
- Soft Selection uses Blender proportional editing for transforms. Edge Distance
  means connected-only, with no edge-count cutoff. Falloff is Blender's radius.
  Pinch, Bubble, Affect Backfacing, Shaded Faces and a custom curve preview are unavailable.
  Fixed-value mesh operations do not use proportional influence.
- Hinge From Edge, Extrude Along Spline and hidden Edit Triangulation are disabled.
  Turn rotates real edges and Retriangulate creates real triangles. Remove Unused
  Map Verts is disabled because Blender stores UVs on face corners.
- Extrude uses Blender region or individual-face extrusion. Vertex extrusion
  creates wire edges. Edge extrusion uses the average selected surface normal,
  with local Z as the fallback. Extrusion Base Width is disabled. Chamfer Tension
  maps to Blender's bevel profile, so intermediate shapes differ from Max.
- Bevel has Group, Local Normal and By Polygon modes. It uses BMesh inset with
  height and outline. Max's Local Normal Bias is unavailable.
- Bridge uses Blender edge-loop bridging. Taper and Bias scale intermediate
  rings with a linear envelope, which can differ from Max. Smooth sets the new
  bridge edges by face angle. Existing smoothing groups take precedence.
  Twist 1 and Twist 2 set the relative loop offset. The selection and pick
  controls are disabled because Bridge uses Blender's current selection.
  Connect subdivides selected edges or connects vertices. Its Pinch and Slide
  settings are disabled. MSmooth uses native smooth subdivision, not NURMS.
- Create fills the selected vertices instead of picking vertices in the viewport.
  Insert Vertex splits selected edges at their midpoint, or pokes selected faces.
  Create Shape From Selection copies each selected edge to a separate poly spline.
- Slice Plane uses numeric local coordinates without Max's plane gizmo. QuickSlice
  cuts a view-aligned BMesh plane through two clicked screen points.
  Ring and Loop shifts use quad topology and
  Blender's face/vertex order, so direction can differ on irregular meshes.
  Named Selections Copy/Paste stores one selection per mesh and sub-object level.
- Weight and Subdivision Surface Smoothness are disabled because Blender's
  subdivision has no equivalent. NURMS uses a live Subdivision Surface modifier.
  Auto Smooth supports up to 32 disconnected smooth patches in one operation.
- Edge Depth, Hard, Smooth and Display Hard Edges, Full Interactivity, Vertex
  Colors, Subdivision Displacement and Paint Deformation remain visible but
  disabled. Max's automatic Hard/Smooth smoothing-group reassignment, vertex
  channels, displacement approximation and paint tools are not mapped.

- Grid and Snap Settings is a modeless floating viewport region. Drag its title to move it. Close it with X. The viewport outside the dialog remains available for editing. Snap and Angle/Percent toolbar right-click opens it directly. Spinner Snap right-click opens General > Spinners in a compact Preference Settings dialog.
- Snap markers use green for an active point and yellow for a snapped point. Marker Display and Size control the drawing without changing target selection. Vertex keeps the 2026 crosshair. Grid Points uses the Snaps dialog box with a half diagonal from its centre to the top-right corner. Pivot uses a box with a full diagonal. Endpoint uses the measured dialog Y with a stem and two lower arms. The other types use the supplied Max glyph references, including triangles, corner brackets, the Midpoint right angle and Face ring. Current isolated viewport captures are unavailable for those glyph-based shapes. No snap-type text label is drawn. The rubber band stays solid.
- Hold the Snaps Toggle button to choose 2D, 2.5D or 3D in its compact icon flyout. The button keeps the current mode icon when snapping is off. The Shift-right-click snap quad uses compact rows, tick marks and separate section bars. Its drawing primitives can also support the other quad menus.
- Tangent snaps, NURBS snaps, user grids and AutoGrid are unavailable. Blender controls the visible grid extent and its adaptive subdivision. Those controls are disabled in the dialog.
- Spinner Snap applies to primitive float fields in the Command Panel, including typed edits. It does not change every Blender spinner. Curve segments use evaluated geometry, so curved-segment snaps follow Blender's tessellation.
- Use the add-on's toolbar, Edit menu, quad menu or W/E/R for the shared magnetic transform tools. Transforms invoked directly through Blender's own operators retain Blender's snapping behavior. The snap tools support object mode and Editable Poly mesh levels.

- Blender keeps one shading mode per viewport *area*, so all four quads share the same shading (Max can set it per viewport).
- Reference clones share Blender data in both directions. They do not have Max's one-way reference stack. Controller Instance uses one-way drivers from the original children, rather than Max's shared controller objects.
- Shift-clone dialogs use Blender's dialog frame and controls. Gizmo hit areas are calculated in screen space. Gimbal and custom normal orientations can differ from Blender's native handle picking.
- Disabling the add-on removes clone previews immediately. An open clone dialog stays until you dismiss it.
- There's no Teapot or Ribbon.
- The ViewCube uses a raster label atlas and GPU artwork rather than Autodesk's assets. It has no Fit-to-View on View Change or adjustable compass north. Its smaller default size and permanent transparency are deliberate preferences, rather than Max's stock settings. Tiny is unlabeled, as in Max.
- Free rotation uses a virtual sphere whose grabbed position affects the rotation. Angle Snap quantizes its reference Euler components. Max's internal trackball, free-snap rounding and Legacy R4 sensitivity have not been compared against a running Max instance. Local Aligned uses the object's frame. Max's per-sub-object normal interpretation and animated controllers remain unverified.
- Gizmo colours, proportions and slice transparency follow Autodesk's documentation images. Exact GPU antialiasing and undocumented opacity values are estimates. Multiple gizmos cover individual object pivots. Independent sub-object tripods are not implemented.
- Rotate Transform Type-In and Gizmos Preferences use floating Blender editor windows. Their controls occupy the sidebar, and Blender supplies the frame and canvas. Absolute sub-object rotation uses the object's frame. Local sub-object Type-In exposes offsets only.
- Rotate deliberately ignores geometry snap targets, including Max's documented ability to use a snapped point as a rotation pivot. This keeps Angle Snap independent of S.
- Shift-drag reuses the shared cloning module when installed. The standalone fallback provides Copy, Instance, a one-way Reference geometry dependency, mesh separation/naming and Edge/Border extension. Its dialog frame and hierarchy controller options differ from the shared module.
- Edit Poly is still a base-mesh editing shortcut, not a non-destructive modifier. Shift+E imported from Nathan.hsx resolves to that shortcut. It cannot edit an unconverted primitive. A separate stack design is needed to retain Box beneath Edit Poly.
- Keyboard Entry uses the existing viewport construction planes. It has no custom grid objects or AutoGrid. GeoSphere keeps Blender's icosphere tessellation.
- Keyboard Entry uses Blender's numeric widgets and unit formatting. Spinner arrows and unit spacing differ from Max.
- Keyboard Entry rejects equal Tube radii and a zero Torus cross-section radius rather than creating zero-thickness geometry.
- Mouse creation still uses fixed second radii for Cone, Tube and Torus. Use Keyboard Entry to set both radii.
- PlanePlus uses Width and Length, like the original plug-in. It always generates image UVs and does not expose its Real-World Map Size option. The image draw handler follows the parametric rectangle, so modifiers do not deform that viewport image. Convert to Editable Poly to use the material display for a modified mesh.
- Show Frozen in Gray changes the viewport materials of meshes through a temporary copy. It preserves the render shaders and restores the original mesh and materials on unfreeze. Other object types use Blender's object color, which some viewport shading modes can override.

## Updating

From 1.5.0 on, the add-on can update itself from this repo's GitHub Releases. Use **Customize › Check for Updates**, **Utilities › NotuoDesk 3ds Maxxed** in the Command Panel, or the add-on's preferences.

- If a newer release exists, **Update to x.y.z** downloads it and installs it over the current version in one click.
- It checks on startup by default. You can turn that off in the preferences.
- Blender's **Preferences › System › Network › Allow Online Access** has to be on.
- **While the repo is private,** paste a GitHub token into the add-on preferences (**GitHub Token**). Create a *fine-grained* token at GitHub › Settings › Developer settings › Personal access tokens. Limit it to this repository, with **Contents: Read-only** access. The token is stored in Blender's preferences file. If the repo is public, no token is needed.
- **Publishing an update:** bump `version` in `blender_manifest.toml`, build the zip, and attach it to a new GitHub Release tagged `vX.Y.Z`.

## Building from source

The editable icon sources are in `notuodesk_3ds_maxxed/icons/src/`. To rebuild the
transparent 32px and 64px PNGs, install the build-only renderer and run:

```powershell
python -m pip install resvg-py==0.5.0 Pillow
python tools/build_icons.py --contact-sheet icons-contact.png
```

Blender needs no extra packages. See `notuodesk_3ds_maxxed/icons/README.md` for
artwork provenance and test instructions.

```bash
blender --command extension build --source-dir notuodesk_3ds_maxxed --output-dir .
```

## License

GPL-3.0-or-later (required for Blender add-ons). See [LICENSE](LICENSE).

## Constraints integration hook

`snaps.constraint_session` freezes Edit Poly geometry before clone creation. Move, Rotate and Scale use `MoveSession.apply_targets` after snapping and axis orientation. Active Constraints retain the shared snap tools with snaps on or off. Shift-clone writes to preview vertices using the original source rails and leaves the source in place. The transform owns cancel and undo, and Clone Part of Mesh owns clone acceptance. See [transform integration](docs/poly-constraints-integration.md) for the hook contract used by the later Max Rotate tools.

All interactive standard and extended primitive measurements, Line points and PlanePlus placement and endpoints use `snaps.snap_point`. Grid Points attracts only within Snap Radius. Typed Keyboard Entry values stay exact. Line's Shift angle constraint and PlanePlus's Shift square constraint apply after picking. PlanePlus keeps its explicit pivot instead of AutoPivot. Loft and Target Weld use the picked location to identify existing source geometry. They never move source objects or create a weld target at an empty grid point. Shift-drag on the snap tools uses the existing Clone Options or Clone Part of Mesh transaction.

Caddy fields and OK, Apply and Cancel use the shared icon family. Extrude Height
and Tessellate Tension have distinct symbols. Constraints keeps its named radio
choices and shows the current mode symbol beside its heading. Main Toolbar snap
buttons use icons, including the current 2D, 2.5D or 3D snap mode.
