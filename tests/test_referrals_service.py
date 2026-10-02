import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.analytics.events import (
    EVENT_REFERRAL_COMPLETED_PROFILE,
    EVENT_REFERRAL_INVITE,
    EVENT_REFERRAL_REGISTRATION,
)
from app.auth.service import AuthError, register_email_user
from app.db.models import MarketingAttribution, ProductEvent, Referral, User
from app.referrals import service as referrals


class ReferralServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)

    def make_user(self, db, email, code, status="ACTIVE"):
        user = User(
            email=email,
            password_hash="x",
            referral_code=code,
            status=status,
        )
        db.add(user)
        db.flush()
        return user

    def test_referral_link_preserves_existing_query_and_adds_code(self):
        with Session(self.engine) as db:
            user = self.make_user(db, "a@example.com", "abc123")
            db.commit()
            url = referrals.referral_link(
                db,
                user_id=user.id,
                base_url="https://match.example/join?utm_source=instagram",
            )
            self.assertIn("utm_source=instagram", url)
            self.assertIn("ref=abc123", url)

    def test_resolver_accepts_active_and_soft_banned_but_not_banned(self):
        with Session(self.engine) as db:
            active = self.make_user(db, "a@example.com", "active")
            soft = self.make_user(db, "s@example.com", "soft", status="SOFT_BANNED")
            banned = self.make_user(db, "b@example.com", "banned", status="BANNED")
            db.commit()
            self.assertEqual(referrals.resolve_referral_code(db, code="active").id, active.id)
            self.assertEqual(referrals.resolve_referral_code(db, code="soft").id, soft.id)
            self.assertIsNone(referrals.resolve_referral_code(db, code="banned"))

    def test_invite_increments_counter_and_tracks_event(self):
        with Session(self.engine) as db:
            user = self.make_user(db, "a@example.com", "a")
            db.commit()
            count = referrals.record_invite(
                db, user_id=user.id, channel="whatsapp", now=self.now
            )
            db.commit()
            self.assertEqual(count, 1)
            event = db.query(ProductEvent).filter_by(
                user_id=user.id,
                event_type=EVENT_REFERRAL_INVITE,
            ).one()
            self.assertEqual(event.metadata_json["channel"], "whatsapp")

    def test_registration_from_referral_code_creates_attribution_and_referral(self):
        with Session(self.engine) as db:
            referrer = self.make_user(db, "ref@example.com", "ref-code")
            db.commit()

            referred = register_email_user(
                db,
                "new@example.com",
                "very-secure-password",
                referral_code="ref-code",
            )
            db.commit()

            self.assertEqual(referred.referred_by, referrer.id)
            row = db.query(Referral).filter_by(referred_user_id=referred.id).one()
            self.assertEqual(row.referrer_user_id, referrer.id)
            self.assertEqual(row.referral_code_used, "ref-code")
            attribution = db.get(MarketingAttribution, referred.id)
            self.assertEqual(attribution.referral_input, "ref-code")
            self.assertEqual(
                db.query(ProductEvent)
                .filter_by(
                    user_id=referrer.id,
                    event_type=EVENT_REFERRAL_REGISTRATION,
                )
                .count(),
                1,
            )

    def test_invalid_referral_code_does_not_block_registration(self):
        with Session(self.engine) as db:
            user = register_email_user(
                db,
                "new@example.com",
                "very-secure-password",
                referral_code="does-not-exist",
            )
            db.commit()
            self.assertIsNone(user.referred_by)
            self.assertEqual(db.query(Referral).count(), 0)
            self.assertEqual(
                db.get(MarketingAttribution, user.id).referral_input,
                "does-not-exist",
            )

    def test_conflicting_referral_inputs_are_rejected(self):
        with Session(self.engine) as db:
            one = self.make_user(db, "one@example.com", "one")
            self.make_user(db, "two@example.com", "two")
            db.commit()
            with self.assertRaises(AuthError):
                register_email_user(
                    db,
                    "new@example.com",
                    "very-secure-password",
                    referred_by=one.id,
                    referral_code="two",
                )

    def test_referral_is_idempotent_and_cannot_be_reattributed(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com", "a")
            b = self.make_user(db, "b@example.com", "b")
            c = self.make_user(db, "c@example.com", "c")
            db.commit()

            first = referrals.register_referral(
                db,
                referrer_user_id=a.id,
                referred_user_id=c.id,
                referral_code_used="a",
                now=self.now,
            )
            second = referrals.register_referral(
                db,
                referrer_user_id=a.id,
                referred_user_id=c.id,
                referral_code_used="a",
                now=self.now,
            )
            self.assertEqual(first.id, second.id)
            with self.assertRaises(referrals.ReferralError):
                referrals.register_referral(
                    db,
                    referrer_user_id=b.id,
                    referred_user_id=c.id,
                    referral_code_used="b",
                    now=self.now,
                )

    def test_self_referral_is_rejected(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com", "a")
            db.commit()
            with self.assertRaises(referrals.ReferralError):
                referrals.register_referral(
                    db,
                    referrer_user_id=a.id,
                    referred_user_id=a.id,
                    referral_code_used="a",
                    now=self.now,
                )

    def test_profile_completion_is_recorded_once(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com", "a")
            b = self.make_user(db, "b@example.com", "b")
            referrals.register_referral(
                db,
                referrer_user_id=a.id,
                referred_user_id=b.id,
                referral_code_used="a",
                now=self.now,
            )
            db.commit()

            first = referrals.mark_referred_profile_completed(
                db,
                referred_user_id=b.id,
                now=self.now,
            )
            second = referrals.mark_referred_profile_completed(
                db,
                referred_user_id=b.id,
                now=self.now,
            )
            db.commit()
            self.assertEqual(first.id, second.id)
            self.assertIsNotNone(first.profile_completed_at)
            self.assertEqual(
                db.query(ProductEvent)
                .filter_by(
                    user_id=a.id,
                    event_type=EVENT_REFERRAL_COMPLETED_PROFILE,
                )
                .count(),
                1,
            )

    def test_stats_track_invites_registrations_and_completed_profiles(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com", "a")
            b = self.make_user(db, "b@example.com", "b")
            c = self.make_user(db, "c@example.com", "c")
            db.commit()
            referrals.record_invite(db, user_id=a.id, now=self.now)
            referrals.record_invite(db, user_id=a.id, now=self.now)
            referrals.register_referral(
                db, referrer_user_id=a.id, referred_user_id=b.id, now=self.now
            )
            referrals.register_referral(
                db, referrer_user_id=a.id, referred_user_id=c.id, now=self.now
            )
            referrals.mark_referred_profile_completed(
                db, referred_user_id=b.id, now=self.now
            )
            db.commit()
            stats = referrals.referral_stats(db, user_id=a.id)
            self.assertEqual(stats["invites_sent"], 2)
            self.assertEqual(stats["registrations"], 2)
            self.assertEqual(stats["completed_profiles"], 1)
            self.assertEqual(stats["registration_rate"], 100.0)
            self.assertEqual(stats["completion_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()
