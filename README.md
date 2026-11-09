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
| Parametric primitives | Length/Width/Height/Segs stay editable in **Parameters** until you convert to Editable Poly or enter sub-object mode |
| Modifier List and stack | About 60 modifiers under their Max names (see below). Newest is on top, with a visibility toggle per modifier |
| Editable Poly | Selection, Edit Vertices/Edges/Borders/Polygons/Elements and Edit Geometry rollouts |
| Quad menus | Right-click (display / tools / transform) and Ctrl+right-click (modeling) |
| Status bar | "1 Object Selected", X/Y/Z type-in, Grid, Auto Key, Set Key |
| Look | Max dark UI, cyan selection outline, red sub-object selection, blue vertices, random object colors, names like Box001 |

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

## Snaps

S toggles positional snaps. The toolbar flyout chooses 2D, 2.5D or 3D. Grid Points is the initial snap type. Grid snapping is magnetic: points stay free outside the 20-pixel Snap Radius. Primitive bases and heights use the same rule, so they no longer jump in whole-unit increments.

W, E and R select the shared Max Move, Rotate and Scale gizmos. Move a box by its corner onto another corner, or move selected Editable Poly vertices onto unselected vertices in the same mesh or another object. Move and Scale retain their magnetic snap base. Rotate uses its Use Center setting and ignores positional snap targets. A cyan marker shows positional snap targets and a rubber band connects them to the base. Release commits. Right-click cancels the drag.

Right-click a snap toolbar button for **Grid and Snap Settings**. Its Snaps, Options, Home Grid and User Grids tabs use Max's labels. The available targets are Grid Points, Pivot, Perpendicular on straight segments, Bounding Box, Vertex, Endpoint, Edge/Segment, Midpoint, Face, Center Face and Grid Lines. Unsupported settings are greyed out with a reason. Snap settings live in the add-on preferences, as Max stores them in its user settings rather than the scene file.

Shift+right-click opens the snap quad, including during a transform or primitive creation. Release the left button, choose an override, then press it again to resume the current drag. Standard chooses a one-shot override. None disables snaps for the next action, and Last repeats the previous override. Alt+S cycles through enabled snap types. The regular checkboxes return after the action. A controls Angle Snap, initially 5 degrees. Ctrl+Shift+P controls Percent Snap, initially 10 percent. Spinner Snap quantizes changed primitive parameter fields in the Command Panel. Grid Spacing and Major Lines map to Blender's grid overlay controls. 2D accepts geometry on the active construction plane and rejects off-plane targets.

## Rotate and transform gizmos

E selects Linear Roll rotation. Drag an axis ring along its tangent, at 0.5 degrees per pixel. The grey outer ring rotates in the screen plane. Drag inside the sphere for free rotation. A turns Angle Snap on or off, including during a drag. Its default increment is 5 degrees. Angle Snap works with S on or off and never pulls the rotation toward a vertex, edge, face or grid point. Percent Snap stays separate.

During an axis drag, a translucent slice shows the direction and amount of rotation. Its colour follows the axis, as in Autodesk's red X example. Complete turns overlap. Yellow tangent guides and the live X/Y/Z angle readout follow the stepped angle. Right-click or Esc restores the starting transform. A completed rotation uses one undo step. Shift-drag opens Clone Options or Clone Part of Mesh.

The transform toolbar offers View, Screen, World, Local, Parent, Grid, Working, Gimbal, Local Aligned and Pick reference systems. Pick accepts a viewport click or H and remembers four objects. Use Center is an icon flyout. Local disables it and uses individual pivots. F12 toggles a floating Rotate Transform Type-In window. Absolute fields and Offset fields update the viewport live. Offset fields reset to zero after each edit. Angle Snap does not round typed values.

Move has projected cone arrowheads and connected plane corners. Scale has point ends and nested triangular handles. The small centre tripods are muted, with colour on the locked axes. Rotate's rings retain their drawing. The Scale flyout also offers Non-Uniform Scale and Squash. Picking an axis or plane keeps that constraint for later drags on the selection. F5, F6 and F7 select X, Y and Z. F8 cycles XY, YZ and ZX. Max stores these locks separately for each transform and for Object and sub-object modes. Locked handles remain yellow. With positional snaps on, Move respects the lock only when Use Axis Constraints in Snaps is on. Plus and minus change the shared gizmo size. X hides or shows all three.

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
| M / 8 / F10 | Material Editor / Environment / Render Setup |
| Shift+Q / F9 | Render |
| F12 / Ctrl+X | Transform Type-In / Expert Mode |
| O | Adaptive Degradation (lighter viewport for heavy scenes) |
| Shift+E, Ctrl+Shift+E, Ctrl+Shift+C | Extrude, Connect, Chamfer |
| Alt+C / Alt+L / Alt+R | Cut / Loop / Ring |
| Backspace / Ctrl+Backspace | Remove / Remove with vertices |
| Ctrl+PgUp / Ctrl+PgDn | Grow / Shrink |
| PgUp / PgDn | Select parent / child |
| , . Home End / | Previous/next frame, first/last frame, play |

You can switch each feature on or off (hotkeys, menu bar, toolbar, status bar, labels, random colors) under **Preferences › Add-ons › NotuoDesk 3ds Maxxed**.

## Known differences from 3ds Max

- Grid and Snap Settings stays open in a separate, modeless Blender editor window. The controls occupy its sidebar. Blender supplies the window frame, canvas and sidebar tabs. Use the panel's X or the window's close button. Toolbar right-click opens it directly without a button context menu underneath.
- Tangent snaps, NURBS snaps, user grids and AutoGrid are unavailable. Blender controls the visible grid extent and its adaptive subdivision. Those controls are disabled in the dialog.
- Spinner Snap applies to primitive float fields in the Command Panel, including typed edits. It does not change every Blender spinner. Curve segments use evaluated geometry, so curved-segment snaps follow Blender's tessellation.
- Use the add-on's toolbar, Edit menu, quad menu or W/E/R for the shared magnetic transform tools. Transforms invoked directly through Blender's own operators retain Blender's snapping behavior. The snap tools support object mode and Editable Poly mesh levels.

- Blender keeps one shading mode per viewport *area*, so all four quads share the same shading (Max can set it per viewport).
- There's no Teapot, ViewCube or Ribbon. Blender's navigation gizmo stands in for the ViewCube.
- Free rotation uses a virtual sphere whose grabbed position affects the rotation. Angle Snap quantizes its reference Euler components. Max's internal trackball, free-snap rounding and Legacy R4 sensitivity have not been compared against a running Max instance. Local Aligned uses the object's frame. Max's per-sub-object normal interpretation and animated controllers remain unverified.
- Gizmo colours, proportions and slice transparency follow Autodesk's documentation images. Exact GPU antialiasing and undocumented opacity values are estimates. Multiple gizmos cover individual object pivots. Independent sub-object tripods are not implemented.
- Rotate Transform Type-In and Gizmos Preferences use floating Blender editor windows. Their controls occupy the sidebar, and Blender supplies the frame and canvas. Absolute sub-object rotation uses the object's frame. Local sub-object Type-In exposes offsets only.
- Rotate deliberately ignores geometry snap targets, including Max's documented ability to use a snapped point as a rotation pivot. This keeps Angle Snap independent of S.
- Shift-drag reuses the shared cloning module when installed. The standalone fallback provides Copy, Instance, a one-way Reference geometry dependency, mesh separation/naming and Edge/Border extension. Its dialog frame and hierarchy controller options differ from the shared module.
- Entering a sub-object level on a primitive converts it straight to Editable Poly; in Max you would add an Edit Poly modifier instead.

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
