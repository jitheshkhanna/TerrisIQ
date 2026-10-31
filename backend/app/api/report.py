"""PDF due-diligence report endpoint."""
from fastapi import APIRouter
from fastapi.responses import Response

from app.api.risk import resolve_city
from app.core.scoring import assess
from app.engines.us_flood import in_us, us_assess
from app.models.schemas import RiskRequest
from app.pdf.generator import build_report

router = APIRouter(prefix="/api/v1", tags=["report"])


def _filename(result):
    label = (result.get("address") or "parcel").split(",")[0]
    safe = "".join(ch if ch.isalnum() else "-" for ch in label).strip("-").lower() or "parcel"
    return "property-risk-%s-grade-%s.pdf" % (safe[:40], result["composite_grade"])


def _assess(req):
    if in_us(req.latitude, req.longitude):
        return us_assess(req.latitude, req.longitude, req.address)
    city = resolve_city(req.latitude, req.longitude, req.city)
    return assess(city, req.latitude, req.longitude, req.address)


@router.post("/report")
async def report(req: RiskRequest):
    result = _assess(req)
    pdf = build_report(result)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="%s"' % _filename(result)})


@router.get("/report")
async def report_get(latitude: float, longitude: float, address: str = None):
    result = _assess(RiskRequest(latitude=latitude, longitude=longitude, address=address))
    pdf = build_report(result)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="%s"' % _filename(result)})
