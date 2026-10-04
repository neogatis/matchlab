import json
import unittest
from pathlib import Path

from app.release import (
    REQUIRED_CAPABILITIES,
    current_matchlab_readiness,
    evaluate_store_readiness,
)


ROOT = Path(__file__).resolve().parents[1]


class StoreReadinessTests(unittest.TestCase):
    def test_fail_closed_when_capability_is_missing(self):
        result=evaluate_store_readiness({})
        self.assertFalse(result.ready)
        self.assertEqual(set(result.blockers),set(REQUIRED_CAPABILITIES))
        self.assertEqual(result.completion_percent,0)

    def test_ready_only_when_every_required_capability_is_true(self):
        capabilities={key:True for key in REQUIRED_CAPABILITIES}
        result=evaluate_store_readiness(capabilities)
        self.assertTrue(result.ready)
        self.assertEqual(result.blockers,())
        self.assertEqual(result.completion_percent,100)

    def test_unknown_capabilities_do_not_hide_required_blockers(self):
        result=evaluate_store_readiness({"something_else":True})
        self.assertFalse(result.ready)
        self.assertEqual(result.completion_percent,0)

    def test_current_project_does_not_claim_store_ready(self):
        result=current_matchlab_readiness()
        self.assertFalse(result.ready)
        self.assertIn("ios_build_pipeline",result.blockers)
        self.assertIn("android_build_pipeline",result.blockers)
        self.assertIn("push_provider_delivery",result.blockers)
        self.assertIn("billing_provider_verification",result.blockers)

    def test_existing_safety_foundations_are_recognized(self):
        result=current_matchlab_readiness()
        self.assertIn("photo_moderation",result.completed)
        self.assertIn("block_and_report",result.completed)

    def test_phase26_privacy_foundations_are_recognized(self):
        result=current_matchlab_readiness()
        self.assertIn("account_deletion_flow",result.completed)
        self.assertIn("data_export_flow",result.completed)
        self.assertIn("retention_policy",result.completed)

    def test_production_cutover_foundations_are_recognized(self):
        result=current_matchlab_readiness()
        self.assertIn("postgres_http_runtime",result.completed)
        self.assertIn("secure_http_boundary",result.completed)
        self.assertIn("privacy_policy_url",result.completed)
        self.assertIn("terms_url",result.completed)
        self.assertIn("photo_object_storage",result.completed)

    def test_manifest_matches_fail_closed_readiness(self):
        manifest=json.loads(
            (ROOT/"release"/"store_readiness.json").read_text(encoding="utf-8")
        )
        result=current_matchlab_readiness()
        self.assertEqual(bool(manifest["submission_ready"]),result.ready)
        self.assertEqual(manifest["minimum_age"],18)
        self.assertEqual(manifest["plans"],["FREE","PREMIUM","PREMIUM_PLUS"])
        self.assertIn("DEEP_COMPATIBILITY_REPORT",manifest["one_time_products"])

    def test_native_client_claims_match_current_platform_state(self):
        manifest=json.loads(
            (ROOT/"release"/"store_readiness.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["platforms"]["ios"]["native_client_present"])
        self.assertEqual(manifest["platforms"]["ios"]["bundle_id"],"com.neogatis.matchlab")
        self.assertTrue(manifest["platforms"]["android"]["native_client_present"])
        self.assertEqual(
            manifest["platforms"]["android"]["application_id"],
            "com.neogatis.matchlab",
        )


if __name__=="__main__":
    unittest.main()
