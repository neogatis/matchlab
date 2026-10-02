import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Notification, PushDelivery, PushDevice, User
from app.push import service as push


class MemoryVault:
    def __init__(self):
        self.values = {}
        self.counter = 0

    def store(self, token):
        self.counter += 1
        ref = f"vault:{self.counter}"
        self.values[ref] = token
        return ref

    def resolve(self, token_ref):
        return self.values[token_ref]

    def delete(self, token_ref):
        self.values.pop(token_ref, None)


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class PushServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)
        self.vault = MemoryVault()

    def make_user(self, db, email="push@example.com"):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
        )
        db.add(user)
        db.flush()
        return user

    def register(self, db, user_id, token="token-1234567890123456"):
        return push.register_device(
            db,
            user_id=user_id,
            provider="FCM",
            platform="ANDROID",
            token=token,
            vault=self.vault,
            locale="ru-KZ",
            now=self.now,
        )

    def test_device_registration_stores_reference_not_raw_token(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            token = "token-1234567890123456"
            device = self.register(db, user.id, token=token)
            db.commit()

            self.assertNotEqual(device.token_ref, token)
            self.assertEqual(self.vault.resolve(device.token_ref), token)
            self.assertEqual(len(device.token_hash), 64)
            self.assertNotIn(token, device.token_hash)

    def test_provider_platform_mismatch_is_rejected(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            with self.assertRaises(push.PushError):
                push.register_device(
                    db,
                    user_id=user.id,
                    provider="APNS",
                    platform="ANDROID",
                    token="token-1234567890123456",
                    vault=self.vault,
                    now=self.now,
                )

    def test_enqueue_is_idempotent_per_notification_and_device(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            device = self.register(db, user.id)
            note = Notification(
                user_id=user.id,
                kind="MESSAGE",
                text="private text that must not be pushed",
                created_at=self.now,
            )
            db.add(note)
            db.flush()

            first = push.enqueue_notification(
                db,
                notification_id=note.id,
                now=self.now,
            )
            second = push.enqueue_notification(
                db,
                notification_id=note.id,
                now=self.now,
            )
            db.commit()

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].id, second[0].id)
            self.assertEqual(db.query(PushDelivery).count(), 1)
            self.assertEqual(first[0].device_id, device.id)

    def test_message_payload_never_contains_notification_body(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            note = Notification(
                user_id=user.id,
                kind="MESSAGE",
                text="secret conversation text",
                created_at=self.now,
            )
            db.add(note)
            db.flush()

            title, body, data = push.safe_payload(note)
            self.assertEqual(title, "MatchLab")
            self.assertEqual(body, "У вас новое сообщение")
            self.assertNotIn("secret", body)
            self.assertEqual(data, {"kind": "MESSAGE"})

    def test_successful_dispatch_marks_sent(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            device = self.register(db, user.id)
            note = Notification(
                user_id=user.id,
                kind="MATCH",
                text="match",
                created_at=self.now,
            )
            db.add(note)
            db.flush()
            delivery = push.enqueue_notification(
                db,
                notification_id=note.id,
                now=self.now,
            )[0]
            db.commit()

            client = FakeProvider(
                push.PushSendResult(ok=True, provider_message_id="provider-1")
            )
            result = push.dispatch_delivery(
                db,
                delivery_id=delivery.id,
                clients={"FCM": client},
                vault=self.vault,
                now=self.now,
            )
            db.commit()

            self.assertEqual(result.status, "SENT")
            self.assertEqual(result.provider_message_id, "provider-1")
            self.assertIsNotNone(result.sent_at)
            self.assertEqual(client.calls[0]["token"], self.vault.resolve(device.token_ref))

    def test_invalid_token_disables_device(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            device = self.register(db, user.id)
            note = Notification(
                user_id=user.id,
                kind="MESSAGE",
                text="message",
                created_at=self.now,
            )
            db.add(note)
            db.flush()
            delivery = push.enqueue_notification(
                db,
                notification_id=note.id,
                now=self.now,
            )[0]
            db.commit()

            client = FakeProvider(
                push.PushSendResult(
                    ok=False,
                    invalid_token=True,
                    error="unregistered",
                )
            )
            result = push.dispatch_delivery(
                db,
                delivery_id=delivery.id,
                clients={"FCM": client},
                vault=self.vault,
                now=self.now,
            )
            db.commit()

            self.assertEqual(result.status, "DISABLED")
            self.assertFalse(db.get(PushDevice, device.id).enabled)
            self.assertNotIn(device.token_ref, self.vault.values)

    def test_transient_failure_is_retried_later(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            self.register(db, user.id)
            note = Notification(
                user_id=user.id,
                kind="MATCH",
                text="match",
                created_at=self.now,
            )
            db.add(note)
            db.flush()
            delivery = push.enqueue_notification(
                db,
                notification_id=note.id,
                now=self.now,
            )[0]
            db.commit()

            client = FakeProvider(
                push.PushSendResult(ok=False, error="timeout")
            )
            result = push.dispatch_delivery(
                db,
                delivery_id=delivery.id,
                clients={"FCM": client},
                vault=self.vault,
                now=self.now,
            )
            db.commit()

            self.assertEqual(result.status, "FAILED")
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.next_attempt_at, self.now + timedelta(minutes=1))
            self.assertEqual(
                push.pending_deliveries(
                    db,
                    now=self.now + timedelta(seconds=30),
                ),
                [],
            )
            self.assertEqual(
                [x.id for x in push.pending_deliveries(
                    db,
                    now=self.now + timedelta(minutes=2),
                )],
                [delivery.id],
            )

    def test_database_constraints_reject_invalid_provider_and_negative_attempts(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            db.add(
                PushDevice(
                    user_id=user.id,
                    provider="UNKNOWN",
                    platform="ANDROID",
                    token_hash="a" * 64,
                    token_ref="vault:bad",
                    locale="ru-KZ",
                    enabled=True,
                    last_seen_at=self.now,
                    created_at=self.now,
                    updated_at=self.now,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
