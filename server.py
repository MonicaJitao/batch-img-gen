"""
本地代理服务器 - 转发图像生成请求，托管前端页面
运行: uvicorn server:app --reload --host 127.0.0.1 --port 8765
"""

import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_BASE = os.getenv("API_BASE", "https://api.tu-zi.com").rstrip("/")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TIMEOUT = httpx.Timeout(connect=10, read=120, write=30, pool=10)
# 参考图 multipart 上传可能较大，读写超时放宽
VIDEO_TIMEOUT = httpx.Timeout(connect=30, read=300, write=300, pool=10)


def json_or_text_response(resp: httpx.Response) -> Response:
    try:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except ValueError:
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type"),
        )


@app.post("/v1/videos")
async def proxy_videos_create(request: Request):
    """代理 POST /v1/videos：multipart/form-data，支持重复字段 input_reference。"""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured in .env")
    try:
        form = await request.form()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid multipart form: {e}") from e

    multipart = []
    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            body = await value.read()
            filename = value.filename or "reference.bin"
            content_type = value.content_type or "application/octet-stream"
            multipart.append((key, (filename, body, content_type)))
        else:
            multipart.append((key, (None, str(value))))

    if not multipart:
        raise HTTPException(status_code=400, detail="Empty form body")

    async with httpx.AsyncClient(timeout=VIDEO_TIMEOUT) as client:
        resp = await client.post(
            f"{API_BASE}/v1/videos",
            files=multipart,
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    return json_or_text_response(resp)


@app.get("/v1/videos/{task_id}")
async def proxy_videos_status(task_id: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured in .env")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{API_BASE}/v1/videos/{task_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    return json_or_text_response(resp)


@app.post("/v1/images/generations")
async def proxy_generate(request: Request):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured in .env")
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{API_BASE}/v1/images/generations",
            json=body,
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    return json_or_text_response(resp)


@app.get("/v1/images/generations/{task_id}")
async def proxy_status(task_id: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured in .env")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{API_BASE}/v1/images/generations/{task_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    return json_or_text_response(resp)


app.mount("/", StaticFiles(directory=".", html=True), name="static")
