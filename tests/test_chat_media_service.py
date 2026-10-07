import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.chat import service as chat
from app.db.models import (
    ChatMediaUploadTicket,
    Conversation,
    Match,
    Message,
    PhotoObjectDeletion,
    Profile,
    User,
)


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def presign_upload(self, object_key, mime, expires_seconds=600):
        return {
            "url": "https://upload.invalid/" + object_key,
            "method": "PUT",
            "headers": {"Content-Type": mime},
        }

    def head(self, object_key):
        raw, mime = self.objects[object_key]
        return SimpleNamespace(
            content_length=len(raw),
            content_type=mime,
            etag="etag",
        )

    def get_prefix(self, object_key, *, max_bytes=4096):
        raw, _ = self.objects[object_key]
        return raw[:max_bytes]

    def sanitize_image(self, object_key, *, expected_mime, max_bytes):
        return self.head(object_key)

    def delete(self, object_key):
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class ChatMediaServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["DATABASE_URL"])

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        self.now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
        self.storage = FakeStorage()

    def add_user(self, db, email):
        user = User(
            email=email,
            password_hash="x",
            referral_code=email.split("@")[0],
        )
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id, display_name=email.split("@")[0]))
        db.flush()
        return user.id

    def add_conversation(self, db):
        a = self.add_user(db, "a@example.com")
        b = self.add_user(db, "b@example.com")
        low, high = sorted((a, b))
        match = Match(
            user1=low,
            user2=high,
            compatibility_score=91,
            mutual_fit_score=88,
            algorithm_version="test",
            created_at=self.now,
        )
        db.add(match)
        db.flush()
        conversation = chat.get_or_create_conversation(
            db,
            match_id=match.id,
            user_id=a,
            now=self.now,
        )
        db.flush()
        return a, b, conversation

    def prepare(self, db, *, conversation_id, user_id, mime="video/mp4", kind="video"):
        prepared = chat.prepare_media_upload(
            db,
            conversation_id=conversation_id,
            user_id=user_id,
            mime=mime,
            kind=kind,
            size=24,
            name="clip.mp4",
            storage=self.storage,
        )
        return prepared

    def test_prepare_upload_creates_ticket_and_send_consumes_it(self):
        with Session(self.engine) as db:
            a, _, conversation = self.add_conversation(db)
            prepared = self.prepare(
                db,
                conversation_id=conversation.id,
                user_id=a,
            )
            ticket = db.query(ChatMediaUploadTicket).one()
            self.assertEqual(ticket.status, "PREPARED")
            self.assertEqual(ticket.object_key, prepared["object_key"])

            # ISO-BMFF/MP4 family: size + ftyp + brand payload.
            raw = b"\x00\x00\x00\x18ftypisom" + b"0" * 12
            self.storage.objects[prepared["object_key"]] = (raw, "video/mp4")

            message = chat.send_message(
                db,
                conversation_id=conversation.id,
                sender_id=a,
                body="Наше видео",
                client_message_id="media-1",
                media={
                    "object_key": prepared["object_key"],
                    "kind": "video",
                    "mime": "video/mp4",
                    "name": "client-name.mp4",
                },
                storage=self.storage,
                now=self.now,
            )
            db.commit()

            ticket = db.get(ChatMediaUploadTicket, ticket.id)
            self.assertEqual(ticket.status, "CONSUMED")
            self.assertIsNotNone(ticket.consumed_at)

            payload = chat.message_payload(message, user_id=a)
            self.assertEqual(payload["body"], "Наше видео")
            self.assertEqual(payload["media"]["kind"], "video")
            self.assertEqual(payload["media"]["mime"], "video/mp4")
            self.assertTrue(payload["media"]["url"].endswith(f"/{message.id}"))

    def test_media_access_is_participant_only(self):
        with Session(self.engine) as db:
            a, _, conversation = self.add_conversation(db)
            outsider = self.add_user(db, "outside@example.com")
            prepared = self.prepare(
                db,
                conversation_id=conversation.id,
                user_id=a,
                mime="audio/webm",
                kind="voice",
            )
            self.storage.objects[prepared["object_key"]] = (
                b"\x1a\x45\xdf\xa3" + b"0" * 20,
                "audio/webm",
            )
            message = chat.send_message(
                db,
                conversation_id=conversation.id,
                sender_id=a,
                body="",
                media={
                    "object_key": prepared["object_key"],
                    "kind": "voice",
                    "mime": "audio/webm",
                    "duration_seconds": 3.5,
                },
                storage=self.storage,
                now=self.now,
            )
            db.commit()

            media = chat.get_message_media(db, message_id=message.id, user_id=a)
            self.assertEqual(media["kind"], "voice")
            with self.assertRaises(chat.NotConversationParticipant):
                chat.get_message_media(db, message_id=message.id, user_id=outsider)

    def test_invalid_signature_is_rejected_and_queued_for_cleanup(self):
        with Session(self.engine) as db:
            a, _, conversation = self.add_conversation(db)
            prepared = self.prepare(
                db,
                conversation_id=conversation.id,
                user_id=a,
            )
            self.storage.objects[prepared["object_key"]] = (
                b"this-is-not-a-video",
                "video/mp4",
            )
            with self.assertRaises(chat.MessageValidationError):
                chat.send_message(
                    db,
                    conversation_id=conversation.id,
                    sender_id=a,
                    body="",
                    media={
                        "object_key": prepared["object_key"],
                        "kind": "video",
                        "mime": "video/mp4",
                    },
                    storage=self.storage,
                    now=self.now,
                )
            db.commit()

            ticket = db.query(ChatMediaUploadTicket).one()
            self.assertEqual(ticket.status, "CANCELLED")
            deletion = db.query(PhotoObjectDeletion).one()
            self.assertEqual(deletion.object_key, prepared["object_key"])
            self.assertIn(prepared["object_key"], self.storage.deleted)
            self.assertEqual(db.query(Message).count(), 0)

    def test_expired_unconsumed_upload_is_queued_for_deletion(self):
        with Session(self.engine) as db:
            a, _, conversation = self.add_conversation(db)
            prepared = self.prepare(
                db,
                conversation_id=conversation.id,
                user_id=a,
            )
            db.commit()

        with Session(self.engine) as db:
            ticket = db.query(ChatMediaUploadTicket).one()
            result = chat.expire_chat_media_uploads(
                db,
                now=ticket.expires_at + timedelta(seconds=1),
            )
            db.commit()
            self.assertEqual(result["expired"], 1)
            ticket = db.query(ChatMediaUploadTicket).one()
            self.assertEqual(ticket.status, "EXPIRED")
            deletion = db.query(PhotoObjectDeletion).one()
            self.assertEqual(deletion.object_key, prepared["object_key"])

    def test_caption_limit_is_enforced_server_side(self):
        with Session(self.engine) as db:
            a, _, conversation = self.add_conversation(db)
            prepared = self.prepare(
                db,
                conversation_id=conversation.id,
                user_id=a,
            )
            self.storage.objects[prepared["object_key"]] = (
                b"\x00\x00\x00\x18ftypisom" + b"0" * 12,
                "video/mp4",
            )
            with self.assertRaises(chat.MessageValidationError):
                chat.send_message(
                    db,
                    conversation_id=conversation.id,
                    sender_id=a,
                    body="x" * 1001,
                    media={
                        "object_key": prepared["object_key"],
                        "kind": "video",
                        "mime": "video/mp4",
                    },
                    storage=self.storage,
                    now=self.now,
                )


if __name__ == "__main__":
    unittest.main()
