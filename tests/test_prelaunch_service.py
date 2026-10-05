import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.models import (
    Market,
    Profile,
    QuestionnaireAnswer,
    Setting,
    User,
)
from app.interests import service as interests
from app.matching.service import rank_candidates
from app.prelaunch import (
    candidate_output_enabled,
    feature_flags,
    own_compatibility_profile,
    prelaunch_mode,
    waitlist_status,
)
from app.questionnaire import service as questionnaire


class PrelaunchServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE settings, users, markets, questionnaire_versions "
                "RESTART IDENTITY CASCADE"
            ))
        with Session(self.engine) as db:
            market=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=True,
            )
            db.add(market); db.flush()
            self.market_id=market.id
            version=questionnaire.seed_v7_questionnaire(db)
            db.commit()
            self.question_ids=[
                q.id for q in questionnaire.questions_for_version(db,version.id)
            ]

    def add_ready_user(self,db,email,*,gender="M",seek_gender="ANY",answer=3):
        user=User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            status="ACTIVE",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user); db.flush()
        db.add(Profile(
            user_id=user.id,display_name=email.split("@")[0],dob=date(1997,5,30),
            gender=gender,seek_gender=seek_gender,city="Алматы",country_code="KZ",
            market_id=self.market_id,relationship_status="ACTIVE_SEARCH",
            eligibility_status="ACTIVE_FOR_MATCHING",profile_completed=True,
            questionnaire_completed=True,partner_preferences_completed=True,
            photos_completed=True,readiness_score=90,
            readiness_chat="YES",readiness_offline="YES",
            height=175,dating_goal="SERIOUS",children_status="NO_CHILDREN",
            children_plans="MAYBE",smoking="NO",alcohol="RARE",
            lifestyle="BALANCED",
        ))
        for qid in self.question_ids:
            db.add(QuestionnaireAnswer(user_id=user.id,question_id=qid,value_int=answer))
        db.flush()
        return user.id

    def set_setting(self,db,key,value):
        row=db.get(Setting,key)
        if row is None:
            db.add(Setting(key=key,value=value))
        else:
            row.value=value
        db.flush()

    def test_defaults_fail_closed_for_candidate_output(self):
        with Session(self.engine) as db:
            self.assertTrue(prelaunch_mode(db))
            self.assertFalse(candidate_output_enabled(db))
            flags=feature_flags(db)
            self.assertTrue(flags["registration_enabled"])
            self.assertTrue(flags["questionnaire_enabled"])
            self.assertTrue(flags["photo_upload_enabled"])
            self.assertTrue(flags["own_compatibility_profile_enabled"])
            self.assertTrue(flags["waitlist_enabled"])
            self.assertFalse(flags["candidate_output_enabled"])

    def test_prelaunch_ready_profile_enters_waitlist(self):
        with Session(self.engine) as db:
            user_id=self.add_ready_user(db,"ready@example.com")
            db.commit()
            state=waitlist_status(db,user_id=user_id)
            self.assertTrue(state["ready"])
            self.assertEqual(state["state"],"WAITLIST")
            self.assertFalse(state["features"]["candidate_output_enabled"])

    def test_incomplete_profile_does_not_claim_waitlist_ready(self):
        with Session(self.engine) as db:
            user_id=self.add_ready_user(db,"incomplete@example.com")
            profile=db.get(Profile,user_id)
            profile.photos_completed=False
            db.commit()
            state=waitlist_status(db,user_id=user_id)
            self.assertFalse(state["ready"])
            self.assertEqual(state["state"],"PROFILE_INCOMPLETE_OR_INACTIVE")

    def test_controlled_matching_can_be_enabled_during_prelaunch(self):
        with Session(self.engine) as db:
            self.set_setting(db,"PRE_LAUNCH_MODE","true")
            self.set_setting(db,"PRELAUNCH_MATCHING_ENABLED","true")
            user_id=self.add_ready_user(db,"ready@example.com")
            db.commit()
            self.assertTrue(candidate_output_enabled(db))
            self.assertEqual(waitlist_status(db,user_id=user_id)["state"],"MATCHING_ACTIVE")

    def test_public_launch_always_allows_candidate_output(self):
        with Session(self.engine) as db:
            self.set_setting(db,"PRE_LAUNCH_MODE","false")
            self.set_setting(db,"PRELAUNCH_MATCHING_ENABLED","false")
            db.commit()
            self.assertFalse(prelaunch_mode(db))
            self.assertTrue(candidate_output_enabled(db))

    def test_own_compatibility_profile_preserves_v7_summary_formula(self):
        with Session(self.engine) as db:
            user_id=self.add_ready_user(db,"summary@example.com",answer=5)
            db.commit()
            result=own_compatibility_profile(db,user_id=user_id)
            self.assertEqual(result["version"],"v7-64")
            self.assertEqual(
                result["summary"],
                {
                    "Ценности":100,
                    "Ориентация на семью":100,
                    "Потребность в близости":100,
                    "Социальность":100,
                    "Амбициозность":100,
                },
            )
            self.assertIn("не оценка личности",result["note"])

    def test_rank_candidates_returns_empty_while_prelaunch_output_disabled(self):
        with Session(self.engine) as db:
            a=self.add_ready_user(db,"a@example.com",gender="M",seek_gender="ANY")
            self.add_ready_user(db,"b@example.com",gender="F",seek_gender="ANY")
            db.commit()
            self.assertEqual(rank_candidates(db,user_id=a,limit=5),[])

    def test_rank_candidates_works_when_controlled_test_is_enabled(self):
        with Session(self.engine) as db:
            self.set_setting(db,"PRELAUNCH_MATCHING_ENABLED","true")
            a=self.add_ready_user(db,"a@example.com",gender="M",seek_gender="ANY")
            b=self.add_ready_user(db,"b@example.com",gender="F",seek_gender="ANY")
            db.commit()
            rows=rank_candidates(db,user_id=a,limit=5)
            self.assertIn(b,[row["user_id"] for row in rows])

    def test_interest_service_uses_same_fail_closed_policy(self):
        with Session(self.engine) as db:
            a=self.add_ready_user(db,"a@example.com")
            b=self.add_ready_user(db,"b@example.com")
            db.commit()
            with self.assertRaises(interests.InterestActionsDisabled):
                interests.express_interest(db,from_user=a,to_user=b)


if __name__=="__main__":
    unittest.main()
