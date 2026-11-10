import re

TARGET_DOC_TOKENS = 5500

SECTION_RULES: list[tuple[str, int]] = [
    (r"사업\s*개요|추진\s*배경|사업\s*목적|과업\s*목적",        1800),
    (r"과업\s*(내용|범위|지시서)|수행\s*(내용|범위)|주요\s*업무", 1800),
    (r"기술\s*요구사항|기능\s*요구사항|구축\s*(내용|범위)",      1800),
    (r"자격\s*요건|참가\s*자격|제한\s*(사항|조건)",             600),
    (r"사업\s*기간|수행\s*기간|납품\s*기한|과업\s*기간",         400),
    (r"예산|사업\s*금액|계약\s*금액|추정\s*가격",               400),
    (r"평가\s*(기준|항목)|기술\s*평가",                         300),
    (r"제안서\s*작성|작성\s*요령",                              200),
    (r"별첨|붙임|첨부",                                         150),
]

SECTION_HEADER_RE = re.compile(
    r'^(?:\d{1,2}[\.\)]\s+|#{1,3}\s+|[IVX]+\.\s+)'
    r'[가-힣A-Za-z0-9\s]{2,30}$',
    re.MULTILINE,
)


def estimate_tokens(text: str) -> int:
    korean = sum(1 for c in text if '가' <= c <= '힣')
    other = len(text) - korean
    return int(korean * 1.5 + other * 0.3)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    chars, tokens = [], 0.0
    for c in text:
        t = 1.5 if '가' <= c <= '힣' else 0.3
        if tokens + t > max_tokens:
            break
        chars.append(c)
        tokens += t
    return "".join(chars)


def _truncate_at_paragraph(text: str, max_tokens: int) -> str:
    truncated = _truncate_to_tokens(text, max_tokens - 50)
    boundary = truncated.rfind("\n\n")
    if boundary > len(truncated) // 2:
        truncated = truncated[:boundary]
    return truncated + "\n\n[... 이하 내용 생략 (원문 길이 초과) ...]"


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_HEADER_RE.finditer(text))
    if not matches:
        return [("", text)]
    parts = []
    if matches[0].start() > 0:
        parts.append(("", text[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((m.group().strip(), text[m.end() : end]))
    return parts


def _get_section_budget(header: str) -> int:
    for pattern, budget in SECTION_RULES:
        if re.search(pattern, header):
            return budget
    return 300


def compress_document(raw_text: str) -> str:
    if estimate_tokens(raw_text) <= TARGET_DOC_TOKENS:
        return raw_text
    sections = _split_sections(raw_text)
    if len(sections) == 1 and sections[0][0] == "":
        return _truncate_at_paragraph(raw_text, TARGET_DOC_TOKENS)
    parts: list[str] = []
    remaining = TARGET_DOC_TOKENS
    for header, body in sections:
        budget = _get_section_budget(header)
        body_tokens = estimate_tokens(body)
        if body_tokens <= budget and body_tokens <= remaining:
            parts.append(f"{header}\n{body}".strip())
            remaining -= body_tokens
        elif remaining > 200:
            allowed = min(budget, remaining) - 50
            truncated = _truncate_to_tokens(body, allowed)
            parts.append(f"{header}\n{truncated}\n[... 이하 내용 생략 ...]".strip())
            remaining -= estimate_tokens(truncated)
        if remaining <= 200:
            break
    return "\n\n".join(parts)
