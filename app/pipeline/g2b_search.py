import asyncio
import dataclasses
from typing import Optional
from nara_server.g2b_api import search_bids, search_prespec, fetch_eorder_files, is_bid_open


@dataclasses.dataclass
class BidResult:
    bid_title: str
    bid_number: str
    file_url: Optional[str]
    filename: Optional[str]
    deadline: str
    budget: str
    is_open: bool
    source: str  # 'regular' | 'prespec'
    bid_page_url: Optional[str] = None
    prespec_reg_no: Optional[str] = None  # bfSpecRgstNo for cross-reference fallback


def _find_proposal_file(item: dict) -> tuple[Optional[str], Optional[str]]:
    """ntceSpecDocUrl1~10 중 제안요청서/과업지시서 우선, 없으면 첫 번째 파일 반환."""
    for keyword in ("제안요청서", "과업지시서", "제안"):
        for i in range(1, 11):
            url = item.get(f"ntceSpecDocUrl{i}", "")
            name = item.get(f"ntceSpecFileNm{i}", "")
            if url and name and keyword in name:
                return url, name
    for i in range(1, 11):
        url = item.get(f"ntceSpecDocUrl{i}", "")
        name = item.get(f"ntceSpecFileNm{i}", "")
        if url:
            return url, name or ""
    return None, None


def _find_prespec_file(item: dict) -> tuple[Optional[str], Optional[str]]:
    """사전규격 아이템은 specDocFileUrl1~5 사용."""
    for i in range(1, 6):
        url = item.get(f"specDocFileUrl{i}", "")
        if url:
            return url, f"규격문서 {i}"
    return None, None


def _map_bid(item: dict, source: str) -> BidResult:
    if source == "regular":
        file_url, filename = _find_proposal_file(item)
        deadline = item.get("bidClseDt", "")
        # bdgtAmt / presmptPrce are the correct fields for regular bids
        budget = str(item.get("bdgtAmt") or item.get("presmptPrce") or "")
        prespec_reg_no = item.get("bfSpecRgstNo") or None
    else:
        file_url, filename = _find_prespec_file(item)
        deadline = item.get("opninRgstClseDt") or item.get("rcptDt", "")
        budget = str(item.get("asignBdgtAmt") or "")
        prespec_reg_no = None

    return BidResult(
        bid_title=item.get("bidNtceNm") or item.get("prdctClsfcNoNm", ""),
        bid_number=item.get("bidNtceNo") or item.get("bfSpecRgstNo", ""),
        file_url=file_url,
        filename=filename,
        deadline=deadline,
        budget=budget,
        is_open=is_bid_open(deadline),
        source=source,
        bid_page_url=item.get("bidNtceDtlUrl") or item.get("bidNtceUrl"),
        prespec_reg_no=prespec_reg_no,
    )


async def _fill_missing_files(results: list[BidResult], prespec_items: list[dict]) -> None:
    """
    file_url 없는 regular 공고에 대해 두 단계로 파일 조회:
    1. e-발주 첨부파일 API 병렬 조회
    2. bfSpecRgstNo → 사전규격 문서 크로스레퍼런스 (최종 fallback)
    """
    # Build prespec file map keyed by bfSpecRgstNo
    prespec_file_map: dict[str, tuple[str, str]] = {}
    for item in prespec_items:
        spec_no = item.get("bfSpecRgstNo", "")
        if spec_no:
            url, label = _find_prespec_file(item)
            if url:
                prespec_file_map[spec_no] = (url, label or "규격문서")

    # Step 1: e-발주 parallel lookup
    tasks = []
    indices = []
    for i, bid in enumerate(results):
        if bid.source == "regular" and not bid.file_url and bid.bid_number:
            tasks.append(fetch_eorder_files(bid.bid_number))
            indices.append(i)

    if tasks:
        eorder_results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, files in zip(indices, eorder_results):
            if isinstance(files, list) and files:
                results[i].file_url = files[0][0]
                results[i].filename = files[0][1]

    # Step 2: bfSpecRgstNo cross-reference fallback
    for bid in results:
        if bid.source == "regular" and not bid.file_url and bid.prespec_reg_no:
            entry = prespec_file_map.get(bid.prespec_reg_no)
            if entry:
                bid.file_url, bid.filename = entry


async def search_bids_structured(keyword: str, days: int = 30) -> list[BidResult]:
    bid_task = search_bids(keyword, days)
    prespec_task = search_prespec(keyword, days)
    bids_raw, prespec_raw = await asyncio.gather(bid_task, prespec_task, return_exceptions=True)

    prespec_items = prespec_raw if isinstance(prespec_raw, list) else []

    results: list[BidResult] = []
    if isinstance(bids_raw, list):
        results.extend(_map_bid(item, "regular") for item in bids_raw)
    results.extend(_map_bid(item, "prespec") for item in prespec_items)

    await _fill_missing_files(results, prespec_items)
    return results
