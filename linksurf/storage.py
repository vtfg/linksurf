import boto3

from linksurf.helpers import get_env

MINIO_ENDPOINT = get_env("MINIO_ENDPOINT", default="http://localhost:9000")
MINIO_ACCESS_KEY = get_env("MINIO_ACCESS_KEY", default="minioadmin")
MINIO_SECRET_KEY = get_env("MINIO_SECRET_KEY", default="minioadmin")
MINIO_BUCKET = get_env("MINIO_BUCKET", default="linksurf")

_client = None


def init_storage() -> None:
    global _client

    _client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )

    existing = [b["Name"] for b in _client.list_buckets()["Buckets"]]

    if MINIO_BUCKET not in existing:
        _client.create_bucket(Bucket=MINIO_BUCKET)


def upload_html(url_hash: str, html: str) -> str:
    key = f"html/{url_hash}"
    _client.put_object(
        Bucket=MINIO_BUCKET,
        Key=key,
        Body=html.encode(),
        ContentType="text/plain",
    )
    return f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}"
