import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

async def test_is_bid_open_future():
    from nara_server.g2b_api import is_bid_open
    future = (datetime.now() + timedelta(days=5)).strftime("%Y%m%d%H%M")
    assert is_bid_open(future) is True

async def test_is_bid_open_past():
    from nara_server.g2b_api import is_bid_open
    past = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d%H%M")
    assert is_bid_open(past) is False

async def test_is_bid_open_empty():
    from nara_server.g2b_api import is_bid_open
    assert is_bid_open("") is False
    assert is_bid_open(None) is False

async def test_get_date_range_days():
    from nara_server.g2b_api import get_date_range
    start, end = get_date_range(days=7)
    assert len(start) == 12 and len(end) == 12
    start_dt = datetime.strptime(start, "%Y%m%d%H%M")
    end_dt = datetime.strptime(end, "%Y%m%d%H%M")
    assert 6 <= (end_dt - start_dt).days <= 8

async def test_get_date_chunks():
    from nara_server.g2b_api import get_date_chunks
    chunks = get_date_chunks(days=30, chunk_size=15)
    assert len(chunks) == 2
    for start, end in chunks:
        assert len(start) == 12

async def test_parse_response_single_item():
    from nara_server.g2b_api import _parse_items
    data = {"response": {"header": {"resultCode": "00"}, "body": {
        "items": {"item": {"bidNtceNm": "Test", "bidNtceNo": "001", "bidClseDt": "202601010000"}},
        "totalCount": 1
    }}}
    items = _parse_items(data)
    assert len(items) == 1 and items[0]["bidNtceNm"] == "Test"

async def test_parse_response_list():
    from nara_server.g2b_api import _parse_items
    data = {"response": {"header": {"resultCode": "00"}, "body": {
        "items": {"item": [{"bidNtceNm": "A"}, {"bidNtceNm": "B"}]},
        "totalCount": 2
    }}}
    assert len(_parse_items(data)) == 2

async def test_parse_response_no_data():
    from nara_server.g2b_api import _parse_items
    assert _parse_items({"response": {"header": {"resultCode": "03"}, "body": {}}}) == []

async def test_search_bids_structured_returns_bid_results():
    from unittest.mock import AsyncMock, patch
    from app.pipeline.g2b_search import search_bids_structured, BidResult

    mock_bids = [{"bidNtceNm": "AI 시스템 구축", "bidNtceNo": "001",
                  "ntceSpecDocUrl1": "http://ex.com/f.hwp", "ntceSpecFileNm1": "f.hwp",
                  "bidClseDt": "203001010000", "asignBdgtAmt": "100000000", "dminsttNm": "기관"}]
    mock_prespec = []

    with patch("app.pipeline.g2b_search.search_bids", new_callable=AsyncMock, return_value=mock_bids), \
         patch("app.pipeline.g2b_search.search_prespec", new_callable=AsyncMock, return_value=mock_prespec):
        results = await search_bids_structured("AI", days=30)

    assert len(results) == 1
    assert isinstance(results[0], BidResult)
    assert results[0].bid_title == "AI 시스템 구축"
    assert results[0].is_open is True
    assert results[0].source == "regular"

async def test_bid_result_serializable():
    from app.pipeline.g2b_search import BidResult
    import dataclasses, json
    r = BidResult(bid_title="T", bid_number="N", file_url="u", filename="f.hwp",
                  deadline="203001010000", budget="1억", is_open=True, source="regular")
    d = dataclasses.asdict(r)
    json.dumps(d)  # must not raise
