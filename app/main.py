from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.db.database import create_tables
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield

app = FastAPI(title="nara-web", lifespan=lifespan)

from app.auth.router import router as auth_router
from app.projects.router import router as projects_router
from app.conversations.router import router as conv_router
from app.bookmarks.router import router as bookmarks_router

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(conv_router)
app.include_router(bookmarks_router)

@app.get("/health")
async def health():
    from app.config import settings
    return {"status": "ok", "vllm": settings.vllm_base_url}

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
