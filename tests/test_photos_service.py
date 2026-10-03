import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Market,
    ModerationAction,
    Photo,
    PhotoObjectDeletion,
    PhotoUploadTicket,
    Profile,
    User,
)
from app.photos import service as photos
from app.photos.storage import ObjectMetadata


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.upload_presigns = []
        self.download_presigns = []

    def presign_upload(self, object_key, mime, expires_seconds=600):
        self.upload_presigns.append((object_key,mime,expires_seconds))
        return {
            "url": f"https://upload.invalid/{object_key}",
            "method": "PUT",
            "headers": {"Content-Type": mime},
        }

    def presign_download(self, object_key, expires_seconds=900):
        self.download_presigns.append((object_key,expires_seconds))
        return f"https://download.invalid/{object_key}"

    def head(self, object_key):
        if object_key not in self.objects:
            raise KeyError(object_key)
        return self.objects[object_key]

    def sanitize_image(self, object_key, *, expected_mime, max_bytes):
        metadata = self.head(object_key)
        if metadata.content_type != expected_mime:
            raise ValueError("content type mismatch")
        if metadata.content_length > max_bytes:
            raise ValueError("file too large")
        return metadata

    def delete(self, object_key):
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class PhotoServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(text(
                "TRUNCATE TABLE moderation_actions, photo_object_deletions, "
                "photo_upload_tickets, photos, users, markets RESTART IDENTITY CASCADE"
            ))
        self.now = datetime.now(timezone.utc)
        self.storage = FakeStorage()
        with Session(self.engine) as db:
            market=Market(
                code="KZ-ALA",country_code="KZ",city_code="ALA",display_name="Алматы",
                timezone="Asia/Almaty",currency_code="KZT",default_language="ru-KZ",
                supported_languages=["ru-KZ"],registration_open=True,matching_open=False,
            )
            user=User(email="photo@example.com",password_hash="x",referral_code="photo-ref")
            db.add_all([market,user]); db.flush()
            db.add(Profile(user_id=user.id,display_name="Photo User",market_id=market.id))
            db.commit()
            self.user_id=user.id

    def prepare_and_upload(self, db, *, mime="image/jpeg", size=100_000, etag="etag"):
        prepared=photos.prepare_upload(
            db,user_id=self.user_id,mime=mime,storage=self.storage,now=self.now
        )
        self.storage.objects[prepared["object_key"]]=ObjectMetadata(
            content_length=size,content_type=mime,etag=etag
        )
        photo=photos.finalize_upload(
            db,user_id=self.user_id,ticket_token=prepared["ticket"],
            storage=self.storage,now=self.now + timedelta(seconds=1),
        )
        return photo,prepared

    def test_prepare_upload_uses_random_user_scoped_key_and_secret_ticket(self):
        with Session(self.engine) as db:
            prepared=photos.prepare_upload(
                db,user_id=self.user_id,mime="image/jpeg",storage=self.storage,now=self.now
            )
            db.commit()
            self.assertTrue(prepared["object_key"].startswith(f"users/{self.user_id}/"))
            self.assertTrue(prepared["object_key"].endswith(".jpg"))
            self.assertEqual(prepared["upload"]["method"],"PUT")
            self.assertEqual(prepared["upload"]["headers"]["Content-Type"],"image/jpeg")
            ticket_id,secret=prepared["ticket"].split(".",1)
            row=db.get(PhotoUploadTicket,int(ticket_id))
            self.assertIsNotNone(row)
            self.assertNotEqual(row.secret_hash,secret)
            self.assertEqual(row.status,"PREPARED")

    def test_unsupported_mime_is_rejected(self):
        with Session(self.engine) as db:
            with self.assertRaises(photos.PhotoError):
                photos.prepare_upload(
                    db,user_id=self.user_id,mime="image/svg+xml",
                    storage=self.storage,now=self.now,
                )

    def test_finalize_creates_pending_photo_using_storage_metadata(self):
        with Session(self.engine) as db:
            photo,prepared=self.prepare_and_upload(db,size=321_000,etag="abc")
            db.commit()
            self.assertEqual(photo.storage_key,prepared["object_key"])
            self.assertEqual(photo.byte_size,321_000)
            self.assertEqual(photo.object_etag,"abc")
            self.assertEqual(photo.moderation_status,"PENDING")
            self.assertTrue(photo.is_main)
            ticket_id=int(prepared["ticket"].split(".",1)[0])
            ticket=db.get(PhotoUploadTicket,ticket_id)
            self.assertEqual(ticket.status,"CONSUMED")
            self.assertIsNotNone(ticket.consumed_at)
            self.assertFalse(db.get(Profile,self.user_id).photos_completed)

    def test_expired_ticket_is_rejected(self):
        with Session(self.engine) as db:
            prepared=photos.prepare_upload(
                db,user_id=self.user_id,mime="image/jpeg",storage=self.storage,now=self.now
            )
            with self.assertRaises(photos.UploadTicketError):
                photos.finalize_upload(
                    db,user_id=self.user_id,ticket_token=prepared["ticket"],
                    storage=self.storage,now=self.now + timedelta(minutes=11),
                )
            db.commit()
            ticket_id=int(prepared["ticket"].split(".",1)[0])
            self.assertEqual(db.get(PhotoUploadTicket,ticket_id).status,"EXPIRED")

    def test_oversized_file_is_deleted_and_not_registered(self):
        with Session(self.engine) as db:
            prepared=photos.prepare_upload(
                db,user_id=self.user_id,mime="image/jpeg",storage=self.storage,now=self.now
            )
            self.storage.objects[prepared["object_key"]]=ObjectMetadata(
                content_length=photos.MAX_FILE_BYTES+1,
                content_type="image/jpeg",
                etag="too-big",
            )
            with self.assertRaises(photos.PhotoError):
                photos.finalize_upload(
                    db,user_id=self.user_id,ticket_token=prepared["ticket"],
                    storage=self.storage,now=self.now+timedelta(seconds=1),
                )
            db.commit()
            self.assertIn(prepared["object_key"],self.storage.deleted)
            self.assertEqual(
                db.query(Photo).filter_by(user_id=self.user_id).count(),0
            )

    def test_only_approved_photos_are_visible(self):
        with Session(self.engine) as db:
            p1,_=self.prepare_and_upload(db)
            p2,_=self.prepare_and_upload(db,etag="2")
            db.commit()
            self.assertEqual(photos.visible_photos(db,user_id=self.user_id),[])

            photos.moderate_photo(db,photo_id=p1.id,status="APPROVED",actor="test")
            photos.moderate_photo(db,photo_id=p2.id,status="REJECTED",actor="test",reason="bad")
            db.commit()

            visible=photos.visible_photos(db,user_id=self.user_id)
            self.assertEqual([p.id for p in visible],[p1.id])
            payloads=photos.visible_photo_payloads(
                db,user_id=self.user_id,storage=self.storage
            )
            self.assertEqual(len(payloads),1)
            self.assertIn(str(p1.storage_key),payloads[0]["url"])
            self.assertNotIn(str(p2.storage_key),payloads[0]["url"])

    def test_two_approved_photos_complete_photo_step_and_have_main(self):
        with Session(self.engine) as db:
            p1,_=self.prepare_and_upload(db,etag="1")
            p2,_=self.prepare_and_upload(db,etag="2")
            photos.moderate_photo(db,photo_id=p1.id,status="APPROVED",actor="moderator")
            self.assertFalse(db.get(Profile,self.user_id).photos_completed)
            photos.moderate_photo(db,photo_id=p2.id,status="APPROVED",actor="moderator")
            db.commit()

            profile=db.get(Profile,self.user_id)
            self.assertTrue(profile.photos_completed)
            visible=photos.visible_photos(db,user_id=self.user_id)
            self.assertEqual(len(visible),2)
            self.assertTrue(any(p.is_main for p in visible))
            self.assertEqual(
                db.query(ModerationAction).filter_by(target_type="photo").count(),2
            )

    def test_rejected_main_is_never_public_and_main_moves_to_approved_photo(self):
        with Session(self.engine) as db:
            p1,_=self.prepare_and_upload(db,etag="1")
            p2,_=self.prepare_and_upload(db,etag="2")
            photos.moderate_photo(db,photo_id=p1.id,status="APPROVED",actor="moderator")
            photos.moderate_photo(db,photo_id=p2.id,status="APPROVED",actor="moderator")
            db.commit()
            self.assertTrue(p1.is_main)

            photos.moderate_photo(
                db,photo_id=p1.id,status="REJECTED",actor="moderator",reason="policy"
            )
            db.commit()

            visible=photos.visible_photos(db,user_id=self.user_id)
            self.assertEqual([p.id for p in visible],[p2.id])
            self.assertTrue(visible[0].is_main)
            self.assertFalse(db.get(Profile,self.user_id).photos_completed)

    def test_reorder_and_main_selection_are_owner_scoped(self):
        with Session(self.engine) as db:
            p1,_=self.prepare_and_upload(db,etag="1")
            p2,_=self.prepare_and_upload(db,etag="2")
            photos.reorder_photos(
                db,user_id=self.user_id,ordered_photo_ids=[p2.id,p1.id]
            )
            photos.set_main_photo(db,user_id=self.user_id,photo_id=p2.id)
            db.commit()
            rows=photos.list_owner_photos(db,user_id=self.user_id)
            self.assertEqual([p.id for p in rows],[p2.id,p1.id])
            self.assertTrue(rows[0].is_main)
            self.assertFalse(rows[1].is_main)

    def test_maximum_five_photos_including_active_upload_tickets(self):
        with Session(self.engine) as db:
            for _ in range(photos.MAX_PHOTOS):
                photos.prepare_upload(
                    db,user_id=self.user_id,mime="image/jpeg",
                    storage=self.storage,now=self.now,
                )
            with self.assertRaises(photos.PhotoLimitReached):
                photos.prepare_upload(
                    db,user_id=self.user_id,mime="image/jpeg",
                    storage=self.storage,now=self.now,
                )

    def test_delete_uses_transactional_outbox_and_worker_removes_object(self):
        with Session(self.engine) as db:
            p1,_=self.prepare_and_upload(db,etag="1")
            key=p1.storage_key
            db.commit()

            photos.delete_photo(db,user_id=self.user_id,photo_id=p1.id)
            db.commit()
            self.assertIsNone(db.get(Photo,p1.id))
            queued=db.query(PhotoObjectDeletion).filter_by(object_key=key).one()
            self.assertEqual(queued.status,"PENDING")
            self.assertIn(key,self.storage.objects)

            result=photos.process_deletion_outbox(db,storage=self.storage)
            db.commit()
            self.assertEqual(result["done"],1)
            self.assertIn(key,self.storage.deleted)
            self.assertEqual(queued.status,"DONE")

    def test_database_rejects_invalid_photo_metadata(self):
        with Session(self.engine) as db:
            db.add(Photo(
                user_id=self.user_id,
                storage_key="users/1/bad.jpg",
                mime="image/jpeg",
                byte_size=-1,
                sort_order=-1,
                moderation_status="VISIBLE",
            ))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_photo_progress_reports_minimum_and_recommendation(self):
        with Session(self.engine) as db:
            progress=photos.photo_progress(db,user_id=self.user_id)
            self.assertEqual(progress["minimum"],2)
            self.assertEqual(progress["recommended_min"],3)
            self.assertEqual(progress["recommended_max"],5)
            self.assertEqual(progress["maximum"],5)
            self.assertFalse(progress["complete"])


if __name__=="__main__":
    unittest.main()
