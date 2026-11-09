"""Run in an isolated profile: blender -b --factory-startup --python tests/test_max_interchange.py.

Enable this checkout through BLENDER_USER_SCRIPTS before running.
"""

import pathlib
import tempfile
import unittest
from unittest.mock import patch

import addon_utils
import bpy
from mathutils import Matrix
from mathutils.kdtree import KDTree

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)


class InterchangeTests(unittest.TestCase):
    def setUp(self):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.context.scene.unit_settings.system = "METRIC"
        bpy.context.scene.unit_settings.scale_length = 1.0
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def cube(self, name="Box001"):
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.object
        ob.name = name
        return ob

    def test_export_settings(self):
        from notuodesk_3ds_maxxed import max_export
        settings = max_export.fbx_settings(selected=True, embed=True, animation=False)
        self.assertEqual(settings["axis_up"], "Z")
        self.assertEqual(settings["axis_forward"], "Y")
        self.assertEqual(settings["apply_scale_options"], "FBX_SCALE_UNITS")
        self.assertTrue(settings["apply_unit_scale"])
        self.assertTrue(settings["use_selection"])
        self.assertFalse(settings["use_subsurf"])
        self.assertTrue(settings["use_mesh_edges"])
        self.assertTrue(settings["use_mesh_modifiers"])
        self.assertEqual(settings["path_mode"], "COPY")
        self.assertTrue(settings["embed_textures"])
        self.assertFalse(settings["bake_anim"])
        self.assertFalse(settings["add_leaf_bones"])
        self.assertEqual(settings["object_types"], {"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"})
        smoothing = bpy.ops.export_scene.fbx.get_rna_type().properties["mesh_smooth_type"].enum_items.keys()
        self.assertEqual(settings["mesh_smooth_type"], "SMOOTH_GROUP" if "SMOOTH_GROUP" in smoothing else "FACE")
        self.assertFalse(settings["bake_space_transform"])

    def test_scale_hierarchy_once_and_smoothing_masks(self):
        from notuodesk_3ds_maxxed import max_reader
        root = bpy.data.objects.new("Group001", None)
        bpy.context.collection.objects.link(root)
        root.location = (10, 0, 0)
        child = self.cube()
        child.parent = root
        child.location = (5, 0, 0)
        bpy.context.view_layer.update()
        max_reader.scale_roots(bpy.context, [root, child], 0.0254)
        self.assertAlmostEqual(child.matrix_world.translation.x, 15 * 0.0254, places=6)
        self.assertAlmostEqual(child.dimensions.x, 2 * 0.0254, places=6)
        masks = [1, 3, 2, 0, 4, 4]
        self.assertTrue(max_reader.apply_smoothing(child.data, masks))
        self.assertEqual([p.use_smooth for p in child.data.polygons], [True, True, True, False, True, True])
        edges = {e.index: [] for e in child.data.edges}
        for p in child.data.polygons:
            for li in p.loop_indices:
                edges[child.data.loops[li].edge_index].append(p.index)
        for edge in child.data.edges:
            a, b = edges[edge.index]
            self.assertEqual(edge.use_edge_sharp, not bool(masks[a] & masks[b]))
        self.assertEqual([v.value for v in child.data.attributes["max_smoothing_group"].data], masks)
        self.assertFalse(max_reader.apply_smoothing(child.data, [1]))
        print("VERIFIED hierarchy scales once and overlapping smoothing masks become sharp edges", flush=True)

    def test_relink_missing_image_node(self):
        from notuodesk_3ds_maxxed import max_import
        mat = bpy.data.materials.new("Paint")
        mat.use_nodes = True
        image = bpy.data.images.new("Diffuse", 2, 2)
        path = pathlib.Path(self.tmp.name) / "Diffuse (1).png"
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
        image.filepath = "Z:/missing/Diffuse.png"
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        mat["max_bitmap"] = "Diffuse"
        linked, missing = max_import.relink_textures([mat], [self.tmp.name])
        self.assertEqual(linked, ["Diffuse"])
        self.assertFalse(missing)
        self.assertEqual(pathlib.Path(node.image.filepath), path)
        self.assertIsNone(max_import._find_image({"diffused": "wrong.png"}, "Diffuse"))
        print("VERIFIED missing texture relink: existing image node and renamed copy, no fuzzy substitution", flush=True)

    def test_relink_operator_image_only_material(self):
        for material in list(bpy.data.materials):
            bpy.data.materials.remove(material, do_unlink=True)
        mat = bpy.data.materials.new("FBX Paint")
        mat.use_nodes = True
        image = bpy.data.images.new("FBX Diffuse", 2, 2)
        path = pathlib.Path(self.tmp.name) / "FBX Diffuse.png"
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
        image.source = "FILE"
        image.filepath = "Z:/missing/FBX Diffuse.png"
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        self.assertNotIn("max_bitmap", mat)
        self.assertEqual(bpy.ops.max.relink_textures(directory=self.tmp.name), {"FINISHED"})
        self.assertEqual(pathlib.Path(node.image.filepath), path)
        self.assertEqual(len(node.image.pixels), 16)
        print("VERIFIED public relink operator repairs image-only FBX material without max_bitmap", flush=True)

    def test_reader_material_name_and_bitmap_suffix(self):
        from notuodesk_3ds_maxxed import max_reader
        mat = bpy.data.materials.new("04___Default_Albedo 1")
        max_reader.restore_material_names([mat], ["04___Default"])
        self.assertEqual(mat.name, "04___Default")
        self.assertEqual(mat["max_bitmap"], "Albedo 1")

    def test_embedded_media_and_material_name(self):
        from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
        from io_scene_fbx import parse_fbx
        ob = self.cube()
        mat = bpy.data.materials.new("Brushed___steel")
        mat.use_nodes = True
        ob.data.materials.append(mat)
        image = bpy.data.images.new("Steel", 2, 2)
        image.filepath_raw = str(pathlib.Path(self.tmp.name) / "steel.png")
        image.file_format = "PNG"
        image.save()
        image.source = "FILE"
        PrincipledBSDFWrapper(mat, is_readonly=False).base_color_texture.image = image
        path = str(pathlib.Path(self.tmp.name) / "media.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False, embed_media=True), {"FINISHED"})
        root, _ = parse_fbx.parse(path)
        objects = next(e for e in root.elems if e.id == b"Objects")
        videos = [e for e in objects.elems if e.id == b"Video"]
        self.assertEqual(len(videos), 1)
        content = next(e.props[0] for e in videos[0].elems if e.id == b"Content")
        self.assertEqual(content, (pathlib.Path(self.tmp.name) / "steel.png").read_bytes())
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.materials.remove(mat)
        bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        self.assertEqual(bpy.context.scene.objects["Box001"].data.materials[0].name, "Brushed___steel")
        print("VERIFIED media embedded byte-for-byte and material name preserved", flush=True)

    def test_scene_units_reused_and_non_meter_scene(self):
        ob = self.cube()
        scene = bpy.context.scene
        scene.max_system_units = "MILLIMETERS"
        scene.unit_settings.scale_length = 0.01
        path = str(pathlib.Path(self.tmp.name) / "scene-units.fbx")
        self.assertEqual(bpy.ops.max.export_max_fbx(filepath=path, animation=False), {"FINISHED"})
        self.assertEqual(scene.max_system_units, "MILLIMETERS")
        self.assertAlmostEqual(scene.unit_settings.scale_length, 0.01)
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        self.assertAlmostEqual(bpy.context.scene.objects["Box001"].dimensions.x, 2.0, places=5)
        self.assertEqual(scene.max_system_units, "MILLIMETERS")
        print("VERIFIED shared System Units and centimeter Blender scene scale", flush=True)

    def test_animated_transform(self):
        ob = self.cube()
        scene = bpy.context.scene
        scene.frame_start, scene.frame_end = 1, 3
        ob.location = (1, 2, 3)
        ob.keyframe_insert(data_path="location", frame=1)
        ob.location = (5, 2, 3)
        ob.keyframe_insert(data_path="location", frame=3)
        scene.frame_set(1)
        path = str(pathlib.Path(self.tmp.name) / "animation.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, units="FEET", animation=True), {"FINISHED"})
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.max.import_max_fbx(filepath=path, animation=True)
        for frame, x in ((1, 1), (3, 5)):
            scene.frame_set(frame)
            self.assertAlmostEqual(scene.objects["Box001"].matrix_world.translation.x, x, places=5)
        print("VERIFIED baked animation endpoints across FBX unit conversion", flush=True)

    def test_units_metadata_and_roundtrip(self):
        from io_scene_fbx import parse_fbx
        for units, cm in [("INCHES", 2.54), ("CENTIMETERS", 1.0), ("MILLIMETERS", 0.1),
                          ("FEET", 30.48), ("METERS", 100.0), ("GENERIC", 100.0)]:
            for ob in list(bpy.data.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            ob = self.cube()
            ob.location = (1, -2, 3)
            ob.rotation_euler = (0.2, 0.3, -0.4)
            ob.scale = (2, 3, 4)
            bpy.context.view_layer.update()
            before = ob.matrix_world.copy()
            path = str(pathlib.Path(self.tmp.name) / (units + ".fbx"))
            result = bpy.ops.max.export_max_fbx(filepath=path, units=units, animation=False)
            self.assertEqual(result, {"FINISHED"})
            tree, version = parse_fbx.parse(path)
            settings = next(e for e in tree.elems if e.id == b"GlobalSettings")
            props = next(e for e in settings.elems if e.id == b"Properties70")
            values = {p.props[0]: p.props[-1] for p in props.elems}
            self.assertAlmostEqual(values[b"UnitScaleFactor"], cm, places=5)
            self.assertEqual(values[b"UpAxis"], 2)
            self.assertEqual(values[b"UpAxisSign"], 1)
            self.assertEqual(bpy.context.scene.unit_settings.system, "METRIC")
            self.assertEqual(bpy.context.scene.unit_settings.scale_length, 1.0)
            bpy.data.objects.remove(ob, do_unlink=True)
            self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
            after = bpy.context.scene.objects["Box001"].matrix_world
            self.assertLess(max(abs(before[i][j]-after[i][j]) for i in range(4) for j in range(4)), 2e-5)
        print("VERIFIED unit metadata and transform roundtrip: all 6 system units", flush=True)

    def test_selected_hierarchy_camera_light_and_pivot(self):
        root = bpy.data.objects.new("Group001", None)
        bpy.context.collection.objects.link(root)
        root.location = (3, 4, 5)
        child = self.cube()
        child.parent = root
        child.location = (2, 1, 7)
        # An offset mesh exercises the object origin independently of its geometry.
        child.data.transform(Matrix.Translation((2, -1, 3)))
        camera = bpy.data.objects.new("Camera001", bpy.data.cameras.new("Camera001"))
        light = bpy.data.objects.new("Light001", bpy.data.lights.new("Light001", "POINT"))
        for ob in (camera, light):
            bpy.context.collection.objects.link(ob)
            ob.parent = root
            ob.location = (1, 2, 3)
        excluded = self.cube("Excluded")
        for ob in bpy.context.scene.objects:
            ob.select_set(ob != excluded)
        bpy.context.view_layer.update()
        before = {ob.name: ob.matrix_world.copy() for ob in (root, child, camera, light)}
        vertex = child.matrix_world @ child.data.vertices[0].co
        path = str(pathlib.Path(self.tmp.name) / "selected.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False), {"FINISHED"})
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        # Blender 5.0.1's bundled FBX light importer uses a removed Cycles property.
        # Keep the exporter check independent of that upstream importer failure.
        cycles_enabled = addon_utils.check("cycles")[1]
        if cycles_enabled:
            addon_utils.disable("cycles")
        try:
            bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        finally:
            if cycles_enabled:
                addon_utils.enable("cycles")
        self.assertEqual(set(bpy.context.scene.objects.keys()), set(before))
        for name, matrix in before.items():
            ob = bpy.context.scene.objects[name]
            self.assertLess(max(abs(matrix[i][j]-ob.matrix_world[i][j]) for i in range(4) for j in range(4)), 2e-5)
            if name != "Group001":
                self.assertEqual(ob.parent.name, "Group001")
        ob = bpy.context.scene.objects["Box001"]
        self.assertLess((ob.matrix_world @ ob.data.vertices[0].co - vertex).length, 2e-5)
        print("VERIFIED selected export: names, hierarchy, offset pivot, camera and light", flush=True)

    def evaluated_geometry(self, ob, matrix_world=None):
        bpy.context.view_layer.update()
        evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            matrix = evaluated.matrix_world if matrix_world is None else matrix_world
            return [matrix @ v.co for v in mesh.vertices], len(mesh.polygons)
        finally:
            evaluated.to_mesh_clear()

    def assert_geometry_matches(self, before, ob, matrix_world=None):
        vertices, faces = self.evaluated_geometry(ob, matrix_world)
        self.assertEqual(faces, before[1])
        self.assertEqual(len(vertices), len(before[0]))
        # FBX may reorder vertices. Compare positions in both directions instead of indices.
        for source, target in ((before[0], vertices), (vertices, before[0])):
            tree = KDTree(len(target))
            for i, vertex in enumerate(target):
                tree.insert(vertex, i)
            tree.balance()
            self.assertLess(max(tree.find(vertex)[2] for vertex in source), 2e-5)

    def test_subdivision_followed_by_shell_bakes_shape(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            with self.subTest(export=export.idname()):
                ob = self.cube()
                sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
                sub.levels = sub.render_levels = 2
                shell = ob.modifiers.new("Shell", "SOLIDIFY")
                shell.thickness = 0.4
                before = self.evaluated_geometry(ob)
                safe = self.cube("Editable001")
                safe_sub = safe.modifiers.new("TurboSmooth", "SUBSURF")
                safe_sub.levels = safe_sub.render_levels = 1
                safe_before = self.evaluated_geometry(safe)
                ob.select_set(True)
                path = str(pathlib.Path(self.tmp.name) / "shell.fbx")
                self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
                self.assertEqual([m.type for m in ob.modifiers], ["SUBSURF", "SOLIDIFY"])
                self.assertEqual(sub.levels, 2)
                self.assertAlmostEqual(shell.thickness, 0.4)
                self.assert_geometry_matches(before, ob)
                self.assertEqual(safe_sub.levels, 1)
                self.assert_geometry_matches(safe_before, safe)
                bpy.data.objects.remove(ob, do_unlink=True)
                bpy.data.objects.remove(safe, do_unlink=True)
                bpy.ops.max.import_max_fbx(filepath=path, animation=False)
                imported = bpy.context.scene.objects["Box001"]
                self.assert_geometry_matches(before, imported)
                self.assertFalse(any(m.type == "SUBSURF" for m in imported.modifiers))
                bpy.data.objects.remove(imported, do_unlink=True)
                imported_safe = bpy.context.scene.objects["Editable001"]
                self.assert_geometry_matches(safe_before, imported_safe)
                self.assertFalse(any(m.type == "SUBSURF" for m in imported_safe.modifiers))
                bpy.data.objects.remove(imported_safe, do_unlink=True)
        print("VERIFIED TurboSmooth then Shell: both export operators bake matching evaluated vertices within 2e-5", flush=True)

    def test_collection_instance_subdivision_roundtrip(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for linked, nested, trailing_shell in ((True, False, True), (False, False, True), (False, True, True),
                                                   (True, False, False), (False, False, False), (False, True, False)):
                with self.subTest(export=export.idname(), source_in_scene=linked, nested=nested, shell=trailing_shell):
                    for ob in list(bpy.data.objects):
                        bpy.data.objects.remove(ob, do_unlink=True)
                    source = self.cube("InstanceBox")
                    collection = bpy.data.collections.new("InstanceSource")
                    collection.objects.link(source)
                    for owner in list(source.users_collection):
                        if owner != collection:
                            owner.objects.unlink(source)
                    if linked:
                        bpy.context.scene.collection.children.link(collection)
                    sub = source.modifiers.new("TurboSmooth", "SUBSURF")
                    sub.levels = sub.render_levels = 2
                    if trailing_shell:
                        shell = source.modifiers.new("Shell", "SOLIDIFY")
                        shell.thickness = 0.4
                    if nested:
                        outer = bpy.data.collections.new("OuterSource")
                        outer.children.link(collection)
                        collection = outer
                    instance = bpy.data.objects.new("Instance001", None)
                    instance.instance_type = "COLLECTION"
                    instance.instance_collection = collection
                    instance.location = (3, -2, 1)
                    instance_position = instance.location.copy()
                    bpy.context.collection.objects.link(instance)
                    bpy.context.view_layer.update()
                    for ob in bpy.context.view_layer.objects:
                        ob.select_set(ob == instance)
                    bpy.context.view_layer.update()
                    graph = bpy.context.evaluated_depsgraph_get()
                    instance_matrix = next(i.matrix_world.copy() for i in graph.object_instances
                                           if i.is_instance and i.object.original == source)
                    before = self.evaluated_geometry(source, instance_matrix)
                    path = str(pathlib.Path(self.tmp.name) / "instance.fbx")
                    self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
                    self.assertEqual([m.type for m in source.modifiers],
                                     ["SUBSURF", "SOLIDIFY"] if trailing_shell else ["SUBSURF"])
                    self.assertEqual(sub.levels, 2)
                    if trailing_shell:
                        self.assertAlmostEqual(shell.thickness, 0.4)
                    self.assertEqual(instance.instance_collection, collection)
                    self.assert_geometry_matches(before, source, matrix_world=instance_matrix)
                    for ob in list(bpy.data.objects):
                        bpy.data.objects.remove(ob, do_unlink=True)
                    self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
                    # Scene export also includes the linked source at its original position.
                    imported = next(ob for ob in bpy.context.scene.objects if ob.type == "MESH"
                                    and (ob.matrix_world.translation - instance_position).length < 2e-5)
                    self.assert_geometry_matches(before, imported)
                    self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers), 0)
                    print(f"VERIFIED collection instance: {export.idname()}, source_in_scene={linked}, "
                          f"nested={nested}, trailing_shell={trailing_shell}, evaluated geometry within 2e-5", flush=True)

    def test_converted_curve_and_text_subdivision_bakes_shape(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for kind in ("CURVE", "FONT"):
                for trailing_shell in (False, True):
                    with self.subTest(export=export.idname(), type=kind, shell=trailing_shell):
                        for ob in list(bpy.data.objects):
                            bpy.data.objects.remove(ob, do_unlink=True)
                        if kind == "CURVE":
                            bpy.ops.curve.primitive_bezier_circle_add()
                        else:
                            bpy.ops.object.text_add()
                            bpy.context.object.data.body = "Max"
                        ob = bpy.context.object
                        ob.name = "Converted001"
                        ob.data.extrude = 0.2
                        sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
                        sub.levels = sub.render_levels = 1
                        if trailing_shell:
                            shell = ob.modifiers.new("Shell", "SOLIDIFY")
                            shell.thickness = 0.4
                        before = self.evaluated_geometry(ob)
                        path = str(pathlib.Path(self.tmp.name) / "converted.fbx")
                        self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
                        self.assertEqual(ob.type, kind)
                        self.assertEqual(sub.levels, 1)
                        self.assertEqual(len(ob.modifiers), 2 if trailing_shell else 1)
                        self.assert_geometry_matches(before, ob)
                        bpy.data.objects.remove(ob, do_unlink=True)
                        self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
                        imported = bpy.context.scene.objects["Converted001"]
                        self.assert_geometry_matches(before, imported)
                        self.assertFalse(any(m.type == "SUBSURF" for m in imported.modifiers))
                        print(f"VERIFIED converted {kind}: {export.idname()}, trailing_shell={trailing_shell}, "
                              "evaluated geometry within 2e-5", flush=True)

    def test_bake_ignores_disabled_trailing_modifier(self):
        ob = self.cube()
        sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
        sub.levels = sub.render_levels = 1
        shell = ob.modifiers.new("Shell", "SOLIDIFY")
        shell.show_viewport = shell.show_render = False
        before = self.evaluated_geometry(ob)
        path = str(pathlib.Path(self.tmp.name) / "disabled-shell.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False), {"FINISHED"})
        self.assertFalse(shell.show_viewport or shell.show_render)
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        imported = bpy.context.scene.objects["Box001"]
        self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers), 0)
        self.assert_geometry_matches(before, imported)
        print("VERIFIED evaluated bake ignores disabled trailing Shell", flush=True)

    def test_selected_bake_excludes_unselected_stack(self):
        unsafe = self.cube("Excluded")
        unsafe.modifiers.new("TurboSmooth", "SUBSURF")
        unsafe.modifiers.new("Shell", "SOLIDIFY")
        ob = self.cube()
        sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
        sub.levels = sub.render_levels = 1
        before = self.evaluated_geometry(ob)
        self.assertFalse(unsafe.select_get())
        path = str(pathlib.Path(self.tmp.name) / "selected-subdivision.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False), {"FINISHED"})
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        imported = bpy.context.scene.objects["Box001"]
        self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers), 0)
        self.assert_geometry_matches(before, imported)
        print("VERIFIED selected bake excludes unselected stack", flush=True)

    def test_selected_bake_excludes_unselected_instance(self):
        source = self.cube("ExcludedInstanceSource")
        source.modifiers.new("TurboSmooth", "SUBSURF")
        source.modifiers.new("Shell", "SOLIDIFY")
        collection = bpy.data.collections.new("ExcludedSource")
        collection.objects.link(source)
        for owner in list(source.users_collection):
            if owner != collection:
                owner.objects.unlink(source)
        instance = bpy.data.objects.new("ExcludedInstance", None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = collection
        bpy.context.collection.objects.link(instance)
        ob = self.cube()
        sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
        sub.levels = sub.render_levels = 1
        before = self.evaluated_geometry(ob)
        self.assertEqual(list(bpy.context.selected_objects), [ob])
        path = str(pathlib.Path(self.tmp.name) / "selected-instance-scope.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False), {"FINISHED"})
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
        self.assertEqual(set(bpy.context.scene.objects.keys()), {"Box001"})
        imported = bpy.context.scene.objects["Box001"]
        self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers), 0)
        self.assert_geometry_matches(before, imported)
        print("VERIFIED selected bake excludes unselected collection instance", flush=True)

    def test_failed_export_restores_units(self):
        self.cube()
        bpy.context.scene.unit_settings.system = "IMPERIAL"
        bpy.context.scene.unit_settings.scale_length = 0.01
        from io_scene_fbx import export_fbx_bin
        with patch.object(export_fbx_bin, "save", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                bpy.ops.max.export_max_fbx(filepath=str(pathlib.Path(self.tmp.name) / "fail.fbx"), units="FEET")
        self.assertEqual(bpy.context.scene.unit_settings.system, "IMPERIAL")
        self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length, 0.01)

    def clear_objects(self):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)

    def posed_mesh(self):
        self.clear_objects()
        ob = self.cube("PosedMesh")
        bpy.ops.object.armature_add()
        rig = bpy.context.object
        rig.name = "SourceRig"
        bpy.ops.object.mode_set(mode="EDIT")
        lower = rig.data.edit_bones[0]
        lower.head, lower.tail = (0, 0, -1), (0, 0, 0)
        upper = rig.data.edit_bones.new("Top")
        upper.head, upper.tail, upper.parent = (0, 0, 0), (0, 0, 1), lower
        bpy.ops.object.mode_set(mode="OBJECT")
        for name in ("Bone", "Top"):
            group = ob.vertex_groups.new(name=name)
            group.add([v.index for v in ob.data.vertices if (v.co.z > 0) == (name == "Top")], 1, "REPLACE")
        arm = ob.modifiers.new("Skin", "ARMATURE")
        arm.object = rig
        sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
        sub.levels = sub.render_levels = 2
        rig.pose.bones["Top"].rotation_mode = "XYZ"
        rig.pose.bones["Top"].rotation_euler.y = 0.8
        ob.select_set(True)
        bpy.context.view_layer.update()
        return ob, rig

    def test_posed_armature_before_subdivision_bakes_current_pose(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for animation in (False, True):
                with self.subTest(export=export.idname(), animation=animation):
                    ob, rig = self.posed_mesh()
                    before = self.evaluated_geometry(ob)
                    state = self.export_state()
                    path = str(pathlib.Path(self.tmp.name) / "posed.fbx")
                    self.assertEqual(export(filepath=path, animation=animation), {"FINISHED"})
                    self.assertEqual(rig.data.pose_position, "POSE")
                    self.assertEqual(state, self.export_state())
                    self.assert_geometry_matches(before, ob)
                    self.clear_objects()
                    self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=animation), {"FINISHED"})
                    self.assert_geometry_matches(before, bpy.data.objects["PosedMesh"])
        print("VERIFIED posed Armature before TurboSmooth: both operators and animation settings match current evaluated pose", flush=True)

    def test_mesh_evaluation_failure_restores_source_rig(self):
        from io_scene_fbx import export_fbx_bin
        from notuodesk_3ds_maxxed import max_export

        class Proxy:
            def __init__(self, base, **overrides):
                self.base, self.overrides = base, overrides

            def __getattr__(self, name):
                return self.overrides.get(name, getattr(self.base, name))

        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for failure_at in (1, 2):
                with self.subTest(export=export.idname(), failure_at=failure_at):
                    ob, rig = self.posed_mesh()
                    self.cube("SecondMesh")
                    ob.select_set(True)
                    before = self.evaluated_geometry(ob)
                    state = self.export_state()
                    mesh_ids = set(bpy.data.meshes)
                    new_mesh = bpy.data.meshes.new_from_object
                    calls = 0

                    def fail_mesh(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == failure_at:
                            raise RuntimeError("injected mesh evaluation failure")
                        return new_mesh(*args, **kwargs)

                    proxy = Proxy(bpy, data=Proxy(bpy.data, meshes=Proxy(bpy.data.meshes, new_from_object=fail_mesh)))
                    # Before the fix this reaches native FBX after its real POSE -> REST change.
                    # After the fix the same failure reaches the wrapper's evaluated bake.
                    with patch.object(export_fbx_bin, "bpy", proxy), patch.object(max_export, "bpy", proxy):
                        with self.assertRaises(RuntimeError):
                            export(filepath=str(pathlib.Path(self.tmp.name) / "failure.fbx"), animation=False)
                    self.assertEqual(rig.data.pose_position, "POSE")
                    self.assertEqual(state, self.export_state())
                    self.assertEqual(set(bpy.data.meshes), mesh_ids)
                    self.assertEqual(ob.modifiers[0].object, rig)
                    self.assert_geometry_matches(before, ob)
        print("VERIFIED evaluation failure: both public operators restore source rig, data, modifiers and scene state", flush=True)

    def test_unwritable_bake_restores_pose_mode_and_complete_state(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            with self.subTest(export=export.idname()):
                ob, rig = self.posed_mesh()
                bpy.context.view_layer.objects.active = rig
                bpy.ops.object.mode_set(mode="POSE")
                bpy.context.scene.frame_set(2, subframe=0.375)
                before = self.evaluated_geometry(ob)
                state = self.export_state()
                mesh_ids = set(bpy.data.meshes)
                path = pathlib.Path(self.tmp.name) / "directory.fbx"
                path.mkdir(exist_ok=True)
                with self.assertRaises(RuntimeError):
                    export(filepath=str(path), units="FEET", animation=True)
                self.assertEqual(state, self.export_state())
                self.assertEqual(set(bpy.data.meshes), mesh_ids)
                self.assert_geometry_matches(before, ob)
                bpy.ops.object.mode_set(mode="OBJECT")
        print("VERIFIED real write failures restore pose mode, subframe, units, mesh data, rig and modifiers through both operators", flush=True)

    def mesh_signature(self, ob):
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = ob.evaluated_get(graph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        try:
            matrix = evaluated.matrix_world
            normals = matrix.to_3x3().inverted().transposed()
            return (len(mesh.edges), [(matrix @ mesh.vertices[loop.vertex_index].co,
                                      (normals @ mesh.corner_normals[i].vector).normalized())
                                     for i, loop in enumerate(mesh.loops)])
        finally:
            evaluated.to_mesh_clear()

    def test_baked_loose_edges_parent_inverse_and_flat_normals(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in ("LOOSE_EDGES", "PARENT_INVERSE", "FLAT_NORMALS"):
                with self.subTest(export=export.idname(), case=case):
                    self.clear_objects()
                    ob = self.cube("ReviewSource")
                    ob.data.vertices[0].co.x -= 0.37
                    if case == "LOOSE_EDGES":
                        mesh = bpy.data.meshes.new("Loose")
                        mesh.from_pydata([tuple(v.co) for v in ob.data.vertices] + [(4, 0, 0), (5, 0, 0)],
                                         [(8, 9)], [tuple(p.vertices) for p in ob.data.polygons])
                        ob.data = mesh
                    if case == "PARENT_INVERSE":
                        parent = bpy.data.objects.new("Parent", None)
                        bpy.context.collection.objects.link(parent)
                        parent.scale = (2, 0.7, 1.3)
                        parent.rotation_euler = (0.2, 0.4, 0.7)
                        ob.parent = parent
                        ob.location = (1, 2, 0.3)
                        ob.rotation_euler = (0.7, 0.3, 0.1)
                        bpy.context.view_layer.update()
                        ob.matrix_parent_inverse = parent.matrix_world.inverted()
                        parent.select_set(True)
                    sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
                    sub.levels = sub.render_levels = 2
                    before = self.evaluated_geometry(ob)
                    edges, corners = self.mesh_signature(ob)
                    path = str(pathlib.Path(self.tmp.name) / (case + ".fbx"))
                    self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
                    self.assert_geometry_matches(before, ob)
                    self.clear_objects()
                    self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
                    imported = bpy.data.objects["ReviewSource"]
                    self.assert_geometry_matches(before, imported)
                    after_edges, after_corners = self.mesh_signature(imported)
                    self.assertEqual(edges, after_edges)
                    self.assertEqual(len(imported.modifiers), 0)
                    for source, target in ((corners, after_corners), (after_corners, corners)):
                        tree = KDTree(len(target))
                        for i, (position, _normal) in enumerate(target):
                            tree.insert(position, i)
                        tree.balance()
                        for position, normal in source:
                            matches = tree.find_range(position, 3e-5)
                            self.assertTrue(matches)
                            self.assertLess(min((normal - target[i][1]).length for _, i, _ in matches), 1e-4)
                    print(f"VERIFIED baked {case}: {export.idname()} vertices/faces/edges and corner normals match evaluated scene", flush=True)

    def subdivision_fixture(self, case):
        """Independent evaluated geometry fixtures for the baked export."""
        self.clear_objects()
        if case == "CURVE":
            bpy.ops.curve.primitive_bezier_circle_add()
        elif case == "FONT":
            bpy.ops.object.text_add()
            bpy.context.object.data.body = "Max"
        elif case == "SURFACE":
            bpy.ops.surface.primitive_nurbs_surface_surface_add()
            bpy.context.object.data.splines[0].points[5].co.z = 0.7
        elif case == "META":
            bpy.ops.object.metaball_add()
            bpy.context.object.data.resolution = 0.4
        elif case.startswith("BOUNDARY"):
            bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3)
            bpy.context.object.data.vertices[0].co.z = 0.7
        else:
            self.cube()
        ob = bpy.context.object
        ob.name = "MatrixSource"
        if ob.type in {"CURVE", "FONT"}:
            ob.data.extrude = 0.2
            ob.data.resolution_u = 4
        sub = None
        if case not in {"META", "PLAIN"}:
            sub = ob.modifiers.new("TurboSmooth", "SUBSURF")
            sub.levels = sub.render_levels = 2
        if case == "SHELL" or case == "HIDDEN_SHELL":
            ob.modifiers.new("Shell", "SOLIDIFY").thickness = 0.4
        elif case == "MULTIPLE":
            other = ob.modifiers.new("Second subdivision", "SUBSURF")
            other.levels = other.render_levels = 1
        elif case == "PREFIX":
            mirror = ob.modifiers.new("Mirror", "MIRROR")
            mirror.use_mirror_merge = False
            bpy.ops.object.modifier_move_up(modifier=mirror.name)
        elif case == "DISABLED_TRAILING":
            shell = ob.modifiers.new("Shell", "SOLIDIFY")
            shell.show_viewport = shell.show_render = False
        elif case == "SIMPLE":
            sub.subdivision_type = "SIMPLE"
        elif case == "LIMIT_OFF":
            sub.use_limit_surface = False
        elif case == "QUALITY":
            sub.quality = 1
        elif case == "UNEQUAL_LEVELS":
            sub.render_levels = 1
        elif case == "VIEWPORT_ONLY":
            sub.show_render = False
        elif case == "RENDER_ONLY":
            sub.show_viewport = False
        elif case == "CUSTOM_NORMALS":
            sub.use_custom_normals = True
        elif case.startswith("UV_"):
            sub.uv_smooth = case[3:]
        elif case == "BOUNDARY_CORNERS":
            sub.boundary_smooth = "PRESERVE_CORNERS"
        if case in {"CREASES_ON", "CREASES_OFF", "VERTEX_CREASE", "CREASES_OFF_ZERO"}:
            attr = ob.data.attributes.new("crease_vert" if case == "VERTEX_CREASE" else "crease_edge",
                                          "FLOAT", "POINT" if case == "VERTEX_CREASE" else "EDGE")
            for value in attr.data:
                value.value = 0 if case == "CREASES_OFF_ZERO" else 0.7
        if case in {"CREASES_OFF", "CREASES_OFF_ZERO", "CREASES_OFF_EMPTY"}:
            sub.use_creases = False
        targets = [(ob.name, self.evaluated_geometry(ob))]
        if case.startswith("LINKED_"):
            linked = bpy.data.objects.new("LinkedSource", ob.data)
            bpy.context.collection.objects.link(linked)
            linked.location.x = 4
            if case != "LINKED_NONE":
                mod = linked.modifiers.new("TurboSmooth", "SUBSURF")
                mod.levels = mod.render_levels = 2 if case == "LINKED_EQUAL" else 1
            linked.select_set(True)
            targets.append((linked.name, self.evaluated_geometry(linked)))
        if case in {"HIDDEN_SHELL", "HIDDEN_MIXED", "HIDDEN_SAFE"}:
            ob.hide_viewport = True
        elif case == "HIDE_SET":
            ob.hide_set(True)
        elif case == "HIDE_RENDER":
            ob.hide_render = True
        if case == "HIDDEN_MIXED":
            bpy.ops.curve.primitive_bezier_circle_add()
            curve = bpy.context.object
            curve.name = "UnrelatedCurve"
            curve.data.extrude = 0.2
            mod = curve.modifiers.new("TurboSmooth", "SUBSURF")
            mod.levels = mod.render_levels = 1
            targets.append((curve.name, self.evaluated_geometry(curve)))
        if case in {"COLLECTION_HIDDEN", "LAYER_HIDDEN"}:
            collection = bpy.data.collections.new("HiddenExportCollection")
            bpy.context.scene.collection.children.link(collection)
            collection.objects.link(ob)
            for owner in list(ob.users_collection):
                if owner != collection:
                    owner.objects.unlink(ob)
            if case == "COLLECTION_HIDDEN":
                collection.hide_viewport = True
            else:
                bpy.context.view_layer.layer_collection.children[collection.name].hide_viewport = True
        bpy.context.view_layer.update()
        return targets

    def export_state(self):
        def props(owner):
            result = []
            for prop in owner.bl_rna.properties:
                if prop.type in {"BOOLEAN", "INT", "FLOAT", "ENUM", "STRING"}:
                    value = getattr(owner, prop.identifier)
                    result.append((prop.identifier, tuple(value) if getattr(prop, "is_array", False) else value))
            return result

        def layers(layer):
            return [(layer.name, layer.hide_viewport, layer.exclude)] + [
                item for child in layer.children for item in layers(child)]
        return ([(ob.name, ob.hide_viewport, ob.hide_render, ob.hide_get(), ob.select_get(),
                  ob.mode, ob.data.as_pointer() if ob.data else None,
                  tuple(tuple(row) for row in ob.matrix_world),
                  [props(m) for m in ob.modifiers])
                 for ob in bpy.data.objects],
                [(c.name, c.hide_viewport, c.hide_render) for c in bpy.data.collections],
                layers(bpy.context.view_layer.layer_collection),
                bpy.context.view_layer.objects.active,
                [(a.name, a.pose_position) for a in bpy.data.armatures],
                (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe),
                (bpy.context.scene.unit_settings.system, bpy.context.scene.unit_settings.scale_length))

    def subdivision_roundtrip(self, case, export):
        targets = self.subdivision_fixture(case)
        state = self.export_state()
        path = str(pathlib.Path(self.tmp.name) / (case + ".fbx"))
        # Explicit selection allows hidden sources to exercise the public EXEC path too.
        selected = list(bpy.context.scene.objects)
        with bpy.context.temp_override(selected_objects=selected):
            self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
        self.assertEqual(state, self.export_state(), "Export must restore all visibility and selection")
        # Remove fixture-only visibility barriers before checking the imported geometry.
        for c in bpy.data.collections:
            c.hide_viewport = False
        for layer in bpy.context.view_layer.layer_collection.children:
            layer.hide_viewport = False
        self.clear_objects()
        self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
        self.assertEqual({name for name, _ in targets}, set(bpy.context.scene.objects.keys()))
        for name, before in targets:
            imported = bpy.context.scene.objects[name]
            imported.hide_viewport = False
            imported.hide_set(False)
            self.assert_geometry_matches(before, imported)
            self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers), 0)

    def test_linked_subdivision_settings_roundtrip(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in ("LINKED_DIFFERENT", "LINKED_NONE", "LINKED_EQUAL"):
                with self.subTest(export=export.idname(), case=case):
                    self.subdivision_roundtrip(case, export)
        print("VERIFIED linked meshes bake independent evaluated geometry for equal/different/absent modifiers", flush=True)

    def test_disabled_objects_bake_evaluated_geometry(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in ("HIDDEN_SHELL", "HIDDEN_MIXED"):
                with self.subTest(export=export.idname(), case=case):
                    self.subdivision_roundtrip(case, export)
        print("VERIFIED disabled objects: Shell and unrelated Curve preserve evaluated geometry and visibility", flush=True)

    def test_unsupported_subdivision_settings_bake_shape(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in ("LIMIT_OFF", "CREASES_OFF"):
                with self.subTest(export=export.idname(), case=case):
                    self.subdivision_roundtrip(case, export)
        print("VERIFIED limit surface off and disabled nonzero creases bake matching geometry", flush=True)

    def test_subdivision_export_geometry_matrix(self):
        # Every row compares real evaluated geometry after both public export operators.
        cases = ("SAFE", "PLAIN", "SHELL", "MULTIPLE", "PREFIX", "DISABLED_TRAILING", "SIMPLE",
                 "QUALITY", "UNEQUAL_LEVELS", "VIEWPORT_ONLY", "RENDER_ONLY", "CUSTOM_NORMALS",
                 "UV_NONE", "UV_PRESERVE_CORNERS", "UV_PRESERVE_CORNERS_AND_JUNCTIONS", "UV_SMOOTH_ALL",
                 "BOUNDARY_ALL", "BOUNDARY_CORNERS", "CREASES_ON", "CREASES_OFF_EMPTY",
                 "CREASES_OFF_ZERO", "VERTEX_CREASE", "CURVE", "FONT", "SURFACE", "META",
                 "HIDDEN_SAFE", "HIDE_SET", "HIDE_RENDER", "COLLECTION_HIDDEN", "LAYER_HIDDEN")
        passed = 0
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in cases:
                print(f"MATRIX [{passed + 1}/{len(cases) * 2}] {export.idname()} {case}", flush=True)
                with self.subTest(export=export.idname(), case=case):
                    self.subdivision_roundtrip(case, export)
                    passed += 1
        print(f"VERIFIED subdivision geometry matrix: {passed}/{len(cases) * 2} real round trips within 2e-5", flush=True)

    def test_failed_export_restores_visibility_and_selection(self):
        from io_scene_fbx import export_fbx_bin
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for case in ("HIDDEN_SHELL", "HIDE_SET", "COLLECTION_HIDDEN", "LAYER_HIDDEN"):
                self.subdivision_fixture(case)
                state = self.export_state()
                def fail(*args, **kwargs):
                    self.assertTrue(bpy.data.objects["MatrixSource"].visible_get())
                    raise RuntimeError("injected visibility cleanup failure")
                with bpy.context.temp_override(selected_objects=list(bpy.context.scene.objects)):
                    with patch.object(export_fbx_bin, "save", side_effect=fail):
                        with self.assertRaises(RuntimeError):
                            export(filepath=str(pathlib.Path(self.tmp.name) / "fail.fbx"))
                self.assertEqual(state, self.export_state())
                for c in bpy.data.collections:
                    c.hide_viewport = False
                for layer in bpy.context.view_layer.layer_collection.children:
                    layer.hide_viewport = False
        print("VERIFIED failed exports restore visibility and selection through both operators", flush=True)

    def test_linked_instance_sources_and_selection_scope(self):
        for export in (bpy.ops.max.export_selected_fbx, bpy.ops.max.export_max_fbx):
            for hidden in (False, True):
                for equal in (False, True):
                    with self.subTest(export=export.idname(), hidden=hidden, equal=equal):
                        targets = self.subdivision_fixture("LINKED_EQUAL" if equal else "LINKED_DIFFERENT")
                        collection = bpy.data.collections.new("LinkedInstanceSources")
                        for name, _ in targets:
                            ob = bpy.data.objects[name]
                            collection.objects.link(ob)
                            for owner in list(ob.users_collection):
                                if owner != collection:
                                    owner.objects.unlink(ob)
                            ob.hide_viewport = hidden
                        instance = bpy.data.objects.new("InstanceCarrier", None)
                        instance.instance_type = "COLLECTION"
                        instance.instance_collection = collection
                        bpy.context.collection.objects.link(instance)
                        instance.select_set(True)
                        bpy.context.view_layer.update()
                        state = self.export_state()
                        path = str(pathlib.Path(self.tmp.name) / "linked-instance.fbx")
                        self.assertEqual(export(filepath=path, animation=False), {"FINISHED"})
                        self.assertEqual(state, self.export_state())
                        self.clear_objects()
                        self.assertEqual(bpy.ops.max.import_max_fbx(filepath=path, animation=False), {"FINISHED"})
                        meshes = [ob for ob in bpy.context.scene.objects if ob.type == "MESH"]
                        self.assertEqual(len(meshes), 2)
                        for name, before in targets:
                            # Native FBX names duplis after their carrier. Match the known origins.
                            origin_x = 4 if name == "LinkedSource" else 0
                            imported = next(ob for ob in meshes if abs(ob.matrix_world.translation.x - origin_x) < 2e-5)
                            imported.hide_viewport = False
                            imported.hide_set(False)
                            self.assert_geometry_matches(before, imported)
                            self.assertEqual(sum(m.type == "SUBSURF" for m in imported.modifiers),
                                             0)
        # An unselected linked object must not influence the exported geometry record.
        self.subdivision_fixture("LINKED_DIFFERENT")
        bpy.data.objects["LinkedSource"].select_set(False)
        source = bpy.data.objects["MatrixSource"]
        before = self.evaluated_geometry(source)
        path = str(pathlib.Path(self.tmp.name) / "selected-linked.fbx")
        self.assertEqual(bpy.ops.max.export_selected_fbx(filepath=path, animation=False), {"FINISHED"})
        self.clear_objects()
        bpy.ops.max.import_max_fbx(filepath=path, animation=False)
        self.assertEqual(set(bpy.context.scene.objects.keys()), {"MatrixSource"})
        self.assert_geometry_matches(before, bpy.data.objects["MatrixSource"])
        self.assertEqual(len(bpy.data.objects["MatrixSource"].modifiers), 0)
        print("VERIFIED linked instance sources, hidden source evaluation, and selected-only linked mesh scope", flush=True)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InterchangeTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
