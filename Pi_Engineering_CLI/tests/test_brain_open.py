from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_workspace import AgentSettings, ModelSettings, Workspace


class BrainOpenTests(unittest.TestCase):
    def test_high_ceilings_accepted(self):
        model = ModelSettings(
            provider="compat",
            endpoint="https://api.example.com/v1",
            model="any-open-model-id",
            token_env="MY_KEY",
            timeout=3600,
            context_chars=8000000,
            output_tokens=200000,
        )
        agent = AgentSettings(max_steps=10000, deadline_seconds=86400)
        self.assertEqual(model.model, "any-open-model-id")
        self.assertEqual(agent.max_steps, 10000)

    def test_make_model_routes_compat(self):
        from pi_models import OpenAICompatModel, make_model
        settings = ModelSettings(provider="compat", model="x", endpoint="https://api.example.com/v1")
        self.assertIsInstance(make_model(settings), OpenAICompatModel)

    def test_brain_set_via_workspace_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            config.model = ModelSettings(
                provider="grok",
                model="grok-4.6",
                endpoint="https://api.x.ai/v1",
                token_env="XAI_API_KEY",
                context_chars=500000,
                output_tokens=16384,
            )
            config.agents["engineer"] = config.agents["engineer"].model_copy(
                update={"max_steps": 128, "deadline_seconds": 7200}
            )
            workspace.save(config)
            loaded = workspace.config()
            self.assertEqual(loaded.model.provider, "grok")
            self.assertEqual(loaded.agents["engineer"].max_steps, 128)


if __name__ == "__main__":
    unittest.main()
