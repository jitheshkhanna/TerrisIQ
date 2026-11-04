"""Build Scope — development-potential calculator (region-adaptive, indicative).

Pure deterministic math: given a plot area, the abutting road width, the intended use and
(optionally) airport/terrain height limits, it reports the buildable envelope — FSI/FAR,
ground coverage, setbacks, OSR, parking, the net permissible building height and the plot
area in the region's customary units — plus the NOC checklist those numbers trigger.

WHY it lives here and not in a PostGIS service: none of this needs parcel geometry or
spatial data. It is rule arithmetic over a handful of user inputs, so it runs inside the
Vercel 250 MB serverless budget with zero new dependencies.

HONESTY — and why it is region-adaptive. Floor-space rules are jurisdiction-specific and
large. Only **Tamil Nadu** has a bundled indicative ruleset here (the TNCDBR 2019 structure
in `RULESET`), and even that carries a verify-with-the-authority disclaimer. Everywhere else
the FSI/FAR is set by the local development-control rules (a state/city DCR in India, the
municipal zoning code in the US) and is NOT nationally fixed — so we do NOT invent it. For a
non-TN plot the engine computes everything that is universal or NBC-2016-generic (coverage,
setbacks, OSR, parking, the AGL height math, unit conversion) and asks for the plot's local
FSI/FAR (`fsi_override`) to size the floor area, rather than printing a Tamil Nadu number
over a Mumbai or Houston plot. Every result carries its rule `basis`, the governing
`jurisdiction`, and a mandatory `disclaimer`.

The net height is the real cross-constraint from the blueprint:
    AGL = PTE - G            (airport net permissible height above ground level)
    net_permissible = min(regulatory height cap, airport AGL, HACA cap)
"""
from typing import Optional

# --- Indicative TNCDBR-2019-style ruleset (edit here to correct; see module docstring). ---

USES = ("residential", "commercial", "mixed", "industrial", "institutional", "plotted_layout")

# Normal FSI by use. TNCDBR 2019 broadly allows up to ~2.0 normal for most urban uses; these
# are indicative ceilings before the road-width premium is added. Tamil Nadu only.
_NORMAL_FSI = {
    "residential": 1.5,
    "commercial": 2.0,
    "mixed": 2.0,
    "industrial": 1.5,
    "institutional": 1.5,
    "plotted_layout": 0.0,  # a plotted layout is subdivision, not vertical FSI
}

# Premium (purchasable) FSI added on top of normal, graded by abutting road width. TNCDBR
# 2019 ties premium FSI eligibility to road width; wider roads unlock more. Indicative bands.
_PREMIUM_FSI_BY_ROAD = (
    # (min_road_width_m, premium_fsi_added)
    (18.0, 1.0),
    (12.0, 0.75),
    (9.0, 0.5),
    (0.0, 0.0),   # below 9 m: no premium FSI
)

# Maximum ground coverage (footprint / plot area) by use. NBC-2016-style generic ceilings,
# used across jurisdictions as an indicative default (verify against the local code).
_GROUND_COVERAGE = {
    "residential": 0.65,
    "commercial": 0.70,
    "mixed": 0.65,
    "industrial": 0.60,
    "institutional": 0.55,
    "plotted_layout": 0.0,
}

# Open Space Reservation: fraction of plot reserved as communal open space, required above a
# plot-area threshold (TNCDBR ~10% for larger developments; smaller plots pay a shelter fee).
_OSR_FRACTION = 0.10
_OSR_THRESHOLD_SQM = 3000.0

# Parking: car equivalent spaces required per unit of built-up area, by use.
_PARKING_PER_100SQM = {
    "residential": 1.0,
    "commercial": 1.5,
    "mixed": 1.25,
    "industrial": 0.5,
    "institutional": 1.0,
    "plotted_layout": 0.0,
}

# High-rise threshold: above this height the all-around setback regime applies (TNCDBR treats
# buildings above ~18.3 m / stilt+4 floors as high-rise/"special"; NBC uses a similar ~15 m).
_HIGH_RISE_M = 18.3

# Typical dwelling built-up area, for a rough unit count on residential/mixed plots.
_DWELLING_SQM = 90.0

# --- Jurisdiction profiles: who sets the rules, and how FSI/FAR is obtained. --------------
# Only Tamil Nadu has a bundled indicative FSI table. Elsewhere FSI/FAR is genuinely local, so
# fsi_mode="local" means "use the user-supplied value or admit it is unset" — never guessed.
JURISDICTIONS = ("tamil_nadu", "india", "us")
_JURIS = {
    "tamil_nadu": {
        "label": "Tamil Nadu — TNCDBR 2019 (indicative)",
        "authority": "CMDA / DTCP",
        "height_authority": "AAI (Airports Authority of India) NOCAS",
        "fsi_term": "FSI",
        "fsi_mode": "tncdbr",
        "std": "TNCDBR 2019",
    },
    "india": {
        "label": "India — confirm the local State/City DCR (NBC 2016 baseline)",
        "authority": "your State/City Development Control Rules",
        "height_authority": "AAI (Airports Authority of India) NOCAS",
        "fsi_term": "FSI",
        "fsi_mode": "local",
        "std": "NBC 2016 (indicative)",
    },
    "us": {
        "label": "United States — confirm the local municipal zoning code",
        "authority": "the local municipal zoning ordinance",
        "height_authority": "FAA (14 CFR Part 77)",
        "fsi_term": "FAR",
        "fsi_mode": "local",
        "std": "local zoning (indicative)",
    },
}

# 1 square metre expressed in each customary plot unit. Cent and ground are South Indian;
# sq yd (gaj) is common in the north; acres and sq ft are near-universal.
_AREA_IN = {
    "sqm": 1.0,
    "sqft": 10.76391,
    "sq_yd": 1.19599,
    "cents": 0.0247105,   # 1 cent = 435.6 sqft = 40.4686 sqm
    "grounds": 0.0044850,  # 1 ground = 2400 sqft = 222.967 sqm (Chennai/TN)
    "acres": 0.000247105,
}


def area_in_units(plot_area_sqm: float) -> dict:
    """The plot area in every customary unit, so the UI can show cents / sq yd / acres / sqft."""
    return {u: round(plot_area_sqm * f, 3) for u, f in _AREA_IN.items()}


def _premium_fsi(road_width_m: float) -> float:
    for min_w, add in _PREMIUM_FSI_BY_ROAD:
        if road_width_m >= min_w:
            return add
    return 0.0


def _setbacks(height_m: float, plot_area_sqm: float, std: str) -> dict:
    """Setbacks scale with building height. Non-high-rise uses a small front/rear/side set;
    high-rise uses a minimum all-around open space that grows with height."""
    if height_m <= _HIGH_RISE_M:
        # Indicative non-high-rise setbacks, nudged up a little for larger plots.
        front = 3.0 if plot_area_sqm < 300 else 4.5
        side = 1.5 if plot_area_sqm < 300 else 3.0
        rear = 3.0
        return {
            "regime": "non-high-rise",
            "front_m": front, "side1_m": side, "side2_m": side, "rear_m": rear,
            "basis": "%s non-high-rise setbacks (indicative; scales with plot size)." % std,
        }
    # High-rise: minimum 7 m all around at the threshold, +1 m per ~6 m of extra height,
    # capped at 16 m — indicative of the high-rise open-space table.
    allround = min(16.0, 7.0 + max(0.0, (height_m - _HIGH_RISE_M)) / 6.0)
    allround = round(allround, 1)
    return {
        "regime": "high-rise",
        "front_m": allround, "side1_m": allround, "side2_m": allround, "rear_m": allround,
        "basis": "%s high-rise all-around open space (indicative; grows with height)." % std,
    }


def _noc_checklist(use, height_m, net_height, flags, height_authority, airport) -> list:
    """The clearances these inputs trigger. Spatial NOCs (CRZ, lake/drain buffer, heritage,
    defence) depend on the parcel's location, which this pure-math engine does not have — so
    they are surfaced from user-declared `flags` and from height. Each item says why.
    `airport`, when the caller resolved one from the point, names the real aerodrome."""
    flags = flags or {}
    items = []

    def add(authority, needed, why):
        items.append({"authority": authority, "required": bool(needed), "reason": why})

    # Height-triggered clearance, named to the real aerodrome when the point resolved one.
    if airport:
        add("%s height NOC" % height_authority, True,
            "Plot is within ~%d km of %s (%s). Any appreciable height needs an obstacle-"
            "surface clearance; the net permissible height below is capped by it."
            % (airport["funnel_km"], airport["name"], airport["kind"]))
    else:
        add("%s height NOC" % height_authority, height_m is not None and height_m > 0,
            "Any building of appreciable height near an airfield needs an obstacle-surface "
            "clearance; the net permissible height below is capped by it.")
    add("Fire & Rescue Services NOC", height_m is not None and height_m > _HIGH_RISE_M,
        "High-rise buildings (above ~18.3 m) require a fire services NOC.")
    # Defence airbase, from the located aerodrome or a user-declared flag.
    add("IAF / Defence clearance",
        flags.get("near_defence_airbase") or (airport and airport.get("kind") == "defence"),
        "Plot near a defence airbase caution zone (reduced height limits, slower NOC).")
    # Location-declared triggers (set these flags from spatial checks when available).
    add("Coastal (CRZ) clearance", flags.get("near_coast"),
        "Plot declared within/near the Coastal Regulation Zone (see CRZ screening).")
    add("Water Body NOC", flags.get("near_water_body") or flags.get("near_storm_drain"),
        "Plot declared near a lake, tank, poramboke or storm-water drain buffer.")
    add("Heritage clearance", flags.get("near_monument"),
        "Plot declared within a monument regulated/prohibited zone.")
    add("Metro / Railway NOC", flags.get("near_metro_or_rail"),
        "Plot declared near a metro or railway alignment buffer.")
    if use == "industrial":
        add("Pollution Control Board consent", True,
            "Industrial use requires consent to establish/operate from the state/EPA PCB.")
    return items


def build_scope(
    plot_area_sqm: float,
    road_width_m: float,
    use: str = "residential",
    proposed_height_m: Optional[float] = None,
    pte_amsl_m: Optional[float] = None,
    ground_elev_amsl_m: Optional[float] = None,
    haca_cap_m: Optional[float] = None,
    flags: Optional[dict] = None,
    jurisdiction: str = "tamil_nadu",
    fsi_override: Optional[float] = None,
    airport: Optional[dict] = None,
) -> dict:
    """Compute the indicative development envelope. See module docstring for the honesty note.

    jurisdiction: tamil_nadu (bundled TNCDBR table) | india (local DCR, NBC baseline) | us
        (local zoning / FAR). Outside Tamil Nadu the FSI/FAR is not invented.
    fsi_override: the plot's local FSI/FAR, from its DCR/zoning. Required to size the floor
        area outside Tamil Nadu; ignored in Tamil Nadu where the TNCDBR table applies.
    airport: {name, kind, distance_m, funnel_km} if the caller resolved an aerodrome from the
        point (see india_hazards.nearest_airport) — names the real obstacle authority.
    pte_amsl_m / ground_elev_amsl_m: airport permissible top elevation and ground elevation,
        both m AMSL; their difference is the net permissible height (AGL = PTE - G).
    haca_cap_m: a Hill Area Conservation Authority height cap, if one applies.
    flags: location-declared booleans for the NOC checklist (near_coast, near_water_body,
        near_storm_drain, near_monument, near_defence_airbase, near_metro_or_rail).
    """
    use = (use or "residential").strip().lower()
    if use not in USES:
        raise ValueError("use must be one of %s" % ", ".join(USES))
    jurisdiction = (jurisdiction or "tamil_nadu").strip().lower()
    if jurisdiction not in JURISDICTIONS:
        raise ValueError("jurisdiction must be one of %s" % ", ".join(JURISDICTIONS))
    if plot_area_sqm is None or plot_area_sqm <= 0:
        raise ValueError("plot_area_sqm must be positive")
    if road_width_m is None or road_width_m < 0:
        raise ValueError("road_width_m must be >= 0")

    prof = _JURIS[jurisdiction]
    fsi_term = prof["fsi_term"]

    # --- FSI / FAR: the only genuinely region-specific number; never guessed outside TN. ----
    if prof["fsi_mode"] == "tncdbr" and use != "plotted_layout":
        normal_fsi = _NORMAL_FSI[use]
        premium_fsi = _premium_fsi(road_width_m)
        max_fsi = round(normal_fsi + premium_fsi, 3)
        fsi_basis = "Normal FSI by use + road-width premium FSI (TNCDBR 2019, indicative)."
    elif prof["fsi_mode"] == "tncdbr":  # plotted_layout: subdivision, no vertical FSI
        normal_fsi = premium_fsi = max_fsi = 0.0
        fsi_basis = "A plotted layout is land subdivision, not vertical floor space."
    elif fsi_override is not None:
        if fsi_override <= 0:
            raise ValueError("fsi_override must be positive")
        normal_fsi = max_fsi = round(float(fsi_override), 3)
        premium_fsi = 0.0
        fsi_basis = "User-supplied local %s from %s." % (fsi_term, prof["authority"])
    else:
        normal_fsi = premium_fsi = max_fsi = None
        fsi_basis = ("%s is set by %s and is not nationally fixed — enter your plot's %s to "
                     "size the floor area." % (fsi_term, prof["authority"], fsi_term))

    coverage = _GROUND_COVERAGE[use]
    footprint_sqm = round(plot_area_sqm * coverage, 1)
    max_builtup_normal = round(plot_area_sqm * normal_fsi, 1) if normal_fsi is not None else None
    max_builtup_premium = round(plot_area_sqm * max_fsi, 1) if max_fsi is not None else None

    # --- Height constraints ---------------------------------------------------------------
    aai_agl = None
    if pte_amsl_m is not None and ground_elev_amsl_m is not None:
        aai_agl = round(pte_amsl_m - ground_elev_amsl_m, 2)  # AGL = PTE - G

    caps = {}
    if aai_agl is not None:
        caps["aai_agl_m"] = aai_agl
    if haca_cap_m is not None:
        caps["haca_cap_m"] = haca_cap_m
    net_permissible = min(caps.values()) if caps else None

    height_for_setbacks = proposed_height_m if proposed_height_m else (
        net_permissible if net_permissible else 15.0)
    setbacks = _setbacks(height_for_setbacks, plot_area_sqm, prof["std"])

    # --- OSR ------------------------------------------------------------------------------
    osr_required = plot_area_sqm >= _OSR_THRESHOLD_SQM
    osr = {
        "required": osr_required,
        "area_sqm": round(plot_area_sqm * _OSR_FRACTION, 1) if osr_required else 0.0,
        "basis": "~10%% of plot reserved as open space for developments over %d m² (else a "
                 "shelter fee); %s." % (int(_OSR_THRESHOLD_SQM), prof["std"]),
    }

    # --- Parking & rough yield ------------------------------------------------------------
    builtup_for_parking = max_builtup_premium
    parking_spaces = (int(round(_PARKING_PER_100SQM[use] * builtup_for_parking / 100.0))
                      if builtup_for_parking else None)
    approx_units = None
    if use in ("residential", "mixed") and max_builtup_premium:
        approx_units = int(max_builtup_premium // _DWELLING_SQM)

    return {
        "jurisdiction": {"code": jurisdiction, "label": prof["label"],
                         "authority": prof["authority"]},
        "inputs": {
            "plot_area_sqm": plot_area_sqm, "road_width_m": road_width_m, "use": use,
            "proposed_height_m": proposed_height_m, "fsi_override": fsi_override,
        },
        "area_in_units": area_in_units(plot_area_sqm),
        "fsi": {
            "term": fsi_term,
            "normal": normal_fsi,
            "premium_added": premium_fsi,
            "max_with_premium": max_fsi,
            "needs_local_value": max_fsi is None,
            "basis": fsi_basis,
        },
        "ground_coverage": {
            "fraction": coverage,
            "max_footprint_sqm": footprint_sqm,
            "basis": "Max ground coverage by use (%s)." % prof["std"],
        },
        "built_up_area_sqm": {
            "at_normal_fsi": max_builtup_normal,
            "at_premium_fsi": max_builtup_premium,
        },
        "setbacks": setbacks,
        "osr": osr,
        "parking": {
            "car_equivalent_spaces": parking_spaces,
            "basis": "%.2f car-equivalent spaces per 100 m² built-up (%s)."
                     % (_PARKING_PER_100SQM[use], use),
        },
        "height": {
            "aai_net_permissible_agl_m": aai_agl,
            "haca_cap_m": haca_cap_m,
            "net_permissible_m": net_permissible,
            "constrained_by": (min(caps, key=caps.get) if caps else None),
            "authority": prof["height_authority"],
            "basis": "AGL = PTE - G; net = min(regulatory cap, airport AGL, HACA cap). Provide "
                     "PTE and ground elevation (m AMSL) from %s for the airport cap."
                     % prof["height_authority"],
        },
        "yield": {"approx_dwelling_units": approx_units, "dwelling_sqm_assumed": _DWELLING_SQM
                  if approx_units is not None else None},
        "noc_checklist": _noc_checklist(use, proposed_height_m, net_permissible, flags,
                                        prof["height_authority"], airport),
        "disclaimer": (
            "Indicative development-potential ESTIMATE for %s, not a sanctioned plan. FSI/FAR, "
            "setbacks, coverage, OSR, parking and height vary by locality, zone and amendments. "
            "Verify with the planning authority (%s) and a licensed architect before relying "
            "on it." % (prof["label"], prof["authority"])
        ),
    }


if __name__ == "__main__":
    # Tamil Nadu: TNCDBR table applies, FSI computed from use + road.
    tn = build_scope(1000, 18, "residential", jurisdiction="tamil_nadu")
    assert tn["fsi"]["max_with_premium"] == 2.5, tn["fsi"]  # 1.5 normal + 1.0 premium
    assert tn["built_up_area_sqm"]["at_premium_fsi"] == 2500.0
    assert tn["jurisdiction"]["authority"] == "CMDA / DTCP"

    # Rest of India: FSI not invented — null and flagged until the user supplies the local DCR.
    mh = build_scope(1000, 18, "residential", jurisdiction="india")
    assert mh["fsi"]["max_with_premium"] is None and mh["fsi"]["needs_local_value"]
    assert mh["built_up_area_sqm"]["at_premium_fsi"] is None
    assert "AAI" in mh["height"]["authority"]
    # With the local FSI supplied, the floor area sizes up.
    mh2 = build_scope(1000, 18, "residential", jurisdiction="india", fsi_override=2.7)
    assert mh2["built_up_area_sqm"]["at_premium_fsi"] == 2700.0

    # US: FAR term, FAA height authority, zoning authority, FAR from the user.
    us = build_scope(10000, 18, "commercial", jurisdiction="us", fsi_override=3.0)
    assert us["fsi"]["term"] == "FAR" and us["fsi"]["max_with_premium"] == 3.0
    assert us["height"]["authority"].startswith("FAA")
    assert "zoning" in us["jurisdiction"]["authority"]

    # Units: 1000 sqm ≈ 24.71 cents ≈ 4.485 grounds ≈ 0.247 acres.
    u = area_in_units(1000.0)
    assert abs(u["cents"] - 24.711) < 0.05 and abs(u["grounds"] - 4.485) < 0.05, u

    # Located airport names the real aerodrome and forces the height NOC + defence flag.
    ap = {"name": "AFS Sulur", "kind": "defence", "distance_m": 4000, "funnel_km": 20}
    noc = build_scope(500, 12, "residential", jurisdiction="india", airport=ap)["noc_checklist"]
    assert any(n["required"] and "Sulur" in n["reason"] for n in noc), noc
    assert any(n["authority"].startswith("IAF") and n["required"] for n in noc)

    print("build_scope region-adaptive offline OK")
