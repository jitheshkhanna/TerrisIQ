/** Client for the ChennaiTerraRisk API. Requests are same-origin; next.config.ts
 *  rewrites /api/* to the FastAPI backend. */

export type Confidence = "high" | "medium" | "low";
export type CityDepth = "deep" | "moderate" | "baseline";

export interface City {
  slug: string;
  name: string;
  state: string;
  corporation: string;
  centre: { lat: number; lng: number };
  bbox: { lat_min: number; lng_min: number; lat_max: number; lng_max: number };
  /** How much is actually known here. Drives what the UI is allowed to claim. */
  depth: CityDepth;
  layers: string[];
  scoreable_dimensions: string[];
  ward_label: string;
  zone_label: string;
  notes: Record<string, string>;
}

export interface ScoreComponent {
  key: string;
  points: number;
  label: string;
}

export type FactLevel = "high" | "medium" | "low" | "good" | "info";

export interface Fact {
  text: string;
  level: FactLevel;
}

export interface RiskScore {
  score: number;
  grade: string;
  band: string;
  /** Plain language, e.g. "Low risk". Letters are kept only for API compatibility. */
  verdict: string;
  /** 1 very low ... 5 very high */
  level: number;
  /** Five-word findings for the card; full sentences live in `warnings`. */
  facts: Fact[];
  confidence: Confidence;
  warnings: string[];
  components: ScoreComponent[];
  details: Record<string, unknown>;
}

/** GCC ward and zone: the nomenclature property paperwork is filed against. */
export interface Administrative {
  city?: string;
  city_name?: string;
  ward_number?: string | null;
  ward_name?: string | null;
  ward: string | null;
  zone: string | null;
  zone_number: number | null;
  summary: string;
  inside_gcc: boolean;
  basis: string | null;
  ward_is_official?: boolean;
  nearest_zone: string | null;
  nearest_zone_m: number | null;
  note: string | null;
}

export interface RiskResult {
  city: City;
  latitude: number;
  longitude: number;
  address: string | null;
  administrative: Administrative;
  flood: RiskScore;
  /** Null where the city maps no industrial or waste sources. */
  contamination: RiskScore | null;
  /** Null where the city publishes no groundwater evidence at all. */
  scarcity: RiskScore | null;
  composite_score: number;
  composite_grade: string;
  composite_band: string;
  verdict: string;
  level: number;
  unadjusted_grade: string;
  grade_floor_applied: boolean;
  grade_floor_reason: string | null;
  severity_note: string | null;
  confidence: Confidence;
  summary: string;
  weights: Record<string, number>;
  base_weights: Record<string, number>;
  unavailable_dimensions: string[];
  /** Coastal Regulation Zone screening (distance-to-coast proxy); null inland. */
  crz: { applicable: boolean; band: string; distance_m: number; headline: string; note: string } | null;
  coverage_note: string | null;
  evidence_ceiling_applied: boolean;
  evidence_ceiling_reason: string | null;
  h3_cell: string | null;
  cached: boolean;
  generated_at: string;
  disclaimer: string;
}

export interface GeocodeResult {
  /** What was searched for, e.g. "100 Feet Road" */
  label: string;
  /** Where it is, e.g. "Velachery, Chennai 600042" */
  context: string;
  /** Locality / Street / Landmark / Station / ... */
  category: string;
  latitude: number;
  longitude: number;
  type: string | null;
}

export interface GeocodeResponse {
  query: string;
  /** Set when local shorthand was expanded, e.g. "omr" -> "Old Mahabalipuram Road" */
  expanded: string | null;
  source: string;
  results: GeocodeResult[];
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* fall through to statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export type NowcastStatus = "clear" | "watch" | "likely" | "active" | "unavailable";
export interface Nowcast {
  status: NowcastStatus;
  headline: string | null;
  rain_mm_h?: number;
  rain_3h_mm?: number;
  intensity?: string;
  observed_at?: string | null;
  alert?: { title: string; issuer: string; category: string } | null;
}

/** Live waterlogging signal (rain now x flood susceptibility + official alerts). Never
 *  throws for the caller: any failure resolves to an unavailable status so the strip hides. */
export async function nowcast(
  lat: number, lng: number, floodLevel: number, region?: string | null,
): Promise<Nowcast> {
  try {
    const q = `/api/v1/nowcast?lat=${lat}&lng=${lng}&flood_level=${floodLevel}`
      + (region ? `&region=${encodeURIComponent(region)}` : "");
    const res = await fetch(q);
    if (!res.ok) return { status: "unavailable", headline: null };
    return (await res.json()) as Nowcast;
  } catch {
    return { status: "unavailable", headline: null };
  }
}

export async function assessRisk(
  latitude: number,
  longitude: number,
  address?: string | null,
  city?: string | null,
): Promise<RiskResult> {
  const res = await fetch("/api/v1/risk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude, longitude, address: address ?? null, city: city ?? null }),
  });
  return asJson<RiskResult>(res);
}

export async function listCities(): Promise<City[]> {
  const res = await fetch("/api/v1/cities");
  const body = await asJson<{ cities: City[] }>(res);
  return body.cities;
}

export async function geocode(
  q: string,
  city?: string | null,
  signal?: AbortSignal,
): Promise<GeocodeResponse> {
  // fast=1 uses the LocationIQ type-ahead path (same as the extension): ~0.5s instead of
  // the ~4s Photon-with-fallbacks path. Photon still backs it up server-side.
  const params = new URLSearchParams({ q, limit: "6", fast: "1" });
  if (city) params.set("city", city);
  const res = await fetch(`/api/v1/geocode?${params.toString()}`, { signal });
  return asJson<GeocodeResponse>(res);
}

/** The full display string for a result, used for the report heading. */
export function fullLabel(result: GeocodeResult): string {
  return result.context ? `${result.label}, ${result.context}` : result.label;
}

/**
 * If the user pasted a Google Maps link or a bare "lat, lng", pull the exact
 * coordinates out of it so we can score the pin directly — no geocoder, no guessing.
 * Coordinates from a link the user pasted themselves are user-provided input, which is
 * why this is fine where an extension auto-reading Maps was not. Returns null for
 * ordinary place text (which then goes to the geocoder as before). Short share links
 * (maps.app.goo.gl) carry no coordinates and must be resolved server-side first.
 */
export function parseLocationInput(raw: string): GeocodeResult | null {
  const text = raw.trim();
  if (!text) return null;

  const ok = (lat: number, lng: number): GeocodeResult | null => {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return {
      label: `${lat.toFixed(5)}, ${lng.toFixed(5)}`,
      context: "Pinned from a map link",
      category: "Pinned location",
      latitude: lat,
      longitude: lng,
      type: "pin",
    };
  };

  // Bare "13.0416, 80.2339" (comma or whitespace separated).
  const bare = text.match(/^(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)$/);
  if (bare) return ok(parseFloat(bare[1]), parseFloat(bare[2]));

  if (!/^https?:\/\/|maps\.|google\.|goo\.gl/i.test(text)) return null;

  // A selected place carries its exact coordinate as !3d<lat>!4d<lng> — prefer it.
  const place = text.match(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/);
  if (place) return ok(parseFloat(place[1]), parseFloat(place[2]));

  // The @lat,lng,zoom viewport centre, present in most Maps URLs.
  const at = text.match(/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/);
  if (at) return ok(parseFloat(at[1]), parseFloat(at[2]));

  // ?q=lat,lng / ?query=lat,lng / ?ll=lat,lng / ?daddr=lat,lng
  const q = text.match(/[?&](?:q|query|ll|sll|daddr|center)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/);
  if (q) return ok(parseFloat(q[1]), parseFloat(q[2]));

  return null;
}

/** True for a Google Maps share link that hides its coordinates behind a redirect. */
export function isShortMapLink(raw: string): boolean {
  return /(?:maps\.app\.goo\.gl|goo\.gl\/maps|g\.co\/kgs)/i.test(raw.trim());
}

export interface ChatTurn {
  role: "user" | "model";
  text: string;
}

/** Compact, plain-text summary of a score — the only data the assistant is given, so it
 *  answers about the exact location the user is looking at and can't wander off it. */
export function riskContext(r: RiskResult): string {
  const dim = (name: string, s: RiskScore | null) => {
    if (!s) return `${name}: not scored for this city.`;
    const facts = s.facts?.map((f) => f.text).filter(Boolean).join("; ");
    return `${name}: ${s.verdict}${facts ? ` (${facts})` : ""}.`;
  };
  const lines = [
    `Location: ${r.address || `${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}`}.`,
    `City: ${r.city?.name ?? "unknown"} (data depth: ${r.city?.depth ?? "unknown"}).`,
    r.administrative?.ward ? `Ward/zone: ${r.administrative.ward}.` : "",
    `Overall: ${r.verdict} (level ${r.level} of 5).`,
    dim("Flooding", r.flood),
    dim("Water pollution", r.contamination),
    dim("Water shortage", r.scarcity),
    `Confidence: ${r.confidence}.`,
    r.coverage_note ? `Coverage note: ${r.coverage_note}` : "",
    r.severity_note ? `Note: ${r.severity_note}` : "",
    r.summary ? `Summary: ${r.summary}` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

export async function askChat(
  question: string,
  context: string | null,
  history: ChatTurn[],
): Promise<string> {
  const res = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, context, history }),
  });
  const body = await asJson<{ answer: string }>(res);
  return body.answer;
}

export async function reverseGeocode(lat: number, lng: number): Promise<string | null> {
  try {
    const res = await fetch(`/api/v1/reverse?lat=${lat}&lng=${lng}`);
    const body = await asJson<{ label: string | null }>(res);
    return body.label;
  } catch {
    return null;
  }
}

export function reportUrl(
  lat: number,
  lng: number,
  address?: string | null,
  city?: string | null,
): string {
  const params = new URLSearchParams({ latitude: String(lat), longitude: String(lng) });
  if (address) params.set("address", address);
  if (city) params.set("city", city);
  return `/api/v1/report?${params.toString()}`;
}

export const DEPTH_LABEL: Record<CityDepth, string> = {
  deep: "Full flood survey",
  moderate: "Partial data",
  baseline: "Terrain only",
};

export { gradeFill, gradeText, gradeTrack } from "./design";
