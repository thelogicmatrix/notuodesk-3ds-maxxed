"""Preference facade changes existing fields, never creates shadow settings."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from _w15_setup import bpy
from notuodesk_3ds_maxxed import get_prefs, max_preferences as preferences
preferences.install()


class PreferenceTests(unittest.TestCase):
    def test_draft_cancel_and_commit_preserve_hotkeys(self):
        prefs = get_prefs()
        before = prefs.show_labels
        hsx = prefs.imported_hsx
        tx = preferences.PreferenceDraft(prefs)
        tx.values["show_labels"] = not before
        tx.cancel()
        self.assertEqual(prefs.show_labels, before)
        tx = preferences.PreferenceDraft(prefs)
        tx.values["show_labels"] = not before
        tx.apply()
        self.assertEqual(prefs.show_labels, not before)
        self.assertEqual(prefs.imported_hsx, hsx)
        prefs.show_labels = before

    def test_no_settings_and_retired_fields(self):
        tx = preferences.PreferenceDraft(None)
        self.assertEqual(tx.values, {})
        tx.apply()
        self.assertNotIn("github_token", preferences.FIELDS)
        self.assertNotIn("update_repo", preferences.FIELDS)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
