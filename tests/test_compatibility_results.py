import json
import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.compatibility import (
    CompatibilityUnavailable,
    build_compatibility_result,
    public_result_keys,
    safe_ai_explanation_context,
)
from app.db.models import (
    Block,
    Market,
    PartnerPreference,
    Profile,
    QuestionnaireAnswer,
    User,
)
from app.questionnaire import service as questionnaire


class CompatibilityResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE users, markets, questionnaire_versions RESTART IDENTITY CASCADE"
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
                supported_languages=["ru-KZ","kk-KZ"],
                registration_open=True,
                matching_open=True,
            )
            db.add(market)
            db.flush()
            self.market_id = market.id
            version = questionnaire.seed_v7_questionnaire(db)
            db.commit()
            self.questions = questionnaire.questions_for_version(db, version.id)

    def add_user(self, db, *, email, gender, seek_gender, answers_by_section=None):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            email_verified_at=self.now,
        )
        db.add(user)
        db.flush()

        profile = Profile(
            user_id=user.id,
            display_name=email.split("@")[0],
            dob=date(1997, 1, 1),
            gender=gender,
            seek_gender=seek_gender,
            city="Алматы",
            country_code="KZ",
            market_id=self.market_id,
            relationship_status="ACTIVE_SEARCH",
            eligibility_status="ACTIVE_FOR_MATCHING",
            dating_goal="SERIOUS",
            readiness_score=90,
            height=175,
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
        db.add(profile)

        answers_by_section = answers_by_section or {}
        for q in self.questions:
            value = answers_by_section.get(q.category, 3)
            db.add(
                QuestionnaireAnswer(
                    user_id=user.id,
                    question_id=q.id,
                    value_int=value,
                )
            )
        db.flush()
        return user.id

    def test_public_result_has_expected_shape_and_no_internal_ranking_components(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(db,email="candidate@example.com",gender="F",seek_gender="M")
            db.commit()

            result = build_compatibility_result(
                db,
                viewer_user_id=a,
                candidate_user_id=b,
                now=self.now,
            )

            self.assertEqual(set(result), public_result_keys())
            self.assertTrue(result["available"])
            self.assertEqual(result["candidate_user_id"], b)
            self.assertEqual(result["compatibility_percent"], 100)
            self.assertEqual(len(result["categories"]), 8)
            self.assertNotIn("final_mutual_fit_score", result)
            self.assertNotIn("activity_score", result)
            self.assertNotIn("readiness_score", result)
            self.assertNotIn("mutual_preference_score", result)

    def test_raw_answers_and_partner_criteria_are_not_exposed(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(
                db,
                email="candidate@example.com",
                gender="F",
                seek_gender="M",
                answers_by_section={"Семья": 5, "Дети": 5},
            )
            db.add(
                PartnerPreference(
                    user_id=b,
                    criterion_key="height",
                    importance="HARD",
                    min_value=150,
                    max_value=195,
                )
            )
            db.commit()

            result = build_compatibility_result(
                db,
                viewer_user_id=a,
                candidate_user_id=b,
                now=self.now,
            )
            payload = json.dumps(result, ensure_ascii=False, sort_keys=True)

            self.assertNotIn('"value_int"', payload)
            self.assertNotIn('"question_id"', payload)
            self.assertNotIn('"min_value"', payload)
            self.assertNotIn('"max_value"', payload)
            self.assertNotIn('"importance"', payload)
            self.assertNotIn('"HARD"', payload)
            self.assertNotIn("150", payload)
            self.assertNotIn("195", payload)

    def test_strengths_and_discussion_points_follow_category_scores(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(
                db,
                email="candidate@example.com",
                gender="F",
                seek_gender="M",
                answers_by_section={
                    "Ценности": 3,
                    "Деньги": 3,
                    "Интересы": 5,
                    "Семья": 5,
                    "Дети": 5,
                },
            )
            db.commit()

            result = build_compatibility_result(
                db,
                viewer_user_id=a,
                candidate_user_id=b,
                now=self.now,
            )
            cards = {item["key"]: item for item in result["categories"]}

            self.assertEqual(cards["values_score"]["score"], 100)
            self.assertEqual(cards["interests_score"]["score"], 50)
            self.assertTrue(result["why_you_match"])
            self.assertTrue(result["what_to_discuss"])
            self.assertTrue(any("досуг" in x.lower() or "интерес" in x.lower() for x in result["what_to_discuss"]))

    def test_ineligible_pair_has_no_compatibility_result(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(db,email="candidate@example.com",gender="F",seek_gender="M")
            db.add(Block(blocker=b,blocked=a,created_at=self.now))
            db.commit()

            with self.assertRaises(CompatibilityUnavailable):
                build_compatibility_result(
                    db,
                    viewer_user_id=a,
                    candidate_user_id=b,
                    now=self.now,
                )

    def test_safe_ai_context_can_only_rephrase_public_facts(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(db,email="candidate@example.com",gender="F",seek_gender="M")
            db.commit()

            result = build_compatibility_result(
                db,
                viewer_user_id=a,
                candidate_user_id=b,
                now=self.now,
            )
            context = safe_ai_explanation_context(result)
            payload = json.dumps(context, ensure_ascii=False, sort_keys=True)

            self.assertTrue(context["rules"]["may_rephrase_only"])
            self.assertTrue(context["rules"]["must_not_change_scores"])
            self.assertTrue(context["rules"]["must_not_reveal_raw_answers"])
            self.assertTrue(context["rules"]["must_not_reveal_partner_preferences"])
            self.assertNotIn("candidate_user_id", context)
            self.assertNotIn("final_mutual_fit_score", payload)
            self.assertNotIn("activity_score", payload)
            self.assertNotIn("readiness_score", payload)

    def test_public_copy_is_not_a_relationship_success_prediction(self):
        with Session(self.engine) as db:
            a = self.add_user(db,email="viewer@example.com",gender="M",seek_gender="F")
            b = self.add_user(db,email="candidate@example.com",gender="F",seek_gender="M")
            db.commit()

            result = build_compatibility_result(
                db,
                viewer_user_id=a,
                candidate_user_id=b,
                now=self.now,
            )
            self.assertIn("не прогноз отношений", result["disclaimer"].lower())


if __name__ == "__main__":
    unittest.main()
