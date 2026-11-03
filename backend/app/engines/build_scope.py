"""Build Scope — development-potential calculator (TNCDBR 2019/2024, indicative).

Pure deterministic math: given a plot area, the abutting road width, the intended use and
(optionally) airport/terrain height limits, it reports the buildable envelope — FSI (normal
vs premium), ground coverage, setbacks, OSR, parking, and the net permissible building
height — plus the NOC checklist that those numbers trigger.

WHY it lives here and not in a PostGIS service: none of this needs parcel geometry or
spatial data. It is rule arithmetic over a handful of user inputs, so it runs inside the
Vercel 250 MB serverless budget with zero new dependencies.

HONESTY: the Tamil Nadu Combined Development and Building Rules are a large, locality-specific
gazette (CMA vs non-CMA, use zone, building class, 2024 amendments). The values in `RULESET`
below are INDICATIVE defaults encoding the *structure* of TNCDBR 2019 so the engine is
transparent and correctable — they are not a substitute for the gazetted rules. Every result
carries its rule `basis` and a mandatory `disclaimer`: verify with the planning authority
(CMDA/DTCP/BDA/HMDA) before relying on it. Correct a value? Edit `RULESET`, not the logic.

The net height is the real cross-constraint from the blueprint:
    AGL = PTE - G            (AAI net permissible height above ground level)
    net_permissible = min(regulatory height cap, AAI AGL, HACA cap)
"""
from typing import Optional

# --- Indicative TNCDBR-2019-style ruleset (edit here to correct; see module docstring). ---

USES = ("residential", "commercial", "mixed", "industrial", "institutional", "plotted_layout")

# Normal FSI by use. TNCDBR 2019 broadly allows up to ~2.0 normal for most urban uses; these
# are indicative ceilings before the road-width premium is added.
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

# Maximum ground coverage (footprint / plot area) by use.
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
# buildings above ~18.3 m / stilt+4 floors as high-rise/"special").
_HIGH_RISE_M = 18.3

# Typical dwelling built-up area, for a rough unit count on residential/mixed plots.
_DWELLING_SQM = 90.0


def _premium_fsi(road_width_m: float) -> float:
    for min_w, add in _PREMIUM_FSI_BY_ROAD:
        if road_width_m >= min_w:
            return add
    return 0.0


def _setbacks(height_m: float, plot_area_sqm: float) -> dict:
    """Setbacks scale with building height. Non-high-rise uses a small front/rear/side set;
    high-rise uses a minimum all-around open space that grows with height (TNCDBR Table)."""
    if height_m <= _HIGH_RISE_M:
        # Indicative non-high-rise setbacks, nudged up a little for larger plots.
        front = 3.0 if plot_area_sqm < 300 else 4.5
        side = 1.5 if plot_area_sqm < 300 else 3.0
        rear = 3.0
        return {
            "regime": "non-high-rise",
            "front_m": front, "side1_m": side, "side2_m": side, "rear_m": rear,
            "basis": "TNCDBR non-high-rise setbacks (indicative; scales with plot size).",
        }
    # High-rise: minimum 7 m all around at the threshold, +1 m per ~6 m of extra height,
    # capped at 16 m — indicative of the TNCDBR high-rise open-space table.
    allround = min(16.0, 7.0 + max(0.0, (height_m - _HIGH_RISE_M)) / 6.0)
    allround = round(allround, 1)
    return {
        "regime": "high-rise",
        "front_m": allround, "side1_m": allround, "side2_m": allround, "rear_m": allround,
        "basis": "TNCDBR high-rise all-around open space (indicative; grows with height).",
    }


def _noc_checklist(use, height_m, net_height, flags) -> list:
    """The clearances these inputs trigger. Spatial NOCs (CRZ, lake/drain buffer, heritage,
    defence) depend on the parcel's location, which this pure-math engine does not have — so
    they are surfaced from user-declared `flags` and from height. Each item says why."""
    flags = flags or {}
    items = []

    def add(authority, needed, why):
        items.append({"authority": authority, "required": bool(needed), "reason": why})

    # Height-triggered clearances.
    add("AAI (Airports Authority of India) height NOC", height_m is not None and height_m > 0,
        "Any building of appreciable height near an airfield needs AAI NOCAS clearance; "
        "the net permissible height below is capped by it.")
    add("Fire & Rescue Services NOC", height_m is not None and height_m > _HIGH_RISE_M,
        "High-rise buildings (above ~18.3 m) require a fire services NOC.")
    # Location-declared triggers (set these flags from spatial checks when available).
    add("TNSCZMA / Coastal (CRZ) clearance", flags.get("near_coast"),
        "Plot declared within/near the Coastal Regulation Zone (see CRZ screening).")
    add("PWD/WRD Water Body NOC", flags.get("near_water_body") or flags.get("near_storm_drain"),
        "Plot declared near a lake, tank, poramboke or storm-water drain buffer.")
    add("ASI Heritage clearance", flags.get("near_monument"),
        "Plot declared within an ASI monument regulated/prohibited zone.")
    add("IAF / Defence clearance", flags.get("near_defence_airbase"),
        "Plot declared near a defence airbase caution zone.")
    add("Metro / Railway (CMRL / Rly) NOC", flags.get("near_metro_or_rail"),
        "Plot declared near a metro or railway alignment buffer.")
    if use == "industrial":
        add("TNPCB (Pollution Control Board) consent", True,
            "Industrial use requires consent to establish/operate from the state PCB.")
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
) -> dict:
    """Compute the indicative development envelope. See module docstring for the honesty note.

    pte_amsl_m / ground_elev_amsl_m: AAI permissible top elevation and the ground elevation,
    both in metres AMSL; their difference is the AAI net permissible height (AGL = PTE - G).
    haca_cap_m: a Hill Area Conservation Authority height cap, if one applies.
    flags: location-declared booleans for the NOC checklist (near_coast, near_water_body,
    near_storm_drain, near_monument, near_defence_airbase, near_metro_or_rail).
    """
    use = (use or "residential").strip().lower()
    if use not in USES:
        raise ValueError("use must be one of %s" % ", ".join(USES))
    if plot_area_sqm is None or plot_area_sqm <= 0:
        raise ValueError("plot_area_sqm must be positive")
    if road_width_m is None or road_width_m < 0:
        raise ValueError("road_width_m must be >= 0")

    normal_fsi = _NORMAL_FSI[use]
    premium_fsi = _premium_fsi(road_width_m)
    max_fsi = round(normal_fsi + premium_fsi, 3)
    coverage = _GROUND_COVERAGE[use]

    footprint_sqm = round(plot_area_sqm * coverage, 1)
    max_builtup_normal = round(plot_area_sqm * normal_fsi, 1)
    max_builtup_premium = round(plot_area_sqm * max_fsi, 1)

    # --- Height constraints ---------------------------------------------------------------
    aai_agl = None
    if pte_amsl_m is not None and ground_elev_amsl_m is not None:
        aai_agl = round(pte_amsl_m - ground_elev_amsl_m, 2)  # AGL = PTE - G

    # Regulatory height proxy: a non-high-rise plot can go to ~15 m; wider roads/FSI allow
    # high-rise. We do not invent a precise cap — we report what constrains it.
    caps = {}
    if aai_agl is not None:
        caps["aai_agl_m"] = aai_agl
    if haca_cap_m is not None:
        caps["haca_cap_m"] = haca_cap_m
    net_permissible = min(caps.values()) if caps else None

    height_for_setbacks = proposed_height_m if proposed_height_m else (
        net_permissible if net_permissible else 15.0)
    setbacks = _setbacks(height_for_setbacks, plot_area_sqm)

    # --- OSR ------------------------------------------------------------------------------
    osr_required = plot_area_sqm >= _OSR_THRESHOLD_SQM
    osr = {
        "required": osr_required,
        "area_sqm": round(plot_area_sqm * _OSR_FRACTION, 1) if osr_required else 0.0,
        "basis": "TNCDBR ~10%% of plot for developments over %d m² (else shelter fee)."
                 % int(_OSR_THRESHOLD_SQM),
    }

    # --- Parking & rough yield ------------------------------------------------------------
    builtup_for_parking = max_builtup_premium
    parking_spaces = int(round(_PARKING_PER_100SQM[use] * builtup_for_parking / 100.0))
    approx_units = None
    if use in ("residential", "mixed"):
        approx_units = int(max_builtup_premium // _DWELLING_SQM)

    return {
        "inputs": {
            "plot_area_sqm": plot_area_sqm, "road_width_m": road_width_m, "use": use,
            "proposed_height_m": proposed_height_m,
        },
        "fsi": {
            "normal": normal_fsi,
            "premium_added": premium_fsi,
            "max_with_premium": max_fsi,
            "basis": "Normal FSI by use + road-width premium FSI (TNCDBR 2019, indicative).",
        },
        "ground_coverage": {
            "fraction": coverage,
            "max_footprint_sqm": footprint_sqm,
            "basis": "Max ground coverage by use (indicative).",
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
            "basis": "AGL = PTE - G; net = min(regulatory cap, AAI AGL, HACA cap). Provide "
                     "PTE and ground elevation (m AMSL) from AAI NOCAS for the AAI cap.",
        },
        "yield": {"approx_dwelling_units": approx_units, "dwelling_sqm_assumed": _DWELLING_SQM
                  if approx_units is not None else None},
        "noc_checklist": _noc_checklist(use, proposed_height_m, net_permissible, flags),
        "disclaimer": (
            "Indicative development-potential ESTIMATE from TNCDBR-2019-style rules, not a "
            "sanctioned plan. FSI, setbacks, coverage, OSR, parking and height vary by "
            "locality, zone and the 2024 amendments. Verify with the planning authority "
            "(CMDA/DTCP/BDA/HMDA) and a licensed architect before relying on it."
        ),
    }
