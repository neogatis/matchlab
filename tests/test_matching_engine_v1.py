import os
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Block,
    Market,
    PartnerPreference,
    Profile,
    QuestionnaireAnswer,
    Setting,
    User,
)
from app.matching import service as matching
from app.matching.config import CATEGORY_SECTIONS
from app.preferences import service as preferences
from app.questionnaire import service as questionnaire
from app.questionnaire.catalog_v7 import V7_QUESTIONS


class MatchingEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE settings, users, markets, questionnaire_versions RESTART IDENTITY CASCADE"
            ))

        self.now = datetime.now(timezone.utc)
        with Session(self.engine) as db:
            self.ala = Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                latitude=43.238949,longitude=76.889709,
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=True,
            )
            self.ast = Market(
                code="KZ-AST",country_code="KZ",city_code="AST",display_name="Астана",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                latitude=51.169392,longitude=71.449074,
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=True,
            )
            db.add_all([self.ala,self.ast]); db.flush()
            self.ala_id,self.ast_id=self.ala.id,self.ast.id
            version=questionnaire.seed_v7_questionnaire(db)
            db.commit()
            self.version_id=version.id
            self.questions=questionnaire.questions_for_version(db,version.id)
            self.question_ids=[q.id for q in self.questions]
            db.add(Setting(key="PRE_LAUNCH_MODE", value="true"))
            db.add(Setting(key="PRELAUNCH_MATCHING_ENABLED", value="true"))
            db.commit()

    def add_user(
        self,
        db,
        *,
        email,
        gender="M",
        seek_gender="ANY",
        dob=date(1997,1,1),
        market_id=None,
        relationship_status="ACTIVE_SEARCH",
        eligibility_status="ACTIVE_FOR_MATCHING",
        dating_goal="SERIOUS",
        readiness_score=100,
        height=175,
        children_status="NO_CHILDREN",
        children_plans="WANTS",
        smoking="NO",
        alcohol="RARE",
        lifestyle="ACTIVE",
        religion="",
        nationality="",
        answer_value=3,
        updated_at=None,
    ):
        user=User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            email_verified_at=self.now,
        )
        db.add(user); db.flush()
        p=Profile(
            user_id=user.id,
            display_name=email.split("@")[0],
            dob=dob,
            gender=gender,
            seek_gender=seek_gender,
            city="Алматы" if (market_id or self.ala_id)==self.ala_id else "Астана",
            country_code="KZ",
            market_id=market_id or self.ala_id,
            relationship_status=relationship_status,
            eligibility_status=eligibility_status,
            dating_goal=dating_goal,
            readiness_score=readiness_score,
            height=height,
            children_status=children_status,
            children_plans=children_plans,
            smoking=smoking,
            alcohol=alcohol,
            lifestyle=lifestyle,
            religion=religion,
            nationality=nationality,
            questionnaire_completed=True,
            partner_preferences_completed=True,
            photos_completed=True,
            profile_completed=True,
            updated_at=updated_at or self.now,
        )
        db.add(p)
        for qid in self.question_ids:
            db.add(QuestionnaireAnswer(user_id=user.id,question_id=qid,value_int=answer_value))
        db.flush()
        return user.id

    def pref(self,db,user_id,key,importance,*,values=None,min_value=None,max_value=None):
        row=PartnerPreference(
            user_id=user_id,criterion_key=key,importance=importance,
            values_json=values,min_value=min_value,max_value=max_value,
        )
        db.add(row); db.flush()
        return row

    def test_database_rejects_invalid_coordinates_and_children_status(self):
        with Session(self.engine) as db:
            bad=Market(
                code="BAD",country_code="KZ",city_code="BAD",display_name="Bad",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                latitude=100,longitude=0,supported_languages=["ru-KZ"],
                registration_open=True,matching_open=True,
            )
            db.add(bad)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with Session(self.engine) as db:
            user=User(email="badchild@example.com",password_hash="x",referral_code="badchild")
            db.add(user); db.flush()
            p=Profile(user_id=user.id,display_name="Bad",children_status="UNKNOWN")
            db.add(p)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_category_mapping_covers_every_v7_section_once(self):
        all_sections=[section for sections in CATEGORY_SECTIONS.values() for section in sections]
        catalog_sections={section for _,section,_ in V7_QUESTIONS}
        self.assertEqual(set(all_sections),catalog_sections)
        self.assertEqual(len(all_sections),len(set(all_sections)))

    def test_mutual_pair_passes_and_identical_answers_score_100_compatibility(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M")
            db.commit()
            result=matching.evaluate_pair(db,a,b,now=self.now)
            self.assertTrue(result["eligible"],result)
            self.assertEqual(result["compatibility_score"],100)
            self.assertEqual(len(result["category_scores"]),8)
            self.assertEqual(set(result["category_scores"].values()),{100})
            self.assertGreaterEqual(result["final_mutual_fit_score"],0)
            self.assertLessEqual(result["final_mutual_fit_score"],100)

    def test_unverified_email_does_not_block_matching(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M")
            db.get(User,a).email_verified_at=None
            db.get(User,b).email_verified_at=None
            db.commit()
            result=matching.evaluate_pair(db,a,b,now=self.now)
            self.assertTrue(result["eligible"],result)

    def test_unverified_email_candidate_is_still_ranked(self):
        with Session(self.engine) as db:
            source=self.add_user(db,email="source@example.com",seek_gender="ANY")
            candidate=self.add_user(db,email="candidate@example.com",seek_gender="ANY")
            db.get(User,source).email_verified_at=None
            db.get(User,candidate).email_verified_at=None
            db.commit()
            ranked=matching.rank_candidates(db,user_id=source,limit=5,now=self.now)
            self.assertIn(candidate,[row["user_id"] for row in ranked])

    def test_configured_gender_ignore_overrides_legacy_seek_gender_filter(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F")
            b=self.add_user(db,email="b@example.com",gender="M",seek_gender="ANY")
            self.pref(db,a,"gender","IGNORE")
            db.commit()
            result=matching.evaluate_pair(db,a,b,now=self.now)
            self.assertTrue(result["eligible"],result)

    def test_configured_gender_hard_still_filters(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="ANY")
            b=self.add_user(db,email="b@example.com",gender="M",seek_gender="ANY")
            self.pref(db,a,"gender","HARD",values=["F"])
            db.commit()
            result=matching.evaluate_pair(db,a,b,now=self.now)
            self.assertFalse(result["eligible"])
            self.assertEqual(result["reason"],"source_hard:gender")

    def test_one_sided_hard_age_conflict_blocks_pair(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F",dob=date(1997,1,1))
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M",dob=date(1985,1,1))
            self.pref(db,a,"age","HARD",min_value=24,max_value=35)
            db.commit()
            ok,reason=matching.mutual_hard_pass(db,a,b)
            self.assertFalse(ok)
            self.assertEqual(reason,"source_hard:age")

    def test_reverse_hard_height_conflict_blocks_pair(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F",height=170)
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M",height=165)
            self.pref(db,b,"height","HARD",min_value=180,max_value=200)
            db.commit()
            ok,reason=matching.mutual_hard_pass(db,a,b)
            self.assertFalse(ok)
            self.assertEqual(reason,"target_hard:height")

    def test_paused_in_relationship_and_blocked_profiles_are_excluded(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F")
            paused=self.add_user(
                db,email="paused@example.com",gender="F",seek_gender="M",
                relationship_status="PAUSED",eligibility_status="NOT_ACTIVE_FOR_MATCHING",
            )
            db.commit()
            self.assertFalse(matching.evaluate_pair(db,a,paused)["eligible"])

        self.setUp()
        with Session(self.engine) as db:
            a=self.add_user(db,email="a2@example.com",gender="M",seek_gender="F")
            rel=self.add_user(
                db,email="rel@example.com",gender="F",seek_gender="M",
                relationship_status="IN_RELATIONSHIP",eligibility_status="NOT_ACTIVE_FOR_MATCHING",
            )
            db.commit()
            self.assertFalse(matching.evaluate_pair(db,a,rel)["eligible"])

        self.setUp()
        with Session(self.engine) as db:
            a=self.add_user(db,email="a3@example.com",gender="M",seek_gender="F")
            b=self.add_user(db,email="b3@example.com",gender="F",seek_gender="M")
            db.add(Block(blocker=b,blocked=a,created_at=self.now))
            db.commit()
            result=matching.evaluate_pair(db,a,b)
            self.assertFalse(result["eligible"])
            self.assertEqual(result["reason"],"blocked")

    def test_hard_distance_uses_market_centroids(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F",market_id=self.ala_id)
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M",market_id=self.ast_id)
            self.pref(db,a,"distance_km","HARD",max_value=100)
            db.commit()
            result=matching.evaluate_pair(db,a,b)
            self.assertFalse(result["eligible"])
            self.assertEqual(result["reason"],"source_hard:distance_km")

    def test_soft_preferences_affect_mutual_preference_score_but_not_eligibility(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F",smoking="NO",lifestyle="ACTIVE")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M",smoking="NO",lifestyle="ACTIVE")
            self.pref(db,a,"smoking","IMPORTANT",values=["NO"])
            self.pref(db,b,"lifestyle","PREFERENCE",values=["ACTIVE"])
            db.commit()
            good=matching.evaluate_pair(db,a,b)
            self.assertTrue(good["eligible"])
            self.assertEqual(good["mutual_preference_score"],100)

            db.get(Profile,b).smoking="YES"
            db.commit()
            lower=matching.evaluate_pair(db,a,b)
            self.assertTrue(lower["eligible"])
            self.assertLess(lower["mutual_preference_score"],good["mutual_preference_score"])

    def test_any_soft_preference_is_neutral_and_not_scored(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M")
            db.commit()
            baseline=matching.mutual_preference_score(db,a,b)
            self.assertEqual(baseline,50)

            self.pref(db,a,"smoking","PREFERENCE",values=["ANY"])
            db.commit()
            self.assertEqual(matching.mutual_preference_score(db,a,b),baseline)

    def test_any_market_and_religion_are_neutral(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="ANY",religion="islam")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="ANY",religion="christian")
            self.pref(db,a,"market","PREFERENCE",values=["ANY"])
            self.pref(db,a,"religion","PREFERENCE",values=["ANY"])
            db.commit()
            self.assertEqual(matching.mutual_preference_score(db,a,b),50)

    def test_ignore_preference_is_not_in_soft_denominator(self):
        with Session(self.engine) as db:
            a=self.add_user(db,email="a@example.com",gender="M",seek_gender="F",smoking="YES")
            b=self.add_user(db,email="b@example.com",gender="F",seek_gender="M",smoking="NO")
            self.pref(db,a,"smoking","IGNORE",values=["NO"])
            db.commit()
            self.assertEqual(matching.mutual_preference_score(db,a,b),50)

    def test_preference_service_normalizes_legacy_any_to_ignore(self):
        with Session(self.engine) as db:
            user_id=self.add_user(db,email="a@example.com")
            db.commit()
            row=preferences.set_preference(
                db,
                user_id=user_id,
                key="smoking",
                importance="PREFERENCE",
                value=["ANY"],
            )
            db.commit()
            self.assertEqual(row.importance,"IGNORE")
            self.assertIsNone(row.values_json)

    def test_questionnaire_difference_changes_ranking(self):
        with Session(self.engine) as db:
            source=self.add_user(db,email="source@example.com",seek_gender="ANY",answer_value=3)
            best=self.add_user(db,email="best@example.com",seek_gender="ANY",answer_value=3)
            mid=self.add_user(db,email="mid@example.com",seek_gender="ANY",answer_value=4)
            low=self.add_user(db,email="low@example.com",seek_gender="ANY",answer_value=5)
            db.commit()
            ranked=matching.rank_candidates(db,user_id=source,limit=3,now=self.now)
            self.assertEqual([x["user_id"] for x in ranked],[best,mid,low])
            self.assertGreater(ranked[0]["compatibility_score"],ranked[1]["compatibility_score"])
            self.assertGreater(ranked[1]["compatibility_score"],ranked[2]["compatibility_score"])

    def test_activity_score_penalizes_old_inactive_profile(self):
        with Session(self.engine) as db:
            fresh=self.add_user(db,email="fresh@example.com",updated_at=self.now)
            old=self.add_user(db,email="old@example.com",updated_at=self.now-timedelta(days=45))
            db.commit()
            self.assertEqual(matching.user_activity_score(db,db.get(Profile,fresh),now=self.now),100)
            self.assertEqual(matching.user_activity_score(db,db.get(Profile,old),now=self.now),10)

    def test_large_candidate_pool_returns_small_ranked_set(self):
        with Session(self.engine) as db:
            source=self.add_user(db,email="source@example.com",seek_gender="ANY",answer_value=3)
            for i in range(75):
                self.add_user(
                    db,email=f"candidate{i}@example.com",seek_gender="ANY",
                    answer_value=3 + (i % 3) - 1,
                )
            db.commit()
            ranked=matching.rank_candidates(db,user_id=source,limit=5,pool_limit=500,now=self.now)
            self.assertEqual(len(ranked),5)
            self.assertTrue(all(x["eligible"] for x in ranked))
            self.assertTrue(all(ranked[i]["final_mutual_fit_score"] >= ranked[i+1]["final_mutual_fit_score"] for i in range(4)))


if __name__=="__main__":
    unittest.main()
