import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.db.models import Market, Profile, QuestionnaireAnswer, User
from app.matching.service import rank_candidates
from app.questionnaire import service as questionnaire


class PerformanceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users, markets, questionnaire_versions, settings RESTART IDENTITY CASCADE"))
            c.execute(text("INSERT INTO settings(key,value) VALUES ('PRE_LAUNCH_MODE','false')"))
        self.now=datetime.now(timezone.utc)

    def seed_user(self,db,email,market_id,question_ids,answer=3):
        u=User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            email_verified_at=self.now,
        )
        db.add(u); db.flush()
        db.add(Profile(
            user_id=u.id,display_name=email.split("@")[0],dob=date(1997,1,1),
            gender="M",seek_gender="ANY",city="Алматы",country_code="KZ",
            market_id=market_id,relationship_status="ACTIVE_SEARCH",
            eligibility_status="ACTIVE_FOR_MATCHING",readiness_score=90,
            questionnaire_completed=True,partner_preferences_completed=True,
            photos_completed=True,profile_completed=True,updated_at=self.now,
        ))
        for qid in question_ids:
            db.add(QuestionnaireAnswer(user_id=u.id,question_id=qid,value_int=answer))
        db.flush()
        return u.id

    def test_matching_work_is_explicitly_bounded(self):
        with Session(self.engine) as db:
            market=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ"],registration_open=True,matching_open=True,
            )
            db.add(market); db.flush()
            version=questionnaire.seed_v7_questionnaire(db); db.flush()
            qids=[q.id for q in questionnaire.questions_for_version(db,version.id)]
            source=self.seed_user(db,"source@example.com",market.id,qids)
            for i in range(30):
                self.seed_user(db,f"candidate{i}@example.com",market.id,qids,answer=3+(i%3)-1)
            db.commit()

            with self.assertRaises(ValueError):
                rank_candidates(db,user_id=source,limit=5,pool_limit=1001,now=self.now)
            ranked=rank_candidates(db,user_id=source,limit=5,pool_limit=100,now=self.now)
            self.assertEqual(len(ranked),5)

    def test_matching_query_count_has_a_regression_budget(self):
        with Session(self.engine) as db:
            market=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ"],registration_open=True,matching_open=True,
            )
            db.add(market); db.flush()
            version=questionnaire.seed_v7_questionnaire(db); db.flush()
            qids=[q.id for q in questionnaire.questions_for_version(db,version.id)]
            source=self.seed_user(db,"source@example.com",market.id,qids)
            for i in range(20):
                self.seed_user(db,f"candidate{i}@example.com",market.id,qids)
            db.commit()

            count=0
            def before_cursor_execute(conn,cursor,statement,parameters,context,executemany):
                nonlocal count
                count += 1

            event.listen(self.engine,"before_cursor_execute",before_cursor_execute)
            try:
                ranked=rank_candidates(db,user_id=source,limit=5,pool_limit=100,now=self.now)
            finally:
                event.remove(self.engine,"before_cursor_execute",before_cursor_execute)

            self.assertEqual(len(ranked),5)
            # This is a regression ceiling, not a target. The Phase 22 audit
            # documents that matching still has N+1 work to remove before scale.
            self.assertLess(count,600,f"matching query count regressed: {count}")


if __name__=="__main__":
    unittest.main()
