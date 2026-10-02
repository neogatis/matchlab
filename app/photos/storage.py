from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import boto3


@dataclass(frozen=True)
class ObjectMetadata:
    content_length: int
    content_type: str
    etag: str | None


class S3PhotoStorage:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls) -> "S3PhotoStorage":
        bucket = os.environ.get("MATCH_PHOTO_BUCKET", "").strip()
        endpoint = os.environ.get("AWS_ENDPOINT_URL_S3", "").strip()
        region = os.environ.get("AWS_REGION", "").strip()
        access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
        missing = [
            name
            for name, value in [
                ("MATCH_PHOTO_BUCKET", bucket),
                ("AWS_ENDPOINT_URL_S3", endpoint),
                ("AWS_REGION", region),
                ("AWS_ACCESS_KEY_ID", access_key),
                ("AWS_SECRET_ACCESS_KEY", secret_key),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError("Missing photo storage configuration: " + ", ".join(missing))

        client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        return cls(client, bucket)

    def presign_upload(self, object_key: str, mime: str, expires_seconds: int = 600) -> dict[str, Any]:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": mime,
            },
            ExpiresIn=expires_seconds,
        )
        return {
            "url": url,
            "method": "PUT",
            "headers": {"Content-Type": mime},
        }

    def presign_download(self, object_key: str, expires_seconds: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_seconds,
        )

    def head(self, object_key: str) -> ObjectMetadata:
        result = self.client.head_object(Bucket=self.bucket, Key=object_key)
        return ObjectMetadata(
            content_length=int(result.get("ContentLength") or 0),
            content_type=str(result.get("ContentType") or ""),
            etag=(str(result.get("ETag") or "").strip('"') or None),
        )

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
