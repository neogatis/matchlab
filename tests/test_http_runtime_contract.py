import os
import unittest
from unittest.mock import patch

from app.http.server import API_PREFIX, _allowed_origins, _cookie_value
from app.security.http import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME


class HttpRuntimeContractTests(unittest.TestCase):
    def test_api_prefix_is_versioned(self):
        self.assertEqual(API_PREFIX, "/api/v1")

    def test_allowed_origins_are_fail_closed_and_normalized(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_allowed_origins(), set())

        with patch.dict(
            os.environ,
            {
                "PUBLIC_URL": "https://matchlab.example/",
                "ALLOWED_ORIGINS": "https://admin.example/, https://matchlab.example",
            },
            clear=True,
        ):
            self.assertEqual(
                _allowed_origins(),
                {"https://matchlab.example", "https://admin.example"},
            )

    def test_cookie_parser_returns_only_requested_cookie(self):
        header = (
            f"{SESSION_COOKIE_NAME}=selector.secret; "
            f"{CSRF_COOKIE_NAME}=csrf-value; other=ignored"
        )
        self.assertEqual(_cookie_value(header, SESSION_COOKIE_NAME), "selector.secret")
        self.assertEqual(_cookie_value(header, CSRF_COOKIE_NAME), "csrf-value")
        self.assertEqual(_cookie_value(header, "missing"), "")


if __name__ == "__main__":
    unittest.main()
