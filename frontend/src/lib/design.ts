/** Colour and view tokens shared between the DOM and the MapLibre style.
 *
 *  Two rules hold this together:
 *
 *  1. **Text never wears a fill colour.** Score numbers and labels use ink or a darkened
 *     text tone that clears 4.5:1; a coloured dot beside them carries the status. The
 *     bright hues below are for fills and map marks only.
 *  2. **The hazard ramp is ordinal**: one hue, monotone lightness, light end clearing
 *     2:1 on the map. Five ordered levels in a red/amber/green rainbow would put the
 *     order in hue instead of in value, and collapse under colour-vision deficiency.
 *     Checked with the data-viz validator: monotone L, adjacent ΔL, 2.21:1 light end,
 *     6° hue spread.
 */

export const FLOOD_RAMP = {
  "Very Low": "#e59a7c",
  Low: "#d87755",
  Moderate: "#c6552e",
  High: "#a53a19",
  "Very High": "#7d280f",
} as const;

export const FLOOD_ORDER = ["Very Low", "Low", "Moderate", "High", "Very High"] as const;

/** Fills and marks. Always carry dark ink on top, never white. */
export const GRADE_FILL: Record<string, string> = {
  A: "#0ca30c",
  B: "#0ca30c",
  C: "#fab219",
  D: "#ec835a",
  F: "#d34949",
};

/** The same states as text, darkened until each clears 4.5:1 on the surface. */
export const GRADE_TEXT: Record<string, string> = {
  A: "#0a870a",
  B: "#0a870a",
  C: "#986d0f",
  D: "#ac6042",
  F: "#d03b3b",
};

/** Meter tracks: a wash of the fill's own hue, so state reads across the whole bar. */
export const GRADE_TRACK: Record<string, string> = {
  A: "#d7efd7",
  B: "#d7efd7",
  C: "#fbe9c4",
  D: "#f9dfd3",
  F: "#f4d9d9",
};

export const INK = {
  primary: "#0b0b0b",
  secondary: "#52514e",
  muted: "#716f6b",
  hairline: "#dedcd4",
  surface: "#fcfcfb",
} as const;

export const MAP = {
  water: "#a9c6dc",
  waterLine: "#8aaec9",
  drain: "#6b7684",
  drainBad: "#c0392b",
  industrial: "#8a7fb0",
  hotspot: "#1f2937",
  dumpsite: "#5c4632",
  wardLine: "#0b0b0b",
} as const;

/** The map shows one thing at a time.
 *
 *  Seven independent checkboxes let anyone build an unreadable screen, and the default
 *  state was already close to one: hazard, water, drains, industry, hotspots, dumpyards
 *  and ward lines all stacked over a city-wide choropleth. These four views map onto the
 *  three risks the tool actually scores, so choosing one is choosing a question.
 */
export type MapView = "flood" | "drainage" | "contamination" | "plain";

export const VIEWS: { id: MapView; label: string; hint: string }[] = [
  { id: "flood", label: "Flood", hint: "Inundation zones and past flooding" },
  { id: "drainage", label: "Water", hint: "Storm water drains, rivers and lakes" },
  { id: "contamination", label: "Industry", hint: "Industrial land and dumpyards" },
  { id: "plain", label: "None", hint: "Basemap only" },
];

/** Which map layers each view switches on. */
export const VIEW_LAYERS: Record<MapView, string[]> = {
  flood: ["flood_zones-fill", "low_lying-fill", "flood_hotspots-circle"],
  drainage: ["swd-line", "waterbodies-fill", "waterbodies-line"],
  contamination: ["industrial_osm-fill", "dumpsites-circle"],
  plain: [],
};

export const ALL_DATA_LAYERS = Array.from(new Set(Object.values(VIEW_LAYERS).flat()));

export function gradeFill(grade: string): string {
  return GRADE_FILL[grade] ?? INK.muted;
}

export function gradeText(grade: string): string {
  return GRADE_TEXT[grade] ?? INK.secondary;
}

export function gradeTrack(grade: string): string {
  return GRADE_TRACK[grade] ?? "#e6e4dd";
}
