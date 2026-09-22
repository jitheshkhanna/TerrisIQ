"""Monsoon flood and water-stagnation risk (composite weight 0.45).

Two quite different models live here, because the data does:

* **Chennai** has a graded GCC inundation survey - 7,453 polygons validated against the
  53 recorded 2020 hotspots. That polygon carries most of the score.
* **Everywhere else** has no such survey. Bengaluru publishes low-lying areas and
  flood-prone points, Hyderabad publishes flooding points, and the rest have nothing but
  terrain and mapped water. The point budget shifts onto those signals rather than
  leaving the score artificially low, and confidence drops to say so.
"""
from app.core import config as cfg
from app.core.elevation import elevation_profile
from app.core.geo import get_store, point_utm
from app.engines.common import ScoreBuilder

SEVERITY = {"Very High": 5, "High": 4, "Moderate": 3, "Low": 2, "Very Low": 1}


def _dist(metres):
    if metres < 1000:
        return "%d m" % int(round(metres, -1))
    return "%.1f km" % (metres / 1000.0)


ZONE_FACT_LEVEL = {"Very High": "high", "High": "high", "Moderate": "medium",
                   "Low": "low", "Very Low": "good"}


def _worst_category(layer, pt, radius):
    cats = [layer.props[i].get("CATEGORY") for i in layer.within(pt, radius)]
    cats = [c for c in cats if c in SEVERITY]
    return max(cats, key=lambda c: SEVERITY[c]) if cats else None


def _survey_component(sb, store, pt):
    """Chennai's graded inundation polygons."""
    layer = store.layer("flood_zones")
    parcel_cat = _worst_category(layer, pt, cfg.PARCEL_WINDOW_M)
    if parcel_cat:
        sb.add("flood_zone", cfg.FLOOD_ZONE_POINTS[parcel_cat],
               "Inundation category at the parcel: %s" % parcel_cat,
               category=parcel_cat, basis="parcel")
        sb.fact("%s flood zone" % parcel_cat, ZONE_FACT_LEVEL[parcel_cat])
        if parcel_cat in ("Very High", "High"):
            sb.warn("The corporation maps this plot inside a '%s' inundation zone." % parcel_cat)
        return

    wide_cat = _worst_category(layer, pt, cfg.NEIGHBOURHOOD_WINDOW_M)
    if wide_cat:
        sb.add("flood_zone", cfg.FLOOD_ZONE_POINTS[wide_cat] * cfg.NEIGHBOURHOOD_DISCOUNT,
               "Nearest mapped inundation category within %dm: %s"
               % (cfg.NEIGHBOURHOOD_WINDOW_M, wide_cat),
               category=wide_cat, basis="neighbourhood")
        sb.fact("%s flood zone nearby" % wide_cat,
                "medium" if ZONE_FACT_LEVEL[wide_cat] == "high" else ZONE_FACT_LEVEL[wide_cat])
        sb.downgrade("medium")
        if wide_cat in ("Very High", "High"):
            sb.warn("A '%s' inundation zone starts within %dm of this plot."
                    % (wide_cat, cfg.NEIGHBOURHOOD_WINDOW_M))
        return

    idx, dist = layer.nearest(pt)
    if dist is not None and dist > 1000:
        sb.fact("Outside flood survey", "info")
        sb.warn("The flood survey stops %.1f km short of this plot. The score here rests "
                "on terrain and water distance alone." % (dist / 1000.0))
        sb.downgrade("low")
    else:
        sb.downgrade("medium")
    sb.details["flood_zone"] = {"category": None,
                                "nearest_zone_m": round(dist) if dist else None}


def _low_lying_component(sb, store, pt):
    """Mapped low-lying ground, which is the closest thing Bengaluru has to a survey."""
    layer = store.layer("low_lying")
    if not len(layer):
        return False
    hits = layer.within(pt, cfg.LOW_LYING_WINDOW_M)
    if hits:
        name = layer.props[hits[0]].get("name") or "a mapped low-lying area"
        sb.add("low_lying", cfg.NO_SURVEY_POINTS["low_lying"],
               "Inside mapped low-lying ground (%s)" % name, name=name)
        sb.fact("Mapped low-lying ground", "high")
        sb.warn("The corporation maps this plot as low-lying ground, which is where "
                "water collects first when it rains hard.")
        return True
    idx, dist = layer.nearest(pt)
    if idx is not None and dist is not None and dist < 400:
        sb.add("low_lying", cfg.NO_SURVEY_POINTS["low_lying"] * 0.35,
               "Mapped low-lying ground %.0fm away" % dist, distance_m=round(dist))
        return True
    return False


def _drain_component(sb, store, pt, has_survey):
    layer = store.layer("swd")
    if not len(layer):
        return
    idx, dist, props = layer.nearest_with_props(pt)
    if idx is None:
        return
    cap = cfg.DRAIN_CAP if has_survey else cfg.NO_SURVEY_POINTS["drain_cap"]

    if dist > cfg.DRAIN_UNCOVERED_M:
        sb.details["drainage"] = {"nearest_drain_m": round(dist), "coverage": "unmapped"}
        sb.fact("Drains not surveyed", "info")
        sb.warn("The drain network is not surveyed here. The nearest mapped drain is "
                "%.1f km away, so nobody has assessed the drainage on this plot."
                % (dist / 1000.0))
        sb.downgrade("medium")
        return

    if dist >= cfg.DRAIN_NO_DRAIN_M:
        pts, label = cap, "No surveyed storm water drain within %dm" % cfg.DRAIN_NO_DRAIN_M
    elif dist >= cfg.DRAIN_FAR_M:
        pts, label = cap * 0.75, "Nearest storm water drain is %.0fm away" % dist
    elif dist >= cfg.DRAIN_NEAR_M:
        pts, label = cap * 0.4, "Nearest storm water drain is %.0fm away" % dist
    else:
        pts, label = 0.0, "Storm water drain within %.0fm" % dist

    status = (props.get("STATUS") or "").strip().lower()
    penalty = cfg.DRAIN_BAD_CONDITION_POINTS if (status == "bad" and dist < cfg.DRAIN_NO_DRAIN_M) else 0.0
    if penalty:
        sb.fact("Nearest drain in bad condition", "medium")
        sb.warn("The corporation records the nearest storm water drain as in bad condition.")

    sb.add("drainage", pts + penalty, label, cap=cap,
           nearest_drain_m=round(dist), drain_type=props.get("DRAIN_TYPE"),
           drain_status=props.get("STATUS"))
    if dist >= cfg.DRAIN_NO_DRAIN_M:
        sb.fact("No drain within %d m" % cfg.DRAIN_NO_DRAIN_M, "high")
        sb.warn("No storm water drain within %dm. Expect water to stand for days after "
                "heavy rain." % cfg.DRAIN_NO_DRAIN_M)


def _waterbody_component(sb, store, pt, has_survey):
    layer = store.layer("waterbodies")
    if not len(layer):
        return
    idx, dist, props = layer.nearest_with_props(pt)
    if idx is None:
        return
    feature_type = props.get("waterway") or props.get("natural") or "water body"
    name = props.get("name") or "an unnamed %s" % feature_type

    if has_survey:
        near, mid, far = cfg.WATERBODY_POINTS
    else:
        near = cfg.NO_SURVEY_POINTS["water_very_near"]
        mid = cfg.NO_SURVEY_POINTS["water_near"]
        far = cfg.NO_SURVEY_POINTS["water_mid"]

    if dist < cfg.WATERBODY_VERY_NEAR_M:
        pts = near
        subject = name if props.get("name") else name.capitalize()
        proximity = ("This plot sits on the edge of %s." % name if dist < 1
                     else "%s runs %.0fm away." % (subject, dist))
        sb.fact("Water body %s away" % _dist(dist) if dist >= 1 else "On a water body's edge",
                "high" if dist < 50 else "medium")
        sb.warn("%s Expect backflow and bank overtopping when it rains hard." % proximity)
    elif dist < cfg.WATERBODY_NEAR_M:
        pts = mid
    elif dist < cfg.WATERBODY_MID_M:
        pts = far
    else:
        pts = 0.0
    sb.add("waterbody", pts, "Nearest water (%s) is %.0fm away" % (name, dist),
           nearest_waterbody_m=round(dist), name=name)


def _elevation_component(sb, lat, lng, has_survey):
    profile = elevation_profile(lat, lng)
    sb.details["elevation"] = profile
    if not profile.get("available") or profile.get("relative_m") is None:
        sb.warn("The elevation service did not answer, so terrain is missing from this score.")
        sb.downgrade("medium")
        return
    rel = profile["relative_m"]
    # Where a survey exists the local hollow is the useful signal; where none does, the
    # catchment ring is what separates a plot that water runs toward from one it runs
    # away from.
    wide = profile.get("relative_catchment_m")
    basin = wide if wide is not None else rel

    if has_survey:
        pts = 0.0
        for threshold, value in cfg.ELEVATION_BANDS:
            if rel <= threshold:
                pts = value
                break
    else:
        # Terrain is doing far more work when nobody has surveyed inundation.
        p = cfg.NO_SURVEY_POINTS
        if basin <= -4.0:
            pts = p["elevation_hollow"]
        elif basin <= -2.0:
            pts = p["elevation_dip"]
        elif basin <= -0.5:
            pts = p["elevation_slight"]
        elif basin >= 6.0:
            # Only a clear rise over the whole catchment earns a discount. A 2 m bump
            # inside 250 m is noise, and rewarding it discounted every Bengaluru plot.
            pts = p["elevation_rise"]
        else:
            pts = 0.0

    if has_survey and rel <= -1.0:
        sb.fact("%.1f m below surroundings" % abs(rel), "high" if rel <= -2.0 else "medium")
        sb.warn("The plot lies %.1fm below the land around it, so it collects the "
                "neighbourhood's runoff." % abs(rel))
    elif not has_survey and basin <= -2.0:
        sb.fact("%.1f m below catchment" % abs(basin), "high" if basin <= -4.0 else "medium")
        sb.warn("The plot sits %.1fm below the surrounding catchment, so rainfall from "
                "a wide area drains toward it." % abs(basin))

    label = ("Elevation %.0fm; %.1fm relative to surroundings"
             % (profile["elevation_m"], rel))
    if not has_survey and wide is not None:
        label = ("Elevation %.0fm; %+.1fm vs the 1 km catchment"
                 % (profile["elevation_m"], wide))
    if (has_survey and rel >= 1.5) or (not has_survey and wide is not None and basin >= 6.0):
        sb.fact("Sits on higher ground", "good")
    sb.add("elevation", pts, label, elevation_m=profile["elevation_m"],
           relative_m=rel, relative_catchment_m=wide)


def _hotspot_component(sb, store, pt, has_survey):
    layer = store.layer("flood_hotspots")
    if not len(layer):
        return
    idx, dist, props = layer.nearest_with_props(pt)
    if idx is None:
        return
    if has_survey:
        near, mid = cfg.HOTSPOT_POINTS
    else:
        near = cfg.NO_SURVEY_POINTS["hotspot_near"]
        mid = cfg.NO_SURVEY_POINTS["hotspot_mid"]
    name = props.get("name") or "a recorded flooding point"
    if dist < cfg.HOTSPOT_NEAR_M:
        pts = near
        sb.fact("Flooding recorded %s away" % _dist(dist), "high")
        sb.warn("The corporation has recorded flooding at '%s', %.0fm away." % (name, dist))
    elif dist < cfg.HOTSPOT_MID_M:
        pts = mid
    else:
        pts = 0.0
    sb.add("historical", pts,
           "Nearest recorded flooding point ('%s') is %.0fm away" % (name, dist),
           nearest_hotspot_m=round(dist), hotspot_name=name)


def _context(store, pt):
    layer = store.layer("flood_context")
    notes = []
    for i in layer.within(pt, 3000):
        props = layer.props[i]
        dist = layer.geoms_utm[i].distance(pt)
        if dist <= props.get("radius_m", 2000):
            notes.append({"locality": props["name"], "note": props["note"],
                          "distance_m": round(dist)})
    return notes


def calculate_flood_risk(city, lat, lng):
    store = get_store(city)
    pt = point_utm(city, lat, lng)
    sb = ScoreBuilder("flood")

    has_survey = store.has("flood_zones")
    if has_survey:
        _survey_component(sb, store, pt)
    else:
        found_low_lying = _low_lying_component(sb, store, pt)
        sb.downgrade("medium" if found_low_lying or store.has("flood_hotspots") else "low")
        sb.fact("No flood survey for %s" % city.name, "info")
        sb.warn("No graded flood survey is published for %s. This score comes from "
                "terrain, mapped water%s - it is a screening signal, not a survey."
                % (city.name,
                   ", recorded flooding and drains" if store.has("flood_hotspots")
                   else " and drains"))

    _drain_component(sb, store, pt, has_survey)
    _waterbody_component(sb, store, pt, has_survey)
    _elevation_component(sb, lat, lng, has_survey)
    _hotspot_component(sb, store, pt, has_survey)

    # Only reassure where a survey was actually checked. "No major flood signs" for a
    # Bellandur plot in a city nobody has surveyed would be the exact false comfort the
    # evidence ceiling exists to prevent.
    if has_survey and not sb.has_signal():
        sb.fact("No major flood signs", "good")
    result = sb.build()
    result["basis"] = "inundation_survey" if has_survey else "terrain_and_proxies"
    context = _context(store, pt)
    if context:
        result["details"]["locality_context"] = context
    return result
