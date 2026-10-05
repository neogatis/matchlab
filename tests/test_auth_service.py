import base64
import hashlib
import os
import secrets
import unittest
from datetime import timedelta

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.auth import service as auth
from app.db.models import AuthChallenge, MarketingAttribution, Session as DbSession, User


def legacy_hash(password: str) -> str:
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return base64.b64encode(salt + digest).decode()


class AuthServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            for table in [
                "auth_outbox","auth_challenges","auth_rate_limits","auth_identities",
                "sessions","profiles","user_status_history","marketing_attribution",
                "users"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))

    def test_register_hashes_with_argon2_and_normalizes_email(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "  Test.User@Example.COM ", "very-secure-password")
            db.commit()
            self.assertEqual(user.email, "test.user@example.com")
            self.assertTrue(user.password_hash.startswith("$argon2"))
            ok, rehash = auth.verify_password("very-secure-password", user.password_hash)
            self.assertTrue(ok)
            self.assertFalse(rehash)

    def test_registration_persists_first_touch_attribution(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(
                db,
                "utm@example.com",
                "very-secure-password",
                attribution={
                    "utm_source": "meta",
                    "utm_medium": "paid_social",
                    "utm_campaign": "almaty_launch",
                    "utm_content": "video_01",
                    "utm_term": "serious_dating",
                    "referral_input": "friend-code",
                },
            )
            db.commit()
            row = db.get(MarketingAttribution, user.id)
            self.assertEqual(row.utm_source, "meta")
            self.assertEqual(row.utm_medium, "paid_social")
            self.assertEqual(row.utm_campaign, "almaty_launch")
            self.assertEqual(row.utm_content, "video_01")
            self.assertEqual(row.utm_term, "serious_dating")
            self.assertEqual(row.referral_input, "friend-code")

    def test_legacy_password_is_transparently_upgraded(self):
        with Session(self.engine) as db:
            user = User(
                email="legacy@example.com",
                password_hash=legacy_hash("legacy-password"),
                referral_code="legacy-ref",
            )
            db.add(user); db.commit()
            old = user.password_hash

            logged_in = auth.authenticate_password(
                db, "legacy@example.com", "legacy-password", apply_rate_limit=False
            )
            db.commit()
            self.assertEqual(logged_in.id, user.id)
            self.assertNotEqual(logged_in.password_hash, old)
            self.assertTrue(logged_in.password_hash.startswith("$argon2"))

    def test_session_cookie_secret_is_not_stored_raw(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "session@example.com", "very-secure-password")
            cookie = auth.create_session(db, user.id, user_agent="pytest")
            db.commit()

            selector, secret = cookie.split(".", 1)
            row = db.get(DbSession, selector)
            self.assertIsNotNone(row)
            self.assertNotEqual(row.secret_hash, secret)
            self.assertEqual(row.secret_hash, hashlib.sha256(secret.encode()).hexdigest())

            principal = auth.lookup_session(db, cookie)
            self.assertEqual(principal.user_id, user.id)
            self.assertFalse(principal.legacy)
            self.assertIsNone(auth.lookup_session(db, selector + ".wrong-secret"))

            self.assertTrue(auth.revoke_session(db, cookie))
            db.commit()
            self.assertIsNone(auth.lookup_session(db, cookie))

    def test_legacy_cookie_can_be_validated_without_storing_raw_token(self):
        raw = secrets.token_urlsafe(32)
        h = hashlib.sha256(raw.encode()).hexdigest()
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "legacy-session@example.com", "very-secure-password")
            db.add(DbSession(
                token="legacy:" + h[:32],
                user_id=user.id,
                secret_hash=h,
                created_at=auth.utcnow(),
                expires_at=auth.utcnow() + timedelta(days=30),
            ))
            db.commit()

            principal = auth.lookup_session(db, raw)
            self.assertEqual(principal.user_id, user.id)
            self.assertTrue(principal.legacy)
            stored = db.execute(select(DbSession)).scalar_one()
            self.assertNotEqual(stored.token, raw)
            self.assertNotEqual(stored.secret_hash, raw)

    def test_email_challenge_is_one_time_and_marks_email_verified(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "verify@example.com", "very-secure-password")
            code = auth.create_challenge(
                db,
                user_id=user.id,
                purpose="EMAIL_VERIFY",
                channel="email",
                target=user.email,
            )
            db.commit()

            with self.assertRaises(auth.InvalidOrExpiredChallenge):
                auth.verify_email_challenge(db, email=user.email, secret="wrong")
            db.commit()

            verified = auth.verify_email_challenge(db, email=user.email, secret=code)
            db.commit()
            self.assertIsNotNone(verified.email_verified_at)

            with self.assertRaises(auth.InvalidOrExpiredChallenge):
                auth.verify_email_challenge(db, email=user.email, secret=code)

    def test_password_reset_revokes_existing_sessions(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "reset@example.com", "very-secure-password")
            cookie = auth.create_session(db, user.id)
            token = auth.create_challenge(
                db,
                user_id=user.id,
                purpose="PASSWORD_RESET",
                channel="email",
                target=user.email,
            )
            db.commit()

            auth.reset_password_with_challenge(
                db,
                email=user.email,
                secret=token,
                new_password="another-secure-password",
            )
            db.commit()

            self.assertIsNone(auth.lookup_session(db, cookie))
            ok, _ = auth.verify_password("another-secure-password", user.password_hash)
            self.assertTrue(ok)

    def test_login_rate_limit_blocks_after_threshold(self):
        now = auth.utcnow()
        for i in range(8):
            with Session(self.engine) as db:
                with self.assertRaises(auth.InvalidCredentials):
                    auth.authenticate_password(
                        db,
                        "nobody@example.com",
                        "invalid-password",
                        apply_rate_limit=True,
                        now=now,
                    )
                db.commit()

        with Session(self.engine) as db:
            with self.assertRaises(auth.RateLimited) as ctx:
                auth.authenticate_password(
                    db,
                    "nobody@example.com",
                    "invalid-password",
                    apply_rate_limit=True,
                    now=now,
                )
            db.commit()
            self.assertGreaterEqual(ctx.exception.retry_after_seconds, 1)

    def test_expired_challenge_is_rejected(self):
        now = auth.utcnow()
        with Session(self.engine) as db:
            user = auth.register_email_user(db, "expired@example.com", "very-secure-password")
            code = auth.create_challenge(
                db,
                user_id=user.id,
                purpose="EMAIL_VERIFY",
                channel="email",
                target=user.email,
                ttl=timedelta(seconds=1),
                now=now,
            )
            db.commit()

            with self.assertRaises(auth.InvalidOrExpiredChallenge):
                auth.verify_email_challenge(
                    db,
                    email=user.email,
                    secret=code,
                    now=now + timedelta(seconds=2),
                )


if __name__ == "__main__":
    unittest.main()
