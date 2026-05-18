import asyncio
import dataclasses
from typing import Optional
from nara_server.g2b_api import search_bids, search_prespec, is_bid_open


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


def _map_bid(item: dict, source: str) -> BidResult:
    return BidResult(
        bid_title=item.get("bidNtceNm") or item.get("prdctClsfcNoNm", ""),
        bid_number=item.get("bidNtceNo") or item.get("bfSpecRgstNo", ""),
        file_url=item.get("ntceSpecDocUrl1"),
        filename=item.get("ntceSpecFileNm1"),
        deadline=item.get("bidClseDt") or item.get("rcptDt", ""),
        budget=str(item.get("asignBdgtAmt") or item.get("estimatedAmt", "")),
        is_open=is_bid_open(item.get("bidClseDt") or item.get("rcptDt")),
        source=source,
    )


async def search_bids_structured(keyword: str, days: int = 30) -> list[BidResult]:
    bid_task = search_bids(keyword, days)
    prespec_task = search_prespec(keyword, days)
    bids_raw, prespec_raw = await asyncio.gather(bid_task, prespec_task, return_exceptions=True)

    results: list[BidResult] = []
    if isinstance(bids_raw, list):
        results.extend(_map_bid(item, "regular") for item in bids_raw)
    if isinstance(prespec_raw, list):
        results.extend(_map_bid(item, "prespec") for item in prespec_raw)
    return results
