import os
import unittest
from datetime import timedelta

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.auth import service as auth
from app.auth.oauth import VerifiedIdentity, link_identity, login_or_register_identity
from app.db.models import AuthIdentity, User


class FakeSmsSender:
    def __init__(self):
        self.messages = []

    def send_otp(self, *, phone_e164, code):
        self.messages.append((phone_e164, code))
        return type("Result", (), {"provider": "FAKE", "message_id": "fake-1"})()


class MultichannelAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            for table in [
                "auth_outbox","auth_challenges","auth_rate_limits","auth_identities",
                "sessions","profiles","user_status_history","marketing_attribution",
                "referrals","product_events","users"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))

    def test_phone_otp_registers_and_logs_in_user(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+7 701 123 45 67",
                sender=sender,
            )
            db.commit()
            self.assertEqual(len(sender.messages), 1)
            phone, code = sender.messages[0]
            self.assertEqual(phone, "+77011234567")

            user = auth.verify_phone_login_code(
                db,
                phone_e164="+77011234567",
                code=code,
            )
            db.commit()
            self.assertEqual(user.phone_e164, "+77011234567")
            self.assertIsNotNone(user.phone_verified_at)
            self.assertTrue(user.email.endswith("@phone.matchlab.invalid"))

            identity = db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.user_id == user.id,
                    AuthIdentity.provider == "PHONE",
                )
            ).scalar_one()
            self.assertIsNotNone(identity.verified_at)

            with self.assertRaises(auth.InvalidOrExpiredChallenge):
                auth.verify_phone_login_code(
                    db,
                    phone_e164="+77011234567",
                    code=code,
                )

    def test_existing_phone_user_reuses_same_account(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+77011234567",
                sender=sender,
            )
            db.commit()
            first = auth.verify_phone_login_code(
                db,
                phone_e164="+77011234567",
                code=sender.messages[-1][1],
            )
            db.commit()
            first_id = first.id

        sender2 = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+77011234567",
                sender=sender2,
            )
            db.commit()
            second = auth.verify_phone_login_code(
                db,
                phone_e164="+77011234567",
                code=sender2.messages[-1][1],
            )
            db.commit()
            self.assertEqual(second.id, first_id)

    def test_phone_can_be_linked_to_existing_email_account(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            user = auth.register_email_user(
                db,
                "linked@example.com",
                "very-secure-password",
            )
            db.flush()
            auth.request_phone_link_code(
                db,
                user_id=user.id,
                phone_e164="+77011234567",
                sender=sender,
            )
            db.commit()

            linked = auth.verify_phone_link_code(
                db,
                user_id=user.id,
                phone_e164="+77011234567",
                code=sender.messages[-1][1],
            )
            db.commit()
            self.assertEqual(linked.phone_e164, "+77011234567")

    def test_oidc_nonce_is_one_time_and_scoped_to_provider(self):
        with Session(self.engine) as db:
            nonce = auth.create_oidc_nonce(
                db,
                provider="GOOGLE",
                purpose="OIDC_LOGIN",
            )
            db.commit()

            auth.consume_oidc_nonce(
                db,
                provider="GOOGLE",
                purpose="OIDC_LOGIN",
                nonce=nonce,
            )
            db.commit()

            with self.assertRaises(auth.InvalidOrExpiredChallenge):
                auth.consume_oidc_nonce(
                    db,
                    provider="GOOGLE",
                    purpose="OIDC_LOGIN",
                    nonce=nonce,
                )

    def test_google_identity_creates_account(self):
        identity = VerifiedIdentity(
            provider="GOOGLE",
            subject="google-subject-1",
            email="google@example.com",
            email_verified=True,
            claims={"sub": "google-subject-1"},
        )
        with Session(self.engine) as db:
            user = login_or_register_identity(db, identity=identity)
            db.commit()

            self.assertEqual(user.email, "google@example.com")
            self.assertIsNotNone(user.email_verified_at)
            row = db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "GOOGLE",
                    AuthIdentity.provider_subject == "google-subject-1",
                )
            ).scalar_one()
            self.assertEqual(row.user_id, user.id)

    def test_verified_email_identity_links_to_verified_existing_account(self):
        identity = VerifiedIdentity(
            provider="APPLE",
            subject="apple-subject-1",
            email="same@example.com",
            email_verified=True,
            claims={"sub": "apple-subject-1"},
        )
        with Session(self.engine) as db:
            user = auth.register_email_user(
                db,
                "same@example.com",
                "very-secure-password",
            )
            user.email_verified_at = auth.utcnow()
            db.flush()
            linked = login_or_register_identity(db, identity=identity)
            db.commit()

            self.assertEqual(linked.id, user.id)
            row = db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "APPLE",
                    AuthIdentity.provider_subject == "apple-subject-1",
                )
            ).scalar_one()
            self.assertEqual(row.user_id, user.id)

    def test_identity_link_rejects_identity_owned_by_other_user(self):
        identity = VerifiedIdentity(
            provider="GOOGLE",
            subject="shared-subject",
            email="one@example.com",
            email_verified=True,
            claims={},
        )
        with Session(self.engine) as db:
            owner = auth.register_email_user(db, "owner@example.com", "very-secure-password")
            other = auth.register_email_user(db, "other@example.com", "very-secure-password")
            db.add(AuthIdentity(
                user_id=owner.id,
                provider="GOOGLE",
                provider_subject="shared-subject",
                provider_email="one@example.com",
                verified_at=auth.utcnow(),
            ))
            db.flush()
            with self.assertRaises(Exception):
                link_identity(db, user_id=other.id, identity=identity)


if __name__ == "__main__":
    unittest.main()
