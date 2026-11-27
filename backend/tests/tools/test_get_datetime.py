"""날짜 해석 단위테스트 (U-DT) — 고정 시각."""

from datetime import datetime, timezone

import pytest

from nadri.core.tourapi import KST
from nadri.tools.get_datetime import datetime_info


@pytest.mark.parametrize("now,weekday,weekend,next_week", [
    (datetime(2026, 11, 18, 14, 0, tzinfo=KST), "수요일", ("2026-11-21", "2026-11-22"), ("2026-11-23", "2026-11-29")),  # U-DT-1
    (datetime(2026, 11, 21, 9, 0, tzinfo=KST), "토요일", ("2026-11-21", "2026-11-22"), ("2026-11-23", "2026-11-29")),   # U-DT-2
    (datetime(2026, 11, 22, 23, 59, tzinfo=KST), "일요일", ("2026-11-21", "2026-11-22"), ("2026-11-23", "2026-11-29")),  # U-DT-3
    (datetime(2026, 11, 23, 0, 0, tzinfo=KST), "월요일", ("2026-11-28", "2026-11-29"), ("2026-11-30", "2026-12-06")),    # U-DT-4
    (datetime(2026, 12, 31, 12, 0, tzinfo=KST), "목요일", ("2027-01-02", "2027-01-03"), ("2027-01-04", "2027-01-10")),   # U-DT-5
])
def test_ranges(now, weekday, weekend, next_week):
    """U-DT-1~5: 요일·이번 주말·다음 주 범위."""
    info = datetime_info(now)
    assert info["weekday"] == weekday
    assert (info["this_weekend"]["start"], info["this_weekend"]["end"]) == weekend
    assert (info["next_week"]["start"], info["next_week"]["end"]) == next_week


def test_utc_converted_to_kst():
    """U-DT-6: UTC 11-20 15:30 → KST 11-21 토요일."""
    info = datetime_info(datetime(2026, 11, 20, 15, 30, tzinfo=timezone.utc))
    assert info["date"] == "2026-11-21" and info["weekday"] == "토요일"


def test_naive_rejected():
    """U-DT-7: 시간대 없는 시각 → ValueError."""
    with pytest.raises(ValueError):
        datetime_info(datetime(2026, 11, 21))


def test_output_format():
    """U-DT-8: +09:00, Asia/Seoul, source·as_of."""
    info = datetime_info(datetime(2026, 11, 21, 9, 0, tzinfo=KST))
    assert info["now"].endswith("+09:00") and info["timezone"] == "Asia/Seoul"
    assert info["source"] and info["as_of"] == "2026-11-21"
