"""LLM 없이 tour_items 행을 엔티티 위키 마크다운으로 렌더하고 원자적으로 저장한다."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nadri.core.models.tour import TourItem
from nadri.core.tourapi import CONTENT_TYPES, KST

SOURCE_LABEL = "한국관광공사 TourAPI 4.0 (KorService2)"


def _yq(value: object) -> str:
    """YAML 안전 인용 — JSON 문자열은 YAML에서도 유효하고 한글을 그대로 둔다(tojson은 \\uXXXX로 바꿔 쓰지 않음)."""
    return json.dumps(value, ensure_ascii=False)


_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=False,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_env.filters["yq"] = _yq


def entity_path(content_type_id: int, contentid: str) -> str:
    """
    엔티티 페이지 상대 경로를 만든다.

    Args:
        content_type_id: 관광 유형 코드
        contentid: 관광지 ID

    Returns:
        'entity/{유형}/{contentid}.md'
    """
    return f"entity/{content_type_id}/{contentid}.md"


def render_entity(item: TourItem) -> str:
    """
    tour_items 행 하나를 엔티티 마크다운으로 렌더한다(LLM 없음, 같은 입력 → 같은 출력).

    Args:
        item: 관광 항목 ORM 객체(updated_at·as_of 포함)

    Returns:
        frontmatter + 본문 마크다운. 값이 없는 줄·빈 절은 출력하지 않는다
    """
    extra = item.extra or {}
    # 1) 기본 정보 줄 — 값이 있는 것만
    basics = [
        (label, value)
        for label, value in (
            ("주소", item.addr),
            ("전화", item.tel),
            ("이용시간", item.usetime),
            ("휴무일", item.restdate),
            ("이용요금", item.fee),
            ("홈페이지", extra.get("homepage")),
        )
        if value
    ]
    # 2) 추가 정보 줄 — intro 나머지 필드(키 정렬)와 info 항목(원래 순서)
    more = [(k, v) for k, v in sorted((extra.get("intro") or {}).items()) if v]
    more += [(row["name"], row["text"]) for row in extra.get("info") or [] if row.get("name") and row.get("text")]

    # 3) 시각은 KST 초 단위 ISO — 현재 시각을 쓰지 않아 결정적
    updated_at = item.updated_at.astimezone(KST).isoformat(timespec="seconds")
    return _env.get_template("entity.md.j2").render(
        item=item,
        extra=extra,
        basics=basics,
        more=more,
        source=SOURCE_LABEL,
        type_name=CONTENT_TYPES.get(item.content_type_id, str(item.content_type_id)),
        updated_at=updated_at,
    )


def content_hash(text: str) -> str:
    """
    페이지 내용 해시.

    Args:
        text: 페이지 전체 문자열

    Returns:
        UTF-8 바이트의 sha256 16진 문자열(64자)
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_page(wiki_dir: Path, rel_path: str, text: str) -> Path:
    """
    임시 파일에 쓰고 rename해 원자적으로 저장한다. 디렉터리는 자동 생성.

    Args:
        wiki_dir: 위키 최상위 폴더
        rel_path: entity_path 결과
        text: 페이지 내용

    Returns:
        저장한 파일 경로
    """
    # 1) 대상 폴더를 만든다
    target = wiki_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    # 2) 같은 폴더에 임시 파일로 쓴다(rename이 같은 파일시스템 안에서 원자적이도록)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        # 3) 기존 파일을 한 번에 교체한다
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target
