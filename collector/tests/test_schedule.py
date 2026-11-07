from datetime import date

from collector.domain.schedule import full_scan_due

TODAY = date(2026, 11, 8)


def test_full_scan_is_due_when_never_run() -> None:
    assert full_scan_due(None, TODAY, interval_days=7)


def test_full_scan_waits_until_interval_passes() -> None:
    assert not full_scan_due(date(2026, 11, 2), TODAY, interval_days=7)


def test_full_scan_is_due_once_interval_passes() -> None:
    assert full_scan_due(date(2026, 11, 1), TODAY, interval_days=7)
