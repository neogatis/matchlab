import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console import (
    CONSOLE_SECTIONS,
    ConsoleAccessDenied,
    bootstrap_first_superadmin,
    chat_metadata,
    dashboard,
    list_users,
    render_console_page,
    set_console_role,
    set_setting,
    settings_overview,
)
from app.db.models import (
    AdminAccount,
    AuditLog,
    Conversation,
    Match,
    Message,
    Profile,
    User,
)


class ConsoleServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)

    def add_user(self, db, email):
        user = User(
            email=email,
            password_hash="test-hash",
            referral_code=email.split("@")[0],
            status="ACTIVE",
        )
        db.add(user)
        db.flush()
        db.add(Profile(
            user_id=user.id,
            display_name=email.split("@")[0],
            dob=date(1997,5,30),
            gender="M",
            city="Алматы",
            relationship_status="ACTIVE_SEARCH",
            eligibility_status="ACTIVE_FOR_MATCHING",
            profile_completed=True,
            questionnaire_completed=True,
            partner_preferences_completed=True,
            photos_completed=True,
        ))
        db.flush()
        return user.id

    def bootstrap(self, db):
        owner = self.add_user(db, "owner@example.com")
        bootstrap_first_superadmin(db, target_user_id=owner, now=self.now)
        db.flush()
        return owner

    def test_bootstrap_and_rbac(self):
        with Session(self.engine) as db:
            owner=self.bootstrap(db)
            viewer=self.add_user(db,"viewer@example.com")
            set_console_role(
                db,console_user_id=owner,target_user_id=viewer,role="VIEWER",now=self.now
            )
            db.commit()
            rows=list_users(db,console_user_id=viewer)
            self.assertTrue(rows)
            self.assertNotIn("password_hash",rows[0])
            with self.assertRaises(ConsoleAccessDenied):
                settings_overview(db,console_user_id=viewer)

    def test_setting_change_is_audited(self):
        with Session(self.engine) as db:
            owner=self.bootstrap(db)
            operator=self.add_user(db,"operator@example.com")
            set_console_role(
                db,console_user_id=owner,target_user_id=operator,role="ADMIN",now=self.now
            )
            db.commit()
            set_setting(
                db,console_user_id=operator,key="PRE_LAUNCH_MODE",value="true",now=self.now
            )
            db.commit()
            self.assertEqual(settings_overview(db,console_user_id=operator)["PRE_LAUNCH_MODE"],"true")
            self.assertEqual(db.query(AuditLog).filter_by(action="SETTING_UPDATE").count(),1)

    def test_dashboard_has_product_metrics(self):
        with Session(self.engine) as db:
            owner=self.bootstrap(db)
            self.add_user(db,"user@example.com")
            db.commit()
            data=dashboard(db,console_user_id=owner)
            expected={
                "ACTIVE_MATCHABLE_USERS","COMPLETED_PROFILES",
                "USERS_WITH_AT_LEAST_ONE_MATCH","MATCH_RATE",
                "MUTUAL_INTEREST_RATE","CONVERSATION_START_RATE",
                "TOTAL_REGISTRATIONS","MEN","WOMEN","ACTIVE_SEARCH",
                "PAUSED","IN_RELATIONSHIP",
            }
            self.assertTrue(expected.issubset(data["metrics"]))
            self.assertEqual(data["metrics"]["TOTAL_REGISTRATIONS"],2)

    def test_chat_metadata_has_no_message_body(self):
        with Session(self.engine) as db:
            owner=self.bootstrap(db)
            other=self.add_user(db,"other@example.com")
            low,high=sorted((owner,other))
            match=Match(
                user1=low,user2=high,compatibility_score=80,mutual_fit_score=80,
                algorithm_version="mutual-v1",created_at=self.now,
            )
            db.add(match); db.flush()
            conv=Conversation(match_id=match.id,created_at=self.now)
            db.add(conv); db.flush()
            db.add(Message(
                conversation_id=conv.id,sender=owner,body="private text",created_at=self.now
            ))
            db.commit()
            rows=chat_metadata(db,console_user_id=owner)
            self.assertEqual(rows[0]["message_count"],1)
            self.assertNotIn("body",rows[0])
            self.assertNotIn("private text",str(rows))

    def test_sections_and_dark_renderer(self):
        self.assertEqual(len(CONSOLE_SECTIONS),12)
        html=render_console_page(
            active_section="Dashboard",
            data={"metrics":{"X":1},"note":"<script>alert(1)</script>"},
        )
        self.assertIn("Audience balance",html)
        self.assertIn("--bg:#171514",html)
        self.assertNotIn("<script>alert(1)</script>",html)
        self.assertIn("&lt;script&gt;",html)

    def test_database_rejects_unknown_role(self):
        with Session(self.engine) as db:
            user=self.add_user(db,"user@example.com")
            db.add(AdminAccount(user_id=user,role="INVALID",is_active=True))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__=="__main__":
    unittest.main()
