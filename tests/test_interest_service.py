import os
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Block,
    Interest,
    Market,
    Match,
    MatchScoreComponent,
    Notification,
    PartnerPreference,
    ProductEvent,
    Profile,
    QuestionnaireAnswer,
    Setting,
    User,
)
from app.interests import service as interests
from app.matching.service import rank_candidates
from app.questionnaire import service as questionnaire


class InterestServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE settings, users, markets, questionnaire_versions "
                "RESTART IDENTITY CASCADE"
            ))

        self.now = datetime.now(timezone.utc)
        with Session(self.engine) as db:
            market = Market(
                code="KZ-ALA",
                country_code="KZ",
                city_code="ALA",
                display_name="Алматы",
                timezone="Asia/Almaty",
                currency_code="KZT",
                default_language="ru-KZ",
                latitude=43.238949,
                longitude=76.889709,
                supported_languages=["ru-KZ", "kk-KZ"],
                registration_open=True,
                matching_open=True,
            )
            db.add(market)
            db.flush()
            self.market_id = market.id
            version = questionnaire.seed_v7_questionnaire(db)
            db.add(Setting(key="PRE_LAUNCH_MODE", value="false"))
            db.add(Setting(key="PRELAUNCH_MATCHING_ENABLED", value="false"))
            db.commit()
            self.question_ids = [
                q.id for q in questionnaire.questions_for_version(db, version.id)
            ]

    def add_user(
        self,
        db,
        *,
        email,
        gender="M",
        seek_gender="ANY",
        dob=date(1997, 1, 1),
        answer_value=3,
        height=175,
    ):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            email_verified_at=self.now,
        )
        db.add(user)
        db.flush()
        db.add(
            Profile(
                user_id=user.id,
                display_name=email.split("@")[0],
                dob=dob,
                gender=gender,
                seek_gender=seek_gender,
                city="Алматы",
                country_code="KZ",
                market_id=self.market_id,
                relationship_status="ACTIVE_SEARCH",
                eligibility_status="ACTIVE_FOR_MATCHING",
                dating_goal="SERIOUS",
                readiness_score=90,
                height=height,
                children_status="NO_CHILDREN",
                children_plans="WANTS",
                smoking="NO",
                alcohol="RARE",
                lifestyle="ACTIVE",
                questionnaire_completed=True,
                partner_preferences_completed=True,
                photos_completed=True,
                profile_completed=True,
                updated_at=self.now,
            )
        )
        for qid in self.question_ids:
            db.add(
                QuestionnaireAnswer(
                    user_id=user.id,
                    question_id=qid,
                    value_int=answer_value,
                )
            )
        db.flush()
        return user.id

    def set_setting(self, db, key, value):
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
        db.flush()

    def test_prelaunch_defaults_fail_closed(self):
        with Session(self.engine) as db:
            db.query(Setting).delete()
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            with self.assertRaises(interests.InterestActionsDisabled):
                interests.express_interest(
                    db, from_user=a, to_user=b, now=self.now
                )

    def test_prelaunch_explicitly_disables_actions(self):
        with Session(self.engine) as db:
            self.set_setting(db, "PRE_LAUNCH_MODE", "true")
            self.set_setting(db, "PRELAUNCH_MATCHING_ENABLED", "false")
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            with self.assertRaises(interests.InterestActionsDisabled):
                interests.express_interest(
                    db, from_user=a, to_user=b, now=self.now
                )

    def test_prelaunch_can_be_explicitly_enabled_for_controlled_test(self):
        with Session(self.engine) as db:
            self.set_setting(db, "PRE_LAUNCH_MODE", "true")
            self.set_setting(db, "PRELAUNCH_MATCHING_ENABLED", "true")
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            result = interests.express_interest(
                db, from_user=a, to_user=b, now=self.now
            )
            db.commit()
            self.assertEqual(result["state"], "INTERESTED")
            self.assertFalse(result["mutual_match"])

    def test_unilateral_interest_does_not_create_match(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            result = interests.express_interest(
                db, from_user=a, to_user=b, now=self.now
            )
            db.commit()

            self.assertTrue(result["changed"])
            self.assertFalse(result["mutual_match"])
            self.assertIsNone(result["match_id"])
            self.assertEqual(db.query(Match).count(), 0)
            row = db.get(Interest, (a, b))
            self.assertEqual(row.state, "INTERESTED")
            self.assertEqual(row.source_algorithm_version, "mutual-v1")

    def test_reciprocal_interest_creates_exactly_one_canonical_match(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com", answer_value=3)
            b = self.add_user(db, email="b@example.com", answer_value=3)
            db.commit()

            interests.express_interest(db, from_user=b, to_user=a, now=self.now)
            db.commit()
            result = interests.express_interest(
                db,
                from_user=a,
                to_user=b,
                now=self.now + timedelta(seconds=1),
            )
            db.commit()

            self.assertTrue(result["mutual_match"])
            match = db.get(Match, result["match_id"])
            self.assertEqual((match.user1, match.user2), tuple(sorted((a, b))))
            self.assertEqual(match.algorithm_version, "mutual-v1")
            self.assertEqual(db.query(Match).count(), 1)
            self.assertEqual(
                db.query(Notification).filter_by(kind="MATCH").count(), 2
            )
            self.assertEqual(
                db.query(ProductEvent)
                .filter_by(event_type="MUTUAL_MATCH_CREATED")
                .count(),
                2,
            )
            self.assertEqual(
                db.query(MatchScoreComponent)
                .filter_by(match_id=match.id)
                .count(),
                11,
            )

    def test_repeated_interest_after_match_is_idempotent(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            interests.express_interest(db, from_user=a, to_user=b, now=self.now)
            interests.express_interest(
                db,
                from_user=b,
                to_user=a,
                now=self.now + timedelta(seconds=1),
            )
            db.commit()

            before_events = db.query(ProductEvent).count()
            before_notifications = db.query(Notification).count()
            result = interests.express_interest(
                db,
                from_user=a,
                to_user=b,
                now=self.now + timedelta(seconds=2),
            )
            db.commit()

            self.assertTrue(result["mutual_match"])
            self.assertFalse(result["changed"])
            self.assertEqual(db.query(Match).count(), 1)
            self.assertEqual(db.query(ProductEvent).count(), before_events)
            self.assertEqual(db.query(Notification).count(), before_notifications)

    def test_skip_hides_candidate_until_cooldown_expires(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            initial = rank_candidates(
                db, user_id=a, limit=5, now=self.now
            )
            self.assertIn(b, [x["user_id"] for x in initial])

            result = interests.skip_candidate(
                db, from_user=a, to_user=b, now=self.now
            )
            db.commit()

            self.assertEqual(result["state"], "SKIPPED")
            self.assertAlmostEqual(
                (result["snooze_until"] - self.now).total_seconds(),
                interests.SKIP_COOLDOWN.total_seconds(),
                delta=1,
            )
            hidden = rank_candidates(
                db,
                user_id=a,
                limit=5,
                now=self.now + timedelta(days=15),
            )
            self.assertNotIn(b, [x["user_id"] for x in hidden])

            returned = rank_candidates(
                db,
                user_id=a,
                limit=5,
                now=self.now + timedelta(days=31),
            )
            self.assertIn(b, [x["user_id"] for x in returned])

    def test_skip_can_change_to_interest_and_form_mutual_match(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            interests.skip_candidate(db, from_user=a, to_user=b, now=self.now)
            interests.express_interest(
                db,
                from_user=b,
                to_user=a,
                now=self.now + timedelta(seconds=1),
            )
            result = interests.express_interest(
                db,
                from_user=a,
                to_user=b,
                now=self.now + timedelta(seconds=2),
            )
            db.commit()

            self.assertTrue(result["mutual_match"])
            row = db.get(Interest, (a, b))
            self.assertEqual(row.state, "INTERESTED")
            self.assertIsNone(row.snooze_until)

    def test_hard_filter_conflict_blocks_interest(self):
        with Session(self.engine) as db:
            a = self.add_user(
                db,
                email="a@example.com",
                dob=date(1997, 1, 1),
            )
            b = self.add_user(
                db,
                email="b@example.com",
                dob=date(1980, 1, 1),
            )
            db.add(
                PartnerPreference(
                    user_id=a,
                    criterion_key="age",
                    importance="HARD",
                    min_value=24,
                    max_value=35,
                )
            )
            db.commit()

            with self.assertRaises(interests.InterestUnavailable):
                interests.express_interest(
                    db, from_user=a, to_user=b, now=self.now
                )
            self.assertIsNone(db.get(Interest, (a, b)))

    def test_blocked_pair_cannot_express_interest(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.add(Block(blocker=b, blocked=a, created_at=self.now))
            db.commit()

            with self.assertRaises(interests.InterestUnavailable):
                interests.express_interest(
                    db, from_user=a, to_user=b, now=self.now
                )

    def test_already_matched_pair_cannot_be_skipped(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()
            interests.express_interest(db, from_user=a, to_user=b, now=self.now)
            interests.express_interest(
                db,
                from_user=b,
                to_user=a,
                now=self.now + timedelta(seconds=1),
            )
            db.commit()

            with self.assertRaises(interests.PairAlreadyMatched):
                interests.skip_candidate(
                    db,
                    from_user=a,
                    to_user=b,
                    now=self.now + timedelta(seconds=2),
                )

    def test_database_rejects_self_interest_invalid_state_and_reversed_match(self):
        with Session(self.engine) as db:
            a = self.add_user(db, email="a@example.com")
            b = self.add_user(db, email="b@example.com")
            db.commit()

            db.add(
                Interest(
                    from_user=a,
                    to_user=a,
                    state="INTERESTED",
                    updated_at=self.now,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(
                Interest(
                    from_user=a,
                    to_user=b,
                    state="UNKNOWN",
                    updated_at=self.now,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(
                Match(
                    user1=max(a, b),
                    user2=min(a, b),
                    compatibility_score=80,
                    mutual_fit_score=80,
                    algorithm_version="test",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
