import aiobotocore.session

from linksurf.helpers import get_env

MINIO_ENDPOINT = get_env("MINIO_ENDPOINT", default="http://localhost:9000")
MINIO_ACCESS_KEY = get_env("MINIO_ACCESS_KEY", default="minioadmin")
MINIO_SECRET_KEY = get_env("MINIO_SECRET_KEY", default="minioadmin")
MINIO_BUCKET = get_env("MINIO_BUCKET", default="linksurf")


def _make_client():
    return aiobotocore.session.get_session().create_client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


async def init_storage() -> None:
    async with _make_client() as client:
        existing = [b["Name"] for b in (await client.list_buckets())["Buckets"]]

        if MINIO_BUCKET not in existing:
            await client.create_bucket(Bucket=MINIO_BUCKET)


async def generate_presigned_upload_url(url_hash: str) -> tuple[str, str]:
    key = f"html/{url_hash}"

    async with _make_client() as client:
        presigned_url = await client.generate_presigned_url(
            "put_object",
            Params={"Bucket": MINIO_BUCKET, "Key": key, "ContentType": "text/plain"},
            ExpiresIn=300,
        )

    return presigned_url, key


def html_storage_url(key: str) -> str:
    return f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}"
