import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from linksurf.common.settings import Settings
from linksurf.services.base import Service

logger = logging.getLogger(__name__)


class BlobStorage(Service):
    NAME = "blob_storage"

    def upload(self, blob: bytes, key: str, content_type: str | None = None) -> None:
        pass

    def download(self, key: str) -> bytes:
        pass


class S3BlobStorage(BlobStorage):
    def __init__(
            self,
            bucket: str,
            region: str = "us-east-1",
            endpoint_url: str | None = None,
            access_key: str | None = None,
            secret_key: str | None = None,
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self._client = None

    def on_start(self, settings: Settings):
        self._client = boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                self._client.create_bucket(Bucket=self.bucket)

                logger.info("Created bucket %s", self.bucket)
            else:
                raise

    def on_stop(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def upload(self, blob: bytes, key: str, content_type: str | None = None) -> None:
        try:
            args = {"Bucket": self.bucket, "Key": key, "Body": blob}

            if content_type:
                args["ContentType"] = content_type

            self._client.put_object(**args)

            logger.debug("Uploaded %d bytes to s3://%s/%s", len(blob), self.bucket, key)
        except (BotoCoreError, ClientError):
            logger.exception("Failed to upload to s3://%s/%s", self.bucket, key)

            raise

    def download(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)

            return response["Body"].read()
        except (BotoCoreError, ClientError) as e:
            logger.exception("Failed to download from s3://%s/%s", self.bucket, key)

            raise
