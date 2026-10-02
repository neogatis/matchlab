import os
import unittest
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.balance import (
    age_band,
    build_balance_report,
    source_breakdown,
    supply_demand_matrix,
)
from app.db.models import (
    Market,
    MarketingAttribution,
    PartnerPreference,
    Profile,
    User,
)


class BalanceServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users, markets RESTART IDENTITY CASCADE"))

        with Session(self.engine) as db:
            ala=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=False,
            )
            ast=Market(
                code="KZ-AST",country_code="KZ",city_code="AST",display_name="Астана",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=False,
            )
            db.add_all([ala,ast]); db.flush()
            self.ala_id=ala.id
            self.ast_id=ast.id
            db.commit()

    def add_user(
        self,
        db,
        *,
        email,
        gender,
        dob,
        seek_gender="ANY",
        market_id=None,
        status="ACTIVE",
        relationship_status="ACTIVE_SEARCH",
        completed=True,
        referred_by=None,
        source=None,
    ):
        user=User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            status=status,
            referred_by=referred_by,
        )
        db.add(user); db.flush()
        profile=Profile(
            user_id=user.id,
            display_name=email.split("@")[0],
            dob=dob,
            gender=gender,
            seek_gender=seek_gender,
            city="Алматы" if (market_id or self.ala_id)==self.ala_id else "Астана",
            country_code="KZ",
            market_id=market_id or self.ala_id,
            relationship_status=relationship_status,
            eligibility_status=(
                "ACTIVE_FOR_MATCHING"
                if relationship_status in {"ACTIVE_SEARCH","OPEN_TO_MATCH"}
                else "NOT_ACTIVE_FOR_MATCHING"
            ),
            profile_completed=completed,
            questionnaire_completed=completed,
            partner_preferences_completed=completed,
            photos_completed=completed,
        )
        db.add(profile)
        if source:
            db.add(MarketingAttribution(user_id=user.id,utm_source=source))
        db.flush()
        return user.id

    def add_preferences(self,db,user_id,*,target_gender,min_age,max_age):
        db.add_all([
            PartnerPreference(
                user_id=user_id,
                criterion_key="gender",
                importance="HARD",
                values_json=[target_gender],
            ),
            PartnerPreference(
                user_id=user_id,
                criterion_key="age",
                importance="HARD",
                min_value=min_age,
                max_value=max_age,
            ),
        ])
        db.flush()

    def test_age_bands(self):
        self.assertEqual(age_band(18),"18–23")
        self.assertEqual(age_band(24),"24–28")
        self.assertEqual(age_band(29),"29–35")
        self.assertEqual(age_band(36),"36–45")
        self.assertEqual(age_band(46),"46+")
        self.assertIsNone(age_band(17))

    def test_prelaunch_market_still_counts_ready_supply(self):
        with Session(self.engine) as db:
            self.add_user(
                db,email="woman@example.com",gender="F",dob=date(2000,1,1),
                seek_gender="M",
            )
            db.commit()
            report=build_balance_report(db,market_code="KZ-ALA")
            self.assertEqual(report["overview"]["active_matchable_users"],1)
            self.assertEqual(report["overview"]["women"],1)

    def test_supply_demand_gap_is_computed_from_mutual_market_pool(self):
        with Session(self.engine) as db:
            f1=self.add_user(
                db,email="f1@example.com",gender="F",dob=date(2000,1,1),seek_gender="M"
            )
            f2=self.add_user(
                db,email="f2@example.com",gender="F",dob=date(1999,1,1),seek_gender="M"
            )
            self.add_user(
                db,email="m1@example.com",gender="M",dob=date(1994,1,1),seek_gender="F"
            )
            self.add_preferences(db,f1,target_gender="M",min_age=29,max_age=35)
            self.add_preferences(db,f2,target_gender="M",min_age=29,max_age=35)
            db.commit()

            rows=supply_demand_matrix(db,market_code="KZ-ALA")
            target=next(
                row for row in rows
                if row["seeker_gender"]=="F"
                and row["target_gender"]=="M"
                and row["age_band"]=="29–35"
            )
            self.assertEqual(target["demand"],2)
            self.assertEqual(target["supply"],1)
            self.assertEqual(target["gap"],1)
            self.assertEqual(target["coverage_percent"],50.0)

    def test_paused_banned_and_incomplete_profiles_do_not_count_as_ready(self):
        with Session(self.engine) as db:
            self.add_user(
                db,email="ok@example.com",gender="F",dob=date(2000,1,1)
            )
            self.add_user(
                db,email="paused@example.com",gender="F",dob=date(2000,1,1),
                relationship_status="PAUSED",
            )
            self.add_user(
                db,email="banned@example.com",gender="F",dob=date(2000,1,1),
                status="BANNED",
            )
            self.add_user(
                db,email="incomplete@example.com",gender="F",dob=date(2000,1,1),
                completed=False,
            )
            db.commit()
            report=build_balance_report(db,market_code="KZ-ALA")
            self.assertEqual(report["overview"]["active_matchable_users"],1)

    def test_market_filter_does_not_mix_cities(self):
        with Session(self.engine) as db:
            self.add_user(
                db,email="ala@example.com",gender="F",dob=date(2000,1,1),
                market_id=self.ala_id,
            )
            self.add_user(
                db,email="ast@example.com",gender="M",dob=date(1995,1,1),
                market_id=self.ast_id,
            )
            db.commit()
            ala=build_balance_report(db,market_code="KZ-ALA")
            ast=build_balance_report(db,market_code="KZ-AST")
            self.assertEqual(ala["overview"]["active_matchable_users"],1)
            self.assertEqual(ala["overview"]["women"],1)
            self.assertEqual(ala["overview"]["men"],0)
            self.assertEqual(ast["overview"]["men"],1)

    def test_source_breakdown_tracks_completed_active_profiles(self):
        with Session(self.engine) as db:
            referrer=self.add_user(
                db,email="referrer@example.com",gender="M",dob=date(1995,1,1),
                completed=False,
            )
            self.add_user(
                db,email="meta@example.com",gender="F",dob=date(2000,1,1),
                source="meta",
            )
            self.add_user(
                db,email="referral@example.com",gender="F",dob=date(2000,1,1),
                referred_by=referrer,
                source="ignored-because-referral",
            )
            self.add_user(
                db,email="direct@example.com",gender="M",dob=date(1994,1,1),
            )
            db.commit()

            rows={row["source"]:row for row in source_breakdown(db,market_code="KZ-ALA")}
            self.assertEqual(rows["meta"]["registrations"],1)
            self.assertEqual(rows["meta"]["completed_active"],1)
            self.assertEqual(rows["referral"]["completed_active"],1)
            self.assertEqual(rows["direct"]["completed_active"],1)

    def test_report_contains_ranked_insights_and_total_gap(self):
        with Session(self.engine) as db:
            f1=self.add_user(db,email="f1@example.com",gender="F",dob=date(2000,1,1))
            f2=self.add_user(db,email="f2@example.com",gender="F",dob=date(1999,1,1))
            self.add_preferences(db,f1,target_gender="M",min_age=29,max_age=35)
            self.add_preferences(db,f2,target_gender="M",min_age=29,max_age=35)
            db.commit()

            report=build_balance_report(db,market_code="KZ-ALA")
            self.assertGreater(report["total_demand_gap"],0)
            self.assertTrue(report["insights"])
            self.assertGreater(report["insights"][0]["gap"],0)
            self.assertIn("не хватает",report["insights"][0]["message"])


if __name__=="__main__":
    unittest.main()
