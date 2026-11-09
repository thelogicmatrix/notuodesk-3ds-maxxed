# NotuoDesk 3ds Maxxed

A Blender add-on (Blender 4.2+, tested on 5.2.3 LTS) that makes Blender look and work like Autodesk 3ds Max. It's aimed at people who know both apps.

![3ds Max layout in Blender: quad viewports, Command Panel, Editable Poly](docs/quad-editpoly.png)

![Animated Melt modifier at frame 60](docs/melt-animation.png)

## Install

1. In Blender, open **Edit › Preferences › Get Extensions**, click the **⌄** menu (top right), then **Install from Disk…**
2. Pick `notuodesk_3ds_maxxed-1.8.0.zip` (download it from this repo's **Releases** page).
3. On first enable, the add-on applies the 3ds Max theme and adds a **3ds Max** workspace, then switches you to it.

To reset a rearranged layout, choose **Customize › Apply 3ds Max Look**. It rebuilds the "3ds Max" workspace from scratch.

To go back to normal Blender, choose **Customize › Restore Blender Look**, or turn the add-on off. Turning it off removes every hotkey and menu change. The theme stays as it is until you restore it.

## What you get

| 3ds Max | In Blender |
|---|---|
| Menu bar: File, Edit, Tools, Group, Views, Create, Modifiers, Animation, Graph Editors, Rendering, Customize, Scripting, Help | Replaces Blender's top menus. Blender's own menus are still there as sub-menus |
| Workspaces dropdown | Top right, replaces the workspace tabs |
| Main Toolbar | Viewport header: undo/redo, link/unlink, select by name, region select, move/rotate/scale, reference coordinate system, pivot, snaps, mirror, align, editors, render |
| Scene Explorer | Outliner on the left |
| 4 viewports: Top, Front, Left, Perspective | Quad view with clickable `[+] [Top] [Standard] [Edged Faces]` labels, like Max:<br>**[+]** maximize, grid, ViewCube, statistics<br>**[Perspective]** Top / Front / Left… and your cameras<br>**[Standard]** High Quality / Standard / Performance, shadows and AO<br>**[Default Shading]** Default Shading, Shaded Materials with Maps, Flat Color, Clay, Wireframe Override, Realistic, ActiveShade, Edged Faces, See-Through |
| Command Panel: Create, Modify, Hierarchy, Motion, Display, Utilities | Right sidebar with collapsible rollouts |
| Click-drag creation (base first, then height) | Box, Cone, Sphere, GeoSphere, Cylinder, Tube, Torus, Pyramid, Plane. Right-click stops creating |
| Keyboard Entry and Creation Method | Type grid coordinates and dimensions, then click Create. Choose Edge / Center, Cube / Box, Base/Apex / Center or Rectangle / Square for mouse creation |
| Parametric primitives | Length/Width/Height/Segs stay editable in **Parameters** until you convert to Editable Poly or enter sub-object mode |
| Modifier List and stack | About 60 modifiers under their Max names (see below). Newest is on top, with a visibility toggle per modifier |
| Editable Poly | Selection, Edit Vertices/Edges/Borders/Polygons/Elements and Edit Geometry rollouts |
| Cut and SwiftLoop | Hover previews and click-to-commit cuts and loops. Right-click ends the tool |
| Quad menus | Right-click (display / tools / transform) and Ctrl+right-click (modeling) |
| Status bar | "1 Object Selected", X/Y/Z type-in, Grid, Auto Key, Set Key |
| Look | Max dark UI, cyan selection outline, red sub-object selection, blue vertices, random object colors, names like Box001 |

## Creating primitives from the keyboard

In **Create > Geometry > Standard Primitives**, pick a primitive and open **Keyboard Entry**. Enter X, Y, Z and its dimensions, then click **Create**. X, Y and Z follow the active viewport's construction grid. For Box, Cone, Cylinder, Tube and Pyramid they place the centre of the base. For Sphere, GeoSphere, Torus and Plane they place the centre.

The rollout starts closed. Each type keeps its own values between creations and when you save the scene. New objects keep editable parameters and the default segment counts. **Creation Method** controls mouse creation only. GeoSphere calls its diameter method **Diameter**, as Max does. **Cube** creates equal sides in one drag.

Tube accepts its radii in either order. Set the inner radius to zero for a solid cylinder that keeps editable Tube parameters. Equal Tube radii and a zero Torus Radius 2 are rejected before creating an object. Cone accepts either end radius at zero. A Torus with Radius 1 at zero becomes a sphere. Horn and spindle tori keep their touching or intersecting shape without collapsed edges at the axis.

The Create rollouts follow Max's order: Object Type, Name and Color, Creation Method, Keyboard Entry, Parameters. Creation Method uses a row of radio buttons. Keyboard Entry has compact labelled spinners, with coordinates above dimensions and a full-width Create button. Numbers use the scene's display units.

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

The objects keep their parameters in **Create > Parameters** and **Modify > Parameters**, including segment counts, Smooth and Generate Mapping Coords. Editing or collapsing an object makes it an Editable Poly, as with Standard Primitives. OilTank, Spindle and Capsule have Overall/Centers height options. Torus Knot has Knot/Circle base curves, winding numbers, warp, eccentricity, twist and lumps.

Object Type follows Max's button order. Parameters use compact labelled fields. Prism limits impossible side lengths to a valid triangle and shows the corrected lengths in Parameters.

Parameter names and segment defaults follow [Autodesk's Extended Primitives reference](https://help.autodesk.com/cloudhelp/2015/ENU/3DSMax/files/GUID-BF868DCF-12E3-431C-A73B-C16C0FD67C98.htm). Types whose Max constructor starts with zero dimensions start at one Blender unit here. ChamferBox, Capsule, Hedra and Prism keep their documented nonzero dimensions. Click-drag creation replaces these dimensions with the size you draw.

## Opening 3ds Max files

![A 3ds Max 2015 character opened with File › Open 3ds Max File](docs/open-max-file.png)

`.max` is a closed Autodesk format. 3ds Maxxed reads it through the open-source [Import Autodesk MAX (.max)](https://extensions.blender.org/add-ons/io-scene-max/) extension (GPL, [source](https://github.com/nrgsille76/io_scene_max)). If it isn't installed, **File › Import › Install .max Reader…** installs it.

- **File › Open 3ds Max File…** opens the file into a new scene, so nothing in your current scene is overwritten.
- **File › Import › Merge 3ds Max File** adds a file's objects to the current scene. You can also drag a `.max` file onto the viewport.
- **System Units:** pick the unit the file was made in. The default is Inches, 3ds Max's US default. The reader ignores units, so without this setting scenes come in at the wrong scale.
- **Materials:** names are cleaned up (`04 - Default` instead of `04___Default_C:\Users\…\pipe_bowl`), and the materials can be edited in **Modify › Material** using V-Ray parameter names.
- **Textures:** bitmaps are searched for next to the `.max` file and in its subfolders, in any image format. Missing files are listed like Max's *Missing External Files*. Point **File › External Data › Relink 3ds Max Textures…** at the folder where they are. It also matches renamed copies like `Name (1).png`. To pick a file for one material directly, use **Modify › Material › Load Bitmap…**.

**What the reader supports:** meshes (Editable Poly/Mesh), primitives, UVs, Standard / Physical / V-Ray / Corona materials, and helpers. It handles uncompressed files from any version, and compressed files up to 3ds Max 2023. **Not supported:** animation, modifiers (meshes come in collapsed), splines, lights, cameras and rigs.

**For full scenes, use FBX:** run [`tools/max_to_blender.ms`](tools/max_to_blender.ms) inside 3ds Max (*Scripting › Run Script*). It exports the open scene, or a whole folder of `.max` files, to FBX. Then use **File › Import › FBX from 3ds Max** in Blender, which keeps animation, skinning, cameras and lights, and turns TurboSmooth into subdivision. *(I haven't been able to test the MAXScript, since 3ds Max isn't available here.)*

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
| N / K | Auto Key / Set Key |
| Ctrl+V / Ctrl+C | Clone / Camera from view |
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

Editable Poly settings shortcuts open a settings dialog. Bridge uses **Segments**, starting at 1 with no intermediate ring. Chamfer starts at **Amount** 1.0. Edge and vertex Extrude settings move the new geometry along averaged adjacent surface normals. Tessellate offers **Edge** and **Face** types. Export Selected opens Blender's FBX exporter with **Selected Objects** on. rapidTools fastBridge and RappaTools3 Inset, Relax and MePoly use the add-on's Bridge, Inset, Relax and Convert to Editable Poly. rapidQCap and fastEdgeLoopRegularizer work when the add-on's Quad Cap and Loop Regularize operators are installed.

## Known differences from 3ds Max

- Cut adds supporting triangles for endpoints inside a polygon. Concave polygons are triangulated before an interior endpoint is added.
- Cut uses three Blender cursor shapes instead of Max's cursor artwork. Its Undo groups one committed segment per step. Max's exact Undo grouping has not been confirmed.
- SwiftLoop follows quad rings and stops at triangles, n-gons and hidden faces. Shift uses cubic interpolation of surface normals, so its flow can differ from Max's proprietary result. Sliding needs a regular loop with two bounding edges at each vertex.
- Imported hotkeys call Blender equivalents. Relax uses vertex smoothing, including Paint Deform Relax. Edit Poly enters mesh editing through the add-on's existing Edit Poly command. Unassignments affect only this add-on's keys. Unknown actions stay in the imported list but get no binding.
- Settings dialogs expose a subset of Max's caddy controls. Edge and vertex Extrude use Blender's topology and omit Max's Extrusion Base Width. Vertex extrusion adds connected vertices and edges, rather than Max's polygon base. Surface normals are equal-weight averages in mesh space. An extrusion without an adjacent surface normal leaves the mesh unchanged. Tessellate Edge Tension maps inversely to Blender's subdivision smoothness over 0 to 1. It does not reproduce Max's full tension range. Extrusion Height starts at 0.1 and Edge Tension at 1.0, since the reference does not specify their initial values.
- Extended Primitives do not include RingWave or Hose. Creation uses the default Corners, Center or Isosceles method. Alternate creation methods and Slice controls are not included.
- Hedra uses reflection-generated polyhedra. Star1, Star2 and axis scaling approximate Max's shapes. Its facet topology and the other primitives' triangulation can differ from Max. OilTank and Spindle use Blender's bevel for Blend.
- Generate Mapping Coords on Extended Primitives uses box projection. It does not reproduce Max's UV layouts. Torus Knot uses whole-number winding, twist, warp and lump counts, and Smooth is an on/off setting. Real-World Map Size and mapping offset/tiling controls are not included.

- Blender keeps one shading mode per viewport *area*, so all four quads share the same shading (Max can set it per viewport).
- There's no Teapot, ViewCube or Ribbon. Blender's navigation gizmo stands in for the ViewCube.
- Shift-drag cloning isn't supported. Use Ctrl+V (Clone), or Blender's Shift+D.
- Entering a sub-object level on a primitive converts it straight to Editable Poly; in Max you would add an Edit Poly modifier instead.
- Keyboard Entry uses the existing viewport construction planes. It has no custom grid objects or AutoGrid. GeoSphere keeps Blender's icosphere tessellation.
- Keyboard Entry uses Blender's numeric widgets and unit formatting. Spinner arrows and unit spacing differ from Max.
- Keyboard Entry rejects equal Tube radii and a zero Torus cross-section radius rather than creating zero-thickness geometry.
- Mouse creation still uses fixed second radii for Cone, Tube and Torus. Use Keyboard Entry to set both radii.

## Updating

From 1.5.0 on, the add-on can update itself from this repo's GitHub Releases. Use **Customize › Check for Updates**, **Utilities › NotuoDesk 3ds Maxxed** in the Command Panel, or the add-on's preferences.

- If a newer release exists, **Update to x.y.z** downloads it and installs it over the current version in one click.
- It checks on startup by default. You can turn that off in the preferences.
- Blender's **Preferences › System › Network › Allow Online Access** has to be on.
- **While the repo is private,** paste a GitHub token into the add-on preferences (**GitHub Token**). Create a *fine-grained* token at GitHub › Settings › Developer settings › Personal access tokens. Limit it to this repository, with **Contents: Read-only** access. The token is stored in Blender's preferences file. If the repo is public, no token is needed.
- **Publishing an update:** bump `version` in `blender_manifest.toml`, build the zip, and attach it to a new GitHub Release tagged `vX.Y.Z`.

## Building from source

```bash
blender --command extension build --source-dir notuodesk_3ds_maxxed --output-dir .
```

## License

GPL-3.0-or-later (required for Blender add-ons). See [LICENSE](LICENSE).
