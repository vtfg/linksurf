from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Query, Response, status

load_dotenv()

from linksurf.manager.cache import init_redis, update_domain_stats
from linksurf.manager.proxy import ProxyPool
from linksurf.manager.database import Link as LinkDocument, init_database, save_domain, save_links, save_url
from linksurf.manager.queue import Queue
from linksurf.manager.storage import generate_presigned_upload_url, html_storage_url, init_storage
from linksurf.helpers import get_env, hash_url
from linksurf.models import (
    PresignedUploadURLQuery,
    PresignedUploadURLResponse,
    ProxyResponse,
    SeedBody,
    SubmitResultBody,
    LinkType,
    SeedResponse,
)

HOST = get_env("MANAGER_HOST", default="0.0.0.0")
PORT = get_env("MANAGER_PORT", cast=int, default=8000)
PROXY_URLS = [url.strip() for url in get_env("PROXY_URLS").split(",")]

queue: Queue | None = None
proxy_pool: ProxyPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing app")

    global queue, proxy_pool

    await init_database()
    await init_redis()
    await init_storage()

    print("Initializing proxy pool")

    proxy_pool = ProxyPool()
    await proxy_pool.setup(PROXY_URLS)

    queue = Queue()
    await queue.connect()

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health", status_code=200)
async def health():
    return {"status": "ok"}


@app.get("/proxy", response_model=ProxyResponse)
async def get_proxy():
    proxy = await proxy_pool.get_next()

    return ProxyResponse(proxy=proxy)


@app.get("/upload-url", response_model=PresignedUploadURLResponse)
async def presigned_upload(query: Annotated[PresignedUploadURLQuery, Query()]):
    url_hash = hash_url(query.url)

    presigned_url, key = await generate_presigned_upload_url(url_hash)

    return PresignedUploadURLResponse(presigned_url=presigned_url, key=key)


@app.post("/result", status_code=204)
async def submit_result(body: SubmitResultBody, background_tasks: BackgroundTasks):
    background_tasks.add_task(_process_result, body)


async def _process_result(body: SubmitResultBody) -> None:
    print(f"Processing result for {body.address}")

    url_hash = hash_url(body.address)
    content_url = html_storage_url(body.content_key)
    domain = urlsplit(body.address).hostname.removeprefix("www.")

    await save_url(
        address=body.address,
        url_hash=url_hash,
        content_url=content_url,
        http=body.http,
        headers=body.headers,
        type=body.type,
        page=body.page,
        last_crawled_at=body.crawled_at,
    )

    await save_domain(domain, body.crawled_at)

    await update_domain_stats(body.address, body.http.response_time, body.http.size, body.crawled_at)

    links = [LinkDocument(**link.model_dump()) for link in body.links]

    await save_links(links)

    for link in body.links:
        depth = 0 if link.type == LinkType.EXTERNAL else body.depth + 1

        await queue.push(link.target, depth)

    print(f"Finished processing result for {body.address}")


@app.post("/seed", status_code=200)
async def seed(body: SeedBody, response: Response):
    added = await queue.push(body.url, 0)

    if not added:
        response.status_code = status.HTTP_400_BAD_REQUEST

    return SeedResponse(ok=added)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
