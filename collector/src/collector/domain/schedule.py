"""수집 모드 일정. 외부 호출 없는 순수 함수다."""

from datetime import date, timedelta


def full_scan_due(last_full_scan_on: date | None, today: date, interval_days: int) -> bool:
    """마지막 전체 탐색에서 간격만큼 지났으면 참이다.

    예약 실행은 늦거나 빠지므로 특정 시각 대신 지난 날짜로 판단한다 (ADR-0013).
    """
    if last_full_scan_on is None:
        return True
    return today - last_full_scan_on >= timedelta(days=interval_days)
