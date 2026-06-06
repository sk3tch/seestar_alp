"""Dawn-park safety guard.

Forces a telescope park at dawn so a night's schedule can never leave the
scope tracking or exposing into daylight -- even if the scheduler is stuck,
sitting idle after a firmware self-cancel, or grinding through a multi-hour
mosaic panel. The watchdog thread that drives this (in seestar_device.py) is
deliberately thin: all of the decision logic lives in the pure functions here
so it can be tested deterministically without hardware.

Two independent triggers, either of which parks:
  * sun altitude has climbed to/above ``dawn_sun_alt_deg`` (the primary,
    location-aware trigger), or
  * an absolute ``hard_local_time`` has passed (a belt-and-suspenders fallback
    that still fires if the location/clock is wrong and the sun calc is off).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional, Tuple


def parse_local_time(value: Optional[str]) -> Optional[time]:
    """Parse a ``"HH:MM"`` string into a ``time``; return ``None`` if unset/invalid."""
    if not value:
        return None
    try:
        hh, mm = str(value).strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


def should_park_for_dawn(
    *,
    enabled: bool,
    armed: bool,
    already_fired: bool,
    now_local: datetime,
    sun_alt_deg: float,
    dawn_sun_alt_deg: float,
    hard_local_time: Optional[time] = None,
) -> Tuple[bool, str]:
    """Decide whether the dawn guard should park the scope right now.

    Returns ``(park, reason)``. ``park`` is True only when the guard is enabled,
    armed (a schedule ran this session), has not already fired, and one of the
    dawn triggers is satisfied. ``reason`` is a human-readable explanation for
    logging/notifying when ``park`` is True (empty otherwise).
    """
    if not enabled or not armed or already_fired:
        return (False, "")

    if sun_alt_deg >= dawn_sun_alt_deg:
        return (
            True,
            f"sun altitude {sun_alt_deg:.1f}° ≥ dawn threshold {dawn_sun_alt_deg:.1f}°",
        )

    if hard_local_time is not None and now_local.time() >= hard_local_time:
        return (
            True,
            f"past hard park time {hard_local_time.strftime('%H:%M')}",
        )

    return (False, "")


def sun_altitude_deg(lat_deg: float, lon_deg: float, when_utc: datetime) -> float:
    """Sun altitude in degrees for a location at a UTC instant (astropy-backed).

    ``when_utc`` is interpreted as UTC. Imports are local so the module stays
    cheap to import and the pure decision logic above has no hard astropy
    dependency.
    """
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time

    location = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg)
    t = Time(when_utc, scale="utc")
    altaz = AltAz(obstime=t, location=location)
    return float(get_sun(t).transform_to(altaz).alt.to_value(u.deg))
