"""langchain-teddynote(HWPLoader)는 필수 (사용자 결정, P4). docs/decisions/2026-11-11-p4-ops.md.

extractor는 HWPLoader import가 실패하면 조용히 olefile 방식(품질 낮음)으로 넘어간다.
langchain을 1.x로
올리면 teddynote 0.5.4가 `langchain.schema`를 못 찾아 그렇게 된다. 그 퇴행을 여기서 잡는다.
"""

import re
from pathlib import Path

import app.files.extractor as extractor

BACKEND = Path(__file__).resolve().parents[2]
ACCEPTED = BACKEND / "security" / "pip-audit-accepted.txt"


def test_hwp_loader_is_really_available():
    assert extractor.HAS_HWPLOADER, "langchain-teddynote HWPLoader import 실패: olefile로 떨어진다"


def test_app_uses_langchain_only_through_hwp_loader():
    """수용한 취약점은 langchain·langgraph의 다른 기능이다.

    앱이 그 기능을 쓰기 시작하면 다시 검토한다.
    """
    pattern = re.compile(r"^\s*(?:from|import)\s+(?:langchain|langgraph)\S*.*$", re.MULTILINE)
    users = {
        str(p.relative_to(BACKEND)): [m.group(0).strip() for m in pattern.finditer(p.read_text())]
        for p in (BACKEND / "app").rglob("*.py")
        if pattern.search(p.read_text())
    }
    assert users == {
        "app/files/extractor.py": [
            "from langchain_teddynote.document_loaders import HWPLoader",
        ]
    }


def test_accepted_vulns_each_have_package_and_reason():
    rows = [
        line.split("#", 1)
        for line in ACCEPTED.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert rows, "수용 목록이 비어 있으면 CI의 pip-audit가 그대로 실패한다"
    for row in rows:
        assert len(row) == 2 and row[1].strip(), row  # ID  # 패키지: 이유
        assert re.fullmatch(r"(PYSEC|GHSA|CVE)-[\w-]+", row[0].strip()), row
        assert row[1].strip().startswith(("langchain", "langgraph")), row
