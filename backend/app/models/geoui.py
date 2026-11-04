"""GeoIntent — a typed JSON protocol for deterministic map control (no screenshots/DOM).

From the blueprint's NASA-IMPACT geoui-intent-protocol idea: instead of an agent driving the
map by uploading screenshots and guessing pixel coordinates, the client and agent exchange a
small typed payload whose `viewport` (bbox), `layers`, `time` and `selection` are first-class
fields in exact decimal degrees. This is the Phase-A piece that is fully portable: the schema
itself, plus a validator the frontend MapLibre adapter and the chat agent both speak.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Viewport(BaseModel):
    bbox: List[float] = Field(..., description="[west, south, east, north] in decimal degrees")
    zoom: Optional[float] = Field(None, ge=0, le=24)

    @field_validator("bbox")
    @classmethod
    def _check_bbox(cls, v):
        if len(v) != 4:
            raise ValueError("bbox must be [west, south, east, north]")
        w, s, e, n = v
        if not (-180 <= w <= 180 and -180 <= e <= 180):
            raise ValueError("longitudes must be within [-180, 180]")
        if not (-90 <= s <= 90 and -90 <= n <= 90):
            raise ValueError("latitudes must be within [-90, 90]")
        if w >= e or s >= n:
            raise ValueError("bbox must have west<east and south<north")
        return v


class LayerState(BaseModel):
    id: str
    visible: bool = True
    opacity: float = Field(1.0, ge=0.0, le=1.0)


class TimeState(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    current_step: Optional[str] = None


class Selection(BaseModel):
    parcel_ulpin: Optional[str] = None
    survey_number: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)


class GeoIntent(BaseModel):
    """One map-state message, equally valid as agent->client or client->agent."""
    viewport: Optional[Viewport] = None
    layers: List[LayerState] = []
    time: Optional[TimeState] = None
    selection: Optional[Selection] = None
