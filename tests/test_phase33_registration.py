import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth import service as auth


class FakeSmsSender:
    def __init__(self):
        self.messages = []

    def send_otp(self, *, phone_e164, code):
        self.messages.append((phone_e164, code))
        return type("Result", (), {"provider": "FAKE", "message_id": "fake"})()


class Phase33RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE auth_outbox, auth_challenges, auth_rate_limits, "
                "auth_identities, sessions, profiles, user_status_history, "
                "marketing_attribution, referrals, product_events, users "
                "RESTART IDENTITY CASCADE"
            ))

    def test_phone_registration_creates_verified_account_with_password(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_registration_code(
                db,
                phone_e164="+7 700 123 45 67",
                sender=sender,
            )
            db.commit()
            code = sender.messages[-1][1]

        with Session(self.engine) as db:
            user = auth.verify_phone_registration_code(
                db,
                phone_e164="+77001234567",
                code=code,
                password="registration-password",
            )
            db.commit()
            user_id = user.id
            self.assertIsNotNone(user.phone_verified_at)

        with Session(self.engine) as db:
            logged_in = auth.authenticate_identifier_password(
                db,
                "+77001234567",
                "registration-password",
                apply_rate_limit=False,
            )
            self.assertEqual(logged_in.id, user_id)

    def test_existing_phone_cannot_use_registration_flow(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+77001234567",
                sender=sender,
            )
            db.commit()
            code = sender.messages[-1][1]

        with Session(self.engine) as db:
            auth.verify_phone_login_code(
                db,
                phone_e164="+77001234567",
                code=code,
            )
            db.commit()

        with Session(self.engine) as db:
            with self.assertRaisesRegex(auth.AuthError, "phone_already_registered"):
                auth.request_phone_registration_code(
                    db,
                    phone_e164="+77001234567",
                    sender=FakeSmsSender(),
                )


if __name__ == "__main__":
    unittest.main()
