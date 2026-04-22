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


async def upload_html(url_hash: str, html: str) -> str:
    key = f"html/{url_hash}"

    async with _make_client() as client:
        await client.put_object(
            Bucket=MINIO_BUCKET,
            Key=key,
            Body=html.encode(),
            ContentType="text/plain",
        )

    return f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}"
