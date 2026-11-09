"""Load batch modules without installing the unfinished wave-2 package host."""
import importlib
import os
from pathlib import Path
import sys
import types

ROOT = Path(os.environ.get('MAXXED_REPO', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'tests'))
package = types.ModuleType('_maxxed_w11')
package.__path__ = [str(ROOT / 'notuodesk_3ds_maxxed')]
sys.modules.setdefault(package.__name__, package)


def load(name):
    return importlib.import_module(package.__name__ + '.' + name)


def evaluated(ob):
    import bpy
    bpy.context.view_layer.update()
    result = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = result.to_mesh()
    vertices = [tuple(v.co) for v in mesh.vertices]
    faces = [tuple(p.vertices) for p in mesh.polygons]
    smooth = [p.use_smooth for p in mesh.polygons]
    result.to_mesh_clear()
    return vertices, faces, smooth
