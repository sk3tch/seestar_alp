"""Unit tests for the dawn-park safety guard (device/dawn_guard.py).

The guard forces a scope park at dawn so a night's schedule can never leave
the telescope tracking/exposing into daylight, even if the scheduler is stuck,
idle, or mid-mosaic. The *decision* logic lives in pure functions tested here;
the watchdog thread in seestar_device.py is thin glue over these.
"""

from datetime import datetime, time

from device.dawn_guard import (
    parse_local_time,
    should_park_for_dawn,
    sun_altitude_deg,
)


# --- parse_local_time ------------------------------------------------------


def test_parse_local_time_valid():
    assert parse_local_time("05:15") == time(5, 15)


def test_parse_local_time_empty_or_none_is_none():
    assert parse_local_time("") is None
    assert parse_local_time(None) is None


def test_parse_local_time_invalid_is_none():
    assert parse_local_time("notatime") is None
    assert parse_local_time("25:99") is None


# --- should_park_for_dawn: core decision -----------------------------------

NOW = datetime(2026, 6, 6, 4, 0, 0)  # 04:00 local, well before sunrise


def test_disabled_never_parks_even_if_sun_is_up():
    park, reason = should_park_for_dawn(
        enabled=False,
        armed=True,
        already_fired=False,
        now_local=NOW,
        sun_alt_deg=45.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=None,
    )
    assert park is False


def test_not_armed_never_parks():
    park, _ = should_park_for_dawn(
        enabled=True,
        armed=False,
        already_fired=False,
        now_local=NOW,
        sun_alt_deg=45.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=None,
    )
    assert park is False


def test_already_fired_does_not_fire_again():
    park, _ = should_park_for_dawn(
        enabled=True,
        armed=True,
        already_fired=True,
        now_local=NOW,
        sun_alt_deg=45.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=None,
    )
    assert park is False


def test_sun_below_threshold_does_not_park():
    park, _ = should_park_for_dawn(
        enabled=True,
        armed=True,
        already_fired=False,
        now_local=NOW,
        sun_alt_deg=-10.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=None,
    )
    assert park is False


def test_sun_at_or_above_threshold_parks():
    park, reason = should_park_for_dawn(
        enabled=True,
        armed=True,
        already_fired=False,
        now_local=NOW,
        sun_alt_deg=-2.0,  # exactly at threshold -> inclusive
        dawn_sun_alt_deg=-2.0,
        hard_local_time=None,
    )
    assert park is True
    assert "sun" in reason.lower()


def test_hard_time_forces_park_even_with_sun_down():
    # Sun still well below the altitude threshold, but the absolute fallback
    # time has passed -> park anyway (defends against a wrong location/clock).
    park, reason = should_park_for_dawn(
        enabled=True,
        armed=True,
        already_fired=False,
        now_local=datetime(2026, 6, 6, 5, 20, 0),
        sun_alt_deg=-30.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=time(5, 15),
    )
    assert park is True
    assert "time" in reason.lower()


def test_before_hard_time_with_sun_down_does_not_park():
    park, _ = should_park_for_dawn(
        enabled=True,
        armed=True,
        already_fired=False,
        now_local=datetime(2026, 6, 6, 5, 0, 0),
        sun_alt_deg=-30.0,
        dawn_sun_alt_deg=-2.0,
        hard_local_time=time(5, 15),
    )
    assert park is False


# --- sun_altitude_deg: authoritative astropy-backed calc -------------------

# San Jose-ish (the scope's reported location): lat 37.27, lon -121.98.
LAT, LON = 37.2661, -121.982


def test_sun_is_below_horizon_at_local_midnight():
    # 2026-06-06 ~00:30 PDT == 07:30 UTC -> deep night, sun well below horizon.
    alt = sun_altitude_deg(LAT, LON, datetime(2026, 6, 6, 7, 30, 0))
    assert alt < -10.0


def test_sun_is_high_at_local_noon():
    # 2026-06-06 ~12:30 PDT == 19:30 UTC -> near solar noon in June, sun high.
    alt = sun_altitude_deg(LAT, LON, datetime(2026, 6, 6, 19, 30, 0))
    assert alt > 60.0
