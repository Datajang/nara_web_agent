"""배포 파일 파서 (테스트 전용). systemd 유닛과 nginx 설정을 단순하게 읽는다."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"
API_PORT = 8010
VLLM_PORT = 8011


def unit(name: str) -> dict[str, dict[str, list[str]]]:
    """[섹션] → 키 → 값 목록 (같은 키 여러 번 허용, 줄 끝 \\ 이어 붙임)."""
    text = (DEPLOY / "systemd" / name).read_text().replace("\\\n", " ")
    out: dict[str, dict[str, list[str]]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            section = line.strip("[]")
            out.setdefault(section, {})
            continue
        key, _, value = line.partition("=")
        out[section].setdefault(key.strip(), []).append(" ".join(value.split()))
    return out


def one(u: dict[str, dict[str, list[str]]], section: str, key: str) -> str:
    values = u[section][key]
    assert len(values) == 1, (section, key, values)
    return values[0]


def nginx_locations(text: str) -> dict[str, str]:
    """location 이름 → 블록 본문 (중첩 없는 단순 설정 가정)."""
    return {
        m.group(1).strip(): m.group(2) for m in re.finditer(r"location\s+([^{]+)\{([^}]*)\}", text)
    }


def env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (DEPLOY / "nara.env.example").read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out
