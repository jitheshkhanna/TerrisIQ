"""Live waterlogging nowcast: a place's flood susceptibility x the rain falling on it now,
plus any official government alert active over it.

Live rainfall: Open-Meteo (keyless, free, global). Official alerts: NDMA Sachet CAP feed
(India, public domain). Both are cached briefly and degrade silently, so the live strip
is reliably present without hammering flaky upstreams. Powers the logistics route-risk and
real-estate "floods when it rains" use cases.
"""
import time

import httpx

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
NDMA_CAP = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"

# Met rainfall-intensity bands, mm/hour.
_LIGHT, _MODERATE, _HEAVY = 0.2, 2.5, 7.5

# Tiny in-process caches: Open-Meteo is flaky (~1/3 503s) and the CAP feed is national, so
# serve a recent reading rather than re-fetching on every card load.
_RAIN_TTL, _ALERT_TTL, _ALERT_FRESH_S = 8 * 60, 10 * 60, 6 * 3600
_rain_cache: dict = {}
_alert_cache: dict = {"at": 0.0, "items": []}


def _intensity(mm_h):
    if mm_h >= _HEAVY:
        return "heavy"
    if mm_h >= _MODERATE:
        return "moderate"
    if mm_h >= _LIGHT:
        return "light"
    return "dry"


def _assess(rain_h, rain_3h, flood_level):
    wet3h = rain_3h >= 5.0
    if rain_h < _LIGHT and not wet3h:
        return "clear", "Dry now. No active waterlogging."
    if flood_level >= 4 and (rain_h >= _HEAVY or wet3h):
        return "active", "Heavy rain over a high-flood area — waterlogging likely now."
    if flood_level >= 3 and rain_h >= _MODERATE:
        return "likely", "Rain over a flood-prone area — watch for waterlogging."
    return "watch", "Light rain now — low waterlogging risk here."


def _fetch_rain(lat, lng, timeout):
    """Open-Meteo current + past-3h precipitation, cached and retried past 503s. Returns
    (rain_mm_h, rain_3h_mm, observed_at) or None."""
    key = (round(lat, 2), round(lng, 2))
    hit = _rain_cache.get(key)
    if hit and time.time() - hit[0] < _RAIN_TTL:
        return hit[1]
    params = {"latitude": lat, "longitude": lng, "current": "precipitation",
              "hourly": "precipitation", "past_hours": 3, "forecast_hours": 1, "timezone": "auto"}
    for _ in range(3):
        try:
            body = httpx.get(OPEN_METEO, params=params, timeout=timeout).json()
            if isinstance(body, dict) and not body.get("error"):
                cur = body.get("current") or {}
                hourly = (body.get("hourly") or {}).get("precipitation") or []
                past3 = sum(float(v) for v in hourly[:-1][-3:] if v is not None) if hourly else 0.0
                out = (float(cur.get("precipitation") or 0.0), past3, cur.get("time"))
                _rain_cache[key] = (time.time(), out)
                return out
        except Exception:
            continue
    return hit[1] if hit else None  # serve a stale reading rather than nothing


def _cap_items(timeout):
    if time.time() - _alert_cache["at"] < _ALERT_TTL:
        return _alert_cache["items"]
    items = []
    try:
        import email.utils
        import xml.etree.ElementTree as ET
        xml = httpx.get(NDMA_CAP, timeout=timeout).text
        for it in ET.fromstring(xml).iter("item"):
            title = (it.findtext("title") or "").strip()
            pub = it.findtext("pubDate") or ""
            ts = email.utils.mktime_tz(email.utils.parsedate_tz(pub)) if pub else 0
            if title and time.time() - ts < _ALERT_FRESH_S:
                items.append({"title": title, "issuer": it.findtext("author") or "",
                              "category": it.findtext("category") or "", "ts": ts})
        _alert_cache.update(at=time.time(), items=items)
    except Exception:
        return _alert_cache["items"]  # keep the last good list on a feed hiccup
    return items


def _official_alert(region, timeout):
    """Most recent active NDMA/IMD alert whose title names the point's area. `region` is a
    comma-separated keyword string (e.g. 'Chennai,Tamil Nadu')."""
    keys = [k.strip().lower() for k in (region or "").split(",") if len(k.strip()) >= 4]
    if not keys:
        return None
    for it in sorted(_cap_items(timeout), key=lambda x: x["ts"], reverse=True):
        low = it["title"].lower()
        if any(k in low for k in keys):
            return {"title": it["title"][:200], "issuer": it["issuer"], "category": it["category"]}
    return None


def waterlogging_now(lat, lng, flood_level=3, region=None, timeout=8.0):
    """Live status. Never raises; an upstream outage returns status 'unavailable' so the
    strip hides rather than breaking the card."""
    rain = _fetch_rain(lat, lng, timeout)
    if rain is None:
        return {"status": "unavailable", "headline": None}
    rain_h, rain_3h, observed_at = rain
    level = int(flood_level or 3)
    status, headline = _assess(rain_h, rain_3h, level)

    alert = _official_alert(region, timeout) if region else None
    if alert:
        # An official warning outranks a quiet rain reading.
        if status in ("clear", "watch"):
            status = "likely"
        headline = alert["title"]

    return {
        "status": status, "headline": headline,
        "rain_mm_h": round(rain_h, 2), "rain_3h_mm": round(rain_3h, 2),
        "intensity": _intensity(rain_h), "observed_at": observed_at,
        "alert": alert,
    }


if __name__ == "__main__":
    assert _assess(0, 0, 5)[0] == "clear"
    assert _assess(9, 0, 4)[0] == "active"
    assert _assess(3, 0, 3)[0] == "likely"
    assert _intensity(10) == "heavy" and _intensity(0) == "dry"
    print("nowcast logic OK")
    print(waterlogging_now(13.0959, 80.2871, 4, region="Chennai,Tamil Nadu"))
