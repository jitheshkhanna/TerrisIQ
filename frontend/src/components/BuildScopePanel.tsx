"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildScope, downloadLayout, regionOf,
  type BuildScope, type BuildScopeInput, type BuildUse, type Region,
} from "@/lib/api";

/* Build Scope — the region-adaptive development-potential calculator. In Tamil Nadu it runs
 * the bundled TNCDBR table; elsewhere in India (NBC baseline) and in the US (zoning/FAR) the
 * floor-space ratio is genuinely local, so the panel asks the user for it instead of inventing
 * one. Plot area is entered in the region's customary units, road width as tap presets, and it
 * recalculates live (no "compute" button). Ground elevation and NOC triggers arrive from the
 * scored location (prefill); height/airspace parameters are an optional advanced step.
 */

/** Values carried over from the active scored location. `key` is the lat,lng signature so the
 *  panel re-seeds only when the user actually scores a new point, never on every re-render. */
export interface BuildScopePrefill {
  key: string;
  lat: number;
  lng: number;
  groundElevM: number | null;
  cityName: string | null;
  flags: Record<string, boolean>;
  triggers: string[];
}

const USES: { id: BuildUse; label: string }[] = [
  { id: "residential", label: "Residential" },
  { id: "commercial", label: "Commercial" },
  { id: "mixed", label: "Mixed use" },
  { id: "industrial", label: "Industrial" },
  { id: "institutional", label: "Institutional" },
  { id: "plotted_layout", label: "Plotted layout" },
];

type AreaUnit = "sqft" | "ground" | "cent" | "acre" | "sqm";
const SQM_PER: Record<AreaUnit, number> = {
  sqm: 1,
  sqft: 0.092903,       // 1 sq.ft
  ground: 222.967,      // 1 Ground = 2400 sq.ft (Chennai/TN)
  cent: 40.4686,        // 1 cent = 435.6 sq.ft
  acre: 4046.86,        // 1 acre = 43,560 sq.ft
};
const UNIT_LABEL: Record<AreaUnit, string> = {
  sqft: "sq.ft", ground: "Grounds", cent: "Cents", acre: "Acres", sqm: "m²",
};
// Which units to offer, by region — the ones buyers there actually quote.
const UNITS_BY_REGION: Record<Region, AreaUnit[]> = {
  tamil_nadu: ["sqft", "ground", "cent", "sqm"],
  india: ["sqft", "cent", "sqm"],
  us: ["sqft", "acre"],
};

// Road-width presets, metres with the foot equivalent people actually quote.
const ROAD_PRESETS = [
  { m: 6, label: "6m · 20ft" }, { m: 9, label: "9m · 30ft" }, { m: 12, label: "12m · 40ft" },
  { m: 18, label: "18m · 60ft" }, { m: 24, label: "24m · 80ft" },
];

function num(v: string): number | null {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

function toSqm(v: number, unit: AreaUnit): number {
  return v * SQM_PER[unit];
}

/** Helper line showing the area in the other customary units for the region. */
function areaHelper(v: number | null, unit: AreaUnit, region: Region): string {
  if (v == null || v <= 0) return "";
  const sqm = toSqm(v, unit);
  const parts = UNITS_BY_REGION[region]
    .filter((u) => u !== unit)
    .map((u) => {
      const val = sqm / SQM_PER[u];
      const n = u === "sqm" || u === "sqft" ? Math.round(val).toLocaleString()
                                            : val.toFixed(val < 10 ? 2 : 1);
      return `${n} ${UNIT_LABEL[u]}`;
    });
  return `≈ ${parts.join(" · ")}`;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl bg-[var(--plane)] px-3 py-2.5">
      <p className="text-[12px] text-[var(--ink-muted)]">{label}</p>
      <p className="mt-0.5 text-[17px] font-semibold text-[var(--ink)]">{value}</p>
      {sub && <p className="mt-0.5 text-[11.5px] text-[var(--ink-muted)]">{sub}</p>}
    </div>
  );
}

function Chip({ text, tone }: { text: string; tone: "good" | "warn" | "neutral" }) {
  const dot = tone === "good" ? "var(--good)" : tone === "warn" ? "var(--warning)" : "var(--edge)";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--plane)] px-2.5 py-1
                     text-[12px] text-[var(--ink)]">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: dot }} aria-hidden />
      {text}
    </span>
  );
}

function Results({ s, input }: { s: BuildScope; input: BuildScopeInput }) {
  const [dl, setDl] = useState<string | null>(null);
  const netH = s.height.net_permissible_m;
  const activeNocs = s.noc_checklist.filter((n) => n.required);

  const grab = async (fmt: "dxf" | "geojson") => {
    setDl(fmt);
    try { await downloadLayout(input, fmt); } catch { /* button re-enables */ } finally { setDl(null); }
  };

  const term = s.fsi.term;
  const fsiMax = s.fsi.max_with_premium;
  const builtPremium = s.built_up_area_sqm.at_premium_fsi;
  const builtNormal = s.built_up_area_sqm.at_normal_fsi;
  const parking = s.parking.car_equivalent_spaces;
  const heightHint = s.height.authority.startsWith("FAA") ? "add FAA cap below" : "add AAI PTE below";

  return (
    <div className="mt-4 space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label={`Max ${term} (with premium)`}
              value={fsiMax != null ? fsiMax.toFixed(2) : "—"}
              sub={fsiMax != null ? `Normal ${s.fsi.normal} + premium ${s.fsi.premium_added}`
                                  : `Enter your local ${term} above`} />
        <Stat label="Max built-up"
              value={builtPremium != null ? `${Math.round(builtPremium).toLocaleString()} m²` : "—"}
              sub={builtNormal != null ? `${Math.round(builtNormal).toLocaleString()} m² at normal ${term}`
                                       : `needs the local ${term}`} />
        <Stat label="Ground coverage" value={`${Math.round(s.ground_coverage.fraction * 100)}%`}
              sub={`${Math.round(s.ground_coverage.max_footprint_sqm).toLocaleString()} m² footprint`} />
        <Stat label="Net permissible height"
              value={netH != null ? `${netH} m` : "—"}
              sub={netH != null ? `capped by ${s.height.constrained_by}` : heightHint} />
        <Stat label="Setbacks" value={`${s.setbacks.front_m} / ${s.setbacks.side1_m} / ${s.setbacks.rear_m} m`}
              sub={`front / side / rear · ${s.setbacks.regime}`} />
        <Stat label="Parking" value={parking != null ? `${parking} ECS` : "—"}
              sub={s.yield.approx_dwelling_units != null ? `~${s.yield.approx_dwelling_units} units`
                   : s.osr.required ? `OSR ${s.osr.area_sqm} m²` : "car-equiv. spaces"} />
      </div>

      <div>
        <p className="text-[13px] font-semibold text-[var(--ink)]">Clearances to obtain</p>
        {activeNocs.length === 0 ? (
          <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
            No clearances triggered by these inputs.
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {activeNocs.map((n) => (
              <li key={n.authority} className="flex items-start gap-2 text-[13px] text-[var(--ink-2)]">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--warning)]" aria-hidden />
                <span><span className="font-medium text-[var(--ink)]">{n.authority}</span> — {n.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <button onClick={() => grab("dxf")} disabled={dl !== null}
                className="rounded-lg border border-[var(--hairline)] px-3 py-2 text-[13px]
                           font-medium text-[var(--ink)] hover:bg-[var(--plane)] disabled:opacity-50">
          {dl === "dxf" ? "Preparing…" : "Download layout (.dxf)"}
        </button>
        <button onClick={() => grab("geojson")} disabled={dl !== null}
                className="rounded-lg border border-[var(--hairline)] px-3 py-2 text-[13px]
                           font-medium text-[var(--ink)] hover:bg-[var(--plane)] disabled:opacity-50">
          {dl === "geojson" ? "Preparing…" : "Download (.geojson)"}
        </button>
      </div>

      <p className="text-[11.5px] leading-snug text-[var(--ink-muted)]">{s.disclaimer}</p>
    </div>
  );
}

export default function BuildScopePanel(
  { prefill, surveyBadge, onInput }:
  { prefill?: BuildScopePrefill; surveyBadge?: string | null;
    onInput?: (input: BuildScopeInput) => void },
) {
  // The point's governing regime drives units, the FSI/FAR vocabulary and the airspace
  // authority. The panel is keyed on prefill.key, so this is fixed for the life of the mount.
  const region: Region = prefill ? regionOf(prefill.lat, prefill.lng) : "tamil_nadu";

  const [use, setUse] = useState<BuildUse>("residential");
  const [unit, setUnit] = useState<AreaUnit>(() => UNITS_BY_REGION[region][0]);
  const [area, setArea] = useState("2400");   // 1 Ground — a familiar Chennai default
  const [road, setRoad] = useState("12");
  const [height, setHeight] = useState("");
  const [pte, setPte] = useState("");
  // The plot's local FSI/FAR, entered by the user. Only used (and shown) outside Tamil Nadu,
  // where the floor-space ratio is set by the local DCR/zoning and is never guessed for them.
  const [fsiOverride, setFsiOverride] = useState("");
  // Seeded from the scored location. The panel is keyed on prefill.key by the parent, so it
  // remounts (re-initialising ground) when the user scores a new point — no sync effect needed.
  const [ground, setGround] = useState(prefill?.groundElevM != null ? String(prefill.groundElevM) : "");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState<BuildScope | null>(null);
  const [lastInput, setLastInput] = useState<BuildScopeInput | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // NOC flags come straight from the scored location; not user-editable, so derive, not mirror.
  const flags = useMemo(() => prefill?.flags ?? {}, [prefill?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const input = useMemo<BuildScopeInput | null>(() => {
    const a = num(area), r = num(road);
    if (a == null || a <= 0 || r == null || r < 0) return null;
    return {
      plot_area_sqm: Math.round(toSqm(a, unit) * 10) / 10, road_width_m: r, use,
      proposed_height_m: num(height), pte_amsl_m: num(pte), ground_elev_amsl_m: num(ground),
      flags: Object.keys(flags).length ? flags : undefined,
      // The point lets the backend resolve jurisdiction + the airport NOC; the override sizes
      // floor area outside Tamil Nadu.
      latitude: prefill?.lat ?? null, longitude: prefill?.lng ?? null,
      fsi_override: num(fsiOverride),
    };
  }, [area, unit, road, use, height, pte, ground, flags, fsiOverride, prefill?.lat, prefill?.lng]);

  // Live recalculation: debounce 300ms so typing feels instant without hammering the API.
  useEffect(() => {
    if (!input) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const res = await buildScope(input);
        setResult(res.scope);
        setLastInput(input);
        onInput?.(input);  // hand the validated input up so the PDF report matches the screen
      } catch { /* keep the last good result */ }
    }, 300);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [input, onInput]);

  // The FSI/FAR vocabulary and whether a local value is needed. Known definitively once the
  // first response lands; estimated from the region before that so the input shows immediately.
  const term = result?.fsi.term ?? (region === "us" ? "FAR" : "FSI");
  const needsLocalFsi = result?.fsi.needs_local_value ?? (region !== "tamil_nadu");
  // The governing jurisdiction label — authoritative from the response, else a region fallback.
  const jurisdictionLabel = result?.jurisdiction.label
    ?? { tamil_nadu: "Tamil Nadu — TNCDBR 2019 (indicative)",
         india: "India — confirm the local DCR (NBC 2016 baseline)",
         us: "United States — confirm the local zoning code" }[region];

  // Status chips summarising what the scored location contributed.
  const groundNum = num(ground);
  const chips = prefill ? [
    { text: groundNum != null ? `Ground: ${groundNum} m AMSL` : "Ground: add elevation", tone: "neutral" as const },
    { text: flags.near_coast ? "CRZ: within 500 m" : "CRZ: clear",
      tone: flags.near_coast ? "warn" as const : "good" as const },
    { text: (flags.near_water_body || flags.near_storm_drain) ? "Water buffer: within 50 m" : "Water buffer: clear",
      tone: (flags.near_water_body || flags.near_storm_drain) ? "warn" as const : "good" as const },
  ] : [];

  return (
    <section className="rounded-2xl border border-[var(--hairline)] bg-[var(--surface)] p-4 sm:p-5">
      <h2 className="text-[17px] font-semibold text-[var(--ink)]">Build Scope</h2>
      <p className="mt-0.5 text-[13px] text-[var(--ink-2)]">
        Indicative development potential — FSI/FAR, setbacks, height caps, NOCs and a
        downloadable layout. Updates live; verify with the planning authority.
      </p>

      {/* Jurisdiction — which development-control regime governs this point. */}
      <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-[var(--plane)]
                      px-2.5 py-1 text-[12px] font-medium text-[var(--ink)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" aria-hidden />
        {jurisdictionLabel}
      </div>

      {surveyBadge && (
        <span className="mt-2 ml-1.5 inline-flex items-center gap-1.5 rounded-full bg-[var(--plane)]
                         px-2.5 py-1 text-[12px] text-[var(--ink)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--good)]" aria-hidden />
          Survey No. {surveyBadge} · from your document
        </span>
      )}

      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {chips.map((c) => <Chip key={c.text} text={c.text} tone={c.tone} />)}
        </div>
      )}

      <div className="mt-4 space-y-3">
        <div>
          <span className="text-[13px] font-medium text-[var(--ink-2)]">Intended use</span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {USES.map((u) => (
              <button key={u.id} onClick={() => setUse(u.id)}
                      className={`rounded-full px-3 py-1.5 text-[13px] font-medium transition ${
                        use === u.id ? "bg-[var(--ink)] text-[var(--surface)]"
                                     : "bg-[var(--plane)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
                {u.label}
              </button>
            ))}
          </div>
        </div>

        {/* Plot area with a unit toggle */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-medium text-[var(--ink-2)]">Plot area</span>
            <div className="flex gap-1 rounded-lg bg-[var(--plane)] p-0.5">
              {UNITS_BY_REGION[region].map((u) => (
                <button key={u} onClick={() => setUnit(u)}
                        className={`rounded-md px-2 py-0.5 text-[12px] font-medium transition ${
                          unit === u ? "bg-[var(--surface)] text-[var(--ink)] shadow-sm"
                                     : "text-[var(--ink-muted)]"}`}>
                  {UNIT_LABEL[u]}
                </button>
              ))}
            </div>
          </div>
          <input inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)}
                 className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                            px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
          <span className="mt-0.5 block text-[11.5px] text-[var(--ink-muted)]">{areaHelper(num(area), unit, region)}</span>
        </div>

        {/* Local FSI / FAR — shown outside Tamil Nadu, where floor-space is set by the local
            DCR/zoning and we never guess it. Entering it sizes the buildable floor area. */}
        {needsLocalFsi && (
          <div>
            <span className="text-[13px] font-medium text-[var(--ink-2)]">
              Local {term} <span className="text-[var(--ink-muted)]">— from your DCR / zoning</span>
            </span>
            <input inputMode="decimal" value={fsiOverride} onChange={(e) => setFsiOverride(e.target.value)}
                   placeholder={`e.g. ${term === "FAR" ? "3.0" : "1.5"} — set by ${result?.jurisdiction.authority ?? "the local authority"}`}
                   className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                              px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
            <span className="mt-0.5 block text-[11.5px] text-[var(--ink-muted)]">
              {num(fsiOverride) ? `Floor area sized at ${term} ${num(fsiOverride)}.`
                                : `We don't invent ${term} here — enter your plot's value to size the floor area.`}
            </span>
          </div>
        )}

        {/* Road width: presets + numeric */}
        <div>
          <span className="text-[13px] font-medium text-[var(--ink-2)]">Abutting road width</span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {ROAD_PRESETS.map((p) => (
              <button key={p.m} onClick={() => setRoad(String(p.m))}
                      className={`rounded-full px-3 py-1.5 text-[12px] font-medium transition ${
                        num(road) === p.m ? "bg-[var(--ink)] text-[var(--surface)]"
                                          : "bg-[var(--plane)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
                {p.label}
              </button>
            ))}
          </div>
          <input inputMode="decimal" value={road} onChange={(e) => setRoad(e.target.value)}
                 placeholder="metres"
                 className="mt-1.5 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                            px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
        </div>

        {/* Advanced: height + airport NOC */}
        <div className="rounded-xl border border-[var(--hairline)]">
          <button onClick={() => setShowAdvanced(!showAdvanced)} aria-expanded={showAdvanced}
                  className="flex min-h-[var(--tap)] w-full items-center justify-between px-3 text-[13px]
                             font-medium text-[var(--ink-2)] hover:text-[var(--ink)]">
            Advanced height &amp; {region === "us" ? "FAA airspace" : "airport NOC"} parameters
            <svg viewBox="0 0 12 12" className={`h-3 w-3 transition ${showAdvanced ? "rotate-180" : ""}`} aria-hidden>
              <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none"
                    strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {showAdvanced && (
            <div className="grid grid-cols-2 gap-3 px-3 pb-3">
              <label className="block">
                <span className="text-[12px] text-[var(--ink-2)]">Proposed height (m)</span>
                <input inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)}
                       className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                                  px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
              </label>
              <label className="block">
                <span className="text-[12px] text-[var(--ink-2)]">Ground elev. (m AMSL)</span>
                <input inputMode="decimal" value={ground} onChange={(e) => setGround(e.target.value)}
                       className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                                  px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
              </label>
              <label className="block col-span-2">
                <span className="text-[12px] text-[var(--ink-2)]">
                  {region === "us" ? "FAA permissible top elevation (m AMSL)"
                                    : "AAI top elevation PTE (m AMSL)"}
                </span>
                <input inputMode="decimal" value={pte} onChange={(e) => setPte(e.target.value)}
                       placeholder={region === "us" ? "from an FAA obstruction evaluation — for the height cap"
                                                     : "from AAI NOCAS — for airport height cap"}
                       className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                                  px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
              </label>
            </div>
          )}
        </div>
      </div>

      {result && lastInput && <Results s={result} input={lastInput} />}
    </section>
  );
}
