"""nara-web v2 API 진입점. 라우터는 단계별로 추가한다 (SPEC §6)."""

from fastapi import FastAPI

app = FastAPI(title="nara-web", version="2.0.0.dev0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
