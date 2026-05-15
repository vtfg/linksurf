import httpx

from linksurf.helpers import get_env
from linksurf.models import (
    PresignedUploadURLResponse,
    ProxyResponse,
    SeedBody,
    SubmitResultBody,
)

MANAGER_URL = get_env("MANAGER_URL", default="http://localhost:8000")


class ManagerClient:
    def __init__(self):
        self._client = httpx.AsyncClient()

    async def get_proxy(self) -> str:
        response = await self._client.get(f"{MANAGER_URL}/proxy", timeout=10)

        response.raise_for_status()

        return ProxyResponse.model_validate(response.json()).proxy

    async def get_presigned_upload_url(self, url: str) -> PresignedUploadURLResponse:
        response = await self._client.get(
            f"{MANAGER_URL}/upload-url",
            params={"url": url},
            timeout=10,
        )

        response.raise_for_status()

        return PresignedUploadURLResponse.model_validate(response.json())

    async def upload_html(self, presigned_url: str, html: str) -> None:
        response = await self._client.put(
            presigned_url,
            content=html.encode(),
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )

        response.raise_for_status()

    async def submit_result(self, body: SubmitResultBody) -> None:
        await self._client.post(
            f"{MANAGER_URL}/result",
            content=body.model_dump_json(),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    async def seed(self, url: str) -> None:
        await self._client.post(
            f"{MANAGER_URL}/seed",
            json=SeedBody(url=url).model_dump(),
            timeout=10,
        )
