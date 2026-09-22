"""Summer water scarcity risk (composite weight 0.25 where it can be scored at all).

This dimension is only honest in two cities:

* **Bengaluru** has 1,114 measured borewell depths. That is real evidence, and the score
  interpolates from the wells nearest the plot.
* **Chennai** has a curated locality table where exactly four entries carry a published
  CGWB/CMWSSB water level and the other sixty are inferred from the regional finding
  that 46 of 51 blocks are overexploited. The engine says which it used.

Everywhere else there is nothing, so the dimension is reported unavailable and dropped
from the composite rather than filled with a guess.
"""
import statistics

from app.core import config as cfg
from app.core.geo import get_store, point_utm
from app.engines.common import ScoreBuilder

# How far out we will look for wells, and how many we need before trusting a median.
WELL_RADIUS_M = 1500
WELL_RADIUS_WIDE_M = 3500
WELL_MIN_SAMPLE = 3


def _wells_component(sb, store, pt):
    """Bengaluru: interpolate from measured borewell depths near the plot."""
    layer = store.layer("groundwater")
    idxs = layer.within(pt, WELL_RADIUS_M)
    radius = WELL_RADIUS_M
    if len(idxs) < WELL_MIN_SAMPLE:
        idxs = layer.within(pt, WELL_RADIUS_WIDE_M)
        radius = WELL_RADIUS_WIDE_M
    depths = []
    for i in idxs:
        raw = layer.props[i].get("depth_in_m")
        try:
            depths.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not depths:
        sb.add("groundwater_block", cfg.FIRKA_REGIONAL_DEFAULT,
               "No measured borewell within %.1f km; city-wide baseline applied"
               % (WELL_RADIUS_WIDE_M / 1000.0), basis="no_wells_nearby")
        sb.fact("No well data nearby", "info")
        sb.warn("No measured borewell near this plot, so the reading falls back to a "
                "city-wide baseline. Ask neighbours what depth their borewell runs at.")
        sb.downgrade("low")
        return

    level = statistics.median(depths)
    if level >= cfg.GW_DEEP_M:
        classification, points = "overexploited", cfg.FIRKA_POINTS["overexploited"]
    elif level >= cfg.GW_MID_M:
        classification, points = "critical", cfg.FIRKA_POINTS["critical"]
    elif level >= cfg.GW_SHALLOW_M:
        classification, points = "semi_critical", cfg.FIRKA_POINTS["semi_critical"]
    else:
        classification, points = "safe", cfg.FIRKA_POINTS["safe"]

    sb.add("groundwater_block", points,
           "%d measured borewells within %.1f km; median depth %.1fm"
           % (len(depths), radius / 1000.0, level),
           basis="measured_wells", wells=len(depths), median_depth_m=round(level, 1),
           shallowest_m=round(min(depths), 1), deepest_m=round(max(depths), 1))

    if level >= cfg.GW_DEEP_M:
        sb.fact("Borewells ~%d m deep" % round(level), "high")
        sb.warn("Borewells around this plot run to a median of %.1fm. Expect to drill "
                "deep and still buy tanker water through summer." % level)
    elif level >= cfg.GW_MID_M:
        sb.fact("Borewells ~%d m deep" % round(level), "medium")
        sb.warn("Borewells around this plot average %.1fm deep, which tightens sharply "
                "between March and July." % level)
    if level < cfg.GW_SHALLOW_M:
        sb.fact("Shallow water table (~%d m)" % max(1, round(level)), "good")
    elif level < cfg.GW_MID_M:
        sb.fact("Borewells ~%d m deep" % round(level), "low")
    if radius == WELL_RADIUS_WIDE_M:
        sb.downgrade("medium")
    return level


def _firka_component(sb, store, pt):
    """Chennai: curated locality table, with provenance stated."""
    layer = store.layer("firkas")
    matched, matched_dist = None, None
    for i, geom in enumerate(layer.geoms_utm):
        props = layer.props[i]
        dist = geom.distance(pt)
        if dist <= float(props.get("radius_m") or 3000):
            if matched is None or dist < matched_dist:
                matched, matched_dist = props, dist

    if matched is None:
        idx, dist, props = layer.nearest_with_props(pt)
        sb.add("groundwater_block", cfg.FIRKA_REGIONAL_DEFAULT,
               "No local record; CGWB regional baseline applied (46 of 51 Chennai blocks "
               "are overexploited)", basis="regional_default")
        sb.fact("Likely overexploited groundwater", "medium")
        sb.warn("No local groundwater record covers this spot, so the score falls back "
                "to CGWB's regional finding. Treat this figure as a rough guide.")
        sb.downgrade("low")
        return None

    classification = matched.get("classification", "overexploited")
    points = cfg.FIRKA_POINTS.get(classification, cfg.FIRKA_REGIONAL_DEFAULT)
    provenance = matched.get("provenance")

    if provenance == "cgwb_cited":
        label = ("%s is classified '%s' in the CGWB/CMWSSB figures"
                 % (matched["firka"], classification.replace("_", "-")))
    else:
        label = ("%s: no local groundwater survey. Treated as '%s' from the CGWB regional "
                 "finding that 46 of Chennai's 51 blocks are overexploited"
                 % (matched["firka"], classification.replace("_", "-")))
    sb.add("groundwater_block", points, label,
           firka=matched["firka"], classification=classification, provenance=provenance,
           avg_gw_level_m=matched.get("avg_gw_level_m"))
    if provenance == "cgwb_regional":
        sb.downgrade("medium")

    if classification == "overexploited":
        if provenance == "cgwb_cited":
            sb.fact("Overexploited groundwater", "high")
            sb.warn("CGWB classes %s as overexploited. Borewell yields drop sharply from "
                    "March through July." % matched["firka"])
        else:
            sb.fact("Likely overexploited groundwater", "medium")
            sb.warn("No groundwater survey covers %s specifically. CGWB reports 46 of "
                    "Chennai's 51 blocks as overexploited, so expect borewell yields to "
                    "drop between March and July, and confirm with neighbours before you "
                    "rely on a well here." % matched["firka"])

    if classification == "safe":
        sb.fact("Safe groundwater block", "good")

    level = matched.get("avg_gw_level_m")
    if level is not None:
        deep, mid, shallow = cfg.GW_DEPTH_POINTS
        pts = deep if level >= cfg.GW_DEEP_M else mid if level >= cfg.GW_MID_M \
            else shallow if level >= cfg.GW_SHALLOW_M else 0.0
        sb.add("groundwater_level", pts,
               "Average groundwater level %.1fm below ground" % level,
               avg_gw_level_m=level)
        if level >= cfg.GW_DEEP_M:
            sb.fact("Water table %d m down" % round(level), "high")
            sb.warn("The water table averages %.1fm down. Households here sink deep "
                    "borewells and still buy tanker water." % level)
    return level


def _coast_component(sb, store, pt):
    layer = store.layer("coastline")
    if not len(layer):
        return
    idx, dist, _ = layer.nearest_with_props(pt)
    if idx is None:
        return
    inner, outer = cfg.COAST_INTRUSION_POINTS
    if dist < cfg.COAST_INTRUSION_INNER_M:
        pts = inner
        proximity = "The coast is right here." if dist < 1 else "The coast is %.0fm away." % dist
        sb.fact("Saltwater risk near coast", "medium")
        sb.warn("%s Shallow borewells along this belt turn saline, and it worsens as the "
                "water table drops through summer." % proximity)
    elif dist < cfg.COAST_INTRUSION_OUTER_M:
        pts = outer
        sb.fact("Coast %.1f km away" % (dist / 1000.0), "low")
        sb.warn("The coast is %.1f km away. Check the borewell water for salinity."
                % (dist / 1000.0))
    else:
        pts = 0.0
    sb.add("seawater_intrusion", pts,
           "Coastline is %.1f km away" % (dist / 1000.0), distance_to_coast_m=round(dist))


def _supply_component(sb, city, store, pt):
    """Proxy for piped-supply reach using the corporation boundary.

    No Indian water utility publishes machine-readable supply-zone boundaries, so the
    ward layer stands in: outside the corporation, households lean far harder on
    borewells and private tankers. Always reported as a proxy.
    """
    layer = store.layer("wards")
    if not len(layer):
        return
    idx, dist = layer.nearest(pt)
    if idx is None:
        return
    if dist > 1000:
        sb.add("piped_supply", cfg.OUTSIDE_GCC_POINTS,
               "Outside the %s boundary (%.1f km), likely beyond the piped network"
               % (city.corporation, dist / 1000.0),
               basis="proxy: corporation boundary")
        sb.fact("Likely no piped water", "medium")
        sb.warn("This plot lies outside %s limits, where piped supply thins out and "
                "households lean on tankers. Confirm the connection status with the "
                "water utility for this specific plot." % city.corporation)
        sb.downgrade("medium")
    else:
        sb.add("piped_supply", 0.0, "Inside the %s boundary" % city.corporation,
               basis="proxy: corporation boundary")


def calculate_scarcity_risk(city, lat, lng):
    """Returns None when the city has no groundwater evidence at all."""
    if "scarcity" not in city.scoreable_dimensions:
        return None
    store = get_store(city)
    pt = point_utm(city, lat, lng)
    sb = ScoreBuilder("scarcity")

    if store.has("groundwater"):
        _wells_component(sb, store, pt)
    else:
        _firka_component(sb, store, pt)

    _coast_component(sb, store, pt)
    _supply_component(sb, city, store, pt)
    if not sb.has_signal() and not sb.has_gap():
        sb.fact("No water stress signs", "good")
    return sb.build()
