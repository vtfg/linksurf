from aiobotocore.client import AioBaseClient
from aiobotocore.session import get_session, AioSession
from botocore.exceptions import ClientError

from linksurf.common.settings import Settings
from linksurf.services.base import Service


class BlobStorage(Service):
    NAME = "blob_storage"

    async def upload(self, blob: bytes, key: str, content_type: str | None = None) -> None:
        raise NotImplementedError()

    async def download(self, key: str) -> bytes:
        raise NotImplementedError()


class S3BlobStorage(BlobStorage):
    def __init__(
            self,
            bucket: str,
            endpoint_url: str,
            access_key: str,
            secret_key: str,
            region: str = "us-east-1",
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self._session: AioSession | None = None
        self._client: AioBaseClient | None = None
        self._context = None

    async def on_start(self, settings: Settings):
        session = get_session()

        context = session.create_client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

        client = await context.__aenter__()

        try:
            await client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await client.create_bucket(Bucket=self.bucket)
            else:
                raise

        self._context = context
        self._client = client

    async def on_stop(self):
        if self._context is not None:
            await self._context.__aexit__(None, None, None)
            self._client = None
            self._context = None

    async def upload(self, blob: bytes, key: str, content_type: str | None = None) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        args = {"Bucket": self.bucket, "Key": key, "Body": blob}

        if content_type:
            args["ContentType"] = content_type

        await self._client.put_object(**args)

    async def download(self, key: str) -> bytes:
        if self._client is None:
            raise RuntimeError("Service not started.")

        response = await self._client.get_object(Bucket=self.bucket, Key=key)

        async with response["Body"] as stream:
            content = await stream.read()

            return content
