import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Profile,
    QuestionnaireQuestion,
    QuestionnaireVersion,
    User,
)
from app.questionnaire import service as qsvc
from app.questionnaire.catalog_v7 import V7_QUESTIONS, V7_VERSION_CODE


class QuestionnaireServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            for table in [
                "questionnaire_answers","questionnaire_questions","questionnaire_versions",
                "user_status_history","profiles","sessions","auth_outbox","auth_challenges",
                "auth_rate_limits","auth_identities","users"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))

        with Session(self.engine) as db:
            user = User(
                email="questionnaire@example.com",
                password_hash="test-hash",
                referral_code="questionnaire-ref",
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id, display_name="Tester"))
            db.commit()
            self.user_id = user.id

    def test_seed_is_idempotent_and_exact_v7_catalog(self):
        with Session(self.engine) as db:
            v1 = qsvc.seed_v7_questionnaire(db)
            db.commit()
            first_id = v1.id
            v2 = qsvc.seed_v7_questionnaire(db)
            db.commit()

            self.assertEqual(v2.id, first_id)
            self.assertEqual(v2.code, V7_VERSION_CODE)
            questions = qsvc.questions_for_version(db, v2.id)
            self.assertEqual(len(questions), 64)
            self.assertEqual(len({q.question_text for q in questions}), 64)
            self.assertEqual(
                [(q.legacy_qid, q.category, q.question_text) for q in questions],
                V7_QUESTIONS,
            )
            self.assertTrue(all(q.answer_type == "scale" for q in questions))
            self.assertTrue(all(q.is_required for q in questions))

    def test_sections_preserve_order_and_four_questions_per_section(self):
        with Session(self.engine) as db:
            qsvc.seed_v7_questionnaire(db)
            db.commit()
            sections = qsvc.sections(db)
            self.assertEqual(len(sections), 16)
            self.assertEqual(sections[0]["category"], "Обо мне")
            self.assertEqual(sections[-1]["category"], "Жизненные планы")
            self.assertTrue(all(len(section["questions"]) == 4 for section in sections))

    def test_progress_starts_zero_and_completes_after_64_answers(self):
        with Session(self.engine) as db:
            version = qsvc.seed_v7_questionnaire(db)
            db.commit()
            state = qsvc.progress(db, user_id=self.user_id)
            self.assertEqual(state["required_total"], 64)
            self.assertEqual(state["required_answered"], 0)
            self.assertEqual(state["percent"], 0)
            self.assertFalse(state["complete"])

            questions = qsvc.questions_for_version(db, version.id)
            for q in questions:
                qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=3)
            db.commit()

            state = qsvc.progress(db, user_id=self.user_id)
            profile = db.get(Profile, self.user_id)
            self.assertEqual(state["required_answered"], 64)
            self.assertEqual(state["percent"], 100)
            self.assertTrue(state["complete"])
            self.assertTrue(profile.questionnaire_completed)

    def test_scale_rejects_out_of_range_and_boolean(self):
        with Session(self.engine) as db:
            version = qsvc.seed_v7_questionnaire(db)
            db.commit()
            q = qsvc.questions_for_version(db, version.id)[0]
            with self.assertRaises(qsvc.InvalidAnswer):
                qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=0)
            with self.assertRaises(qsvc.InvalidAnswer):
                qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=6)
            with self.assertRaises(qsvc.InvalidAnswer):
                qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=True)

    def test_answer_update_does_not_duplicate(self):
        with Session(self.engine) as db:
            version = qsvc.seed_v7_questionnaire(db)
            db.commit()
            q = qsvc.questions_for_version(db, version.id)[0]
            qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=2)
            qsvc.save_answer(db, user_id=self.user_id, question_id=q.id, value=5)
            db.commit()
            row = db.execute(text(
                "SELECT value_int FROM questionnaire_answers WHERE user_id=:u AND question_id=:q"
            ), {"u": self.user_id, "q": q.id}).all()
            self.assertEqual(row, [(5,)])

    def test_only_active_questionnaire_accepts_answers(self):
        with Session(self.engine) as db:
            active = qsvc.seed_v7_questionnaire(db)
            old = QuestionnaireVersion(code="old-v1", title="Old", is_active=False)
            db.add(old); db.flush()
            old_q = QuestionnaireQuestion(
                version_id=old.id,
                category="Old",
                question_text="Old question",
                answer_type="scale",
                is_required=True,
                weight=1,
                match_logic={"scale_min":1,"scale_max":5},
                position=1,
            )
            db.add(old_q); db.commit()
            self.assertTrue(active.is_active)
            with self.assertRaises(qsvc.QuestionnaireError):
                qsvc.save_answer(db, user_id=self.user_id, question_id=old_q.id, value=3)

    def test_database_rejects_invalid_answer_type_and_weight(self):
        with Session(self.engine) as db:
            version = qsvc.seed_v7_questionnaire(db)
            db.commit()
            bad = QuestionnaireQuestion(
                version_id=version.id,
                category="X",
                question_text="Bad",
                answer_type="unknown",
                is_required=True,
                weight=1,
                match_logic={},
                position=999,
            )
            db.add(bad)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            bad2 = QuestionnaireQuestion(
                version_id=version.id,
                category="X",
                question_text="Bad weight",
                answer_type="scale",
                is_required=True,
                weight=0,
                match_logic={},
                position=998,
            )
            db.add(bad2)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_single_multiple_priority_and_text_validation(self):
        with Session(self.engine) as db:
            base = qsvc.seed_v7_questionnaire(db)
            base.is_active = False
            custom = QuestionnaireVersion(code="typed-test", title="Typed", is_active=True)
            db.add(custom); db.flush()

            questions = [
                QuestionnaireQuestion(
                    version_id=custom.id,category="X",question_text="Single",answer_type="single",
                    is_required=True,options_json=[{"value":"A"},{"value":"B"}],weight=1,match_logic={},position=1,
                ),
                QuestionnaireQuestion(
                    version_id=custom.id,category="X",question_text="Multiple",answer_type="multiple",
                    is_required=True,options_json=[{"value":"A"},{"value":"B"}],weight=1,match_logic={},position=2,
                ),
                QuestionnaireQuestion(
                    version_id=custom.id,category="X",question_text="Priority",answer_type="priority",
                    is_required=True,options_json=[{"value":"HIGH"},{"value":"LOW"}],weight=1,match_logic={},position=3,
                ),
                QuestionnaireQuestion(
                    version_id=custom.id,category="X",question_text="Text",answer_type="text",
                    is_required=False,weight=1,match_logic={},position=4,
                ),
            ]
            db.add_all(questions); db.commit()

            qsvc.save_answer(db,user_id=self.user_id,question_id=questions[0].id,value="A")
            qsvc.save_answer(db,user_id=self.user_id,question_id=questions[1].id,value=["A","B"])
            qsvc.save_answer(db,user_id=self.user_id,question_id=questions[2].id,value="HIGH")
            qsvc.save_answer(db,user_id=self.user_id,question_id=questions[3].id,value="note")
            db.commit()

            with self.assertRaises(qsvc.InvalidAnswer):
                qsvc.save_answer(db,user_id=self.user_id,question_id=questions[0].id,value="Z")
            with self.assertRaises(qsvc.InvalidAnswer):
                qsvc.save_answer(db,user_id=self.user_id,question_id=questions[1].id,value=["A","A"])

            state = qsvc.progress(db,user_id=self.user_id)
            self.assertEqual(state["required_total"], 3)
            self.assertEqual(state["required_answered"], 3)
            self.assertTrue(state["complete"])


if __name__ == "__main__":
    unittest.main()
