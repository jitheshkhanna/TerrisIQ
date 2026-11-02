"""Live waterlogging nowcast: a place's flood susceptibility x the rain falling on it now.

Turns the static flood score into a live signal ("waterlogging likely right now") without
any new per-place data: live rainfall comes from Open-Meteo (keyless, free, global), and the
susceptibility is the flood level we already computed. Powers the logistics route-risk and
real-estate "floods when it rains" use cases.
"""
import httpx

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

# Met rainfall-intensity bands, mm/hour.
_LIGHT, _MODERATE, _HEAVY = 0.2, 2.5, 7.5


def _intensity(mm_h):
    if mm_h >= _HEAVY:
        return "heavy"
    if mm_h >= _MODERATE:
        return "moderate"
    if mm_h >= _LIGHT:
        return "light"
    return "dry"


def _assess(rain_h, rain_3h, flood_level):
    """Combine live rain with flood susceptibility (1..5) into a status + one-line headline."""
    wet3h = rain_3h >= 5.0
    if rain_h < _LIGHT and not wet3h:
        return "clear", "Dry now. No active waterlogging."
    if flood_level >= 4 and (rain_h >= _HEAVY or wet3h):
        return "active", "Heavy rain over a high-flood area — waterlogging likely now."
    if flood_level >= 3 and rain_h >= _MODERATE:
        return "likely", "Rain over a flood-prone area — watch for waterlogging."
    return "watch", "Light rain now — low waterlogging risk here."


def waterlogging_now(lat, lng, flood_level=3, timeout=8.0):
    """Never raises: an Open-Meteo outage returns status 'unavailable', so the live strip
    simply hides rather than breaking the card."""
    params = {"latitude": lat, "longitude": lng,
              "current": "precipitation", "hourly": "precipitation",
              "past_hours": 3, "forecast_hours": 1, "timezone": "auto"}
    data = None
    for _ in range(2):
        try:
            resp = httpx.get(OPEN_METEO, params=params, timeout=timeout)
            body = resp.json()
            if isinstance(body, dict) and not body.get("error"):
                data = body
                break
        except Exception:
            continue
    if data is None:
        return {"status": "unavailable", "headline": None}

    current = data.get("current") or {}
    rain_h = float(current.get("precipitation") or 0.0)  # Open-Meteo: preceding-hour sum (mm)
    hourly = (data.get("hourly") or {}).get("precipitation") or []
    # past_hours=3 + forecast_hours=1 -> the last 3 entries before the final one are the past 3h.
    past3 = [float(v) for v in hourly[:-1][-3:] if v is not None] if hourly else []
    rain_3h = sum(past3)

    level = int(flood_level or 3)
    status, headline = _assess(rain_h, rain_3h, level)
    return {
        "status": status,            # clear | watch | likely | active | unavailable
        "headline": headline,
        "rain_mm_h": round(rain_h, 2),
        "rain_3h_mm": round(rain_3h, 2),
        "intensity": _intensity(rain_h),
        "observed_at": current.get("time"),
    }


if __name__ == "__main__":
    assert _assess(0, 0, 5)[0] == "clear"
    assert _assess(9, 0, 4)[0] == "active"
    assert _assess(3, 0, 3)[0] == "likely"
    assert _assess(1, 0, 2)[0] == "watch"
    assert _intensity(10) == "heavy" and _intensity(0) == "dry"
    print("nowcast logic OK")
    print(waterlogging_now(13.0959, 80.2871, 4))
