"""S3 storage facade for offloading heavy artifacts from the OLTP database.

The schema is: heavy report files (CSV/PDF/JSON) are written to object storage
(MinIO in dev, S3 in prod). The API returns either a pre-signed URL for direct
download or, when CDN sits in front of the bucket, a stable CDN URL. The OLTP
database only stores the object key, not the bytes.
"""
import io
import json
import uuid

import boto3
from botocore.client import Config

from .settings import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket() -> None:
    client = _client()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)
    # Public read policy so the Nginx CDN layer can serve objects without
    # forwarding AWS signatures. Presigned URLs remain available for clients
    # that need direct authenticated access.
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{settings.s3_bucket}/*"],
                }
            ],
        }
    )
    client.put_bucket_policy(Bucket=settings.s3_bucket, Policy=policy)


def upload_report(user_id: str, payload: dict) -> dict:
    """Persist a generated report to S3 and return CDN + presigned URLs."""
    key = f"reports/{user_id}/{uuid.uuid4()}.json"
    body = json.dumps(payload).encode("utf-8")
    client = _client()
    client.upload_fileobj(io.BytesIO(body), settings.s3_bucket, key, ExtraArgs={"ContentType": "application/json"})

    presigned = client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presigned_expires_seconds,
    )
    cdn_url = f"{settings.s3_public_base_url}/{settings.s3_bucket}/{key}"
    return {"key": key, "presigned_url": presigned, "cdn_url": cdn_url}
