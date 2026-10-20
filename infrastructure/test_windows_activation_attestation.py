"""Fail-closed offline tests of Windows source sync and activation attestation."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from infrastructure import windows_activation_attestation as attest

T0 = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40


def good_snapshot(pid_base=500, started=None):
    started = (started or T0 - timedelta(minutes=7)).isoformat()
    components = {}
    for i, component in enumerate(attest.REQUIRED_PROCESSES):
        components[component] = {
            "process": {"state": "OBSERVED", "pids": [pid_base + i],
                        "started_utc": started, "script": component + ".py"},
            "script_version": {"state": "MATCHED"},
        }
    return {"components": components}


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_unmatched_or_dirty_code_cannot_claim_sync(self):
        snapshot = good_snapshot()
        for head, origin, clean in ((COMMIT, "b"*40, True), (COMMIT, COMMIT, False),
                                    ("", COMMIT, True)):
            state = attest.advance(self.root, {}, snapshot, head=head, upstream=origin,
                                   clean=clean, clock=T0)
            self.assertEqual(state["state"], "UNVERIFIED")
            self.assertFalse(state["code_synced"])
            self.assertFalse(state["processes_stable"])

    def test_duplicate_missing_and_old_version_never_verified(self):
        cases = []
        missing = good_snapshot()
        missing["components"]["trader"]["process"]["state"] = "UNKNOWN"
        cases.append(missing)
        duplicate = good_snapshot()
        duplicate["components"]["trader"]["process"]["pids"] = [1, 2]
        cases.append(duplicate)
        wrong = good_snapshot()
        wrong["components"]["geo_feed"]["script_version"]["state"] = "MISMATCH"
        cases.append(wrong)
        unproven = good_snapshot()
        unproven["components"]["trader"]["process"].pop("started_utc")
        cases.append(unproven)
        for snapshot in cases:
            state = attest.advance(self.root, {}, snapshot, head=COMMIT,
                                   upstream=COMMIT, clean=True, clock=T0)
            self.assertEqual(state["state"], "CODE_SYNCED_RUNTIME_UNVERIFIED")
            self.assertFalse(state["processes_stable"])

    def test_three_distinct_time_separated_stable_process_samples(self):
        snapshot = good_snapshot()
        a = attest.advance(self.root, {}, snapshot, head=COMMIT, upstream=COMMIT,
                           clean=True, clock=T0)
        b = attest.advance(self.root, a, snapshot, head=COMMIT, upstream=COMMIT,
                           clean=True, clock=T0 + timedelta(seconds=10))
        self.assertEqual(b["consecutive_observations"], 1)
        c = attest.advance(self.root, b, snapshot, head=COMMIT, upstream=COMMIT,
                           clean=True, clock=T0 + timedelta(seconds=40))
        self.assertEqual(c["consecutive_observations"], 2)
        d = attest.advance(self.root, c, snapshot, head=COMMIT, upstream=COMMIT,
                           clean=True, clock=T0 + timedelta(seconds=80))
        self.assertEqual(d["consecutive_observations"], 3)
        self.assertEqual(d["state"], "HOST_PROCESSES_STABLE_SOURCE_ONLY")
        self.assertFalse(d["eod_execution_verified"])
        self.assertEqual(d["first_seen_at_utc"], T0.isoformat())

    def test_recycled_pid_start_time_resets(self):
        snapshot = good_snapshot()
        a = attest.advance(self.root, {}, snapshot, head=COMMIT, upstream=COMMIT,
                           clean=True, clock=T0)
        next_sample = good_snapshot(started=T0.isoformat())
        b = attest.advance(self.root, a, next_sample, head=COMMIT,
                           upstream=COMMIT, clean=True, clock=T0 + timedelta(seconds=60))
        self.assertEqual(b["consecutive_observations"], 1)

    def test_no_eod_claim_until_artifacts_postdate_sync(self):
        day = "2026-10-19"
        state = self.root / "post_close_review_state.json"
        perf = self.root / "analysis/performance/latest.json"
        manifest = self.root / "analysis/evidence" / day / "manifest.json"
        perf.parent.mkdir(parents=True)
        manifest.parent.mkdir(parents=True)
        perf.write_text(json.dumps({
            "metrics": {"review_date": day, "paper_only": True,
                        "generated_at": (T0 + timedelta(seconds=15)).isoformat()},
            "review": {"review_date": day,
                       "generated_at": (T0 + timedelta(seconds=30)).isoformat()},
        }))
        manifest.write_text(json.dumps({
            "review_date": day, "paper_only": True, "sanitized": True,
            "source_database_present": True, "generated_at": (T0 + timedelta(seconds=20)).isoformat(),
            "integrity_analysis": {"status": "PASS"}}))
        state.write_text(json.dumps({"status": "COMPLETED", "review_date": day,
                         "finished_at": (T0 - timedelta(seconds=1)).isoformat()}))
        earlier = attest.review_after_sync(self.root, T0.isoformat(),
                                          clock=T0+timedelta(minutes=1))
        self.assertEqual(earlier["state"], "NOT_VERIFIED")
        state.write_text(json.dumps({"status": "COMPLETED", "review_date": day,
                         "finished_at": (T0 + timedelta(minutes=1)).isoformat()}))
        later = attest.review_after_sync(self.root, T0.isoformat(),
                                        clock=T0+timedelta(minutes=2))
        self.assertEqual(later, {"state": "VERIFIED", "review_date": day})

    def test_eod_report_must_have_matching_date(self):
        day = "2026-10-19"
        state = self.root / "post_close_review_state.json"
        perf = self.root / "analysis/performance/latest.json"
        manifest = self.root / "analysis/evidence" / day / "manifest.json"
        perf.parent.mkdir(parents=True)
        manifest.parent.mkdir(parents=True)
        perf.write_text(json.dumps({
            "metrics": {"review_date": "2026-10-18", "paper_only": True,
                        "generated_at": (T0 + timedelta(seconds=15)).isoformat()},
            "review": {"review_date": "2026-10-18",
                       "generated_at": (T0 + timedelta(seconds=30)).isoformat()},
        }))
        manifest.write_text(json.dumps({
            "review_date": day, "paper_only": True, "sanitized": True,
            "source_database_present": True, "generated_at": (T0 + timedelta(seconds=20)).isoformat(),
            "integrity_analysis": {"status": "PASS"}}))
        state.write_text(json.dumps({"status": "COMPLETED", "review_date": day,
                         "finished_at": (T0 + timedelta(minutes=1)).isoformat()}))
        result = attest.review_after_sync(self.root, T0.isoformat(),
                                          clock=T0+timedelta(minutes=2))
        self.assertEqual(result["state"], "NOT_VERIFIED")

    def test_eod_requires_fresh_matching_artifact_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = "2026-10-19"
            perf = root / "analysis/performance/latest.json"
            manifest = root / "analysis/evidence" / day / "manifest.json"
            perf.parent.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            (root / "post_close_review_state.json").write_text(json.dumps({
                "review_date": day, "status": "COMPLETED",
                "finished_at": (T0 + timedelta(minutes=1)).isoformat(),
            }))
            payload = {
                "metrics": {"review_date": day, "paper_only": True,
                            "generated_at": (T0 - timedelta(hours=1)).isoformat()},
                "review": {"review_date": day,
                           "generated_at": (T0 + timedelta(seconds=40)).isoformat()},
            }
            perf.write_text(json.dumps(payload))
            manifest.write_text(json.dumps({
                "review_date": day, "sanitized": True, "paper_only": True,
                "source_database_present": True,
                "integrity_analysis": {"status": "PASS"},
                "generated_at": (T0 + timedelta(seconds=20)).isoformat(),
            }))
            outcome = attest.review_after_sync(root, T0.isoformat(),
                                              clock=T0 + timedelta(minutes=2))
            self.assertEqual(outcome["reason"], "ARTIFACT_NOT_FROM_POST_SYNC_REVIEW")

    def test_notification_only_marks_success_when_api_accepts(self):
        called = []
        def accepted(title, body):
            called.append((title, body))
            return True
        with patch.object(attest, "git_head", return_value=COMMIT), \
             patch.object(attest, "_head", return_value=COMMIT), \
             patch.object(attest, "_code_clean", return_value=True):
            a = attest.poll(self.root, observation=good_snapshot(), clock=T0,
                            notify=accepted)
            b = attest.poll(self.root, observation=good_snapshot(),
                            clock=T0 + timedelta(seconds=60), notify=accepted)
        self.assertTrue(a["code_synced"])
        self.assertEqual(a["notification"], "API_ACCEPTED")
        self.assertEqual(len(called), 1)
        self.assertNotIn("EOD Verified", called[0][0])
        self.assertNotIn("pid", str(called).lower())
        self.assertEqual(b["notice_key"], a["notice_key"])

    def test_failed_notification_may_retry_without_spamming_success(self):
        attempts = []
        def flaky(*_):
            attempts.append(1)
            return len(attempts) == 2
        with patch.object(attest, "git_head", return_value=COMMIT), \
             patch.object(attest, "_head", return_value=COMMIT), \
             patch.object(attest, "_code_clean", return_value=True):
            first = attest.poll(self.root, observation=good_snapshot(),
                                clock=T0, notify=flaky)
            second = attest.poll(self.root, observation=good_snapshot(),
                                 clock=T0 + timedelta(seconds=60), notify=flaky)
            attest.poll(self.root, observation=good_snapshot(),
                        clock=T0 + timedelta(seconds=120), notify=flaky)
        self.assertEqual(first["notification"], "UNCONFIRMED")
        self.assertEqual(second["notification"], "API_ACCEPTED")
        self.assertEqual(len(attempts), 2)

    def test_agent_hook_is_windows_only_and_read_only(self):
        import inspect
        import stocktracker_deployment_agent as agent
        source = inspect.getsource(agent.scan_once)
        self.assertIn('if os.name == "nt":', source)
        self.assertIn("poll(ROOT, notify=push_attestation)", source)
        self.assertNotIn("stop_active(", source)


if __name__ == "__main__":
    unittest.main()
