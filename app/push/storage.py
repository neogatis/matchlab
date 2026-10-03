from __future__ import annotations

import os
import secrets

import boto3
from botocore.config import Config

from app.push.service import PushError


def _env_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


class S3PushTokenVault:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls) -> "S3PushTokenVault":
        bucket = _env_value("MATCH_PUSH_TOKEN_BUCKET")
        endpoint = _env_value("AWS_ENDPOINT_URL_S3")
        region = _env_value("AWS_REGION")
        access_key = _env_value("AWS_ACCESS_KEY_ID")
        secret_key = _env_value("AWS_SECRET_ACCESS_KEY")
        missing = [
            name
            for name, value in [
                ("MATCH_PUSH_TOKEN_BUCKET", bucket),
                ("AWS_ENDPOINT_URL_S3", endpoint),
                ("AWS_REGION", region),
                ("AWS_ACCESS_KEY_ID", access_key),
                ("AWS_SECRET_ACCESS_KEY", secret_key),
            ]
            if not value
        ]
        if missing:
            raise PushError("missing_push_token_vault_config:" + ",".join(missing))

        client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}),
        )
        return cls(client, bucket)

    def store(self, token: str) -> str:
        raw = (token or "").encode("utf-8")
        if len(raw) < 16 or len(raw) > 4096:
            raise PushError("invalid_token_length")
        key = "push-tokens/" + secrets.token_hex(24)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=raw,
            ContentType="text/plain; charset=utf-8",
            CacheControl="private, max-age=0, no-store",
        )
        return "s3:" + key

    def _key(self, token_ref: str) -> str:
        if not token_ref.startswith("s3:"):
            raise PushError("unsupported_token_ref")
        key = token_ref[3:]
        if not key.startswith("push-tokens/"):
            raise PushError("invalid_token_ref")
        return key

    def resolve(self, token_ref: str) -> str:
        key = self._key(token_ref)
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        body = result["Body"]
        raw = body.read(4097)
        if len(raw) > 4096:
            raise PushError("stored_token_too_large")
        try:
            token = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PushError("stored_token_invalid_utf8") from exc
        if len(token) < 16:
            raise PushError("stored_token_invalid")
        return token

    def delete(self, token_ref: str) -> None:
        key = self._key(token_ref)
        self.client.delete_object(Bucket=self.bucket, Key=key)
