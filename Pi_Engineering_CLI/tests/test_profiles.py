from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_profile import apply_preset, export_recipe, list_presets, load_preset
from pi_workspace import Workspace


class ProfileTests(unittest.TestCase):
    def test_builtin_presets_exist(self):
        names = set(list_presets())
        self.assertEqual(names, {"developer", "hacker", "hardware", "cto"})

    def test_apply_preserves_existing_agents_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            original_role = config.agents["engineer"].role
            config, applied = apply_preset(config, "developer")
            self.assertIn("engineer", applied["skipped_agents"])
            self.assertEqual(config.agents["engineer"].role, original_role)

    def test_apply_replace_agents_overlays(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            config, applied = apply_preset(config, "hacker", replace_agents=True)
            self.assertIn("reviewer", applied["agents"])
            self.assertIn("Adversarial security review", config.agents["reviewer"].role)

    def test_hardware_profile_is_evidence_first(self):
        data, _ = load_preset("hardware")
        self.assertIn("wiring-harness engineers", data["audience"])
        self.assertIn("current capacity", data["agents"]["reviewer"]["role"])

    def test_export_recipe_has_no_secret_values(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            recipe = export_recipe(config)
            blob = json.dumps(recipe)
            self.assertIn("token_env", blob)
            self.assertNotIn("sk-", blob)
            self.assertEqual(recipe["kind"], "pi-engineering-recipe")

    def test_workflows_validate(self):
        from pi_workflow import load_plan
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            for name in ("review.json", "implement-review.json", "security-pass.json", "release-gate.json", "hardware-review.json"):
                path = ROOT / "workflows" / name
                load_plan(path, config)


if __name__ == "__main__":
    unittest.main()
