"""Original Max-style icons, owned by one preview collection."""

from pathlib import Path

import bpy.utils.previews

_collection = None
DIRECTORY = Path(__file__).with_name("icons")


def icon(name):
    """Return the custom icon ID, or zero when its artwork is unavailable."""
    preview = _collection.get(name) if _collection is not None else None
    return preview.icon_id if preview is not None else 0


def ui(name, fallback):
    """UILayout keyword arguments retaining the original Blender fallback."""
    value = icon(name)
    return {"icon_value": value} if value else {"icon": fallback}


def enum_items(items):
    """Enum buttons take custom IDs in their items, not prop_enum keywords."""
    return [(key, label, description, icon(key.lower()) or fallback, number)
            for key, label, description, fallback, number in items]


def register():
    global _collection
    if _collection is not None:
        return
    _collection = bpy.utils.previews.new()
    for source in sorted((DIRECTORY / "src").glob("*.svg")):
        # 64px artwork gives Blender enough pixels at doubled UI scale.
        path = DIRECTORY / (source.stem + "@2x.png")
        if not path.is_file():
            path = DIRECTORY / (source.stem + ".png")
        if path.is_file():
            try:
                preview = _collection.load(source.stem, str(path), "IMAGE")
                # Eager pixels avoid transparent lazy thumbnails during startup.
                pixels = preview.image_pixels_float[:]
                preview.icon_size = preview.image_size
                preview.icon_pixels_float = pixels
            except (OSError, RuntimeError) as exc:
                print(f"[3ds Maxxed] icon {source.stem}: {exc}")


def unregister():
    global _collection
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
