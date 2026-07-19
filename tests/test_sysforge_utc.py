"""UTC storage / display helper tests."""

from datetime import datetime, timedelta, timezone

import pytest

from integrations.sysforge.db import utc


@pytest.mark.area_routes
def test_format_parse_storage_round_trip():
    original = datetime(2024, 12, 20, 17, 30, 0, tzinfo=timezone.utc)
    text = utc.format_storage(original)
    assert text == "2024-12-20 17:30:00"
    parsed = utc.parse_storage(text)
    assert parsed == original
    assert parsed.tzinfo == timezone.utc


@pytest.mark.area_routes
def test_parse_storage_naive_assumes_utc():
    parsed = utc.parse_storage("2024-06-15 08:00:00")
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 8


@pytest.mark.area_routes
def test_to_utc_naive_treated_as_local():
    naive = datetime(2024, 6, 15, 12, 0, 0)
    converted = utc.to_utc(naive)
    assert converted.tzinfo == timezone.utc
    # Round-trip through local wall clock
    local_tz = datetime.now().astimezone().tzinfo
    expected = naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
    assert converted == expected


@pytest.mark.area_routes
def test_to_local_shifts_by_offset():
    utc_dt = datetime(2024, 12, 20, 17, 30, 0, tzinfo=timezone.utc)
    local = utc.to_local(utc_dt)
    assert local.tzinfo is not None
    # Same instant
    assert local.astimezone(timezone.utc) == utc_dt


@pytest.mark.area_routes
def test_format_date_local():
    utc_dt = datetime(2024, 12, 20, 17, 30, 0, tzinfo=timezone.utc)
    local = utc.to_local(utc_dt)
    assert utc.format_date(utc_dt) == local.strftime("%m/%d/%Y")


@pytest.mark.area_routes
def test_format_relative_just_now():
    now = datetime.now(timezone.utc)
    assert utc.format_relative(now, now=now.astimezone()) == "Just now"


@pytest.mark.area_routes
def test_format_relative_hours_ago():
    now = datetime(2024, 12, 20, 18, 0, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=3)
    assert utc.format_relative(past, now=now.astimezone()) == "3 hours ago"


@pytest.mark.area_routes
def test_validate_utc_rejects_naive():
    with pytest.raises(ValueError, match="must be in UTC"):
        utc.validate_utc(datetime(2024, 1, 1, 12, 0, 0))
