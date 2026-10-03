import os
import unittest
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.console.dashboard import prelaunch_dashboard_html
from app.console.metrics import prelaunch_metrics
from app.db.models import Market, Photo, Profile, User


class Phase31PrelaunchMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE photos, profiles, users, markets "
                "RESTART IDENTITY CASCADE"
            ))

        with Session(self.engine) as db:
            market = Market(
                code="KZ-ALA",
                country_code="KZ",
                city_code="ALA",
                display_name="Алматы",
                timezone="Asia/Almaty",
                currency_code="KZT",
                default_language="ru-KZ",
                supported_languages=["ru-KZ"],
                registration_open=True,
                matching_open=False,
            )
            db.add(market)
            db.flush()

            ready = User(
                email="ready-metrics@example.com",
                password_hash="x",
                referral_code="ready-metrics",
                status="ACTIVE",
            )
            incomplete = User(
                email="incomplete-metrics@example.com",
                password_hash="x",
                referral_code="incomplete-metrics",
                status="ACTIVE",
            )
            db.add_all([ready, incomplete])
            db.flush()

            db.add(Profile(
                user_id=ready.id,
                display_name="Ready",
                dob=date(1997, 5, 30),
                gender="M",
                seek_gender="F",
                market_id=market.id,
                city="Алматы",
                country_code="KZ",
                relationship_status="ACTIVE_SEARCH",
                eligibility_status="ACTIVE_FOR_MATCHING",
                height=183,
                dating_goal="SERIOUS",
                children_status="NO_CHILDREN",
                children_plans="MAYBE",
                smoking="NO",
                alcohol="RARE",
                lifestyle="ACTIVE",
                readiness_chat="YES",
                readiness_offline="YES",
                readiness_score=100,
                questionnaire_completed=True,
                partner_preferences_completed=True,
                photos_completed=True,
                profile_completed=True,
            ))
            db.add(Profile(
                user_id=incomplete.id,
                display_name="Incomplete",
                dob=date(1997, 5, 30),
                gender="F",
                seek_gender="M",
                market_id=market.id,
                city="Алматы",
                country_code="KZ",
            ))
            db.flush()

            db.add(Photo(
                user_id=incomplete.id,
                storage_key="users/incomplete/pending.jpg",
                mime="image/jpeg",
                byte_size=1000,
                is_main=True,
                sort_order=0,
                moderation_status="PENDING",
            ))
            db.commit()

    def test_metrics_report_funnel_and_ready_pool(self):
        with Session(self.engine) as db:
            result = prelaunch_metrics(db)

        self.assertEqual(result["users"]["active"], 2)
        self.assertEqual(result["pending_photos"], 1)
        funnel = {row["key"]: row["count"] for row in result["funnel"]}
        self.assertEqual(funnel["registered"], 2)
        self.assertEqual(funnel["profile_started"], 2)
        self.assertEqual(funnel["details"], 1)
        self.assertEqual(funnel["questionnaire"], 1)
        self.assertEqual(funnel["profile_complete"], 1)
        self.assertEqual(funnel["waitlist_ready"], 1)
        self.assertEqual(result["gender"]["M"], 1)
        self.assertEqual(result["gender"]["F"], 1)

    def test_dashboard_points_to_protected_metrics_and_moderation(self):
        html = prelaunch_dashboard_html()
        self.assertIn("/api/v1/admin/prelaunch/metrics", html)
        self.assertIn("/moderation/photos", html)
        self.assertNotIn("DATABASE_URL", html)


if __name__ == "__main__":
    unittest.main()
