# Editable Poly transform integration

`poly_constraints.MoveSession` freezes original topology, world coordinates and
geometric normals. Its public geometry hook is `apply_targets`.

```python
tx = poly_constraints.MoveSession(context)  # Before the first preview.
tx.apply_targets({ob: {vertex_index: requested_world_position}})
tx.finish()  # Commit. Use tx.cancel() to restore the original coordinates.
```

Each preview supplies absolute world positions computed from the drag start.
Apply axis locks, pivot transforms and Angle/Percent Snap before this hook.
Do not feed the previous constrained preview back as the next transform start.
The transform operator owns mouse handling, gizmos and its single undo step.
Only create a constraint session in mesh edit mode when `active(context)` is true.

`poly_transform.MAX_OT_poly_transform` calls this hook for this branch's current
Rotate and Scale tools. The `feat/max-rotate` snapshot tested in the fix round
also calls it from `RotationSession.apply` and `MAX_OT_snap_transform._apply`
for Scale. Those tools retain their own gizmos, pivots, persistent axis locks,
Angle Snap and Percent Snap. Do not replace their Rotate/Scale selectors with
this branch's fallback selector when merging.

## Integrated Snaps tools and the later Rotate merge

Batch 7 keeps `max.snap_move`, `max.snap_rotate` and `max.snap_scale` for active
Constraints, even when target snaps are off. W/E/R, menus, toolbar and constraint
radio changes all use `snaps.select_transform`. None returns to the usual
native or snapped tool according to the snap settings.

`snaps.constraint_session(context)` freezes the geometry before Shift cloning.
`MAX_OT_snap_transform._apply` calls `apply_targets` after magnetic picking,
axis orientation/locks and Angle/Percent Snap. For uniform Move, the optional
`move_delta` and `normal_distance` arguments retain grouped Edge calculations
and the signed common Normal displacement. Rotate and Scale use absolute
per-vertex world positions. The transform calls `finish` before consuming its
one-shot snap override, or `cancel` before removing clone topology.

Shift clone must retain original source rails. Duplicated isolated vertices
have no edges from which to recover them. `MeshClone.constraint_indices` maps
original indices to preview indices using BMesh's duplicate map or extrusion
side edges. Call `MoveSession.retarget_clones(clone_tx)` after creating the clone
transaction. It redirects writes to the preview while retaining source rails,
polygons and normals. The clone transaction closes its session before undo,
load or disable cleanup can remove preview topology. Finish this session before Clone Part of Mesh can remove
preview vertices or create the detached object.

When `feat/max-rotate` merges, retain its gizmos, pivots, axis locks and stepping.
Keep `RotationSession.apply` calling `apply_targets` from frozen positions.
Its Scale adapter must retain the same call in `_apply`. Keep the uniform Move
path and clone remapping described above. Do not restore the older
`invoke_move` delegation inside the integrated snap operator. That fallback
bypasses magnetic picking, snap override input and Shift-clone ownership.
The legacy `poly_move` and `poly_transform` operators remain available for
programmatic use, but integrated selectors must not choose them.

Older Snaps-only trees without `snaps.constraint_session` still need the
`poly_constraints.select_transform` selector guard and `invoke_move` guard
shown in the feature branch. Those are compatibility hooks, not the batch 7
transform route. The rebuilt Move must stay constraint-aware when snaps are off.

## Solver policy

Edge ranks outgoing original rail directions by positive dot product with the
requested displacement, then clamps to the winning segment. Rail length cannot
change the winner during a straight drag. Exact ties use original vertex-index
order. A change in direction can select another rail. Autodesk's 2026 help says
edge choice depends on transform direction. It does not publish tie scoring,
endpoint continuation or loop coordination rules. These details are explicit
implementation choices, without a claim of live Max equivalence.

Face searches only triangles of each vertex's original visible incident
polygons. It does not traverse adjoining polygons or jump to another island.
Move Normal uses a signed common distance along each stored geometric vertex
normal. If selection normals cancel, programmatic Move uses signed drag length
and interactive Move uses horizontal screen distance. Rotate and Scale project
each requested displacement onto that vertex's own normal.

Dense uniform Move groups identical rails so each group scores once per event.
It stores vertex indices because Blender can replace BMesh wrappers when a
modal operator begins its undo snapshot. Arbitrary per-vertex Rotate/Scale
targets use the same direction and surface policy without uniform-move grouping.

## Sources checked on 10 November 2026

- [Editable Poly, Edit Geometry rollout](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Modeling/files/GUID-8DA624B4-32AB-473A-B5B4-77B8934DAE1B.htm)
  says Edge movement follows existing edges depending on transform direction,
  Face stays on polygon surfaces, and Normal uses geometric sub-object normals.
- [EPolyMod API](https://help.autodesk.com/cloudhelp/2026/ENU/MAXDEV-CPP-API-REF/class_e_poly_mod.html)
  says both `EpModRotateSelection` and `EpModScaleSelection` respect Constraints.

Live 3ds Max comparison and Blender 4.2 execution remain unverified.
