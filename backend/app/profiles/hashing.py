"""profile_hash (SPEC §4): 프로필 텍스트를 NFKC 정규화·공백 정리 후 sha256.

keywords는 추천 후보 검색에만 쓰이므로 해시에 넣지 않는다(§4 profiles). 같은 해시끼리만 점수·분석을
공유한다.
"""

import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_profile(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def profile_hash(text: str) -> str:
    return hashlib.sha256(normalize_profile(text).encode("utf-8")).hexdigest()
