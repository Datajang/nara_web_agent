"""추출 워커 예열 (§5.6-5). 워커는 spawn이라 첫 추출 때 HWPLoader 임포트로 1초 넘게 걸린다.

서버 시작 시 워커를 미리 띄워 첫 사용자 요청이 그 비용을 내지 않게 한다.
"""

import asyncio

from fastapi.testclient import TestClient

from app.files import extract


async def test_warm_pool_imports_extractor_in_worker():
    extract._kill_pool()
    try:
        assert await extract.warm_pool() is True
    finally:
        extract._kill_pool()


async def test_restarted_pool_workers_import_extractor_on_start():
    """시간 초과로 풀을 죽이고 새로 만들어도 새 워커가 시작하자마자 추출기를 불러온다."""
    extract._kill_pool()
    try:
        loop = asyncio.get_running_loop()
        loaded = await loop.run_in_executor(extract._get_pool(), extract._extractor_loaded)
        assert loaded is True
    finally:
        extract._kill_pool()


def test_app_startup_warms_extract_pool(monkeypatch):
    import app.main as main

    called: list[bool] = []

    async def fake_warm() -> bool:
        called.append(True)
        return True

    monkeypatch.setattr(main, "warm_pool", fake_warm)
    with TestClient(main.build_app()):
        pass
    assert called == [True]
