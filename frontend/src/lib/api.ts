/** Client for the ChennaiTerraRisk API. Requests are same-origin; next.config.ts
 *  rewrites /api/* to the FastAPI backend. */

export type Confidence = "high" | "medium" | "low";
export type CityDepth = "deep" | "moderate" | "baseline";

/** Which development-control regime governs a point. Mirrors the backend resolver so the UI
 *  can label jurisdiction, pick customary units and region-aware doc types before (and in
 *  step with) a Build Scope call. The Build Scope response's `jurisdiction.code` is
 *  authoritative; this is the instant client-side estimate. */
export type Region = "tamil_nadu" | "india" | "us";

export function regionOf(lat: number, lng: number, citySlug?: string | null): Region {
  if (citySlug === "us") return "us";
  const inUs =
    (lat >= 24 && lat <= 49.5 && lng >= -125 && lng <= -66.5) || // CONUS
    (lat >= 51 && lat <= 71.5 && lng >= -170 && lng <= -129) ||  // Alaska
    (lat >= 18 && lat <= 23 && lng >= -161 && lng <= -154);      // Hawaii
  if (inUs) return "us";
  if (lat >= 8 && lat <= 13.6 && lng >= 76.2 && lng <= 80.4) return "tamil_nadu";
  return "india";
}

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

/** Download the PDF report. POSTs so it can carry the whole workspace — the Build Scope the
 *  user set and the title cross-check from their uploads — which a GET link can't (and which,
 *  being personal, must not sit in a URL). Both extras are optional; the location report
 *  renders without them. */
export async function downloadReport(
  result: RiskResult,
  buildScope?: BuildScopeInput | null,
  titleCheck?: CrossCheck | null,
): Promise<void> {
  const res = await fetch("/api/v1/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      latitude: result.latitude, longitude: result.longitude,
      city: result.city?.slug ?? null, address: result.address ?? null,
      build_scope: buildScope ?? null, title_check: titleCheck ?? null,
    }),
  });
  if (!res.ok) throw new Error("Could not generate the report.");
  const blob = await res.blob();
  const name = (result.address || "parcel").split(",")[0]
    .replace(/[^a-z0-9]+/gi, "-").toLowerCase().slice(0, 40) || "parcel";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `terrisiq-report-${name}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// --- Cadastral: Build Scope (TNCDBR) calculator -------------------------------------------

export type BuildUse =
  | "residential" | "commercial" | "mixed" | "industrial" | "institutional" | "plotted_layout";

export interface BuildScopeInput {
  plot_area_sqm: number;
  road_width_m: number;
  use: BuildUse;
  proposed_height_m?: number | null;
  plot_width_m?: number | null;
  plot_depth_m?: number | null;
  pte_amsl_m?: number | null;
  ground_elev_amsl_m?: number | null;
  haca_cap_m?: number | null;
  flags?: Record<string, boolean>;
  /** The plot point — lets the backend derive jurisdiction and the airport NOC. */
  latitude?: number | null;
  longitude?: number | null;
  /** tamil_nadu | india | us; derived from the point when omitted. */
  jurisdiction?: Region | null;
  /** The plot's local FSI/FAR from its DCR/zoning; required to size floor area outside TN. */
  fsi_override?: number | null;
}

export interface Noc { authority: string; required: boolean; reason: string }

/** The plot area in every customary unit, from the backend. */
export interface AreaInUnits {
  sqm: number; sqft: number; sq_yd: number; cents: number; grounds: number; acres: number;
}

export interface BuildScope {
  jurisdiction: { code: Region; label: string; authority: string };
  area_in_units: AreaInUnits;
  // FSI/FAR is null outside Tamil Nadu until a local value is supplied (never invented).
  fsi: {
    term: string; normal: number | null; premium_added: number | null;
    max_with_premium: number | null; needs_local_value: boolean; basis: string;
  };
  ground_coverage: { fraction: number; max_footprint_sqm: number; basis: string };
  built_up_area_sqm: { at_normal_fsi: number | null; at_premium_fsi: number | null };
  setbacks: { regime: string; front_m: number; side1_m: number; side2_m: number; rear_m: number; basis: string };
  osr: { required: boolean; area_sqm: number; basis: string };
  parking: { car_equivalent_spaces: number | null; basis: string };
  height: {
    aai_net_permissible_agl_m: number | null; haca_cap_m: number | null;
    net_permissible_m: number | null; constrained_by: string | null;
    authority: string; basis: string;
  };
  yield: { approx_dwelling_units: number | null; dwelling_sqm_assumed: number | null };
  noc_checklist: Noc[];
  disclaimer: string;
}

export interface BuildScopeResponse { scope: BuildScope; layout_geojson: unknown }

export async function buildScope(input: BuildScopeInput): Promise<BuildScopeResponse> {
  const res = await fetch("/api/v1/cadastral/build-scope", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return asJson<BuildScopeResponse>(res);
}

/** Download the layout as DXF or GeoJSON. Posts the same inputs and saves the response. */
export async function downloadLayout(input: BuildScopeInput, format: "dxf" | "geojson"): Promise<void> {
  let blob: Blob;
  if (format === "dxf") {
    const res = await fetch("/api/v1/cadastral/build-scope/layout.dxf", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error("Could not generate the DXF.");
    blob = await res.blob();
  } else {
    const r = await buildScope(input);
    blob = new Blob([JSON.stringify(r.layout_geojson, null, 2)], { type: "application/geo+json" });
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `terrisiq_build_scope.${format === "dxf" ? "dxf" : "geojson"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// --- Evidence: real satellite scene provenance (STAC over HTTP) ---------------------------

export interface Scene {
  granule_id: string | null; collection: string | null; datetime: string | null;
  platform: string | null; instrument: string | null; cloud_cover_pct: number | null;
}

/** Recent public Sentinel scenes covering a point. Never throws: returns [] on any failure
 *  so the Evidence drawer degrades gracefully. */
export async function fetchScenes(lat: number, lng: number): Promise<Scene[]> {
  try {
    const res = await fetch(`/api/v1/evidence/scenes?lat=${lat}&lng=${lng}`);
    if (!res.ok) return [];
    const body = (await res.json()) as { scenes: Scene[] };
    return body.scenes ?? [];
  } catch {
    return [];
  }
}

// --- Cadastral: consented document parse (Patta / EC / FMB) -------------------------------

export interface DocFields {
  district?: string | null;
  taluk?: string | null;
  village?: string | null;
  survey_number?: string | null;
  sub_division?: string | null;
  old_survey_numbers?: string[] | null;
  owner_names?: string[] | null;
  document_number?: string | null;
  execution_date?: string | null;
  transaction_value_inr?: string | number | null;
  mortgages?: { created?: string | null; released?: string | null }[] | null;
  boundaries?: { north?: string; south?: string; east?: string; west?: string } | null;
  language?: string | null;
}

export interface DocParseResult {
  doc_type: string;
  parser: string;
  fields: DocFields | null;
  text_excerpt: string | null;
  note: string | null;
  disclaimer: string;
}

export type DocType =
  // Tamil Nadu
  | "patta" | "chitta" | "tslr" | "ec" | "sale_deed" | "fmb"
  // Pan-India
  | "7_12" | "ekhata"
  // United States
  | "deed" | "alta" | "plat" | "fema_elevation"
  | "other";

/** Read a File as base64 (no data: prefix), for the JSON upload body. */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result);
      resolve(s.includes(",") ? s.slice(s.indexOf(",") + 1) : s);
    };
    r.onerror = () => reject(new Error("Could not read the file."));
    r.readAsDataURL(file);
  });
}

export async function parseDocument(
  file: File, docType: DocType, consent: boolean,
): Promise<DocParseResult> {
  const content_base64 = await fileToBase64(file);
  const res = await fetch("/api/v1/cadastral/upload-documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name, content_base64, doc_type: docType,
      mime_type: file.type || "application/pdf", consent,
    }),
  });
  return asJson<DocParseResult>(res);
}

// --- Cadastral: title cross-verification across uploaded documents -----------------------

export type MatchStatus = "match" | "mismatch" | "unknown";

export interface CrossCheck {
  haveDocs: DocType[];
  ownerMatch: { status: MatchStatus; score: number; owner?: string; buyer?: string; note: string } | null;
  surveyParity: { status: MatchStatus; values: string[]; note: string } | null;
  mortgages: { total: number; unreleased: number; note: string } | null;
}

const _HONORIFICS = new Set([
  "thiru", "tmt", "selvi", "mr", "mrs", "ms", "sri", "smt", "kumari", "late",
  "s/o", "d/o", "w/o", "son", "daughter", "wife", "of",
]);

/** Normalise an Indian name for screening comparison: lowercase, drop punctuation and common
 *  honorifics/relations, collapse whitespace. Not transliteration-aware (Tamil phonetics are a
 *  Phase-B refinement) — a screening signal, labelled as approximate. */
function normalizeName(raw: string): string[] {
  return raw.toLowerCase().replace(/[^a-z\s/]/g, " ").split(/\s+/)
    .filter((t) => t && !_HONORIFICS.has(t));
}

/** Dice coefficient over name tokens: 0 (no overlap) to 1 (identical token sets). */
function nameSimilarity(a: string, b: string): number {
  const ta = new Set(normalizeName(a));
  const tb = new Set(normalizeName(b));
  if (ta.size === 0 || tb.size === 0) return 0;
  let inter = 0;
  for (const t of ta) if (tb.has(t)) inter++;
  return (2 * inter) / (ta.size + tb.size);
}

const _MATCH = 0.5; // token-set threshold for a screening "match"

function bestNameMatch(owners: string[], buyers: string[]) {
  let best = { score: 0, owner: "", buyer: "" };
  for (const o of owners) for (const b of buyers) {
    const s = nameSimilarity(o, b);
    if (s > best.score) best = { score: s, owner: o, buyer: b };
  }
  return best;
}

function normalizeSurvey(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "").replace(/[^0-9a-z/]/g, "");
}

/** Cross-verify the documents collected so far. A Patta/Chitta/TSLR supplies the owner; an EC
 *  or sale deed supplies the buyer and the mortgage chain. Returns null until at least one
 *  parsed document with fields is present. */
export function crossVerifyDocuments(docs: Partial<Record<DocType, DocParseResult>>): CrossCheck | null {
  const have = (Object.keys(docs) as DocType[]).filter((k) => docs[k]?.fields);
  if (have.length === 0) return null;

  const owner = docs.patta?.fields ?? docs.chitta?.fields ?? docs.tslr?.fields ?? null;
  const buyerDoc = docs.ec?.fields ?? docs.sale_deed?.fields ?? null;

  // Owner (Patta) vs buyer (EC/deed) name.
  let ownerMatch: CrossCheck["ownerMatch"] = null;
  if (owner?.owner_names?.length && buyerDoc?.owner_names?.length) {
    const b = bestNameMatch(owner.owner_names, buyerDoc.owner_names);
    const status: MatchStatus = b.score >= _MATCH ? "match" : "mismatch";
    ownerMatch = {
      status, score: Math.round(b.score * 100) / 100, owner: b.owner, buyer: b.buyer,
      note: status === "match"
        ? "Patta owner and EC/deed party appear to be the same person (approximate match)."
        : "Patta owner and EC/deed party do not clearly match — verify the chain of title.",
    };
  } else if (owner || buyerDoc) {
    ownerMatch = { status: "unknown", score: 0,
      note: "Upload both a Patta/Chitta and an EC or sale deed to cross-check owner vs. buyer." };
  }

  // Survey-number parity across whatever documents carry one.
  const surveys = have
    .map((k) => docs[k]?.fields?.survey_number)
    .filter((v): v is string => !!v);
  let surveyParity: CrossCheck["surveyParity"] = null;
  if (surveys.length >= 2) {
    const norm = new Set(surveys.map(normalizeSurvey));
    const status: MatchStatus = norm.size === 1 ? "match" : "mismatch";
    surveyParity = { status, values: surveys,
      note: status === "match"
        ? "Survey numbers agree across the uploaded documents."
        : "Survey numbers differ across documents — confirm they describe the same plot." };
  } else if (surveys.length === 1) {
    surveyParity = { status: "unknown", values: surveys,
      note: "Only one document carries a survey number; upload another to cross-check parity." };
  }

  // Encumbrances from the EC/deed mortgage chain.
  let mortgages: CrossCheck["mortgages"] = null;
  const ms = buyerDoc?.mortgages ?? owner?.mortgages ?? [];
  if (ms.length) {
    const unreleased = ms.filter((m) => m?.created && !m?.released).length;
    mortgages = { total: ms.length, unreleased,
      note: unreleased
        ? `${unreleased} mortgage(s) with no recorded release — a live encumbrance; confirm against CERSAI.`
        : "All recorded mortgages show a release." };
  }

  return { haveDocs: have, ownerMatch, surveyParity, mortgages };
}

export const DEPTH_LABEL: Record<CityDepth, string> = {
  deep: "Full flood survey",
  moderate: "Partial data",
  baseline: "Terrain only",
};

export { gradeFill, gradeText, gradeTrack } from "./design";
