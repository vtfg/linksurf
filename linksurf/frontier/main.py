from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Response, status

load_dotenv()

from linksurf.frontier.cache import init_redis
from linksurf.frontier.database import Link as LinkDocument, init_database, save_links, save_url
from linksurf.frontier.queue import Queue
from linksurf.frontier.storage import generate_presigned_upload_url, html_storage_url, init_storage
from linksurf.helpers import get_env, hash_url
from linksurf.models import (
    PresignedUploadURLBody,
    PresignedUploadURLResponse,
    ReserveSlotBody,
    ReserveSlotResponse,
    SeedBody,
    SubmitResultBody, LinkType, SeedResponse,
)

HOST = get_env("FRONTIER_HOST", default="0.0.0.0")
PORT = get_env("FRONTIER_PORT", cast=int, default=8000)

queue: Queue | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue

    await init_database()
    await init_redis()
    await init_storage()

    queue = Queue()
    await queue.connect()

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health", status_code=200)
async def health():
    return {"status": "ok"}


@app.post("/reserve", response_model=ReserveSlotResponse)
async def reserve_slot(body: ReserveSlotBody):
    delay_seconds = await queue.reserve_slot(body.url)

    return ReserveSlotResponse(delay_ms=int(delay_seconds * 1000))


@app.get("/upload-url", response_model=PresignedUploadURLResponse)
async def presigned_upload(body: PresignedUploadURLBody):
    url_hash = hash_url(body.url)

    presigned_url, key = await generate_presigned_upload_url(url_hash)

    return PresignedUploadURLResponse(presigned_url=presigned_url, key=key)


@app.post("/result", status_code=204)
async def submit_result(body: SubmitResultBody, background_tasks: BackgroundTasks):
    background_tasks.add_task(_process_result, body)


async def _process_result(body: SubmitResultBody) -> None:
    url_hash = hash_url(body.address)

    content_url = html_storage_url(body.content_key)

    await save_url(
        address=body.address,
        url_hash=url_hash,
        content_url=content_url,
        http=body.http,
        headers=body.headers,
        type=body.type,
        page=body.page,
    )

    links = [LinkDocument(**link.model_dump()) for link in body.links]

    await save_links(links)

    for link in body.links:
        depth = 0 if link.type == LinkType.EXTERNAL else body.depth + 1

        await queue.push(link.target, depth)


@app.post("/seed", status_code=200)
async def seed(body: SeedBody, response: Response):
    added = await queue.push(body.url, 0)

    if not added:
        response.status_code = status.HTTP_400_BAD_REQUEST

    return SeedResponse(ok=added)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
