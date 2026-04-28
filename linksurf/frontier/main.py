from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI

load_dotenv()

from linksurf.frontier.cache import init_redis
from linksurf.frontier.database import Link as LinkDocument, init_database, save_links, save_page
from linksurf.frontier.queue import Queue
from linksurf.frontier.storage import generate_presigned_upload_url, html_storage_url, init_storage
from linksurf.helpers import get_env, hash_url
from linksurf.models import (
    PresignedUploadURLBody,
    PresignedUploadURLResponse,
    ReserveSlotBody,
    ReserveSlotResponse,
    SeedBody,
    SubmitResultBody,
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
    url_hash = hash_url(body.url)

    html_url = html_storage_url(body.html_key)

    await save_page(body.url, url_hash, html_url, body.metadata)

    links = [LinkDocument(**link.model_dump()) for link in body.links]

    await save_links(links)

    await queue.mark_seen(url_hash)

    for link in body.links:
        await queue.push(link.target, body.depth + 1)


@app.post("/seed", status_code=204)
async def seed(body: SeedBody):
    await queue.push(body.url, 0)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
