"""Parcel risk assessment endpoints."""
from fastapi import APIRouter, HTTPException

from app.core import cities as city_registry
from app.core.resolver import in_india, resolve_region
from app.core.scoring import assess
from app.engines.nowcast import waterlogging_now
from app.engines.universal import assess_universal
from app.engines.us_flood import in_us, us_assess
from app.models.schemas import RiskRequest, RiskResponse

router = APIRouter(prefix="/api/v1", tags=["risk"])


@router.get("/nowcast")
def nowcast(lat: float, lng: float, flood_level: int = 3, region: str = None):
    """Live waterlogging signal: rain falling now x this place's flood susceptibility, plus
    any active official (NDMA/IMD) alert naming the point's `region`."""
    return waterlogging_now(lat, lng, flood_level, region)


def resolve_city(latitude, longitude, slug=None):
    """Pick the city for a request, and refuse rather than guess when it is far away."""
    if slug:
        city = city_registry.get(slug)
        if city is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown city '%s'. Covered: %s"
                       % (slug, ", ".join(sorted(city_registry.CITIES))))
        # A named city that does not contain the point would score the plot against
        # another city's layers and return a confident, meaningless number. Refuse, and
        # say which city the point is actually in.
        if not city.contains(latitude, longitude):
            actual = city_registry.find_by_point(latitude, longitude)
            if actual is not None:
                raise HTTPException(
                    status_code=422,
                    detail="That point is in %s, not %s. Retry with city='%s' or omit "
                           "the city to have it detected."
                           % (actual.name, city.name, actual.slug))
            raise HTTPException(
                status_code=422,
                detail="That point is outside %s and outside every other covered city."
                       % city.name)
        return city

    city = city_registry.find_by_point(latitude, longitude)
    if city is not None:
        return city

    nearest, _ = city_registry.nearest(latitude, longitude)
    raise HTTPException(
        status_code=422,
        detail="That point is not inside a covered city. Nearest covered city is %s. "
               "Covered: %s." % (nearest.name, ", ".join(c.name for c in city_registry.CITIES.values())))


def assess_point(latitude, longitude, address=None, slug=None):
    """Score any point: a surveyed city where one covers it, FEMA for the US, and the
    universal terrain+OSM baseline anywhere else in India. Only points outside both India
    and the US are refused. Used by the /risk endpoints and the PDF report alike."""
    if in_us(latitude, longitude):
        return us_assess(latitude, longitude, address)
    covered = city_registry.find_by_point(latitude, longitude)
    if slug:
        named = city_registry.get(slug)
        if named is not None and named.contains(latitude, longitude):
            covered = named
    if covered is not None:
        return assess(covered, latitude, longitude, address)
    if in_india(latitude, longitude):
        return assess_universal(latitude, longitude, address, resolve_region(latitude, longitude))
    nearest, _ = city_registry.nearest(latitude, longitude)
    raise HTTPException(
        status_code=422,
        detail="That point is outside our India and US coverage. Nearest covered city is %s."
               % nearest.name)


@router.get("/cities")
async def list_cities():
    """Every covered city and, honestly, how much is known about each."""
    return {
        "cities": [c.to_dict() for c in city_registry.CITIES.values()],
        "depth_meaning": {
            "deep": "A graded municipal flood survey exists and has been validated.",
            "moderate": "Recorded flooding points and drains, but no graded survey.",
            "baseline": "No municipal flood or groundwater survey. Terrain and "
                        "OpenStreetMap only.",
        },
    }


@router.post("/risk", response_model=RiskResponse)
async def assess_risk(req: RiskRequest):
    return assess_point(req.latitude, req.longitude, req.address, req.city)


@router.get("/risk", response_model=RiskResponse)
async def assess_risk_get(latitude: float, longitude: float,
                          address: str = None, city: str = None):
    return assess_point(latitude, longitude, address, city)
