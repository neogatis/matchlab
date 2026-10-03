import io
import json
import unittest
from unittest.mock import patch

from app.push.fcm import FcmProviderClient
from app.push.storage import S3PushTokenVault


class FakeBody:
    def __init__(self, raw: bytes):
        self.raw = raw

    def read(self, size=-1):
        return self.raw if size < 0 else self.raw[:size]


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, *, Bucket, Key):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


class FakeCredentials:
    def __init__(self, token="access-token"):
        self.token = token
        self.valid = True

    def refresh(self, request):
        self.token = "refreshed-token"
        self.valid = True


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class PushProviderRuntimeTests(unittest.TestCase):
    def test_s3_vault_round_trip_and_delete(self):
        client = FakeS3()
        vault = S3PushTokenVault(client, "push-bucket")
        token = "fcm-token-12345678901234567890"

        ref = vault.store(token)
        self.assertTrue(ref.startswith("s3:push-tokens/"))
        self.assertNotIn(token, ref)
        self.assertEqual(vault.resolve(ref), token)

        vault.delete(ref)
        with self.assertRaises(KeyError):
            vault.resolve(ref)

    def test_fcm_success_returns_provider_message_id(self):
        client = FcmProviderClient(
            project_id="matchlab-test",
            credentials=FakeCredentials(),
        )
        with patch(
            "requests.post",
            return_value=FakeResponse(
                200,
                {
                    "name": "projects/matchlab-test/messages/0:123456789"
                },
            ),
        ) as post:
            result = client.send(
                token="fcm-token-12345678901234567890",
                title="MatchLab",
                body="У вас новое сообщение",
                data={"kind": "MESSAGE"},
            )

        self.assertTrue(result.ok)
        self.assertEqual(
            result.provider_message_id,
            "projects/matchlab-test/messages/0:123456789",
        )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["message"]["data"], {"kind": "MESSAGE"})
        self.assertEqual(payload["message"]["android"]["priority"], "high")

    def test_fcm_unregistered_marks_invalid_token(self):
        client = FcmProviderClient(
            project_id="matchlab-test",
            credentials=FakeCredentials(),
        )
        payload = {
            "error": {
                "code": 404,
                "status": "NOT_FOUND",
                "message": "Requested entity was not found.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode": "UNREGISTERED",
                    }
                ],
            }
        }
        with patch(
            "requests.post",
            return_value=FakeResponse(404, payload),
        ):
            result = client.send(
                token="fcm-token-12345678901234567890",
                title="MatchLab",
                body="У вас новое сообщение",
                data={"kind": "MESSAGE"},
            )

        self.assertFalse(result.ok)
        self.assertTrue(result.invalid_token)
        self.assertIn("UNREGISTERED", result.error)


if __name__ == "__main__":
    unittest.main()
