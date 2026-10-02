import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_SUBSCRIPTION_STARTED
from app.billing import service as billing
from app.db.models import Payment, ProductEvent, Subscription, User


class BillingServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)

    def make_user(self, db, email="billing@example.com"):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
        )
        db.add(user)
        db.flush()
        return user

    def test_free_plan_keeps_core_product_features(self):
        features = billing.plan_features("FREE")
        self.assertIn("CORE_MATCHING", features)
        self.assertIn("BASIC_COMPATIBILITY", features)
        self.assertIn("QUESTIONNAIRE", features)
        self.assertIn("MESSAGING", features)
        self.assertNotIn("PRIORITY_MATCHING", features)

    def test_premium_plus_is_superset_of_premium(self):
        premium = billing.plan_features("PREMIUM")
        plus = billing.plan_features("PREMIUM_PLUS")
        self.assertTrue(premium.issubset(plus))
        self.assertIn("PRIORITY_MATCHING", plus)
        self.assertIn("AI_RELATIONSHIP_ANALYSIS", plus)

    def test_verified_subscription_activates_plan_and_tracks_conversion_once(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()

            sub = billing.apply_verified_subscription(
                db,
                user_id=user.id,
                provider="APPLE",
                provider_subscription_id="orig-1",
                product_code="premium.monthly",
                tier="PREMIUM",
                status="ACTIVE",
                current_period_start=self.now,
                current_period_end=self.now + timedelta(days=30),
                auto_renew=True,
                environment="SANDBOX",
                verified_at=self.now,
            )
            db.commit()
            self.assertEqual(sub.tier, "PREMIUM")
            self.assertEqual(billing.active_plan(db, user_id=user.id, now=self.now), "PREMIUM")
            self.assertEqual(
                db.query(ProductEvent)
                .filter_by(user_id=user.id, event_type=EVENT_SUBSCRIPTION_STARTED)
                .count(),
                1,
            )

            billing.apply_verified_subscription(
                db,
                user_id=user.id,
                provider="APPLE",
                provider_subscription_id="orig-1",
                product_code="premium_plus.monthly",
                tier="PREMIUM_PLUS",
                status="ACTIVE",
                current_period_start=self.now,
                current_period_end=self.now + timedelta(days=30),
                auto_renew=False,
                environment="SANDBOX",
                verified_at=self.now + timedelta(minutes=1),
            )
            db.commit()
            self.assertEqual(db.query(Subscription).count(), 1)
            self.assertEqual(
                billing.active_plan(db, user_id=user.id, now=self.now),
                "PREMIUM_PLUS",
            )
            self.assertEqual(
                db.query(ProductEvent)
                .filter_by(user_id=user.id, event_type=EVENT_SUBSCRIPTION_STARTED)
                .count(),
                1,
            )

    def test_expired_or_revoked_subscription_falls_back_to_free(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            billing.apply_verified_subscription(
                db,
                user_id=user.id,
                provider="GOOGLE",
                provider_subscription_id="sub-old",
                product_code="premium.monthly",
                tier="PREMIUM",
                status="ACTIVE",
                current_period_start=self.now - timedelta(days=60),
                current_period_end=self.now - timedelta(days=30),
                auto_renew=False,
                verified_at=self.now,
            )
            db.commit()
            self.assertEqual(billing.active_plan(db, user_id=user.id, now=self.now), "FREE")

            billing.apply_verified_subscription(
                db,
                user_id=user.id,
                provider="GOOGLE",
                provider_subscription_id="sub-old",
                product_code="premium.monthly",
                tier="PREMIUM",
                status="REVOKED",
                current_period_start=self.now - timedelta(days=1),
                current_period_end=self.now + timedelta(days=29),
                auto_renew=False,
                verified_at=self.now,
            )
            db.commit()
            self.assertEqual(billing.active_plan(db, user_id=user.id, now=self.now), "FREE")

    def test_subscription_external_id_cannot_move_between_users(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com")
            b = self.make_user(db, "b@example.com")
            db.commit()
            billing.apply_verified_subscription(
                db,
                user_id=a.id,
                provider="APPLE",
                provider_subscription_id="shared-id",
                product_code="premium.monthly",
                tier="PREMIUM",
                status="ACTIVE",
                current_period_start=self.now,
                current_period_end=self.now + timedelta(days=30),
                auto_renew=True,
                verified_at=self.now,
            )
            with self.assertRaises(billing.InvalidVerifiedTransaction):
                billing.apply_verified_subscription(
                    db,
                    user_id=b.id,
                    provider="APPLE",
                    provider_subscription_id="shared-id",
                    product_code="premium.monthly",
                    tier="PREMIUM",
                    status="ACTIVE",
                    current_period_start=self.now,
                    current_period_end=self.now + timedelta(days=30),
                    auto_renew=True,
                    verified_at=self.now,
                )

    def test_verified_payment_is_idempotent_and_conflicts_fail(self):
        with Session(self.engine) as db:
            a = self.make_user(db, "a@example.com")
            b = self.make_user(db, "b@example.com")
            db.commit()
            one = billing.record_verified_payment(
                db,
                user_id=a.id,
                provider="APPLE",
                provider_transaction_id="tx-1",
                product_code="deep-report",
                purchase_kind="ONE_TIME",
                status="PURCHASED",
                purchased_at=self.now,
                amount_minor=1990,
                currency="KZT",
                environment="SANDBOX",
            )
            two = billing.record_verified_payment(
                db,
                user_id=a.id,
                provider="APPLE",
                provider_transaction_id="tx-1",
                product_code="deep-report",
                purchase_kind="ONE_TIME",
                status="PURCHASED",
                purchased_at=self.now,
                amount_minor=1990,
                currency="KZT",
                environment="SANDBOX",
            )
            db.commit()
            self.assertEqual(one.id, two.id)
            self.assertEqual(db.query(Payment).count(), 1)

            with self.assertRaises(billing.InvalidVerifiedTransaction):
                billing.record_verified_payment(
                    db,
                    user_id=b.id,
                    provider="APPLE",
                    provider_transaction_id="tx-1",
                    product_code="deep-report",
                    purchase_kind="ONE_TIME",
                    status="PURCHASED",
                    purchased_at=self.now,
                )

    def test_one_time_deep_report_is_scoped_to_match(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            payment = billing.record_verified_payment(
                db,
                user_id=user.id,
                provider="GOOGLE",
                provider_transaction_id="tx-report",
                product_code="deep-report",
                purchase_kind="ONE_TIME",
                status="PURCHASED",
                purchased_at=self.now,
            )
            entitlement = billing.grant_deep_report(
                db,
                user_id=user.id,
                match_id=42,
                payment_id=payment.id,
            )
            db.commit()
            self.assertEqual(entitlement.scope_key, "match:42")
            self.assertTrue(
                billing.has_entitlement(
                    db,
                    user_id=user.id,
                    entitlement_key=billing.ONE_TIME_DEEP_REPORT,
                    scope_key="match:42",
                    now=self.now,
                )
            )
            self.assertFalse(
                billing.has_entitlement(
                    db,
                    user_id=user.id,
                    entitlement_key=billing.ONE_TIME_DEEP_REPORT,
                    scope_key="match:43",
                    now=self.now,
                )
            )

    def test_pending_or_refunded_payment_cannot_grant_one_time_entitlement(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            payment = billing.record_verified_payment(
                db,
                user_id=user.id,
                provider="WEB",
                provider_transaction_id="pending",
                product_code="deep-report",
                purchase_kind="ONE_TIME",
                status="PENDING",
                purchased_at=self.now,
            )
            db.commit()
            with self.assertRaises(billing.BillingError):
                billing.grant_deep_report(
                    db,
                    user_id=user.id,
                    match_id=1,
                    payment_id=payment.id,
                )

    def test_database_rejects_invalid_provider_and_negative_amount(self):
        with Session(self.engine) as db:
            user = self.make_user(db)
            db.commit()
            db.add(
                Payment(
                    user_id=user.id,
                    provider="UNKNOWN",
                    provider_transaction_id="bad-provider",
                    product_code="x",
                    purchase_kind="ONE_TIME",
                    amount_minor=0,
                    currency="KZT",
                    status="PURCHASED",
                    environment="PRODUCTION",
                    purchased_at=self.now,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(
                Payment(
                    user_id=user.id,
                    provider="WEB",
                    provider_transaction_id="negative",
                    product_code="x",
                    purchase_kind="ONE_TIME",
                    amount_minor=-1,
                    currency="KZT",
                    status="PURCHASED",
                    environment="PRODUCTION",
                    purchased_at=self.now,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
