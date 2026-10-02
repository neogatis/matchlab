import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Market, PartnerPreference, Profile, User
from app.preferences import service as prefs
from app.preferences.catalog import CORE_PREFERENCE_KEYS


class PartnerPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            for table in [
                "partner_preferences","legacy_partner_criteria","user_status_history","profiles",
                "sessions","auth_outbox","auth_challenges","auth_rate_limits","auth_identities",
                "users","markets"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))

        with Session(self.engine) as db:
            market = Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ","kk-KZ"],registration_open=True,matching_open=False,
            )
            user = User(email="prefs@example.com",password_hash="x",referral_code="prefs-ref")
            db.add_all([market,user]); db.flush()
            db.add(Profile(user_id=user.id,display_name="Tester",market_id=market.id,city="Алматы"))
            db.commit()
            self.user_id=user.id

    def test_core_catalog_covers_required_product_preferences(self):
        expected={
            "age","gender","market","distance_km","dating_goal","children_status",
            "children_plans","smoking","alcohol","lifestyle","height",
        }
        self.assertEqual(set(CORE_PREFERENCE_KEYS),expected)

    def test_age_range_and_importance_are_normalized(self):
        with Session(self.engine) as db:
            row=prefs.set_preference(
                db,user_id=self.user_id,key="age",importance="hard",
                value={"min":25,"max":35},
            )
            db.commit()
            self.assertEqual(row.importance,"HARD")
            self.assertEqual(float(row.min_value),25)
            self.assertEqual(float(row.max_value),35)

    def test_invalid_range_is_rejected(self):
        with Session(self.engine) as db:
            with self.assertRaises(prefs.InvalidPreference):
                prefs.set_preference(
                    db,user_id=self.user_id,key="age",importance="HARD",
                    value={"min":40,"max":20},
                )
            with self.assertRaises(prefs.InvalidPreference):
                prefs.set_preference(
                    db,user_id=self.user_id,key="height",importance="IMPORTANT",
                    value={"min":90,"max":210},
                )

    def test_market_values_must_exist_and_be_open_for_registration(self):
        with Session(self.engine) as db:
            prefs.set_preference(
                db,user_id=self.user_id,key="market",importance="HARD",value=["KZ-ALA"]
            )
            with self.assertRaises(prefs.InvalidPreference):
                prefs.set_preference(
                    db,user_id=self.user_id,key="market",importance="HARD",value=["UNKNOWN"]
                )

    def test_any_cannot_be_combined_with_specific_options(self):
        with Session(self.engine) as db:
            with self.assertRaises(prefs.InvalidPreference):
                prefs.set_preference(
                    db,user_id=self.user_id,key="children_status",importance="PREFERENCE",
                    value=["ANY","NO_CHILDREN"],
                )

    def test_ignore_explicitly_clears_stored_value(self):
        with Session(self.engine) as db:
            row=prefs.set_preference(
                db,user_id=self.user_id,key="height",importance="IMPORTANT",
                value={"min":160,"max":190},
            )
            db.commit()
            self.assertIsNotNone(row.min_value)

            row=prefs.set_preference(
                db,user_id=self.user_id,key="height",importance="IGNORE",value=None
            )
            db.commit()
            self.assertEqual(row.importance,"IGNORE")
            self.assertIsNone(row.min_value)
            self.assertIsNone(row.max_value)

    def test_completion_requires_explicit_configuration_of_every_core_key(self):
        values={
            "age":{"importance":"HARD","value":{"min":23,"max":38}},
            "gender":{"importance":"HARD","value":["F"]},
            "market":{"importance":"HARD","value":["KZ-ALA"]},
            "distance_km":{"importance":"PREFERENCE","value":{"max":50}},
            "dating_goal":{"importance":"IMPORTANT","value":["SERIOUS","FAMILY"]},
            "children_status":{"importance":"IGNORE","value":None},
            "children_plans":{"importance":"IMPORTANT","value":["WANTS","MAYBE"]},
            "smoking":{"importance":"IMPORTANT","value":["NO","RARE"]},
            "alcohol":{"importance":"PREFERENCE","value":["NO","RARE","MODERATE"]},
            "lifestyle":{"importance":"PREFERENCE","value":["BALANCED","ACTIVE"]},
            "height":{"importance":"IGNORE","value":None},
        }
        with Session(self.engine) as db:
            start=prefs.completion(db,user_id=self.user_id)
            self.assertFalse(start["complete"])
            self.assertEqual(start["configured_required"],0)

            state=prefs.set_preferences(db,user_id=self.user_id,preferences=values)
            db.commit()
            profile=db.get(Profile,self.user_id)
            self.assertTrue(state["complete"])
            self.assertEqual(state["percent"],100)
            self.assertEqual(state["missing"],[])
            self.assertTrue(profile.partner_preferences_completed)

    def test_unknown_key_is_rejected(self):
        with Session(self.engine) as db:
            with self.assertRaises(prefs.UnknownPreference):
                prefs.set_preference(
                    db,user_id=self.user_id,key="eye_color",importance="HARD",value=["GREEN"]
                )

    def test_database_rejects_inverted_range_even_if_service_is_bypassed(self):
        with Session(self.engine) as db:
            db.add(PartnerPreference(
                user_id=self.user_id,criterion_key="age",importance="HARD",
                min_value=40,max_value=20,
            ))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_nationality_is_optional_self_reported_text_only(self):
        with Session(self.engine) as db:
            row=prefs.set_preference(
                db,user_id=self.user_id,key="nationality",importance="PREFERENCE",
                value=["Казахстан"],
            )
            db.commit()
            self.assertEqual(row.values_json,["Казахстан"])


if __name__=="__main__":
    unittest.main()
