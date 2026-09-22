"""Scoring constants.

Everything the three engines weigh lives here so the model can be tuned without
touching engine logic. Component caps are chosen so a parcel that trips every
sub-signal lands near 100 without any single signal dominating.
"""

# Composite weights (project brief).
WEIGHT_FLOOD = 0.45
WEIGHT_CONTAMINATION = 0.30
WEIGHT_SCARCITY = 0.25

GRADE_BANDS = [(20, "A", "Resilient"), (40, "B", "Low Risk"), (60, "C", "Moderate Risk"),
               (80, "D", "High Risk"), (100, "F", "Critical Vulnerability")]

# Single-dimension severity floor.
#
# The brief's weighted average can report a reassuring grade over a severe finding: a
# parcel inside a CPCB critically polluted cluster scoring 62 on contamination but low
# on flood and scarcity averages out to 38 - "Grade B, Low Risk". For a due diligence
# tool that is the wrong call, because these risks are not substitutes. A buyer cannot
# offset undrinkable groundwater against good drainage.
#
# The composite score itself is left exactly as the brief specifies. Only the headline
# grade is floored, and the response always reports the unadjusted grade alongside it.
GRADE_FLOOR_RULES = [
    (81, "D"),  # any dimension in F caps the headline at D
    (61, "C"),  # any dimension in D caps the headline at C
]
GRADE_SEVERITY = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}

# --- Flood -----------------------------------------------------------------
# A parcel is metres across, and the GCC inundation layer tiles the city with small
# gaps along roads, so strict point-in-polygon produces false negatives. We sample a
# parcel-scale window first, then a wider neighbourhood window at reduced weight.
PARCEL_WINDOW_M = 40
NEIGHBOURHOOD_WINDOW_M = 150
NEIGHBOURHOOD_DISCOUNT = 0.6

# Validated against the 53 GCC 2020 hotspots: "Very High" is 6.1% of the city's area
# but captures 35% of recorded hotspots (5.8x lift), decreasing monotonically down
# the scale. See scripts/validate_flood_layer.py.
FLOOD_ZONE_POINTS = {
    "Very High": 50.0,
    "High": 38.0,
    "Moderate": 25.0,
    "Low": 12.0,
    "Very Low": 4.0,
}

# Storm water drain access. Absence of a drain only counts against a parcel where the
# GCC drain network actually has coverage - outside it, missing data is not evidence.
DRAIN_NO_DRAIN_M = 500
DRAIN_FAR_M = 300
DRAIN_NEAR_M = 150
DRAIN_POINTS_NONE = 20.0
DRAIN_POINTS_FAR = 15.0
DRAIN_POINTS_MID = 8.0
DRAIN_BAD_CONDITION_POINTS = 5.0
DRAIN_UNCOVERED_M = 1500  # beyond this the SWD dataset simply does not map the area
DRAIN_CAP = 20.0

WATERBODY_VERY_NEAR_M = 150
WATERBODY_NEAR_M = 300
WATERBODY_MID_M = 500
WATERBODY_POINTS = (15.0, 8.0, 4.0)

# Relative elevation against a 250 m ring. A hollow collects its neighbours' runoff;
# a rise sheds it, so this component can subtract.
ELEVATION_BANDS = [(-2.0, 15.0), (-1.0, 10.0), (-0.5, 5.0), (1.5, 0.0), (99.0, -5.0)]

HOTSPOT_NEAR_M = 500
HOTSPOT_MID_M = 1000
HOTSPOT_POINTS = (10.0, 5.0)

# --- Contamination ---------------------------------------------------------
CLUSTER_LEVEL_POINTS = {
    "critically_polluted": 50.0,
    "severely_polluted": 38.0,
    "polluted": 28.0,
}
# Beyond a cluster's stated radius the score decays linearly to zero over this distance.
CLUSTER_DECAY_M = 2500.0

OSM_INDUSTRIAL_NEAR_M = 300
OSM_INDUSTRIAL_MID_M = 800
OSM_INDUSTRIAL_FAR_M = 1500
OSM_INDUSTRIAL_POINTS = (20.0, 12.0, 6.0)

DUMPSITE_CORE_POINTS = 35.0
DUMPSITE_DECAY_M = 1500.0
LANDFILL_OSM_NEAR_M = 1000
LANDFILL_OSM_POINTS = 10.0

# --- Scarcity --------------------------------------------------------------
FIRKA_POINTS = {
    "overexploited": 55.0,
    "critical": 42.0,
    "semi_critical": 28.0,
    "safe": 10.0,
}
# CGWB: 46 of 51 Chennai revenue blocks are overexploited and only 2 firkas are safe,
# so an unmatched parcel is far more likely stressed than not - but we mark it
# low-confidence rather than asserting a firka we do not have.
FIRKA_REGIONAL_DEFAULT = 45.0

GW_DEEP_M = 10.0
GW_MID_M = 8.0
GW_SHALLOW_M = 5.0
GW_DEPTH_POINTS = (20.0, 14.0, 8.0)

COAST_INTRUSION_INNER_M = 1000
COAST_INTRUSION_OUTER_M = 3000
COAST_INTRUSION_POINTS = (20.0, 12.0)

# Proxy for CMWSSB piped-supply reach: the GCC boundary. Outside it, households lean
# far harder on borewells and tankers. Labelled as a proxy wherever it is reported.
OUTSIDE_GCC_POINTS = 12.0


# --- Flood scoring where no inundation survey exists -------------------------------
#
# Only Chennai publishes graded inundation polygons, and they carry up to 50 of the 100
# flood points there. Everywhere else that signal simply does not exist, so the budget
# is redistributed across the evidence that does: recorded flooding points, mapped
# low-lying ground, terrain, and water proximity. Without this the ceiling for a
# genuinely dangerous plot in Mumbai would be about 60, and every city outside Chennai
# would look safer than it is purely because less is known about it.
NO_SURVEY_POINTS = {
    "low_lying": 42.0,        # BBMP-style mapped low-lying ground
    "hotspot_near": 26.0,     # within HOTSPOT_NEAR_M of recorded flooding
    "hotspot_mid": 13.0,
    "elevation_hollow": 26.0,  # >=2m below the 250m ring
    "elevation_dip": 17.0,     # >=1m below
    "elevation_slight": 8.0,   # >=0.5m below
    "elevation_rise": -6.0,    # clearly above its surroundings
    "water_very_near": 24.0,
    "water_near": 13.0,
    "water_mid": 6.0,
    "drain_cap": 16.0,
}
LOW_LYING_WINDOW_M = 60
