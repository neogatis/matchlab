import unittest
from types import SimpleNamespace

from app.console.web import photo_moderation_html
from app.push.service import safe_payload


class Phase30ModerationConsoleTests(unittest.TestCase):
    def test_console_uses_protected_admin_endpoints_and_csrf(self):
        html = photo_moderation_html()
        self.assertIn("/api/v1/admin/photos/pending", html)
        self.assertIn("/api/v1/admin/photos/moderate", html)
        self.assertIn("X-CSRF-Token", html)
        self.assertIn("credentials:\"same-origin\"", html)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", html)
        self.assertNotIn("FIREBASE_SERVICE_ACCOUNT_JSON", html)

    def test_photo_approved_push_is_private(self):
        title, body, data = safe_payload(
            SimpleNamespace(kind="PHOTO_APPROVED")
        )
        self.assertEqual(title, "MatchLab")
        self.assertEqual(body, "Ваше фото одобрено")
        self.assertEqual(data, {"kind": "PHOTO_APPROVED"})
        self.assertNotIn("user", body.lower())

    def test_photo_rejected_push_is_private(self):
        title, body, data = safe_payload(
            SimpleNamespace(kind="PHOTO_REJECTED")
        )
        self.assertEqual(title, "MatchLab")
        self.assertEqual(
            body,
            "Одно из фото не прошло модерацию",
        )
        self.assertEqual(data, {"kind": "PHOTO_REJECTED"})


if __name__ == "__main__":
    unittest.main()
