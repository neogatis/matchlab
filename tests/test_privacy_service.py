import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth.service import create_session
from app.chat.media import encode_media_body
from app.db.models import (
    AuditLog,
    AuthIdentity,
    ChatMediaUploadTicket,
    Conversation,
    DataRequest,
    Interest,
    Market,
    MarketingAttribution,
    Match,
    Message,
    Payment,
    Photo,
    PhotoObjectDeletion,
    ProductEvent,
    Profile,
    PushDevice,
    User,
)
from app.privacy.service import (
    DELETION_GRACE_DAYS,
    export_user_data,
    process_due_deletions,
    process_retention_cleanup,
    request_account_deletion,
)


class PrivacyServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "TRUNCATE TABLE audit_logs, data_requests, push_deliveries, push_devices, "
                "notifications, user_entitlements, payments, subscriptions, marketing_attribution, "
                "referrals, reports, blocks, date_proposals, messages, conversations, "
                "match_score_components, matches, interests, legacy_photo_blobs, "
                "photo_object_deletions, photo_upload_tickets, photos, partner_preferences, "
                "questionnaire_answers, user_status_history, profiles, auth_outbox, "
                "auth_rate_limits, auth_challenges, auth_identities, sessions, consents, "
                "product_events, admin_accounts, users, markets RESTART IDENTITY CASCADE"
            ))
        self.now = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)

        with Session(self.engine) as db:
            market = Market(
                code="KZ-ALA",
                country_code="KZ",
                city_code="ALA",
                display_name="Алматы",
                timezone="Asia/Almaty",
                currency_code="KZT",
                default_language="ru-KZ",
                supported_languages=["ru-KZ"],
                registration_open=True,
                matching_open=False,
            )
            db.add(market)
            db.flush()

            user = User(
                email="privacy@example.com",
                password_hash="hashed",
                referral_code="privacy-ref",
            )
            other = User(
                email="other@example.com",
                password_hash="hashed",
                referral_code="other-ref",
            )
            db.add_all([user, other])
            db.flush()

            db.add(Profile(
                user_id=user.id,
                display_name="Privacy User",
                gender="M",
                seek_gender="F",
                city="Алматы",
                country_code="KZ",
                market_id=market.id,
                relationship_status="ACTIVE_SEARCH",
                eligibility_status="ACTIVE_FOR_MATCHING",
            ))
            db.add(MarketingAttribution(
                user_id=user.id,
                utm_source="instagram",
                utm_campaign="waitlist",
            ))
            db.add(Interest(
                from_user=user.id,
                to_user=other.id,
                state="INTERESTED",
                created_at=self.now,
                updated_at=self.now,
            ))
            db.add(AuthIdentity(
                user_id=user.id,
                provider="GOOGLE",
                provider_subject="google-subject",
                provider_email=user.email,
                created_at=self.now,
            ))
            db.add(PushDevice(
                user_id=user.id,
                provider="FCM",
                platform="ANDROID",
                token_hash="token-hash",
                token_ref="secret-ref",
                last_seen_at=self.now,
                created_at=self.now,
                updated_at=self.now,
            ))
            db.add(Photo(
                user_id=user.id,
                storage_key=f"users/{user.id}/photo.jpg",
                mime="image/jpeg",
                byte_size=1000,
                is_main=True,
                sort_order=0,
                moderation_status="APPROVED",
                created_at=self.now,
            ))
            db.add(Payment(
                user_id=user.id,
                provider="GOOGLE",
                provider_transaction_id="txn-1",
                product_code="premium.month",
                purchase_kind="SUBSCRIPTION",
                amount_minor=3990,
                currency="KZT",
                status="PURCHASED",
                environment="PRODUCTION",
                purchased_at=self.now,
                created_at=self.now,
            ))
            create_session(db, user.id, now=self.now)
            db.commit()
            self.user_id = user.id
            self.other_id = other.id

    def test_export_contains_user_data_without_security_secrets_or_other_user_ids(self):
        with Session(self.engine) as db:
            payload = export_user_data(db, user_id=self.user_id, now=self.now)
            db.commit()

            self.assertEqual(payload["account"]["email"], "privacy@example.com")
            self.assertNotIn("password_hash", payload["account"])
            self.assertEqual(payload["profile"]["display_name"], "Privacy User")
            self.assertEqual(len(payload["interest_actions"]), 1)
            self.assertNotIn("to_user", payload["interest_actions"][0])
            self.assertEqual(payload["marketing_attribution"][0]["utm_source"], "instagram")
            request = db.get(DataRequest, payload["export_request_id"])
            self.assertEqual(request.request_type, "EXPORT")
            self.assertEqual(request.status, "COMPLETED")

    def test_delete_request_immediately_deactivates_account_and_revokes_sessions(self):
        with Session(self.engine) as db:
            result = request_account_deletion(db, user_id=self.user_id, now=self.now)
            db.commit()

            user = db.get(User, self.user_id)
            profile = db.get(Profile, self.user_id)
            self.assertEqual(user.status, "DELETION_REQUESTED")
            self.assertEqual(profile.relationship_status, "NOT_ACTIVE")
            self.assertEqual(profile.eligibility_status, "NOT_ACTIVE_FOR_MATCHING")
            self.assertEqual(result["grace_days"], DELETION_GRACE_DAYS)
            self.assertEqual(
                result["purge_after"],
                self.now + timedelta(days=DELETION_GRACE_DAYS),
            )
            active_sessions = db.execute(
                text("SELECT count(*) FROM sessions WHERE user_id=:uid AND revoked_at IS NULL"),
                {"uid": self.user_id},
            ).scalar_one()
            self.assertEqual(active_sessions, 0)

    def test_due_deletion_purges_product_data_and_pseudonymizes_billing_owner(self):
        with Session(self.engine) as db:
            result = request_account_deletion(db, user_id=self.user_id, now=self.now)
            db.commit()
            request_id = result["request_id"]

        with Session(self.engine) as db:
            outcome = process_due_deletions(
                db,
                now=self.now + timedelta(days=DELETION_GRACE_DAYS, minutes=1),
            )
            db.commit()
            self.assertEqual(outcome, {"processed": 1, "purged": 1})

            user = db.get(User, self.user_id)
            self.assertEqual(user.status, "DELETION_REQUESTED")
            self.assertTrue(user.email.endswith("@deleted.invalid"))
            self.assertIsNone(user.phone_e164)
            self.assertIsNone(db.get(Profile, self.user_id))
            self.assertEqual(
                db.query(Photo).filter(Photo.user_id == self.user_id).count(),
                0,
            )
            self.assertEqual(
                db.query(AuthIdentity).filter(AuthIdentity.user_id == self.user_id).count(),
                0,
            )
            self.assertEqual(
                db.query(PushDevice).filter(PushDevice.user_id == self.user_id).count(),
                0,
            )
            self.assertEqual(
                db.query(Interest).filter(
                    (Interest.from_user == self.user_id) | (Interest.to_user == self.user_id)
                ).count(),
                0,
            )

            # Financial transaction history is retained against the pseudonymous tombstone.
            self.assertEqual(
                db.query(Payment).filter(Payment.user_id == self.user_id).count(),
                1,
            )
            deletion = db.query(PhotoObjectDeletion).one()
            self.assertEqual(deletion.object_key, f"users/{self.user_id}/photo.jpg")
            request = db.get(DataRequest, request_id)
            self.assertEqual(request.status, "COMPLETED")
            self.assertIsNotNone(request.completed_at)

    def test_account_purge_queues_chat_media_objects(self):
        chat_key = f"users/{self.user_id}/chat/privacy/video.mp4"
        with Session(self.engine) as db:
            low, high = sorted((self.user_id, self.other_id))
            match = Match(
                user1=low,
                user2=high,
                compatibility_score=80,
                mutual_fit_score=78,
                algorithm_version="test",
                created_at=self.now,
            )
            db.add(match)
            db.flush()
            conversation = Conversation(match_id=match.id, created_at=self.now)
            db.add(conversation)
            db.flush()
            body = encode_media_body({
                "kind": "video",
                "mime": "video/mp4",
                "object_key": chat_key,
                "name": "video.mp4",
                "size": 1024,
            })
            db.add(Message(
                conversation_id=conversation.id,
                sender=self.user_id,
                body=body,
                created_at=self.now,
            ))
            db.add(ChatMediaUploadTicket(
                user_id=self.user_id,
                conversation_id=conversation.id,
                object_key=chat_key,
                mime="video/mp4",
                kind="video",
                original_name="video.mp4",
                expected_size=1024,
                status="CONSUMED",
                expires_at=self.now + timedelta(minutes=15),
                consumed_at=self.now,
                created_at=self.now,
            ))
            db.commit()

        with Session(self.engine) as db:
            request_account_deletion(db, user_id=self.user_id, now=self.now)
            db.commit()

        with Session(self.engine) as db:
            process_due_deletions(
                db,
                now=self.now + timedelta(days=DELETION_GRACE_DAYS, minutes=1),
            )
            db.commit()
            keys = {
                row.object_key
                for row in db.query(PhotoObjectDeletion).all()
            }
            self.assertIn(f"users/{self.user_id}/photo.jpg", keys)
            self.assertIn(chat_key, keys)
            self.assertEqual(
                db.query(ChatMediaUploadTicket)
                .filter(ChatMediaUploadTicket.user_id == self.user_id)
                .count(),
                0,
            )

    def test_retention_cleanup_removes_expired_operational_records(self):
        old = self.now - timedelta(days=400)
        with Session(self.engine) as db:
            db.add(ProductEvent(
                user_id=self.user_id,
                event_type="old_event",
                metadata_json={},
                created_at=old,
            ))
            db.add(AuditLog(
                actor_type="SYSTEM",
                action="old_audit",
                metadata_json={},
                created_at=old,
            ))
            db.add(DataRequest(
                user_id=self.user_id,
                request_type="EXPORT",
                status="COMPLETED",
                requested_at=old,
                completed_at=old,
            ))
            db.commit()

        with Session(self.engine) as db:
            counts = process_retention_cleanup(db, now=self.now)
            db.commit()
            self.assertGreaterEqual(counts["product_analytics"], 1)
            self.assertGreaterEqual(counts["security_audit"], 1)
            self.assertGreaterEqual(counts["completed_data_requests"], 1)


if __name__ == "__main__":
    unittest.main()
