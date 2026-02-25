"""
Unit tests for the utils module.

Tests cover:
- parse_date_range() - date parsing with timezone offset support
- normalize_timezone() - timezone normalization

Run from project root:
    pytest apps/api/tests/test_utils.py -v

Or from apps/api directory:
    PYTHONPATH=../.. python3 -m pytest tests/test_utils.py -v
"""

from datetime import datetime, timedelta, timezone

# =============================================================================
# Replicate the utils module code for isolated testing
# =============================================================================


def parse_date_range(
    start_date: str | None,
    end_date: str | None,
    tz_offset_minutes: int = 0,
) -> tuple[datetime | None, datetime | None]:
    """
    Parse date range strings into timezone-aware datetime objects.

    The dates are interpreted in the user's local timezone (specified by
    tz_offset_minutes), then converted to UTC for database comparison.
    """
    offset = timedelta(minutes=tz_offset_minutes)

    start_dt = None
    if start_date:
        local_start = datetime.fromisoformat(start_date)
        start_dt = (local_start + offset).replace(tzinfo=timezone.utc)

    end_dt = None
    if end_date:
        local_end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
        end_dt = (local_end + offset).replace(tzinfo=timezone.utc)

    return start_dt, end_dt


def normalize_timezone(dt: datetime | None) -> datetime:
    """Normalize a datetime to be timezone-aware (UTC)."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# =============================================================================
# Tests for parse_date_range
# =============================================================================


class TestParseDateRangeNoOffset:
    """Tests for parse_date_range without timezone offset (UTC)."""

    def test_no_dates_returns_none(self):
        """When no dates provided, both should be None."""
        start_dt, end_dt = parse_date_range(None, None)
        assert start_dt is None
        assert end_dt is None

    def test_start_date_only(self):
        """Parsing only start date."""
        start_dt, end_dt = parse_date_range("2026-01-14", None)
        assert start_dt == datetime(2026, 1, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert end_dt is None

    def test_end_date_only(self):
        """Parsing only end date."""
        start_dt, end_dt = parse_date_range(None, "2026-01-14")
        assert start_dt is None
        assert end_dt == datetime(2026, 1, 14, 23, 59, 59, tzinfo=timezone.utc)

    def test_both_dates_utc(self):
        """Both dates with no offset (UTC)."""
        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-15")
        assert start_dt == datetime(2026, 1, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert end_dt == datetime(2026, 1, 15, 23, 59, 59, tzinfo=timezone.utc)

    def test_same_day_range(self):
        """Single day range (Today filter)."""
        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14")
        assert start_dt == datetime(2026, 1, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert end_dt == datetime(2026, 1, 14, 23, 59, 59, tzinfo=timezone.utc)


class TestParseDateRangeWithOffset:
    """Tests for parse_date_range with timezone offsets."""

    def test_ist_timezone_offset(self):
        """
        IST (UTC+5:30) - JavaScript returns -330 for getTimezoneOffset().

        When user selects Jan 14 in IST:
        - Local midnight (00:00 IST) = 18:30 UTC on Jan 13
        - Local end of day (23:59 IST) = 18:29 UTC on Jan 14
        """
        # IST is UTC+5:30, JS getTimezoneOffset returns -330
        tz_offset_minutes = -330

        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", tz_offset_minutes)

        # 00:00 IST = 00:00 - 5:30 = 18:30 UTC on previous day
        expected_start = datetime(2026, 1, 13, 18, 30, 0, tzinfo=timezone.utc)
        # 23:59 IST = 23:59 - 5:30 = 18:29 UTC on same day
        expected_end = datetime(2026, 1, 14, 18, 29, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start, f"Expected {expected_start}, got {start_dt}"
        assert end_dt == expected_end, f"Expected {expected_end}, got {end_dt}"

    def test_pst_timezone_offset(self):
        """
        PST (UTC-8) - JavaScript returns 480 for getTimezoneOffset().

        When user selects Jan 14 in PST:
        - Local midnight (00:00 PST) = 08:00 UTC on Jan 14
        - Local end of day (23:59 PST) = 07:59 UTC on Jan 15
        """
        # PST is UTC-8, JS getTimezoneOffset returns 480
        tz_offset_minutes = 480

        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", tz_offset_minutes)

        # 00:00 PST = 00:00 + 8:00 = 08:00 UTC on same day
        expected_start = datetime(2026, 1, 14, 8, 0, 0, tzinfo=timezone.utc)
        # 23:59 PST = 23:59 + 8:00 = 07:59 UTC on next day
        expected_end = datetime(2026, 1, 15, 7, 59, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start, f"Expected {expected_start}, got {start_dt}"
        assert end_dt == expected_end, f"Expected {expected_end}, got {end_dt}"

    def test_cet_timezone_offset(self):
        """
        CET (UTC+1) - JavaScript returns -60 for getTimezoneOffset().
        """
        # CET is UTC+1, JS getTimezoneOffset returns -60
        tz_offset_minutes = -60

        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", tz_offset_minutes)

        # 00:00 CET = 00:00 - 1:00 = 23:00 UTC on previous day
        expected_start = datetime(2026, 1, 13, 23, 0, 0, tzinfo=timezone.utc)
        # 23:59 CET = 23:59 - 1:00 = 22:59 UTC on same day
        expected_end = datetime(2026, 1, 14, 22, 59, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start, f"Expected {expected_start}, got {start_dt}"
        assert end_dt == expected_end, f"Expected {expected_end}, got {end_dt}"

    def test_jst_timezone_offset(self):
        """
        JST (UTC+9) - JavaScript returns -540 for getTimezoneOffset().
        """
        # JST is UTC+9, JS getTimezoneOffset returns -540
        tz_offset_minutes = -540

        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", tz_offset_minutes)

        # 00:00 JST = 00:00 - 9:00 = 15:00 UTC on previous day
        expected_start = datetime(2026, 1, 13, 15, 0, 0, tzinfo=timezone.utc)
        # 23:59 JST = 23:59 - 9:00 = 14:59 UTC on same day
        expected_end = datetime(2026, 1, 14, 14, 59, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start, f"Expected {expected_start}, got {start_dt}"
        assert end_dt == expected_end, f"Expected {expected_end}, got {end_dt}"

    def test_weekly_range_with_offset(self):
        """Weekly filter with IST timezone."""
        tz_offset_minutes = -330  # IST

        start_dt, end_dt = parse_date_range("2026-01-07", "2026-01-14", tz_offset_minutes)

        # Jan 7, 00:00 IST = Jan 6, 18:30 UTC
        expected_start = datetime(2026, 1, 6, 18, 30, 0, tzinfo=timezone.utc)
        # Jan 14, 23:59 IST = Jan 14, 18:29 UTC
        expected_end = datetime(2026, 1, 14, 18, 29, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start
        assert end_dt == expected_end


class TestParseDateRangeEdgeCases:
    """Edge case tests for parse_date_range."""

    def test_zero_offset_same_as_no_offset(self):
        """Zero offset should behave the same as no offset."""
        start1, end1 = parse_date_range("2026-01-14", "2026-01-14", 0)
        start2, end2 = parse_date_range("2026-01-14", "2026-01-14")

        assert start1 == start2
        assert end1 == end2

    def test_utc_timezone_offset(self):
        """UTC timezone (offset = 0)."""
        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", 0)

        assert start_dt == datetime(2026, 1, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert end_dt == datetime(2026, 1, 14, 23, 59, 59, tzinfo=timezone.utc)

    def test_half_hour_offset(self):
        """Test timezones with half-hour offsets (like IST, Nepal, etc.)."""
        # Nepal is UTC+5:45, JS returns -345
        tz_offset_minutes = -345

        start_dt, end_dt = parse_date_range("2026-01-14", "2026-01-14", tz_offset_minutes)

        # 00:00 NPT = 00:00 - 5:45 = 18:15 UTC on previous day
        expected_start = datetime(2026, 1, 13, 18, 15, 0, tzinfo=timezone.utc)
        # 23:59 NPT = 23:59 - 5:45 = 18:14 UTC on same day
        expected_end = datetime(2026, 1, 14, 18, 14, 59, tzinfo=timezone.utc)

        assert start_dt == expected_start
        assert end_dt == expected_end


# =============================================================================
# Tests for normalize_timezone
# =============================================================================


class TestNormalizeTimezone:
    """Tests for normalize_timezone function."""

    def test_none_returns_min_datetime(self):
        """None should return datetime.min with UTC timezone."""
        result = normalize_timezone(None)
        assert result == datetime.min.replace(tzinfo=timezone.utc)

    def test_naive_datetime_becomes_utc(self):
        """Naive datetime should get UTC timezone attached."""
        naive = datetime(2026, 1, 14, 12, 30, 0)
        result = normalize_timezone(naive)
        assert result == datetime(2026, 1, 14, 12, 30, 0, tzinfo=timezone.utc)

    def test_aware_datetime_unchanged(self):
        """Already timezone-aware datetime should be unchanged."""
        aware = datetime(2026, 1, 14, 12, 30, 0, tzinfo=timezone.utc)
        result = normalize_timezone(aware)
        assert result == aware
