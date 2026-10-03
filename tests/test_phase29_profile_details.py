import os
import unittest
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth.service import hash_password
from app.db.models import Market, Profile, User
from app.profile import service as profiles


class Phase29ProfileDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE user_status_history, profiles, sessions, auth_outbox, "
                "auth_challenges, auth_rate_limits, auth_identities, users, markets "
                "RESTART IDENTITY CASCADE"
            ))
        with Session(self.engine) as db:
            market = profiles.ensure_market(
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
                email="phase29@example.com",
                password_hash=hash_password("very-secure-password"),
                referral_code="phase29-ref",
            )
            db.add(user)
            db.flush()
            self.user_id = user.id
            db.commit()

    def create_basic(self, db):
        return profiles.upsert_basic_profile(
            db,
            user_id=self.user_id,
            display_name="Tester",
            dob=date(1997, 5, 30),
            gender="M",
            seek_gender="F",
            market_code="KZ-ALA",
        )

    def test_details_validation_and_completion(self):
        with Session(self.engine) as db:
            p = self.create_basic(db)
            self.assertFalse(profiles.profile_details_complete(p))
            profiles.set_match_profile_details(
                db,
                user_id=self.user_id,
                height=183,
                dating_goal="SERIOUS",
                children_status="NO_CHILDREN",
                children_plans="MAYBE",
                smoking="NO",
                alcohol="RARE",
                lifestyle="ACTIVE",
                bio="Тестовый профиль",
            )
            db.commit()
            p = db.get(Profile, self.user_id)
            self.assertTrue(profiles.profile_details_complete(p))
            self.assertEqual(p.height, 183)
            self.assertEqual(p.dating_goal, "SERIOUS")

    def test_completion_requires_details_and_readiness(self):
        with Session(self.engine) as db:
            p = self.create_basic(db)
            p.questionnaire_completed = True
            p.partner_preferences_completed = True
            p.photos_completed = True
            profiles.recompute_profile_completion(db, user_id=self.user_id)
            self.assertFalse(p.profile_completed)

            profiles.set_match_profile_details(
                db,
                user_id=self.user_id,
                height=183,
                dating_goal="SERIOUS",
                children_status="NO_CHILDREN",
                children_plans="MAYBE",
                smoking="NO",
                alcohol="RARE",
                lifestyle="ACTIVE",
            )
            self.assertFalse(p.profile_completed)

            profiles.set_readiness(
                db,
                user_id=self.user_id,
                chat="YES",
                offline="YES",
            )
            profiles.recompute_profile_completion(db, user_id=self.user_id)
            db.commit()
            self.assertTrue(p.profile_completed)

    def test_invalid_details_are_rejected(self):
        with Session(self.engine) as db:
            self.create_basic(db)
            with self.assertRaises(profiles.ProfileError):
                profiles.set_match_profile_details(
                    db,
                    user_id=self.user_id,
                    height=99,
                    dating_goal="SERIOUS",
                    children_status="NO_CHILDREN",
                    children_plans="MAYBE",
                    smoking="NO",
                    alcohol="RARE",
                    lifestyle="ACTIVE",
                )


if __name__ == "__main__":
    unittest.main()
