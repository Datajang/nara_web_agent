import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

SEARCH_TRIGGERS = ["찾아줘", "검색해줘", "조회해줘", "알아봐줘"]

async def test_is_search_intent_triggers():
    from app.pipeline.orchestrator import is_search_intent
    assert is_search_intent("AI 개발 찾아줘", None) is True
    assert is_search_intent("입찰 검색해줘", None) is True

async def test_is_search_intent_blocked_in_chat():
    from app.pipeline.orchestrator import is_search_intent
    assert is_search_intent("이 공고 찾아줘", "chat") is False

async def test_is_search_intent_general_question():
    from app.pipeline.orchestrator import is_search_intent
    assert is_search_intent("이 공고 내용이 뭐야?", None) is False

async def test_extract_search_params_json():
    from app.pipeline.orchestrator import _extract_search_params
    with patch("app.pipeline.orchestrator.chat_complete", new_callable=AsyncMock,
               return_value='{"keyword": "AI 시스템", "days": 30}'):
        params = await _extract_search_params("AI 시스템 찾아줘")
    assert params["keyword"] == "AI 시스템"
    assert params["days"] == 30

async def test_extract_search_params_fallback():
    from app.pipeline.orchestrator import _extract_search_params
    with patch("app.pipeline.orchestrator.chat_complete", new_callable=AsyncMock,
               return_value="invalid json"):
        params = await _extract_search_params("AI 개발 검색해줘")
    assert "keyword" in params
    assert params["days"] == 30

async def test_get_current_step_from_messages():
    from app.pipeline.orchestrator import _get_current_step
    from app.db.models import Message

    m_search = Message(role="assistant", step="search", content="결과")
    assert _get_current_step([m_search]) == "search"

    m_analyze = Message(role="assistant", step="analyze", content="분석")
    assert _get_current_step([m_search, m_analyze]) == "analyze"

    assert _get_current_step([]) is None
