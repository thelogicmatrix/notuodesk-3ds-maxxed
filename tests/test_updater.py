"""Retired update routes. Run through run_checks.py tests test_updater."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tomllib
import unittest
from unittest.mock import patch

import bpy


PACKAGE = Path(__file__).resolve().parents[1] / "notuodesk_3ds_maxxed"
IDS = {"max.check_update", "max.install_update", "max.open_online_prefs"}


class UnreadSettings:
    def __getattribute__(self, name):
        raise AssertionError("Retirement accessed settings: " + name)


class RetirementLayout:
    def __init__(self):
        self.labels = []

    def box(self):
        return self

    def label(self, *, text, **kwargs):
        self.labels.append(text)


class UpdaterRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (PACKAGE / "updater.py").is_file(), "Replacement updater is missing"
        spec = importlib.util.spec_from_file_location("w16_retirement", PACKAGE / "updater.py")
        cls.updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.updater)

    def test_manifest_identity_and_capabilities(self):
        metadata = tomllib.loads((PACKAGE / "blender_manifest.toml").read_text(encoding="utf-8"))
        for key, expected in {
            "schema_version": "1.0.0", "id": "notuodesk_3ds_maxxed",
            "version": "1.8.0", "type": "add-on", "blender_version_min": "4.2.0",
            "license": ["SPDX:GPL-3.0-or-later"], "maintainer": "Nathan Wong",
        }.items():
            self.assertEqual(metadata[key], expected)
        self.assertEqual(set(metadata["permissions"]), {"files"})
        self.assertTrue(metadata["permissions"]["files"])
        self.assertLessEqual(len(metadata["permissions"]["files"]), 64)
        self.assertLessEqual(len(metadata["tagline"]), 64)
        self.assertFalse(metadata["tagline"].endswith("."))
        self.assertEqual(self.updater.current_version(), metadata["version"])
        print("W16 metadata identity, version, GPL and files-only permission PASS", flush=True)

    def test_all_routes_and_hooks_are_inert(self):
        import builtins
        import socket
        import threading
        import urllib.request

        updater = self.updater
        self.assertEqual({item.bl_idname for item in updater.classes}, IDS)
        files = (PACKAGE / "updater.py", PACKAGE / "blender_manifest.toml")
        before = [path.read_bytes() for path in files]
        reports = []
        receiver = SimpleNamespace(report=lambda level, message: reports.append((level, message)))
        layout = RetirementLayout()
        original_open = builtins.open

        def read_only(file, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"), "Attempted file write")
            return original_open(file, mode, *args, **kwargs)

        with patch("socket.socket", side_effect=AssertionError("Network attempted")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("Download attempted")), \
             patch("threading.Thread.start", side_effect=AssertionError("Thread started")), \
             patch.object(bpy.app.timers, "register", side_effect=AssertionError("Timer registered")), \
             patch("builtins.open", side_effect=read_only), \
             patch("os.replace", side_effect=AssertionError("File replaced")), \
             patch("os.remove", side_effect=AssertionError("File removed")):
            for _ in range(2):
                self.assertIsNone(updater.register_auto_check())
                self.assertEqual(updater.current_version(), "1.8.0")
                updater.draw_update_box(layout)
                updater.draw_update_box(layout, UnreadSettings())
                for item in updater.classes:
                    self.assertEqual(item.execute(receiver, UnreadSettings()), {"CANCELLED"})
        self.assertEqual(len(reports), 6)
        for level, message in reports:
            self.assertEqual(level, {"INFO"})
            self.assertIn("retired", message.lower())
            self.assertIn("preferences", message.lower())
        self.assertTrue(layout.labels)
        self.assertTrue(any("retired" in label.lower() for label in layout.labels))
        self.assertEqual(updater.status["state"], "RETIRED")
        self.assertFalse(updater.status["latest"])
        self.assertEqual([path.read_bytes() for path in files], before)
        print("W16 three routes, startup and drawing inert, settings opaque PASS", flush=True)

    def test_registration_cycles(self):
        for _ in range(2):
            registered = []
            try:
                for item in self.updater.classes:
                    bpy.utils.register_class(item)
                    registered.append(item)
                for identifier in sorted(IDS):
                    self.assertEqual(getattr(bpy.ops.max, identifier.split(".")[1])(), {"CANCELLED"})
            finally:
                for item in reversed(registered):
                    bpy.utils.unregister_class(item)
        print("W16 legacy operator registration and removal twice PASS", flush=True)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
