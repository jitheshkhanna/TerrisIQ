"""Build Scope calculator + layout export. Checks the arithmetic and the export shapes;
the regulatory values themselves are indicative (see build_scope.py), so we assert the
structure and the cross-constraints, not that a specific FSI is legally correct."""
import pytest

from app.engines.build_scope import build_scope
from app.engines.build_scope_layout import plotted_layout, setback_envelope, to_dxf


def test_premium_fsi_grows_with_road_width():
    narrow = build_scope(1000, 8, "residential")      # below 9 m: no premium
    wide = build_scope(1000, 20, "residential")        # >= 18 m: full premium
    assert narrow["fsi"]["premium_added"] == 0.0
    assert wide["fsi"]["premium_added"] > 0.0
    assert wide["fsi"]["max_with_premium"] > narrow["fsi"]["max_with_premium"]


def test_built_up_area_follows_fsi():
    s = build_scope(1000, 20, "commercial")
    assert s["built_up_area_sqm"]["at_normal_fsi"] == pytest.approx(1000 * s["fsi"]["normal"])
    assert s["built_up_area_sqm"]["at_premium_fsi"] == pytest.approx(
        1000 * s["fsi"]["max_with_premium"])


def test_aai_net_height_is_pte_minus_ground():
    s = build_scope(1000, 20, "residential", pte_amsl_m=60.0, ground_elev_amsl_m=12.0)
    assert s["height"]["aai_net_permissible_agl_m"] == pytest.approx(48.0)
    assert s["height"]["net_permissible_m"] == pytest.approx(48.0)
    assert s["height"]["constrained_by"] == "aai_agl_m"


def test_net_height_takes_the_tightest_cap():
    s = build_scope(1000, 20, "residential", pte_amsl_m=60.0, ground_elev_amsl_m=12.0,
                    haca_cap_m=30.0)
    assert s["height"]["net_permissible_m"] == pytest.approx(30.0)  # HACA is tighter
    assert s["height"]["constrained_by"] == "haca_cap_m"


def test_high_rise_uses_allround_setback():
    low = build_scope(2000, 20, "residential", proposed_height_m=12.0)
    high = build_scope(2000, 20, "residential", proposed_height_m=60.0)
    assert low["setbacks"]["regime"] == "non-high-rise"
    assert high["setbacks"]["regime"] == "high-rise"
    assert high["setbacks"]["front_m"] == high["setbacks"]["rear_m"]  # all-around


def test_osr_threshold():
    small = build_scope(1000, 12, "residential")
    big = build_scope(5000, 12, "residential")
    assert small["osr"]["required"] is False
    assert big["osr"]["required"] is True
    assert big["osr"]["area_sqm"] == pytest.approx(500.0)  # 10% of 5000


def test_industrial_triggers_pcb_noc():
    s = build_scope(1000, 12, "industrial")
    pcb = [n for n in s["noc_checklist"] if "Pollution Control" in n["authority"]]
    assert pcb and pcb[0]["required"] is True


def test_flags_trigger_spatial_nocs():
    s = build_scope(1000, 12, "residential", flags={"near_coast": True})
    crz = [n for n in s["noc_checklist"] if "Coastal" in n["authority"]]
    assert crz and crz[0]["required"] is True


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        build_scope(0, 12, "residential")
    with pytest.raises(ValueError):
        build_scope(1000, 12, "castle")


def test_disclaimer_always_present():
    assert "Verify" in build_scope(1000, 12, "residential")["disclaimer"]


def test_setback_envelope_geojson():
    s = build_scope(900, 12, "residential")          # 30x30 square
    fc = setback_envelope(900, s["setbacks"])
    assert fc["type"] == "FeatureCollection"
    assert fc["buildable"] is True
    names = [f["properties"]["name"] for f in fc["features"]]
    assert "Plot boundary" in names and any("Buildable" in n for n in names)


def test_plotted_layout_and_dxf():
    fc = plotted_layout(4000, width_m=80, depth_m=50)
    assert fc["plot_count"] >= 1
    assert len(fc["schedule"]) == fc["plot_count"]
    dxf = to_dxf(fc)
    assert dxf.startswith("0\nSECTION") and dxf.rstrip().endswith("EOF")
    assert "POLYLINE" in dxf
