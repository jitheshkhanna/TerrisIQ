"""PDF due-diligence report endpoint."""
from fastapi import APIRouter
from fastapi.responses import Response

from app.api.cadastral import scope_from
from app.api.risk import assess_point
from app.models.schemas import ReportRequest, RiskRequest
from app.pdf.generator import build_report

router = APIRouter(prefix="/api/v1", tags=["report"])


def _build_scope(req):
    """Recompute the Build Scope envelope from the inputs the user had in the app, so the PDF
    matches the screen exactly. The report's own point fills in the Build Scope coordinates
    when absent, so jurisdiction and the airport NOC resolve. Returns None if absent or
    invalid — the report still renders."""
    b = getattr(req, "build_scope", None)
    if b is None:
        return None
    if b.latitude is None:
        b.latitude, b.longitude = req.latitude, req.longitude
    try:
        return scope_from(b)
    except ValueError:
        return None


def _filename(result):
    label = (result.get("address") or "parcel").split(",")[0]
    safe = "".join(ch if ch.isalnum() else "-" for ch in label).strip("-").lower() or "parcel"
    return "property-risk-%s-grade-%s.pdf" % (safe[:40], result["composite_grade"])


def _assess(req):
    return assess_point(req.latitude, req.longitude, req.address, getattr(req, "city", None))


@router.post("/report")
async def report(req: ReportRequest):
    result = _assess(req)
    pdf = build_report(result, build_scope=_build_scope(req), title_check=req.title_check)
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
