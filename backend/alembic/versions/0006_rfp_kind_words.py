"""첨부 구분 다시 매기기: 과업내용서·과업설명서·과업명세서·수행지침서도 rfp (2026-11-13)

일반공고 35,975건 중 11,717건이 '제안요청'·'과업지시' 이름의 첨부가 없어 요약에서 첨부를 하나도
읽지 않았다. 서식·설명회 안내(신청서·양식·설명회 등)는 뺀다.
새로 받는 공고는 g2b/mapper.file_kind가 같은 규칙으로 매긴다(띄어쓰기 무시).
데이터만 바꾼다(스키마 변경 없음). 요약 캐시는 source_hash가 바뀌어 자연히 새로 만들어진다.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLAT = "regexp_replace(name, '\\s', '', 'g')"
_NEW = "(과업내용|과업설명|과업명세|수행지침)"
_OLD = "(제안요청|과업지시)"
_NOT = "(신청서|서약서|확약서|위임장|양식|서식|설명회)"  # 과업설명회 참가신청서 등


def upgrade() -> None:
    op.execute(
        f"UPDATE bid_files SET kind = 'rfp' WHERE kind = 'other'"
        f" AND {_FLAT} ~ '{_NEW}' AND {_FLAT} !~ '{_NOT}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE bid_files SET kind = 'other' WHERE kind = 'rfp'"
        f" AND {_FLAT} ~ '{_NEW}' AND {_FLAT} !~ '{_OLD}'"
    )
