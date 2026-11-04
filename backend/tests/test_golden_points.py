"""Golden points — one coordinate per coverage tier, asserting the *routing* and the
*honesty invariants*, not live API values. These are deterministic and offline: anything
that would hit FEMA / EPA / Overpass / Photon is mocked, because CI runs without network and
FEMA refuses non-US IPs. The point of each case is "this coordinate is handled by the right
engine and can never read as silently safe", which is exactly the nationwide guardrail.

    Mannadi, Chennai      13.0927, 80.2890   dense urban, surveyed city        -> DEEP
    Manali, Chennai       13.1667, 80.2667   industrial; CPCB CEPI cluster     -> CEPI match
    Rural Tamil Nadu      10.0311, 78.3392   no survey, TN jurisdiction        -> BASELINE (TN)
    Indore, MP            22.7196, 75.8577    no survey, non-TN India           -> BASELINE (india)
    Houston, TX           29.7604, -95.3698   US federal coverage              -> US (FEMA/EPA)
    Rural Ohio            40.3670, -82.9962   US, likely unmapped by FEMA       -> US + terrain fallback
"""
from app.api.cadastral import resolve_jurisdiction
from app.core.resolver import in_india
from app.engines import india_hazards, us_flood, universal
from app.engines.build_scope import build_scope
from app.engines.us_flood import in_us

MANNADI = (13.0927, 80.2890)
MANALI = (13.1667, 80.2667)
RURAL_TN = (10.0311, 78.3392)
INDORE = (22.7196, 75.8577)
HOUSTON = (29.7604, -95.3698)
RURAL_OHIO = (40.3670, -82.9962)
ALL = [MANNADI, MANALI, RURAL_TN, INDORE, HOUSTON, RURAL_OHIO]


def test_country_routing():
    for p in (MANNADI, MANALI, RURAL_TN, INDORE):
        assert in_india(*p) and not in_us(*p), p
    for p in (HOUSTON, RURAL_OHIO):
        assert in_us(*p) and not in_india(*p), p


def test_jurisdiction_routing():
    for p in (MANNADI, MANALI, RURAL_TN):
        assert resolve_jurisdiction(*p) == "tamil_nadu", p
    assert resolve_jurisdiction(*INDORE) == "india"
    assert resolve_jurisdiction(*HOUSTON) == "us"
    assert resolve_jurisdiction(*RURAL_OHIO) == "us"


def test_national_index_matches():
    # Manali sits inside the CPCB CEPI petrochemical cluster -> MODERATE contamination signal.
    assert india_hazards.nearest_cepi(*MANALI)["level"] == "critically_polluted"
    # Rural TN is far from any CEPI cluster -> no false contamination.
    assert india_hazards.nearest_cepi(*RURAL_TN) is None
    # CGWB regional groundwater category is known for these states.
    assert india_hazards.cgwb_status("Tamil Nadu") == "overexploited"
    assert india_hazards.cgwb_status("Madhya Pradesh") == "semi_critical"


def test_build_scope_region_adapts_per_point():
    # Tamil Nadu: the bundled TNCDBR table applies, FSI is computed.
    tn = build_scope(1000, 18, "residential",
                     jurisdiction=resolve_jurisdiction(*MANNADI))
    assert tn["fsi"]["max_with_premium"] is not None
    assert tn["jurisdiction"]["authority"] == "CMDA / DTCP"
    # Indore (non-TN India): FSI is NOT invented; null + flagged until a local value is given.
    mp = build_scope(1000, 18, "residential", jurisdiction=resolve_jurisdiction(*INDORE))
    assert mp["fsi"]["max_with_premium"] is None and mp["fsi"]["needs_local_value"]
    # Houston (US): FAR terminology + FAA height authority, FAR from the user.
    us = build_scope(4000, 20, "commercial", jurisdiction=resolve_jurisdiction(*HOUSTON),
                     fsi_override=3.0)
    assert us["fsi"]["term"] == "FAR" and us["height"]["authority"].startswith("FAA")


def test_us_fema_unavailable_never_reads_as_safe(monkeypatch):
    """The core US honesty guardrail: when FEMA has no usable mapping (unmapped county, as is
    common in rural Ohio, or the service is down), the point must be scored on the terrain
    baseline — never returned as grade A 'very low risk'."""
    monkeypatch.setattr(us_flood, "fema_flood",
                        lambda lat, lng, timeout=12.0:
                        us_flood._unmapped("FEMA flood service is unreachable right now"))
    monkeypatch.setattr(us_flood, "epa_contamination",
                        lambda lat, lng, timeout=4.5: None)
    # A terrain baseline that found a real low-lying signal (score 45), so we can prove the
    # composite follows the terrain, not the fake grade-A unmapped stub.
    monkeypatch.setattr(universal, "flood_baseline", lambda lat, lng: {
        "score": 45, "confidence": "low", "warnings": [], "components": [], "details": {},
        "facts": [{"text": "No flood survey here", "level": "info"}],
        "basis": "terrain_and_proxies"})

    r = us_flood.us_assess(*RURAL_OHIO)
    assert r["flood"]["basis"] == "terrain_and_proxies", r["flood"]["basis"]
    assert r["composite_grade"] != "A", r["composite_grade"]
    assert r["verdict"] != "Very low risk", r["verdict"]
    # The FEMA gap is surfaced, not hidden.
    assert any("FEMA" in w for w in r["flood"]["warnings"]), r["flood"]["warnings"]


def test_us_fema_mapped_zone_is_trusted(monkeypatch):
    """When FEMA DOES map the point, that graded zone is used as-is (no terrain override)."""
    monkeypatch.setattr(us_flood, "fema_flood", lambda lat, lng, timeout=12.0:
                        us_flood._score_from_attrs([{"FLD_ZONE": "AE"}]))
    monkeypatch.setattr(us_flood, "epa_contamination", lambda lat, lng, timeout=4.5: None)
    r = us_flood.us_assess(*HOUSTON)
    assert r["flood"]["basis"] == "fema_nfhl"
    assert r["flood"]["level"] == 4  # SFHA
