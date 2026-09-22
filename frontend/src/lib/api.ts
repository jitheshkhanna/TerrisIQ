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
  const params = new URLSearchParams({ q, limit: "6" });
  if (city) params.set("city", city);
  const res = await fetch(`/api/v1/geocode?${params.toString()}`, { signal });
  return asJson<GeocodeResponse>(res);
}

/** The full display string for a result, used for the report heading. */
export function fullLabel(result: GeocodeResult): string {
  return result.context ? `${result.label}, ${result.context}` : result.label;
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
