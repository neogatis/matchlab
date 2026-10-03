import unittest

from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    InvalidCsrf,
    InvalidOrigin,
    RequestTooLarge,
    SecurityError,
    new_csrf_token,
    parse_json_body,
    redact,
    validate_csrf,
    validate_origin,
)


class SecurityHttpTests(unittest.TestCase):
    def test_session_cookie_is_secure_httponly_and_samesite(self):
        header=SESSION_COOKIE.header("selector.secret")
        self.assertIn("Secure",header)
        self.assertIn("HttpOnly",header)
        self.assertIn("SameSite=Lax",header)
        self.assertIn("Path=/",header)

    def test_csrf_cookie_is_secure_and_script_readable_for_double_submit(self):
        header=CSRF_COOKIE.header("abc")
        self.assertIn("Secure",header)
        self.assertIn("SameSite=Strict",header)
        self.assertNotIn("HttpOnly",header)

    def test_cookie_header_rejects_injection(self):
        with self.assertRaises(SecurityError):
            SESSION_COOKIE.header("ok; injected=1")
        with self.assertRaises(SecurityError):
            SESSION_COOKIE.header("bad\r\nX-Test: 1")

    def test_csrf_requires_exact_nonempty_match(self):
        token=new_csrf_token()
        validate_csrf(token,token)
        with self.assertRaises(InvalidCsrf):
            validate_csrf(token,token+"x")
        with self.assertRaises(InvalidCsrf):
            validate_csrf("","")

    def test_origin_is_exact_allowlist_not_suffix_match(self):
        allowed={"https://matchlab.example"}
        validate_origin("https://matchlab.example",allowed_origins=allowed)
        with self.assertRaises(InvalidOrigin):
            validate_origin("https://matchlab.example.evil.test",allowed_origins=allowed)
        with self.assertRaises(InvalidOrigin):
            validate_origin(None,allowed_origins=allowed)

    def test_json_body_has_size_and_encoding_limits(self):
        self.assertEqual(parse_json_body(b'{"ok":true}'),{"ok":True})
        with self.assertRaises(RequestTooLarge):
            parse_json_body(b"x"*11,max_bytes=10)
        with self.assertRaises(SecurityError):
            parse_json_body(b"{not-json}")

    def test_redaction_is_recursive_and_does_not_mutate_safe_values(self):
        value={
            "email":"user@example.com",
            "password":"p",
            "nested":{
                "Authorization":"Bearer secret",
                "count":3,
                "api_key":"secret",
            },
            "items":[{"session_token":"x"},{"safe":"y"}],
        }
        result=redact(value)
        self.assertEqual(result["email"],"user@example.com")
        self.assertEqual(result["password"],"[REDACTED]")
        self.assertEqual(result["nested"]["Authorization"],"[REDACTED]")
        self.assertEqual(result["nested"]["api_key"],"[REDACTED]")
        self.assertEqual(result["nested"]["count"],3)
        self.assertEqual(result["items"][0]["session_token"],"[REDACTED]")


if __name__=="__main__":
    unittest.main()
