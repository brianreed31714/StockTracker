"""Read-only failure forensics never execute models, trades or pipeline stages."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from infrastructure.review_artifact_probe import probe


class ReviewArtifactProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/".env.config").write_text("LIVE_TRADING=false\n", encoding="utf-8")

    def test_uninstrumented_93_failures_not_assigned_fake_stage(self):
        (self.root/"post_close_review_state.json").write_text(
            json.dumps({"review_date":"2026-10-16", "status":"FAILED", "attempts":93,
                        "error":"daily review pipeline failed"}), encoding="utf-8")
        with patch.dict(os.environ, {"STOCKTRACKER_RUNTIME_ROOT": "", "OPENAI_API_KEY": ""}):
            output=probe(self.root,"2026-10-16")
        self.assertEqual(output["review_status"],"FAILED")
        self.assertEqual(output["attempts"],93)
        self.assertIsNone(output["failure_stage"])
        self.assertEqual(output["failure_error_text"],"REDACTED")
        self.assertEqual(output["side_effects"],"NONE")

    def test_artifacts_are_only_clues_not_confirmed_completion(self):
        base=self.root/"analysis"/"daily"/"2026-10-16"
        base.mkdir(parents=True)
        (base/"performance_input.json").write_text("{}")
        with patch.dict(os.environ, {"STOCKTRACKER_RUNTIME_ROOT": ""}):
            output=probe(self.root,"2026-10-16")
        self.assertEqual(output["artifacts"]["review_bundle"]["state"],"PRESENT")
        self.assertEqual(output["artifacts"]["ai_review"]["state"],"MISSING")
        self.assertIn("not proof", output["interpretation"])

    def test_external_runtime_root_is_reported_without_path(self):
        runtime=self.root.parent/(self.root.name+"_runtime")
        runtime.mkdir(exist_ok=True)
        self.addCleanup(lambda: runtime.rmdir() if runtime.exists() and not any(runtime.iterdir()) else None)
        (self.root/".env").write_text("STOCKTRACKER_RUNTIME_ROOT="+str(runtime)+"\n", encoding="utf-8")
        with patch.dict(os.environ, {"STOCKTRACKER_RUNTIME_ROOT": ""}):
            output=probe(self.root,"2026-10-16")
        self.assertTrue(output["runtime_external"])
        self.assertNotIn(str(runtime),json.dumps(output))

if __name__=="__main__":
    unittest.main()
