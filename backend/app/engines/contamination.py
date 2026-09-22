"""Groundwater contamination risk (composite weight 0.30)."""
from app.core import config as cfg
from app.core.geo import get_store, point_utm
from app.engines.common import ScoreBuilder


def _km(metres):
    """'850 m away' or '3.3 km away' - short enough for a chip."""
    if metres < 1000:
        return "%d m away" % int(round(metres, -1))
    return "%.1f km away" % (metres / 1000.0)


def _cluster_component(sb, store, pt):
    layer = store.layer("industrial_clusters")
    if not len(layer):
        # Only Chennai has a curated CPCB cluster table. Elsewhere the OSM industrial
        # footprint below carries this dimension on its own, which is weaker evidence:
        # it says an industrial site is there, not what it emits.
        sb.downgrade("medium")
        return

    best_points, best_record, best_dist = 0.0, None, None
    for i, geom in enumerate(layer.geoms_utm):
        props = layer.props[i]
        dist = geom.distance(pt)
        radius = float(props.get("radius_m") or 1500)
        base = cfg.CLUSTER_LEVEL_POINTS.get(props.get("pollution_level"), 20.0)
        if dist <= radius:
            points = base
        elif dist <= radius + cfg.CLUSTER_DECAY_M:
            points = base * (1.0 - (dist - radius) / cfg.CLUSTER_DECAY_M)
        else:
            continue
        if points > best_points:
            best_points, best_record, best_dist = points, props, dist

    if best_record is None:
        idx, dist, props = layer.nearest_with_props(pt)
        sb.add("industrial_cluster", 0.0,
               "No CPCB-flagged industrial cluster within range (nearest: %s, %.1f km)"
               % (props.get("name"), (dist or 0) / 1000.0),
               nearest_cluster=props.get("name"), distance_m=round(dist or 0))
        return

    name = best_record.get("name")
    cepi = best_record.get("cepi_score")
    inside = best_dist <= float(best_record.get("radius_m") or 1500)
    if cepi is not None:
        label = ("%s %s (CPCB CEPI %.1f, %s), %.0fm away"
                 % ("Inside" if inside else "Near", name, cepi,
                    best_record.get("pollution_level", "").replace("_", " "), best_dist))
    else:
        label = ("%s %s (%s; flagged locality, no published CEPI), %.0fm away"
                 % ("Inside" if inside else "Near", name,
                    best_record.get("pollution_level", "").replace("_", " "), best_dist))
        sb.downgrade("medium")

    sb.add("industrial_cluster", best_points, label,
           cluster=name, cepi_score=cepi,
           pollution_level=best_record.get("pollution_level"),
           provenance=best_record.get("provenance"),
           industries=best_record.get("sources"),
           note=best_record.get("note"),
           distance_m=round(best_dist), inside_radius=inside)

    if inside and best_record.get("pollution_level") == "critically_polluted":
        sb.fact("Inside critically polluted zone", "high")
        sb.warn("This plot sits inside %s, which CPCB classes as critically polluted. "
                "Test any borewell here for heavy metals in a laboratory before you "
                "drink, cook or bathe with it." % name)
    elif best_points >= 20:
        sb.fact("Polluting industry %s" % _km(best_dist), "medium")
        sb.warn("%s lies %.0fm away. Have the borewell water tested for heavy metals."
                % (name, best_dist))


def _osm_industrial_component(sb, store, pt):
    layer = store.layer("industrial")
    if not len(layer):
        return
    idx, dist, props = layer.nearest_with_props(pt)
    if idx is None:
        return
    near, mid, far = cfg.OSM_INDUSTRIAL_POINTS
    name = props.get("name") or "an unnamed industrial site"
    if dist < cfg.OSM_INDUSTRIAL_NEAR_M:
        pts = near
        # OSM says industry is there, not what it discharges, so this is a note rather
        # than a warning. A yellow dot beside a "Very low" reading read as a contradiction.
        sb.fact("Industrial site %s" % _km(dist), "low")
        sb.warn("%s, an industrial site, sits %.0fm away." % (name, dist))
    elif dist < cfg.OSM_INDUSTRIAL_MID_M:
        pts = mid
        sb.fact("Industrial site %s" % _km(dist), "low")
    elif dist < cfg.OSM_INDUSTRIAL_FAR_M:
        pts = far
        sb.fact("Industrial site %s" % _km(dist), "low")
    else:
        pts = 0.0
    sb.add("industrial_landuse", pts,
           "Nearest mapped industrial land use (%s) is %.0fm away" % (name, dist),
           name=name, distance_m=round(dist), source="OpenStreetMap landuse=industrial")


def _dumpsite_component(sb, store, pt):
    layer = store.layer("dumpsites")
    points, record, distance = 0.0, None, None
    for i, geom in enumerate(layer.geoms_utm):
        props = layer.props[i]
        dist = geom.distance(pt)
        radius = float(props.get("leachate_radius_m") or 2000)
        if dist <= radius:
            value = cfg.DUMPSITE_CORE_POINTS
        elif dist <= radius + cfg.DUMPSITE_DECAY_M:
            value = cfg.DUMPSITE_CORE_POINTS * (1.0 - (dist - radius) / cfg.DUMPSITE_DECAY_M)
        else:
            continue
        if value > points:
            points, record, distance = value, props, dist

    if record is not None:
        sb.add("dumpsite", points,
               "%.0fm from %s (leachate buffer %dm)"
               % (distance, record["name"], record["leachate_radius_m"]),
               name=record["name"], distance_m=round(distance),
               leachate_radius_m=record["leachate_radius_m"], note=record.get("note"))
        if points >= cfg.DUMPSITE_CORE_POINTS * 0.5:
            sb.fact("In dumpyard leachate zone", "high")
            sb.warn("%s leaks leachate into the shallow aquifer here, carrying heavy "
                    "metals and ammoniacal nitrogen with it." % record["name"])
        elif points >= 5:
            sb.fact("Dumpyard %s" % _km(distance), "low")
            sb.warn("%s lies %.1f km away, at the outer edge of its leachate buffer. It "
                    "adds little at this distance." % (record["name"], distance / 1000.0))
    else:
        layer_osm = store.layer("landfill")
        if len(layer_osm):
            idx, dist, props = layer_osm.nearest_with_props(pt)
            if idx is not None and dist < cfg.LANDFILL_OSM_NEAR_M:
                sb.add("dumpsite", cfg.LANDFILL_OSM_POINTS,
                       "Mapped waste site (%s) %.0fm away"
                       % (props.get("name") or "unnamed", dist),
                       name=props.get("name"), distance_m=round(dist),
                       source="OpenStreetMap landuse=landfill")
                sb.fact("Waste site %s" % _km(dist), "medium")
                sb.warn("A waste disposal site sits %.0fm away." % dist)


def calculate_contamination_risk(city, lat, lng):
    """Returns None where the city has no industrial or waste evidence at all.

    Scoring it zero instead would let a city with no mapped industry look cleaner than
    one that maps its industry honestly - the same trap the scarcity dimension avoids.
    """
    store = get_store(city)
    if not (store.has("industrial") or store.has("industrial_clusters")
            or store.has("landfill") or store.has("dumpsites")):
        return None
    pt = point_utm(city, lat, lng)
    sb = ScoreBuilder("contamination")
    _cluster_component(sb, store, pt)
    _osm_industrial_component(sb, store, pt)
    _dumpsite_component(sb, store, pt)
    if sb.score() == 0:
        sb.fact("No mapped polluters nearby", "good")
        sb.warn("No industrial or waste source is mapped nearby. That means nobody has "
                "recorded one, not that the water has been tested.")
    if not sb.has_signal():
        sb.fact("No major polluters nearby", "good")
    if not store.has("industrial_clusters"):
        sb.warn("%s has no published industrial pollution index, so this reading is "
                "based on where industry sits, not on what it discharges."
                % city.name)
    return sb.build()
