"""TourAPI 응답 원본을 날짜별 불변 JSON 스냅샷으로 저장한다(FR-40)."""

import json
import re
from pathlib import Path

from nadri.core.tourapi import KST, TourApiResponse

# 파일명에 허용하는 문자 — 그 외(경로 구분자·공백·점 등)는 '_'로 바꿔 상위 폴더 탈출을 막는다
_UNSAFE_KEY = re.compile(r"[^0-9A-Za-z가-힣_-]")


def save_raw(raw_dir: Path, resp: TourApiResponse, key: str) -> Path:
    """
    응답 원본을 {raw_dir}/{KST 날짜}/{operation}/{key}.json 에 불변으로 저장하고 경로를 돌려준다.

    Args:
        raw_dir: raw 저장 최상위 폴더
        resp: TourAPI 응답(serviceKey 없는 params 포함)
        key: 목록은 '{지역}_{유형}_p{페이지}', 상세는 contentid

    Returns:
        새로 만든 파일 경로. 같은 이름이 있으면 '{key}.2.json', '{key}.3.json' … 순번 파일

    Side effects:
        파일을 새로 만든다(기존 파일은 덮어쓰지 않음).
    """
    # 1) 폴더: KST 기준 날짜 / 오퍼레이션
    day = resp.fetched_at.astimezone(KST).date().isoformat()
    folder = raw_dir / day / resp.operation
    folder.mkdir(parents=True, exist_ok=True)

    # 2) 저장 내용(한글 그대로)
    safe_key = _UNSAFE_KEY.sub("_", key)
    payload = json.dumps(
        {
            "operation": resp.operation,
            "params": resp.params,
            "fetched_at": resp.fetched_at.isoformat(),
            "body": resp.body,
        },
        ensure_ascii=False,
        indent=2,
    )

    # 3) 'x' 모드로 새 파일만 만든다 — 이미 있으면 순번을 올려 다시 시도
    n = 1
    while True:
        path = folder / (f"{safe_key}.json" if n == 1 else f"{safe_key}.{n}.json")
        try:
            with path.open("x", encoding="utf-8") as f:
                f.write(payload)
            return path
        except FileExistsError:
            n += 1
