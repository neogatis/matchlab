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


class Phase32PasswordLoginTests(unittest.TestCase):
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

    def test_email_and_password_login_by_identifier(self):
        with Session(self.engine) as db:
            user = auth.register_email_user(
                db,
                "login@example.com",
                "very-secure-password",
            )
            db.commit()
            user_id = user.id

        with Session(self.engine) as db:
            logged_in = auth.authenticate_identifier_password(
                db,
                "login@example.com",
                "very-secure-password",
            )
            self.assertEqual(logged_in.id, user_id)

    def test_phone_otp_can_set_password_then_login_by_phone(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+7 747 426 65 22",
                sender=sender,
            )
            db.commit()
            code = sender.messages[-1][1]

        with Session(self.engine) as db:
            user = auth.verify_phone_login_code(
                db,
                phone_e164="+77474266522",
                code=code,
                new_password="matchlab-password-2026",
            )
            db.commit()
            user_id = user.id

        with Session(self.engine) as db:
            logged_in = auth.authenticate_identifier_password(
                db,
                "+7 747 426 65 22",
                "matchlab-password-2026",
            )
            self.assertEqual(logged_in.id, user_id)

    def test_phone_password_can_be_reset_with_new_sms_code(self):
        sender = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+77474266522",
                sender=sender,
            )
            db.commit()
            code = sender.messages[-1][1]

        with Session(self.engine) as db:
            auth.verify_phone_login_code(
                db,
                phone_e164="+77474266522",
                code=code,
                new_password="first-password-2026",
            )
            db.commit()

        sender2 = FakeSmsSender()
        with Session(self.engine) as db:
            auth.request_phone_login_code(
                db,
                phone_e164="+77474266522",
                sender=sender2,
            )
            db.commit()
            code2 = sender2.messages[-1][1]

        with Session(self.engine) as db:
            auth.verify_phone_login_code(
                db,
                phone_e164="+77474266522",
                code=code2,
                new_password="second-password-2026",
            )
            db.commit()

        with Session(self.engine) as db:
            with self.assertRaises(auth.InvalidCredentials):
                auth.authenticate_identifier_password(
                    db,
                    "+77474266522",
                    "first-password-2026",
                    apply_rate_limit=False,
                )
            logged_in = auth.authenticate_identifier_password(
                db,
                "+77474266522",
                "second-password-2026",
                apply_rate_limit=False,
            )
            self.assertIsNotNone(logged_in.id)

    def test_invalid_identifier_does_not_reveal_account_type(self):
        with Session(self.engine) as db:
            with self.assertRaisesRegex(
                auth.InvalidCredentials,
                "Invalid identifier or password",
            ):
                auth.authenticate_identifier_password(
                    db,
                    "+70000000000",
                    "some-password-value",
                    apply_rate_limit=False,
                )


if __name__ == "__main__":
    unittest.main()
