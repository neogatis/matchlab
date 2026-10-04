import os
import unittest
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth.service import hash_password
from app.db.models import AdaptiveQuestionnaireQuestion, Profile, User
from app.profile import service as profiles
from app.questionnaire import adaptive
from app.questionnaire.service import seed_v7_questionnaire


class Phase34AdaptiveQuestionnaireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_ADAPTIVE_MODEL", None)
        with self.engine.begin() as connection:
            connection.execute(text(
                "TRUNCATE TABLE adaptive_questionnaire_answers, "
                "adaptive_questionnaire_questions, questionnaire_answers, "
                "questionnaire_questions, questionnaire_versions, "
                "user_status_history, profiles, sessions, auth_outbox, "
                "auth_challenges, auth_rate_limits, auth_identities, users, markets "
                "RESTART IDENTITY CASCADE"
            ))

        with Session(self.engine) as db:
            seed_v7_questionnaire(db, activate=True)
            profiles.ensure_market(
                db,
                code="KZ-ALA",
                country_code="KZ",
                city_code="ALA",
                display_name="Алматы",
                timezone_name="Asia/Almaty",
                currency_code="KZT",
                default_language="ru-KZ",
                supported_languages=["ru-KZ", "kk-KZ"],
                registration_open=True,
                matching_open=False,
            )
            user = User(
                email="adaptive@example.com",
                password_hash=hash_password("very-secure-password"),
                referral_code="adaptive-ref",
            )
            db.add(user)
            db.flush()
            self.user_id = user.id
            profiles.upsert_basic_profile(
                db,
                user_id=user.id,
                display_name="Adaptive",
                dob=date(1997, 5, 30),
                gender="M",
                seek_gender="F",
                market_code="KZ-ALA",
            )
            db.commit()

    def test_base_phase_prefetches_questions(self):
        with Session(self.engine) as db:
            state = adaptive.state(db, user_id=self.user_id)
            self.assertEqual(state["phase"], "BASE")
            self.assertFalse(state["complete"])
            self.assertEqual(state["progress"]["base_total"], 30)
            self.assertEqual(state["question"]["kind"], "base")
            self.assertEqual(len(state["prefetch"]), 3)
            self.assertIn("похоже", state["question"]["options"][0]["label"])

    def test_consistent_answers_complete_with_adaptive_followups(self):
        with Session(self.engine) as db:
            state = adaptive.state(db, user_id=self.user_id)

            base_answers = 0
            adaptive_answers = 0
            for _ in range(80):
                if state["complete"]:
                    break
                question = state["question"]
                self.assertIsNotNone(question)
                if question["kind"] == "base":
                    base_answers += 1
                else:
                    adaptive_answers += 1
                state = adaptive.answer(
                    db,
                    user_id=self.user_id,
                    question_token=question["token"],
                    value=4,
                )

            db.commit()

            self.assertTrue(state["complete"])
            self.assertEqual(base_answers, 30)
            self.assertGreaterEqual(adaptive_answers, adaptive.MIN_ADAPTIVE_ANSWERS)
            self.assertLessEqual(adaptive_answers, adaptive.MAX_ADAPTIVE_ANSWERS)
            self.assertLess(adaptive_answers, adaptive.MAX_ADAPTIVE_ANSWERS)

            profile = db.get(Profile, self.user_id)
            self.assertTrue(profile.questionnaire_completed)

            generated = db.query(AdaptiveQuestionnaireQuestion).filter_by(
                user_id=self.user_id
            ).all()
            self.assertGreaterEqual(len(generated), adaptive_answers)
            self.assertTrue(all(item.source == "BANK" for item in generated))

            portrait = {
                item["key"]: item
                for item in state["portrait"]
            }
            self.assertEqual(len(portrait), len(adaptive.AXES))
            self.assertEqual(portrait["trust_honesty"]["score"], 75)

    def test_conflicting_answers_request_more_clarification(self):
        with Session(self.engine) as db:
            state = adaptive.state(db, user_id=self.user_id)
            base_index = 0
            adaptive_answers = 0

            for _ in range(100):
                if state["complete"]:
                    break
                question = state["question"]
                if question["kind"] == "base":
                    value = 1 if base_index % 2 == 0 else 5
                    base_index += 1
                else:
                    value = 3
                    adaptive_answers += 1
                state = adaptive.answer(
                    db,
                    user_id=self.user_id,
                    question_token=question["token"],
                    value=value,
                )

            db.commit()
            self.assertTrue(state["complete"])
            self.assertGreaterEqual(adaptive_answers, 12)
            self.assertLessEqual(adaptive_answers, adaptive.MAX_ADAPTIVE_ANSWERS)

    def test_adaptive_questions_are_generated_one_at_a_time(self):
        with Session(self.engine) as db:
            state = adaptive.state(db, user_id=self.user_id)

            while state["phase"] == "BASE":
                state = adaptive.answer(
                    db,
                    user_id=self.user_id,
                    question_token=state["question"]["token"],
                    value=4,
                )

            self.assertEqual(state["phase"], "ADAPTIVE")
            self.assertEqual(state.get("prefetch"), [])
            pending = adaptive._unanswered_generated(db, self.user_id)
            self.assertEqual(len(pending), 1)
            first_id = pending[0].id

            state = adaptive.answer(
                db,
                user_id=self.user_id,
                question_token=state["question"]["token"],
                value=5,
            )
            self.assertEqual(state["phase"], "ADAPTIVE")
            self.assertEqual(state.get("prefetch"), [])
            pending = adaptive._unanswered_generated(db, self.user_id)
            self.assertEqual(len(pending), 1)
            self.assertNotEqual(pending[0].id, first_id)

            total_min = len(adaptive.BASE_ORDER) + adaptive.MIN_ADAPTIVE_ANSWERS
            total_max = len(adaptive.BASE_ORDER) + adaptive.MAX_ADAPTIVE_ANSWERS
            self.assertEqual(total_min, 35)
            self.assertEqual(total_max, 50)

    def test_adaptive_scores_are_comparable_on_fixed_axes(self):
        with Session(self.engine) as db:
            state = adaptive.state(db, user_id=self.user_id)
            for _ in range(80):
                if state["complete"]:
                    break
                state = adaptive.answer(
                    db,
                    user_id=self.user_id,
                    question_token=state["question"]["token"],
                    value=4,
                )
            scores = adaptive.adaptive_category_scores(
                db,
                user_a=self.user_id,
                user_b=self.user_id,
            )
            self.assertTrue(scores)
            self.assertTrue(all(value == 100 for value in scores.values()))


if __name__ == "__main__":
    unittest.main()
