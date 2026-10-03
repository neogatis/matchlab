import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chat import service as chat
from app.db.models import (
    AuditLog,
    Conversation,
    DataRequest,
    Match,
    Message,
    ModerationAction,
    Photo,
    Profile,
    Report,
    User,
)
from app.matching.service import mutual_hard_pass
from app.safety import service as safety


class SafetyServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)

    def add_user(self, db, email, status="ACTIVE"):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
            status=status,
        )
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id, display_name=email.split("@")[0]))
        db.flush()
        return user.id

    def add_match_and_message(self, db, a, b):
        low, high = sorted((a, b))
        match = Match(
            user1=low,
            user2=high,
            compatibility_score=85,
            mutual_fit_score=82,
            algorithm_version="mutual-v1",
            created_at=self.now,
        )
        db.add(match)
        db.flush()
        conversation = Conversation(match_id=match.id, created_at=self.now)
        db.add(conversation)
        db.flush()
        message = Message(
            conversation_id=conversation.id,
            sender=a,
            body="test message",
            created_at=self.now,
        )
        db.add(message)
        db.flush()
        return match, conversation, message

    def test_block_is_idempotent_and_unblock_is_explicit(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            first=safety.block_user(db,blocker=a,blocked=b,now=self.now)
            second=safety.block_user(db,blocker=a,blocked=b,now=self.now)
            db.commit()
            self.assertEqual((first.blocker,first.blocked),(second.blocker,second.blocked))
            self.assertTrue(safety.unblock_user(db,blocker=a,blocked=b))
            self.assertFalse(safety.unblock_user(db,blocker=a,blocked=b))

    def test_report_user_reason_and_self_report_validation(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            row=safety.report_user(db,reporter=a,target_user=b,reason="spam",now=self.now)
            db.commit()
            self.assertEqual(row.reason,"SPAM")
            self.assertEqual(row.status,"OPEN")
            with self.assertRaises(safety.InvalidReport):
                safety.report_user(db,reporter=a,target_user=a,reason="SPAM")
            with self.assertRaises(safety.InvalidReport):
                safety.report_user(db,reporter=a,target_user=b,reason="NOT_A_REASON")

    def test_report_photo_and_photo_moderation_are_logged(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            photo=Photo(
                user_id=b,
                storage_key="users/b/p1.jpg",
                mime="image/jpeg",
                byte_size=100,
                moderation_status="PENDING",
            )
            db.add(photo); db.flush()
            report=safety.report_photo(db,reporter=a,photo_id=photo.id,reason="FAKE_PROFILE",now=self.now)
            safety.moderate_photo(db,actor="admin@example.com",photo_id=photo.id,approved=False,reason="reviewed",now=self.now)
            db.commit()
            self.assertEqual(report.photo_id,photo.id)
            self.assertEqual(db.get(Photo,photo.id).moderation_status,"REJECTED")
            action=db.query(ModerationAction).filter_by(target_type="PHOTO",target_id=str(photo.id)).one()
            self.assertEqual(action.action,"PHOTO_REJECT")

    def test_message_report_requires_chat_participation(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            outsider=self.add_user(db,"x@example.com")
            _,_,message=self.add_match_and_message(db,a,b)
            db.commit()
            report=safety.report_message(db,reporter=b,message_id=message.id,reason="HARASSMENT",now=self.now)
            db.commit()
            self.assertEqual(report.message_id,message.id)
            with self.assertRaises(safety.InvalidReport):
                safety.report_message(db,reporter=outsider,message_id=message.id,reason="HARASSMENT")

    def test_moderation_queue_review_and_close(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            row=safety.report_user(db,reporter=a,target_user=b,reason="SCAM",now=self.now)
            db.commit()
            queue=safety.moderation_queue(db)
            self.assertEqual([x.id for x in queue],[row.id])
            safety.set_report_reviewing(db,report_id=row.id)
            safety.close_report(db,actor="moderator",report_id=row.id,decision="RESOLVED",note="handled",now=self.now)
            db.commit()
            self.assertEqual(db.get(Report,row.id).status,"RESOLVED")
            self.assertEqual(safety.moderation_queue(db),[])
            self.assertEqual(
                db.query(ModerationAction).filter_by(target_type="REPORT",target_id=str(row.id)).count(),
                1,
            )

    def test_soft_ban_ban_unban_are_audited(self):
        with Session(self.engine) as db:
            user_id=self.add_user(db,"a@example.com")
            safety.moderate_user(db,actor="admin",user_id=user_id,action="SOFT_BAN",reason="review",now=self.now)
            db.commit()
            self.assertEqual(db.get(User,user_id).status,"SOFT_BANNED")
            self.assertEqual(mutual_hard_pass(db,user_id,user_id+999)[1],"source_user_inactive")
            self.assertEqual(db.query(AuditLog).filter_by(target_id=str(user_id), action="SAFETY_SOFT_BAN").count(),1)

            safety.moderate_user(db,actor="admin",user_id=user_id,action="BAN",reason="confirmed",now=self.now)
            safety.moderate_user(db,actor="admin",user_id=user_id,action="UNBAN",reason="appeal",now=self.now)
            db.commit()
            self.assertEqual(db.get(User,user_id).status,"ACTIVE")
            self.assertEqual(db.query(ModerationAction).filter_by(target_type="USER",target_id=str(user_id)).count(),3)

    def test_soft_ban_disables_sending_in_existing_chat(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            _,conversation,_=self.add_match_and_message(db,a,b)
            safety.moderate_user(db,actor="admin",user_id=a,action="SOFT_BAN",reason="review",now=self.now)
            db.commit()
            with self.assertRaises(chat.ChatUnavailable):
                chat.send_message(db,conversation_id=conversation.id,sender_id=a,body="hello",now=self.now)

    def test_account_deletion_request_is_idempotent_and_deactivates_user(self):
        with Session(self.engine) as db:
            user_id=self.add_user(db,"a@example.com")
            one=safety.request_account_deletion(db,user_id=user_id,now=self.now)
            two=safety.request_account_deletion(db,user_id=user_id,now=self.now)
            db.commit()
            self.assertEqual(one.id,two.id)
            self.assertEqual(db.get(User,user_id).status,"DELETION_REQUESTED")
            self.assertEqual(db.query(DataRequest).filter_by(user_id=user_id,request_type="DELETE").count(),1)

    def test_database_rejects_invalid_user_and_report_status(self):
        with Session(self.engine) as db:
            user_id=self.add_user(db,"a@example.com")
            user=db.get(User,user_id)
            user.status="UNKNOWN"
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with Session(self.engine) as db:
            a=self.add_user(db,"a2@example.com")
            b=self.add_user(db,"b2@example.com")
            db.add(Report(reporter=a,target_user=b,reason="SPAM",status="UNKNOWN"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_database_requires_exactly_one_report_target(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            photo=Photo(user_id=b,mime="image/jpeg",byte_size=100,moderation_status="PENDING")
            db.add(photo); db.flush()
            db.add(Report(reporter=a,target_user=b,photo_id=photo.id,reason="SPAM",status="OPEN"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__=="__main__":
    unittest.main()
