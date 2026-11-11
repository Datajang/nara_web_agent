"""§13.4 게이트: 사용자 A가 B의 자원에 접근하면 404. §6.1 입력 제한, §6.2 프로필 CRUD."""

from app.profiles.hashing import profile_hash
from tests.helpers import create_user, login

P = "/api/v1/profiles"


async def logged_in(api, email):
    await create_user(api.db, email)
    c = api.client()
    assert (await login(c, email)).status_code == 200
    return c


async def test_other_users_profile_is_404(api):
    a = await logged_in(api, "a@corp.example")
    b = await logged_in(api, "b@corp.example")
    try:
        r = await a.post(
            P, json={"name": "A팀", "description": "AI 플랫폼 구축", "keywords": ["AI"]}
        )
        assert r.status_code == 201
        pid = r.json()["id"]

        for method, body in (("GET", None), ("PATCH", {"name": "탈취"}), ("DELETE", None)):
            r = await b.request(method, f"{P}/{pid}", json=body)
            assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", method
        assert (await b.get(P)).json()["items"] == []
        assert (await a.get(f"{P}/{pid}")).json()["name"] == "A팀"  # 그대로
        assert (await a.get(P)).json()["items"][0]["id"] == pid
    finally:
        await a.aclose()
        await b.aclose()


async def test_profile_crud_hash_and_default(api):
    a = await logged_in(api, "a@corp.example")
    try:
        p1 = (await a.post(P, json={"name": "1", "description": "x  y", "is_default": True})).json()
        p2 = (await a.post(P, json={"name": "2", "description": "z", "is_default": True})).json()
        items = {p["id"]: p for p in (await a.get(P)).json()["items"]}
        assert items[p2["id"]]["is_default"] and not items[p1["id"]]["is_default"]

        r = await a.patch(
            f"{P}/{p1['id']}", json={"description": "새 설명", "keywords": [" a ", "a", "b"]}
        )
        assert r.status_code == 200
        assert r.json()["keywords"] == ["a", "b"]  # 공백 제거·중복 제거
        assert r.json()["profile_hash"] == profile_hash("새 설명")
        assert (await a.delete(f"{P}/{p1['id']}")).status_code == 204
        assert (await a.get(f"{P}/{p1['id']}")).status_code == 404
    finally:
        await a.aclose()


async def test_profile_input_limits(api):
    a = await logged_in(api, "a@corp.example")
    try:
        r = await a.post(P, json={"name": "x", "keywords": [f"k{i}" for i in range(11)]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
        assert (await a.post(P, json={"name": "x", "keywords": ["k" * 51]})).status_code == 422
        assert (await a.post(P, json={"name": "x", "description": "d" * 4001})).status_code == 422
        for i in range(20):
            assert (await a.post(P, json={"name": f"p{i}"})).status_code == 201
        r = await a.post(P, json={"name": "21번째"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    finally:
        await a.aclose()
