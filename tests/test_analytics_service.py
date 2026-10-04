import os
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.analytics.events import (
    EVENT_CHAT_STARTED,
    EVENT_QUESTIONNAIRE_STARTED,
    EVENT_REGISTRATION,
    track_event,
    track_once,
)
from app.analytics.service import analytics_overview, users_with_relevant_match
from app.auth.service import register_email_user
from app.db.models import Match, Market, ProductEvent, Profile, User
from app.profile.service import recompute_profile_completion


class AnalyticsServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE product_events, users, markets RESTART IDENTITY CASCADE"
            ))
        self.now = datetime.now(timezone.utc)

    def add_user(self, db, email, *, created_at=None):
        user=User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            created_at=created_at or self.now,
        )
        db.add(user); db.flush()
        return user.id

    def test_registration_service_tracks_registration_once(self):
        with Session(self.engine) as db:
            user=register_email_user(
                db,
                "registered@example.com",
                "VerySecurePassword-123",
            )
            db.commit()
            events=db.query(ProductEvent).filter_by(
                user_id=user.id,event_type=EVENT_REGISTRATION
            ).all()
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].metadata_json["channel"],"email")

    def test_track_once_is_idempotent(self):
        with Session(self.engine) as db:
            user_id=self.add_user(db,"once@example.com")
            one=track_once(
                db,event_type=EVENT_QUESTIONNAIRE_STARTED,user_id=user_id,now=self.now
            )
            two=track_once(
                db,event_type=EVENT_QUESTIONNAIRE_STARTED,user_id=user_id,
                now=self.now+timedelta(minutes=1),
            )
            db.commit()
            self.assertEqual(one.id,two.id)
            self.assertEqual(
                db.query(ProductEvent).filter_by(
                    user_id=user_id,event_type=EVENT_QUESTIONNAIRE_STARTED
                ).count(),
                1,
            )

    def test_profile_completion_tracks_event_once(self):
        with Session(self.engine) as db:
            market=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ"],registration_open=True,matching_open=False,
            )
            db.add(market); db.flush()
            user_id=self.add_user(db,"complete@example.com")
            db.add(Profile(
                user_id=user_id,display_name="Complete",dob=date(1997,5,30),
                gender="M",seek_gender="F",market_id=market.id,city="Алматы",
                height=183,dating_goal="SERIOUS",children_status="NO_CHILDREN",
                children_plans="MAYBE",smoking="NO",alcohol="RARE",
                lifestyle="ACTIVE",readiness_chat="YES",readiness_offline="MAYBE",
                questionnaire_completed=True,partner_preferences_completed=True,
                photos_completed=True,
            ))
            db.flush()
            self.assertTrue(recompute_profile_completion(db,user_id=user_id,now=self.now))
            self.assertTrue(recompute_profile_completion(db,user_id=user_id,now=self.now))
            db.commit()
            self.assertEqual(
                db.query(ProductEvent).filter_by(
                    user_id=user_id,event_type="PROFILE_COMPLETED"
                ).count(),
                1,
            )

    def test_relevant_match_counts_unique_users_not_rows_twice(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            c=self.add_user(db,"c@example.com")
            db.add_all([
                Match(user1=min(a,b),user2=max(a,b),compatibility_score=80,mutual_fit_score=80,algorithm_version="mutual-v1"),
                Match(user1=min(a,c),user2=max(a,c),compatibility_score=80,mutual_fit_score=80,algorithm_version="mutual-v1"),
            ])
            db.commit()
            self.assertEqual(users_with_relevant_match(db),3)

    def test_overview_does_not_invent_missing_conversion_denominators(self):
        with Session(self.engine) as db:
            self.add_user(db,"a@example.com")
            db.commit()
            data=analytics_overview(db,now=self.now)
            self.assertIsNone(data["metrics"]["registration_conversion"])
            self.assertIsNone(data["metrics"]["subscription_conversion"])
            self.assertIn("registration_conversion",data["unavailable"])
            self.assertEqual(data["metrics"]["USERS_WITH_RELEVANT_MATCH"],0)

    def test_retention_uses_24_hour_day_windows(self):
        registered=self.now-timedelta(days=10)
        with Session(self.engine) as db:
            user_id=self.add_user(db,"retained@example.com",created_at=registered)
            track_event(
                db,event_type="SOME_ACTIVITY",user_id=user_id,
                now=registered+timedelta(days=1,hours=2),
            )
            track_event(
                db,event_type="SOME_ACTIVITY",user_id=user_id,
                now=registered+timedelta(days=7,hours=3),
            )
            db.commit()
            data=analytics_overview(db,now=self.now)
            self.assertEqual(data["metrics"]["D1"],100.0)
            self.assertEqual(data["metrics"]["D7"],100.0)
            self.assertEqual(data["metrics"]["D30"],None)

    def test_chat_start_rate_uses_started_conversations_per_match(self):
        from app.db.models import Conversation, Message

        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=Match(
                user1=min(a,b),user2=max(a,b),compatibility_score=80,
                mutual_fit_score=80,algorithm_version="mutual-v1",
            )
            db.add(match); db.flush()
            conv=Conversation(match_id=match.id)
            db.add(conv); db.flush()
            db.add(Message(conversation_id=conv.id,sender=a,body="hello"))
            db.commit()
            data=analytics_overview(db,now=self.now)
            self.assertEqual(data["metrics"]["chat_start_rate"],100.0)


if __name__=="__main__":
    unittest.main()
