import requests

from linksurf.helpers import get_env
from linksurf.models import (
    PresignedUploadURLResponse,
    ProxyResponse,
    SeedBody,
    SubmitResultBody,
)

MANAGER_URL = get_env("MANAGER_URL", default="http://localhost:8000")


class ManagerClient:
    def get_proxy(self) -> str:
        response = requests.get(f"{MANAGER_URL}/proxy", timeout=10)

        response.raise_for_status()

        return ProxyResponse.model_validate(response.json()).proxy

    def get_presigned_upload_url(self, url: str) -> PresignedUploadURLResponse:
        response = requests.get(f"{MANAGER_URL}/upload-url", json={"url": url}, timeout=10)

        response.raise_for_status()

        return PresignedUploadURLResponse.model_validate(response.json())

    def upload_html(self, presigned_url: str, html: str) -> None:
        response = requests.put(
            presigned_url,
            data=html.encode(),
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )

        response.raise_for_status()

    def submit_result(self, body: SubmitResultBody) -> None:
        requests.post(
            f"{MANAGER_URL}/result",
            data=body.model_dump_json(),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    def seed(self, url: str) -> None:
        requests.post(
            f"{MANAGER_URL}/seed",
            json=SeedBody(url=url).model_dump(),
            timeout=10,
        )
