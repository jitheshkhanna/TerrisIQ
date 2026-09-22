"""PDF due-diligence report endpoint."""
from fastapi import APIRouter
from fastapi.responses import Response

from app.api.risk import resolve_city
from app.core.scoring import assess
from app.models.schemas import RiskRequest
from app.pdf.generator import build_report

router = APIRouter(prefix="/api/v1", tags=["report"])


def _filename(result):
    label = (result.get("address") or "parcel").split(",")[0]
    safe = "".join(ch if ch.isalnum() else "-" for ch in label).strip("-").lower() or "parcel"
    return "property-risk-%s-grade-%s.pdf" % (safe[:40], result["composite_grade"])


@router.post("/report")
async def report(req: RiskRequest):
    city = resolve_city(req.latitude, req.longitude, req.city)
    result = assess(city, req.latitude, req.longitude, req.address)
    pdf = build_report(result)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="%s"' % _filename(result)})


@router.get("/report")
async def report_get(latitude: float, longitude: float, address: str = None):
    req = RiskRequest(latitude=latitude, longitude=longitude, address=address)
    city = resolve_city(req.latitude, req.longitude, req.city)
    result = assess(city, req.latitude, req.longitude, req.address)
    pdf = build_report(result)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="%s"' % _filename(result)})
