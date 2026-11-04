"""Request/response models for the public API."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# World bounds: coverage (India cities vs US) is decided by routing in the endpoint, which
# rejects an uncovered point with a list of what is covered. The model only guards against
# nonsense coordinates.
LAT_MIN, LAT_MAX = -90.0, 90.0
LNG_MIN, LNG_MAX = -180.0, 180.0


class RiskRequest(BaseModel):
    latitude: float = Field(..., ge=LAT_MIN, le=LAT_MAX)
    longitude: float = Field(..., ge=LNG_MIN, le=LNG_MAX)
    city: Optional[str] = Field(
        None, description="City slug. Inferred from the coordinates when omitted.")
    address: Optional[str] = Field(None, max_length=400,
                                   description="Optional label to echo back on the report")


class ScoreComponent(BaseModel):
    key: str
    points: float
    label: str


class RiskScore(BaseModel):
    score: int = Field(..., ge=0, le=100)
    grade: str
    band: str
    verdict: str = Field(..., description="Plain language, e.g. 'Low risk'")
    level: int = Field(..., ge=1, le=5, description="1 very low ... 5 very high")
    basis: Optional[str] = Field(
        None, description="What the score rests on, e.g. inundation_survey vs terrain_and_proxies")
    confidence: str = Field(..., description="high | medium | low - data coverage at this point")
    warnings: List[str] = []
    facts: List[Dict[str, str]] = Field(
        [], description="Five-word findings with a level: high|medium|low|good|info")
    components: List[ScoreComponent] = []
    details: Dict[str, Any] = {}


class Administrative(BaseModel):
    """GCC ward and zone, so a search in everyday language maps onto the nomenclature
    that patta records, GCC applications and CMWSSB connections are filed against."""
    ward: Optional[str] = None
    zone: Optional[str] = None
    zone_number: Optional[int] = None
    summary: str
    city: Optional[str] = None
    city_name: Optional[str] = None
    ward_number: Optional[str] = None
    ward_name: Optional[str] = None
    inside_gcc: bool = Field(..., description="Inside this city's corporation boundary")
    basis: Optional[str] = None
    ward_is_official: bool = Field(
        True, description="False where the boundary comes from OSM, not the corporation")
    nearest_zone: Optional[str] = None
    nearest_zone_m: Optional[int] = None
    note: Optional[str] = None


class CityInfo(BaseModel):
    slug: str
    name: str
    state: str
    corporation: str
    centre: Dict[str, float]
    bbox: Dict[str, float]
    depth: str = Field(..., description="deep | moderate | baseline - how much is known here")
    layers: List[str]
    scoreable_dimensions: List[str]
    ward_label: str
    zone_label: str
    notes: Dict[str, Any] = {}


class RiskResponse(BaseModel):
    city: CityInfo
    latitude: float
    longitude: float
    address: Optional[str] = None
    administrative: Administrative
    flood: RiskScore
    contamination: Optional[RiskScore] = Field(
        None, description="Null where the city maps no industrial or waste sources")
    scarcity: Optional[RiskScore] = Field(
        None, description="Null where the city publishes no groundwater evidence")
    composite_score: int = Field(..., ge=0, le=100)
    composite_grade: str
    composite_band: str
    verdict: str = Field(..., description="Plain-language headline, e.g. 'Low risk'")
    level: int = Field(..., ge=1, le=5)
    unadjusted_grade: str = Field(
        ..., description="Grade from the raw weighted formula, before the severity floor")
    grade_floor_applied: bool = False
    grade_floor_reason: Optional[str] = None
    evidence_ceiling_applied: bool = False
    evidence_ceiling_reason: Optional[str] = None
    severity_note: Optional[str] = None
    confidence: str
    summary: str
    weights: Dict[str, float] = Field(
        ..., description="Renormalised over the dimensions this city can actually score")
    base_weights: Dict[str, float]
    unavailable_dimensions: List[str] = []
    crz: Optional[Dict[str, Any]] = Field(
        None, description="Coastal Regulation Zone screening (distance-to-coast proxy); null inland")
    coverage_note: Optional[str] = None
    h3_cell: Optional[str] = None
    cached: bool = False
    generated_at: str
    disclaimer: str


class BuildScopeRequest(BaseModel):
    """Inputs for the Build Scope (TNCDBR) development-potential calculator. All pure
    arithmetic over user-supplied values — no parcel geometry or spatial data required."""
    plot_area_sqm: float = Field(..., gt=0, le=10_000_000,
                                 description="Plot area in square metres")
    road_width_m: float = Field(..., ge=0, le=200,
                                description="Abutting road width in metres (drives premium FSI)")
    use: str = Field("residential",
                     description="residential | commercial | mixed | industrial | "
                                 "institutional | plotted_layout")
    proposed_height_m: Optional[float] = Field(None, ge=0, le=1000)
    plot_width_m: Optional[float] = Field(None, gt=0, le=10000,
                                          description="Frontage, for the layout export")
    plot_depth_m: Optional[float] = Field(None, gt=0, le=10000,
                                          description="Depth, for the layout export")
    pte_amsl_m: Optional[float] = Field(
        None, description="AAI permissible top elevation (m AMSL), from AAI NOCAS")
    ground_elev_amsl_m: Optional[float] = Field(
        None, description="Ground elevation at the plot (m AMSL)")
    haca_cap_m: Optional[float] = Field(None, ge=0, le=1000,
                                        description="Hill Area Conservation Authority height cap")
    flags: Optional[Dict[str, bool]] = Field(
        None, description="Location-declared NOC triggers: near_coast, near_water_body, "
                          "near_storm_drain, near_monument, near_defence_airbase, "
                          "near_metro_or_rail")


class ReportRequest(RiskRequest):
    """A risk request that may also carry what the user built in the app — the Build Scope
    inputs and the title cross-check from their uploaded documents — so the PDF reflects the
    whole workspace, not just the location score. Both are optional; the location report
    renders without them."""
    build_scope: Optional[BuildScopeRequest] = None
    title_check: Optional[Dict[str, Any]] = Field(
        None, description="Title cross-verification summary derived from the user's uploads")


class GeocodeResult(BaseModel):
    label: str = Field(..., description="What the user searched for, e.g. '100 Feet Road'")
    context: str = Field("", description="Where it is, e.g. 'Velachery, Chennai 600042'")
    category: str = Field("Place", description="Locality / Street / Landmark / Station ...")
    latitude: float
    longitude: float
    type: Optional[str] = None


class GeocodeResponse(BaseModel):
    query: str
    expanded: Optional[str] = Field(
        None, description="The rewritten query, when local shorthand was expanded")
    source: str = "photon"
    results: List[GeocodeResult]
