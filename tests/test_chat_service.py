import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chat import service as chat
from app.db.models import (
    Block,
    Conversation,
    Match,
    Message,
    Notification,
    Profile,
    ProductEvent,
    User,
)


class ChatServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime.now(timezone.utc)

    def add_user(self, db, email):
        user = User(email=email, password_hash="x", referral_code=email.split("@")[0])
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id, display_name=email.split("@")[0]))
        db.flush()
        return user.id

    def add_match(self, db, a, b):
        low, high = sorted((a, b))
        match = Match(
            user1=low,
            user2=high,
            compatibility_score=88,
            mutual_fit_score=84,
            algorithm_version="mutual-v1",
            created_at=self.now,
        )
        db.add(match)
        db.flush()
        return match

    def test_no_conversation_without_mutual_match(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            db.commit()
            with self.assertRaises(chat.ChatUnavailable):
                chat.get_or_create_conversation(db,match_id=999,user_id=a,now=self.now)
            self.assertEqual(db.query(Conversation).count(),0)

    def test_only_match_participants_can_open_conversation(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            outsider=self.add_user(db,"x@example.com")
            match=self.add_match(db,a,b)
            db.commit()
            with self.assertRaises(chat.NotConversationParticipant):
                chat.get_or_create_conversation(db,match_id=match.id,user_id=outsider,now=self.now)

    def test_conversation_is_idempotent_one_per_match(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            db.commit()
            c1=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            c2=chat.get_or_create_conversation(db,match_id=match.id,user_id=b,now=self.now)
            db.commit()
            self.assertEqual(c1.id,c2.id)
            self.assertEqual(db.query(Conversation).count(),1)

    def test_text_message_creates_generic_notification_and_event(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            msg=chat.send_message(
                db,
                conversation_id=conv.id,
                sender_id=a,
                body="  Привет!  ",
                client_message_id="client-1",
                now=self.now,
            )
            db.commit()
            self.assertEqual(msg.body,"Привет!")
            note=db.query(Notification).filter_by(user_id=b,kind="MESSAGE").one()
            self.assertNotIn("Привет",note.text)
            event=db.query(ProductEvent).filter_by(user_id=a,event_type="MESSAGE_SENT").one()
            self.assertEqual(event.metadata_json["conversation_id"],conv.id)
            self.assertNotIn("body",event.metadata_json)

    def test_client_message_id_is_idempotent(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            one=chat.send_message(
                db,conversation_id=conv.id,sender_id=a,body="Один",
                client_message_id="same",now=self.now,
            )
            two=chat.send_message(
                db,conversation_id=conv.id,sender_id=a,body="Другой текст",
                client_message_id="same",now=self.now,
            )
            db.commit()
            self.assertEqual(one.id,two.id)
            self.assertEqual(two.body,"Один")
            self.assertEqual(db.query(Message).count(),1)
            self.assertEqual(db.query(Notification).filter_by(kind="MESSAGE").count(),1)

    def test_unread_and_mark_read_only_affect_incoming_messages(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            own=chat.send_message(db,conversation_id=conv.id,sender_id=a,body="A",now=self.now)
            incoming=chat.send_message(db,conversation_id=conv.id,sender_id=b,body="B",now=self.now)
            db.commit()

            self.assertEqual(chat.unread_count(db,conversation_id=conv.id,user_id=a),1)
            changed=chat.mark_read(db,conversation_id=conv.id,user_id=a,now=self.now)
            db.commit()
            self.assertEqual(changed,1)
            self.assertIsNone(db.get(Message,own.id).read_at)
            self.assertIsNotNone(db.get(Message,incoming.id).read_at)
            self.assertEqual(chat.unread_count(db,conversation_id=conv.id,user_id=a),0)

    def test_message_history_is_participant_only_and_paginated(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            x=self.add_user(db,"x@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            ids=[]
            for i in range(5):
                ids.append(chat.send_message(
                    db,conversation_id=conv.id,sender_id=a if i%2==0 else b,
                    body=f"M{i}",now=self.now,
                ).id)
            db.commit()
            page=chat.list_messages(db,conversation_id=conv.id,user_id=a,limit=2)
            self.assertEqual([m["body"] for m in page],["M3","M4"])
            older=chat.list_messages(db,conversation_id=conv.id,user_id=a,limit=2,before_id=ids[3])
            self.assertEqual([m["body"] for m in older],["M1","M2"])
            with self.assertRaises(chat.NotConversationParticipant):
                chat.list_messages(db,conversation_id=conv.id,user_id=x)

    def test_block_stops_new_messages_but_preserves_history(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            chat.send_message(db,conversation_id=conv.id,sender_id=a,body="Before",now=self.now)
            db.add(Block(blocker=b,blocked=a,created_at=self.now))
            db.commit()

            history=chat.list_messages(db,conversation_id=conv.id,user_id=a)
            self.assertEqual([x["body"] for x in history],["Before"])
            with self.assertRaises(chat.ChatUnavailable):
                chat.send_message(db,conversation_id=conv.id,sender_id=a,body="After",now=self.now)
            with self.assertRaises(chat.ChatUnavailable):
                chat.send_message(db,conversation_id=conv.id,sender_id=b,body="After",now=self.now)

    def test_conversation_list_returns_unread_and_can_send_state(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            chat.send_message(db,conversation_id=conv.id,sender_id=b,body="Hello",now=self.now)
            db.commit()
            rows=chat.list_conversations(db,user_id=a)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["other_user_id"],b)
            self.assertEqual(rows[0]["unread_count"],1)
            self.assertTrue(rows[0]["can_send"])
            self.assertEqual(rows[0]["last_message"]["body"],"Hello")

    def test_validation_and_database_constraint(self):
        with Session(self.engine) as db:
            a=self.add_user(db,"a@example.com")
            b=self.add_user(db,"b@example.com")
            match=self.add_match(db,a,b)
            conv=chat.get_or_create_conversation(db,match_id=match.id,user_id=a,now=self.now)
            with self.assertRaises(chat.MessageValidationError):
                chat.send_message(db,conversation_id=conv.id,sender_id=a,body="   ")
            with self.assertRaises(chat.MessageValidationError):
                chat.send_message(db,conversation_id=conv.id,sender_id=a,body="x"*4001)

            db.add(Message(conversation_id=conv.id,sender=a,body="   "))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__=="__main__":
    unittest.main()
