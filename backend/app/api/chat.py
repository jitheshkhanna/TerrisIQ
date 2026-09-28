"""Conversational Q&A grounded strictly in a location's computed risk data.

The model only ever receives the risk report for the place the user already scored, plus
a hard instruction to answer from it and to admit when something is not in the data. It
must never invent flood or water facts - honesty about the data is the whole product - so
the temperature is low and the prompt forbids speculation.

The Gemini key lives in GEMINI_API_KEY (server env only, never shipped to the client).
Chat is a no-op returning 503 until that is set, so the rest of the API is unaffected.
"""
import os
import time
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["chat"])

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
    % GEMINI_MODEL
)

MAX_QUESTION = 500
MAX_HISTORY = 8

# The free tier returns 503 ("high demand") and 429 under load; a couple of quick retries
# smooth over the transient ones instead of surfacing an error to the user.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRIES = 3
_BACKOFF_S = 0.7

SYSTEM = (
    "You are the Terrisiq assistant. Terrisiq screens Indian properties for environmental "
    "risk: monsoon flooding, groundwater contamination and water scarcity.\n"
    "Answer ONLY from the RISK DATA block below - it is the risk report for the exact "
    "location the user is asking about.\n"
    "Rules:\n"
    "- Never invent or estimate a number, grade or fact that is not in the data.\n"
    "- If the answer is not in the data, say so plainly and suggest what the user could "
    "check instead. Do not guess.\n"
    "- Be concise and plain-spoken, for an ordinary Indian home-buyer. Avoid jargon.\n"
    "- This is a screening tool, not a site survey. If asked outright whether to buy, do "
    "not give a yes/no; explain what the risks mean and say a physical check is still "
    "needed.\n"
    "- If no location has been scored yet, ask the user to search a place or paste a "
    "Google Maps link first."
)


class ChatTurn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    question: str
    context: Optional[str] = None
    history: List[ChatTurn] = []


def _extract_text(data) -> Optional[str]:
    """Join the text parts of the first candidate, ignoring non-text parts such as the
    model's thought-signature block."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    chunks = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]
    joined = "\n".join(chunks).strip()
    return joined or None


@router.post("/chat")
async def chat(req: ChatRequest):
    if not GEMINI_KEY:
        raise HTTPException(status_code=503, detail="Chat is not configured on the server.")

    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question.")
    question = question[:MAX_QUESTION]

    system = SYSTEM + "\n\nRISK DATA:\n" + (req.context or "No location has been scored yet.")
    contents = []
    for turn in req.history[-MAX_HISTORY:]:
        role = "model" if turn.role == "model" else "user"
        contents.append({"role": role, "parts": [{"text": (turn.text or "")[:MAX_QUESTION]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
    }

    resp = None
    for attempt in range(_RETRIES):
        last = attempt == _RETRIES - 1
        try:
            resp = httpx.post(
                GEMINI_URL,
                headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=30.0,
            )
        except (httpx.TransportError, httpx.TimeoutException):
            resp = None
            if last:
                break
            time.sleep(_BACKOFF_S * (attempt + 1))
            continue
        if resp.status_code in _RETRY_STATUS and not last:
            time.sleep(_BACKOFF_S * (attempt + 1))
            continue
        break

    if resp is None or resp.status_code >= 400:
        raise HTTPException(status_code=503,
                            detail="The assistant is busy right now. Try again in a moment.")

    answer = _extract_text(resp.json())
    if not answer:
        raise HTTPException(status_code=502, detail="The assistant did not return an answer.")
    return {"answer": answer}
