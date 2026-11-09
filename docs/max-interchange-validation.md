# Max interchange validation

Checked on 2026-11-09 in Blender 5.0.1, with io_scene_max 1.9.2 (release `37db107`). All input scenes and the reference FBX were copied into `sb-max-interchange/inputs` first. No scene files are included in this repo.

The isolated profile uses `sb-max-interchange/scripts`, `sb-max-interchange/config` and `sb-max-interchange/ext`. The add-on package is a junction to this worktree. The reader is installed only in that sandbox. The tests use factory startup and never save preferences.

## Copied Max scenes

Every row imported supported objects. This does not mean every source object or its evaluated shape survived. Counts describe Blender's imported data. Missing-node counts come from the reader's retained source node list.

All rows used **Inches as an explicit assumption**. The reader does not recover System Units. For each scene, a second import at 1:1 proved that converting to inches scales every object's world matrix uniformly, including children. All imported world transforms are finite. Absolute transforms and dimensions have not been checked against a running copy of Max.

No bitmap assets were present under the source scene folders. No real-scene image loaded. Hangar and Hangar01 now report two missing bitmap names each. The other rows have no recovered bitmap references. This does not prove that their original Max materials had no textures.

| Copied scene | Meshes | Materials | Meshes with UVs | Parent links | Masks recovered on meshes | Missing source nodes |
|---|---:|---:|---:|---:|---:|---:|
| `2026/Bear/BEarFinal.max` | 3 | 1 | 3 | 0 | 3 | 0 |
| `2026/JobApps/3World.max` | 10 | 0 | 0 | 0 | 9 | 1 |
| `2026/JobApps/Card.max` | 1 | 0 | 1 | 0 | 0 | 0 |
| `2026/MoonBase/Battery.max` | 26 | 1 | 26 | 6 | 16 | 0 |
| `2026/MoonBase/Cube.max` | 51 | 0 | 51 | 17 | 22 | 44 |
| `2026/MoonBase/Cube01.max` | 70 | 0 | 70 | 21 | 30 | 44 |
| `2026/MoonBase/Cube02.max` | 72 | 0 | 70 | 18 | 55 | 42 |
| `2026/MoonBase/Environment.max` | 23 | 1 | 23 | 2 | 23 | 0 |
| `2026/MoonBase/Fab.max` | 49 | 0 | 49 | 20 | 32 | 56 |
| `2026/MoonBase/Fab01.max` | 53 | 0 | 53 | 20 | 36 | 52 |
| `2026/MoonBase/Glove.max` | 1 | 1 | 0 | 0 | 0 | 0 |
| `2026/MoonBase/Hangar.max` | 66 | 4 | 66 | 43 | 42 | 0 |
| `2026/MoonBase/Hangar01.max` | 67 | 4 | 67 | 43 | 44 | 0 |
| `2026/MoonBase/oxy.max` | 5 | 0 | 5 | 2 | 5 | 0 |
| `2026/MoonBase/Spikes.max` | 16 | 0 | 16 | 0 | 16 | 0 |
| `2026/Steel/ConsoleParts.max` | 5 | 0 | 5 | 0 | 1 | 0 |
| `2027/Bellroy.max` | 4 | 0 | 4 | 0 | 0 | 1 |

The masks become flat/smooth faces and sharp edges. They remain available as the signed 32-bit `max_smoothing_group` face attribute. A face can share several group bits. An edge stays smooth only when its adjacent masks overlap. Recovery requires exact face topology, uses reader 1.9.2 only, and leaves unmatched meshes alone. Zero masks make flat faces. Native Max shading and explicit normals in `.max` have not been validated.

Specific gaps from the scene audit:

- `3World.max` omits `logo.svg_FillEditPoly001`. Its `Object` mesh is empty. The FBX reference imports a different evaluated mesh set, so `.max` and FBX geometry must not be treated as equivalent.
- `Cube.max`, `Cube01.max`, `Cube02.max` and `Fab01.max` omit bones and IK chains. The surviving parent links and helpers do not form a complete rig.
- `Fab.max` also omits four Editable Poly nodes, `Box001`, `Box048`, `Box050` and `Box051`. The reader prints `ImportError: unpack requires a buffer of 12 bytes` for each. An upstream reproduction is in the PR draft.
- `Bellroy.max` omits `Loft001`, a Loft object. The four meshes import.
- Hangar material names recover to `EnvironmentPack_DefaultMaterial_AlbedoTransparency_1`, `EvPack`, `Material__42` and `Universal`. The reader's appended bitmap stems no longer appear in the material names.

The latest published reader and its current source expose no camera, light or spline import options. The extension describes mesh, material and UV import. It documents compressed-file support only through Max 2023. These particular 2026/2027 copies did import supported data. That result does not establish support for every file from those versions.

## FBX comparison

The copied `3World.fbx` imported through `max.import_max_fbx`, exported through `max.export_max_fbx`, then imported through `max.import_max_fbx` again.

```text
FBX_COMPARISON {"objects": 12, "meshes": 9, "units": "INCHES", "matrix_max_abs": 1.2457711129343352e-07, "vertex_max_abs": 0, "corner_normal_max_abs": 0, "smoothing_flag_changes": []}
VERIFIED reference FBX: names, transforms, scale, pivots, hierarchy, topology, normals, smoothing and material names
```

The comparison matches objects by name, matrices element by element, mesh vertices and polygons, corner normals, face smoothing, sharpness by edge vertex pair, parent names and material slots. The reference has no material slots, so the separate synthetic material test proves non-empty material naming. Object origins are compared through the matrices and local geometry. Edge indices can reorder during FBX import, so sharp edges are compared by their vertex pairs.

## Exporter regression tests

```text
Ran 11 tests in 0.368s
OK
VERIFIED baked animation endpoints across FBX unit conversion
VERIFIED media embedded byte-for-byte and material name preserved
VERIFIED missing texture relink: existing image node and renamed copy, no fuzzy substitution
VERIFIED hierarchy scales once and overlapping smoothing masks become sharp edges
VERIFIED shared System Units and centimeter Blender scene scale
VERIFIED selected export: names, hierarchy, offset pivot, camera and light
VERIFIED subdivision: editable control mesh or applied geometry, source unchanged
VERIFIED unit metadata and transform roundtrip: all 6 system units
```

The tests inspect FBX `UnitScaleFactor`, Z-up metadata, settings for geometry/modifiers/selection/media/animation, source mesh preservation, and restoration of Blender units after an injected exporter failure. Expected exception output appears in that failure test. All tests pass.

Blender 5.0.1's bundled FBX light importer assigns `lamp.cycles.cast_shadow`, a removed property. The camera/light test disables Cycles only inside the isolated test around re-import, then restores it. The shipped wrapper does not disable Cycles or patch Blender. Exporting lights works, but importing a file containing lights with Cycles enabled remains a Blender limitation.

## Commands

From this worktree in PowerShell:

```powershell
$env:BLENDER_USER_SCRIPTS = 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/scripts'
$env:BLENDER_USER_CONFIG = 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/config'
$env:BLENDER_USER_EXTENSIONS = 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/ext'
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/test_max_interchange.py
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/report_max_scenes.py -- 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/inputs' 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/outputs/max-scenes.json'
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' -b --factory-startup --python-exit-code 1 --python tests/roundtrip_max_fbx.py -- 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/inputs/3World.fbx' 'C:/Users/thelo/.claudework/maxxed-review/sb-max-interchange/outputs'
```

Full JSON and logs are in the sandbox's `outputs` directory. `max-scenes.json` includes each object's matrix, missing source names and classes, materials, image paths, counts and reader messages.

## Max settings and limits

Autodesk documents a default system unit of one inch. FBX writes the selected System Units into `UnitScaleFactor`, with geometry converted separately. The exporter restores Blender's scene units afterward. It uses Y-forward and Z-up, which is the identity axis conversion for Blender. Import reads FBX axis metadata and applies no extra manual rotation. FBX animation import uses a zero frame offset.

Apply to Mesh is the default subdivision choice. Keep Editable writes the last Catmull-Clark modifier as FBX Smoothness, preview/render levels and supported crease data. Both modes pass a Blender round trip. Autodesk documents exporting a control mesh plus TurboSmooth attributes, but a Max import of Blender's attributes was not run. Other modifier settings, Max plug-in materials, constraints, rigs and procedural texture graphs do not have general parity. Curves use Blender FBX's mesh conversion.

Blender 5.0.1 supports face smoothing-group bitflags. On versions without that exporter enum, the add-on falls back to face smoothing plus explicit normals. Blender 4.2 was not run, and reconstructed Max group numbers are not guaranteed. Export Selected includes selected objects only, so parent links survive between exported objects. An unselected ancestor is not added automatically.

The menus are registered additively in File, File > Export and Customize. Operators and file output were tested headlessly. File-browser clicking was not driven. Max-side appearance, units, camera/light semantics, and reconstruction of TurboSmooth remain unverified. The reader code and Alt+R operator were not changed.

## Sources

Checked on 2026-11-09. Autodesk defines the destination behavior. Blender's installed exporter/importer code defines the options actually used. The reader release and source define its current limits.

- [Autodesk 2026, Using Units](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Basics/files/GUID-F48CFCBC-AFC7-43E0-95B2-E28985FF1EC5.htm), default system unit and display units.
- [Autodesk 2026, FBX Advanced Options](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Interoperability/files/GUID-94C10F56-EE1D-45E1-9858-7AA9E99CE25D.htm), System Units and axis conversion.
- [Autodesk 2026, FBX Geometry](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Interoperability/files/GUID-249100FE-67BE-43B8-AF12-D20703CDF8D1.htm), smoothing groups and TurboSmooth control mesh versus tessellated geometry.
- [io_scene_max 1.9.2 release](https://github.com/nrgsille76/io_scene_max/releases/tag/v1.9.2) and [Blender extension page](https://extensions.blender.org/add-ons/io-scene-max/), latest reader and supported data.
- [Reader source at 37db107](https://github.com/nrgsille76/io_scene_max/tree/37db107/source), parsed face data, material suffixes and hierarchy scaling.
- Blender 5.0.1 bundled `io_scene_fbx/__init__.py`, `export_fbx_bin.py`, `import_fbx.py` and `fbx_utils.py`, inspected on the test machine. Runtime tests inspect their RNA settings and actual FBX output.

