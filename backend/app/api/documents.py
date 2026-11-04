"""Consented cadastral document parsing (Patta / Chitta / EC / FMB), serverless.

A user uploads a scan of their own land document; we extract the structured fields that feed
the title checks. Two layers, both inside the Vercel budget:
  1. `pypdf` pulls any embedded text layer (born-digital PDFs) with zero external calls.
  2. If the user CONSENTS and a Gemini key is set, the file is sent to the Gemini vision model
     for structured field extraction — this is what reads scanned images and Tamil text that
     have no text layer. Heavy on-box OCR (LayoutLMv3/Donut) is Phase B (GPU); this is the
     serverless stand-in that works today.

PRIVACY (see CLAUDE.md §2.5): the document holds personal data. The Gemini path runs ONLY on
explicit `consent=true`, is disclosed to the user, and document contents are never logged or
echoed beyond the fields the user asked us to extract. The request carries base64 content, so
we need no `python-multipart` dependency.
"""
import base64
import binascii
import io
import json
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/cadastral", tags=["cadastral"])

_MAX_BYTES = 8 * 1024 * 1024  # 8 MB — comfortably within serverless + Gemini inline limits.
# Accepted document types by region. Tamil Nadu + pan-India land records and US title docs.
_DOC_TYPES = ("patta", "chitta", "tslr", "ec", "sale_deed", "fmb",   # Tamil Nadu
              "7_12", "ekhata",                                       # pan-India
              "deed", "alta", "plat", "fema_elevation",               # United States
              "other")
# US title documents read against a grantor/grantee + APN model, not Patta/survey-number.
_US_DOC_TYPES = frozenset(("deed", "alta", "plat", "fema_elevation"))

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
              % GEMINI_MODEL)

_KEYS = (
    "district, taluk, village, survey_number, sub_division, old_survey_numbers (array), "
    "owner_names (array), document_number, execution_date, transaction_value_inr, mortgages "
    "(array of {created, released}), boundaries ({north, south, east, west}), language"
)
_EXTRACT_PROMPT_IN = (
    "You are extracting fields from an Indian land document (Patta/Chitta/TSLR/Encumbrance "
    "Certificate/Sale Deed/FMB/7-12 extract/e-Khata), which may be in Tamil, Marathi, Kannada "
    "and/or English. Return ONLY a JSON object with these keys (use null when a field is not "
    "present; never guess): " + _KEYS + ". Extract strictly from the document."
)
# Same JSON shape, mapped to US title vocabulary so the generic schema still fits: the APN /
# parcel number -> survey_number, grantor+grantee -> owner_names, recorded liens -> mortgages,
# the instrument/recording number -> document_number, the sale price -> transaction_value_inr.
_EXTRACT_PROMPT_US = (
    "You are extracting fields from a US real-property title document (Deed / ALTA survey / "
    "Plat / FEMA Elevation Certificate). Return ONLY a JSON object with these keys (use null "
    "when a field is not present; never guess): " + _KEYS + ". Map US terms to this schema: "
    "put the APN or parcel number in survey_number, the grantor and grantee (or owner) names "
    "in owner_names, the county/state in district/village, recorded liens or mortgages in "
    "mortgages, the recording/instrument number in document_number, and the sale price in "
    "transaction_value_inr. Extract strictly from the document."
)


def _prompt_for(doc_type: str) -> str:
    return _EXTRACT_PROMPT_US if doc_type in _US_DOC_TYPES else _EXTRACT_PROMPT_IN


class DocParseRequest(BaseModel):
    filename: str = Field(..., max_length=255)
    content_base64: str = Field(..., description="Base64 of the file bytes (PDF or image)")
    doc_type: str = Field("other", description=" | ".join(_DOC_TYPES))
    mime_type: str = Field("application/pdf")
    consent: bool = Field(False, description="Must be true to send the document to the "
                                             "vision parser; see privacy note.")


def _pdf_text(data: bytes) -> str:
    """Embedded text layer only (born-digital PDFs); empty for scanned images."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages[:20]]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(pages)).strip()
    except Exception:  # noqa: BLE001 - a malformed PDF must not 500 the endpoint
        return ""


def _gemini_fields(data: bytes, mime_type: str, doc_type: str = "other") -> Optional[dict]:
    """Structured extraction via Gemini vision. Returns the parsed dict, or None on any
    failure (so the endpoint still returns the pypdf text). The prompt adapts to the
    document's region so US title docs map to the same schema as Indian land records."""
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime_type,
                             "data": base64.b64encode(data).decode("ascii")}},
            {"text": _prompt_for(doc_type)},
        ]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json",
                             "maxOutputTokens": 1200},
    }
    try:
        resp = httpx.post(GEMINI_URL, json=payload, timeout=45.0,
                          headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"})
        if resp.status_code >= 400:
            return None
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        return json.loads(text) if text else None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


@router.post("/upload-documents")
def upload_documents(req: DocParseRequest):
    """Parse one consented land document into structured fields. Returns the fields, a short
    text excerpt, and which parser produced them — nothing is stored."""
    doc_type = (req.doc_type or "other").strip().lower()
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=422, detail="doc_type must be one of %s"
                            % ", ".join(_DOC_TYPES))
    try:
        data = base64.b64decode(req.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="content_base64 is not valid base64.")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 8 MB.")

    text = _pdf_text(data) if req.mime_type == "application/pdf" else ""
    fields, parser, note = None, "text-layer", None

    if req.consent and GEMINI_KEY:
        fields = _gemini_fields(data, req.mime_type, doc_type)
        if fields is not None:
            parser = "gemini-vision"
        else:
            note = "Vision parser was unavailable; returning the embedded text only."
    elif not req.consent:
        note = ("Consent not given, so the document was not sent to the vision parser. Only the "
                "embedded text layer (if any) was read on the server.")
    elif not GEMINI_KEY:
        note = "Vision parser is not configured on the server; returning embedded text only."

    if fields is None and not text:
        note = (note or "") + (" " if note else "") + (
            "No text layer found (likely a scanned image). Enable consent, or Phase-B OCR, to "
            "read it.")

    return {
        "doc_type": doc_type,
        "parser": parser,
        "fields": fields,
        "text_excerpt": text[:2000] if text else None,
        "note": note,
        "disclaimer": "Automated extraction — verify every field against the original document "
                      "and the revenue/registration records before relying on it.",
    }
