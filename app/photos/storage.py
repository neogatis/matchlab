from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class ObjectMetadata:
    content_length: int
    content_type: str
    etag: str | None


class InvalidImageObject(ValueError):
    pass


def _env_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def sanitize_image_bytes(raw: bytes, expected_mime: str) -> bytes:
    if not raw:
        raise InvalidImageObject("empty_image")

    expected_format = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }.get((expected_mime or "").lower())
    if expected_format is None:
        raise InvalidImageObject("unsupported_image_type")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        try:
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.format != expected_format:
                    raise InvalidImageObject("image_content_type_mismatch")
                if getattr(probe, "is_animated", False):
                    raise InvalidImageObject("animated_images_not_supported")
                width, height = probe.size
                if width < 200 or height < 200:
                    raise InvalidImageObject("image_dimensions_too_small")
                if width * height > MAX_IMAGE_PIXELS:
                    raise InvalidImageObject("image_dimensions_too_large")
                probe.verify()

            with Image.open(io.BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source)
                image.load()

                # Re-encoding deliberately drops EXIF/GPS and other source metadata.
                output = io.BytesIO()
                if expected_format == "JPEG":
                    if image.mode not in {"RGB", "L"}:
                        image = image.convert("RGB")
                    image.save(
                        output,
                        format="JPEG",
                        quality=92,
                        optimize=True,
                        progressive=True,
                    )
                elif expected_format == "PNG":
                    if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                        image = image.convert("RGBA")
                    image.save(output, format="PNG", optimize=True)
                else:
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGB")
                    image.save(output, format="WEBP", quality=92, method=4)

                sanitized = output.getvalue()
                if not sanitized:
                    raise InvalidImageObject("image_reencode_failed")
                return sanitized
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise InvalidImageObject("invalid_image_content") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


class S3PhotoStorage:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls) -> "S3PhotoStorage":
        bucket = _env_value("MATCH_PHOTO_BUCKET")
        endpoint = _env_value("AWS_ENDPOINT_URL_S3")
        region = _env_value("AWS_REGION")
        access_key = _env_value("AWS_ACCESS_KEY_ID")
        secret_key = _env_value("AWS_SECRET_ACCESS_KEY")
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
            config=Config(s3={"addressing_style": "path"}),
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

    def get_prefix(self, object_key: str, *, max_bytes: int = 4096) -> bytes:
        if max_bytes < 1:
            return b""
        result = self.client.get_object(
            Bucket=self.bucket,
            Key=object_key,
            Range=f"bytes=0-{max_bytes - 1}",
        )
        return result["Body"].read(max_bytes)

    def get_bytes(self, object_key: str, *, max_bytes: int) -> bytes:
        result = self.client.get_object(Bucket=self.bucket, Key=object_key)
        body = result["Body"]
        raw = body.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise InvalidImageObject("image_file_too_large")
        return raw

    def put_bytes(self, object_key: str, *, raw: bytes, mime: str) -> ObjectMetadata:
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=raw,
            ContentType=mime,
            CacheControl="private, max-age=0, no-store",
            Metadata={"sanitized": "true"},
        )
        return self.head(object_key)

    def sanitize_image(
        self,
        object_key: str,
        *,
        expected_mime: str,
        max_bytes: int,
    ) -> ObjectMetadata:
        raw = self.get_bytes(object_key, max_bytes=max_bytes)
        sanitized = sanitize_image_bytes(raw, expected_mime)
        if len(sanitized) > max_bytes:
            raise InvalidImageObject("sanitized_image_too_large")
        return self.put_bytes(
            object_key,
            raw=sanitized,
            mime=expected_mime,
        )

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
