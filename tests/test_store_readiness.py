import unittest

from app.release import (
    REQUIRED_CAPABILITIES,
    current_matchlab_readiness,
    evaluate_store_readiness,
)


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
        self.assertIn("postgres_http_runtime",result.blockers)
        self.assertIn("secure_http_boundary",result.blockers)
        self.assertIn("ios_build_pipeline",result.blockers)
        self.assertIn("android_build_pipeline",result.blockers)
        self.assertIn("data_export_flow",result.blockers)

    def test_existing_safety_foundations_are_recognized(self):
        result=current_matchlab_readiness()
        self.assertIn("photo_moderation",result.completed)
        self.assertIn("block_and_report",result.completed)


if __name__=="__main__":
    unittest.main()
