"""get_datetime 툴 — 현재 KST 날짜·요일과 '이번 주말'·'다음 주' 범위."""

from datetime import datetime, timedelta

from nadri.core.tourapi import KST

WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def datetime_info(now: datetime) -> dict:
    """
    tz-aware 시각을 KST로 바꿔 날짜·요일·이번 주말·다음 주 범위를 계산한다(순수 함수).

    이번 주말 = 오늘이 속한 주(월~일)의 토~일(일요일이면 어제~오늘). 다음 주 = 다음 월요일~일요일.

    Args:
        now: 시간대가 있는 시각

    Returns:
        {"now", "date", "weekday", "timezone", "this_weekend", "next_week", "source", "as_of"}

    Raises:
        ValueError: 시간대 없는(naive) 시각
    """
    # 1) 시간대 없는 시각은 어느 나라 시각인지 몰라 거부한다
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시간대가 있는 시각이 필요합니다")
    # 2) KST로 바꾸고 이번 주 월요일을 구한다
    local = now.astimezone(KST)
    today = local.date()
    monday = today - timedelta(days=today.weekday())
    # 3) 이번 주 토·일, 다음 주 월~일
    saturday, sunday = monday + timedelta(days=5), monday + timedelta(days=6)
    next_monday = monday + timedelta(days=7)
    return {
        "now": local.isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "weekday": WEEKDAYS[today.weekday()],
        "timezone": "Asia/Seoul",
        "this_weekend": {"start": saturday.isoformat(), "end": sunday.isoformat()},
        "next_week": {"start": next_monday.isoformat(), "end": (next_monday + timedelta(days=6)).isoformat()},
        "source": "시스템 시계",
        "as_of": today.isoformat(),
    }


async def get_datetime() -> dict:
    """현재 시각으로 datetime_info를 돌려준다(툴 진입점)."""
    return datetime_info(datetime.now(KST))
