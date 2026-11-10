from datetime import datetime, timedelta

from app.g2b.parse import get_date_chunks, get_date_range, is_bid_open, parse_items


def test_is_bid_open_future():
    future = (datetime.now() + timedelta(days=5)).strftime("%Y%m%d%H%M")
    assert is_bid_open(future) is True


def test_is_bid_open_past():
    past = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d%H%M")
    assert is_bid_open(past) is False


def test_is_bid_open_empty_means_undecided_open():
    # SPEC §4: 마감 미정(빈 값)은 진행중으로 본다.
    assert is_bid_open("") is True
    assert is_bid_open(None) is True


def test_is_bid_open_accepts_all_g2b_formats():
    future = datetime.now() + timedelta(days=5)
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d"):
        assert is_bid_open(future.strftime(fmt)) is True
    past = datetime.now() - timedelta(days=5)
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d"):
        assert is_bid_open(past.strftime(fmt)) is False


def test_get_date_range_days():
    start, end = get_date_range(days=7)
    assert len(start) == 12 and len(end) == 12
    start_dt = datetime.strptime(start, "%Y%m%d%H%M")
    end_dt = datetime.strptime(end, "%Y%m%d%H%M")
    assert 6 <= (end_dt - start_dt).days <= 8


def test_get_date_chunks():
    chunks = get_date_chunks(days=30, chunk_size=15)
    assert len(chunks) == 2
    for start, _end in chunks:
        assert len(start) == 12


def test_parse_response_single_item():
    data = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "items": {"item": {"bidNtceNm": "Test", "bidNtceNo": "001"}},
                "totalCount": 1,
            },
        }
    }
    items = parse_items(data)
    assert len(items) == 1 and items[0]["bidNtceNm"] == "Test"


def test_parse_response_list():
    data = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {"items": {"item": [{"bidNtceNm": "A"}, {"bidNtceNm": "B"}]}, "totalCount": 2},
        }
    }
    assert len(parse_items(data)) == 2


def test_parse_response_plain_list():
    data = {"response": {"header": {"resultCode": "00"}, "body": {"items": [{"bidNtceNm": "A"}]}}}
    assert len(parse_items(data)) == 1


def test_parse_response_null_string():
    data = {"response": {"header": {"resultCode": "00"}, "body": {"items": "null"}}}
    assert parse_items(data) == []


def test_parse_response_no_data():
    assert parse_items({"response": {"header": {"resultCode": "03"}, "body": {}}}) == []
