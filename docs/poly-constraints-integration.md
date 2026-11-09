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

## Move selectors

An invoke-only hook is insufficient when a selector can choose `builtin.move`
with snaps disabled. With the older Snaps implementation, add this guard at
the start of `snaps.select_transform`, before checking snap enablement.

```python
from . import poly_constraints
if kind == "MOVE" and poly_constraints.select_transform(context, kind):
    return
```

Keep the existing `invoke_move` guard at the start of
`MAX_OT_snap_transform.invoke` too. An already selected snap tool must respect
constraints after the object setting changes.

```python
if self.kind == "MOVE":
    result = poly_constraints.invoke_move(
        context, event, constraint_axis=self.constraint_axis,
        from_gizmo=self.from_gizmo)
    if result is not None:
        return result
```

The new Rotate branch always selects its Max Move tool in Object/Edit Mesh
mode, including when snaps are off. Its existing invoke guard delegates to
the constrained Move operator, so that version does not need the older
selector guard. Both selector variants were tested separately in the sandbox.

W, toolbar and menu commands must use one of these constraint-aware selectors.
Never retain a selector that can choose `builtin.move` while Constraints is active.
None and Object mode return to the owning transform tool's ordinary behavior.
Constraint tool keymaps have unique internal names. Their visible Max labels
must not cause a shared keymap with the new Move/Rotate/Scale tools.

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
