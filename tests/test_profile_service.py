import os
import unittest
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.service import hash_password
from app.db.models import Market, Profile, User, UserStatusHistory
from app.profile import service as profiles


class ProfileServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            for table in [
                "user_status_history","profiles","sessions","auth_outbox","auth_challenges",
                "auth_rate_limits","auth_identities","users","markets"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))

        with Session(self.engine) as db:
            self.market = profiles.ensure_market(
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
            self.user = User(
                email="profile@example.com",
                password_hash=hash_password("very-secure-password"),
                referral_code="profile-ref",
            )
            db.add(self.user)
            db.commit()
            self.user_id = self.user.id

    def test_under_18_is_rejected(self):
        with Session(self.engine) as db:
            with self.assertRaises(profiles.UnderageUser):
                profiles.upsert_basic_profile(
                    db,
                    user_id=self.user_id,
                    display_name="Minor",
                    dob=date.today().replace(year=date.today().year - 17),
                    gender="M",
                    seek_gender="F",
                    market_code="KZ-ALA",
                )

    def test_market_drives_city_country_and_locale(self):
        with Session(self.engine) as db:
            p = profiles.upsert_basic_profile(
                db,
                user_id=self.user_id,
                display_name="Dan",
                dob=date(1997,5,30),
                gender="M",
                seek_gender="F",
                market_code="KZ-ALA",
            )
            db.commit()
            self.assertEqual(p.city, "Алматы")
            self.assertEqual(p.country_code, "KZ")
            self.assertEqual(p.preferred_locale, "ru-KZ")
            self.assertIsNotNone(p.market_id)

    def test_architecture_is_not_hardcoded_to_almaty(self):
        with Session(self.engine) as db:
            profiles.ensure_market(
                db,
                code="KZ-AST",
                country_code="KZ",
                city_code="AST",
                display_name="Астана",
                timezone_name="Asia/Almaty",
                currency_code="KZT",
                default_language="ru-KZ",
                supported_languages=["ru-KZ", "kk-KZ"],
                registration_open=True,
                matching_open=True,
            )
            p = profiles.upsert_basic_profile(
                db,
                user_id=self.user_id,
                display_name="Test",
                dob=date(1997,5,30),
                gender="M",
                seek_gender="F",
                market_code="KZ-AST",
            )
            db.commit()
            self.assertEqual(p.city, "Астана")

    def test_relationship_and_open_state_semantics_match_v7(self):
        self.assertEqual(profiles.derive_status(True, "ACTIVE"), ("IN_RELATIONSHIP","NOT_ACTIVE_FOR_MATCHING"))
        self.assertEqual(profiles.derive_status(False, "ACTIVE"), ("ACTIVE_SEARCH","ACTIVE_FOR_MATCHING"))
        self.assertEqual(profiles.derive_status(False, "OPEN"), ("OPEN_TO_MATCH","ACTIVE_FOR_MATCHING"))
        self.assertEqual(profiles.derive_status(False, "UNSURE"), ("PAUSED","NOT_ACTIVE_FOR_MATCHING"))
        self.assertEqual(profiles.derive_status(False, "NO"), ("NOT_ACTIVE","NOT_ACTIVE_FOR_MATCHING"))

    def test_status_change_is_audited(self):
        with Session(self.engine) as db:
            profiles.upsert_basic_profile(
                db,user_id=self.user_id,display_name="Dan",dob=date(1997,5,30),
                gender="M",seek_gender="F",market_code="KZ-ALA",
            )
            profiles.set_relationship_state(
                db,user_id=self.user_id,in_relationship=False,openness="ACTIVE",source="test"
            )
            db.commit()
            p = db.get(Profile, self.user_id)
            self.assertEqual(p.relationship_status, "ACTIVE_SEARCH")
            self.assertEqual(p.eligibility_status, "ACTIVE_FOR_MATCHING")
            history = db.query(UserStatusHistory).filter_by(user_id=self.user_id).all()
            self.assertEqual(len(history),1)
            self.assertEqual(history[0].source,"test")

    def test_readiness_preserves_v7_formula(self):
        self.assertEqual(profiles.readiness_score("YES","YES"),100)
        self.assertEqual(profiles.readiness_score("RATHER_YES","MAYBE"),66)
        self.assertEqual(profiles.readiness_score("LOOK_ONLY","NO"),12)

    def test_database_rejects_invalid_status(self):
        with Session(self.engine) as db:
            p = profiles.upsert_basic_profile(
                db,user_id=self.user_id,display_name="Dan",dob=date(1997,5,30),
                gender="M",seek_gender="F",market_code="KZ-ALA",
            )
            p.relationship_status = "INVALID_STATUS"
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_matchable_requires_market_and_completed_profile(self):
        with Session(self.engine) as db:
            p = profiles.upsert_basic_profile(
                db,user_id=self.user_id,display_name="Dan",dob=date(1997,5,30),
                gender="M",seek_gender="F",market_code="KZ-ALA",
            )
            profiles.set_relationship_state(
                db,user_id=self.user_id,in_relationship=False,openness="ACTIVE"
            )
            p.profile_completed = True
            p.questionnaire_completed = True
            db.commit()
            market = db.get(Market,p.market_id)
            self.assertFalse(profiles.is_matchable(p,market))

            market.matching_open = True
            db.commit()
            self.assertFalse(profiles.is_matchable(p,market))

            p.partner_preferences_completed = True
            db.commit()
            self.assertTrue(profiles.is_matchable(p,market))

            p.relationship_status = "PAUSED"
            p.eligibility_status = "NOT_ACTIVE_FOR_MATCHING"
            db.commit()
            self.assertFalse(profiles.is_matchable(p,market))


if __name__ == "__main__":
    unittest.main()
