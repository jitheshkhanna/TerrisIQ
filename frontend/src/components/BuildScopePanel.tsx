"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildScope, downloadLayout,
  type BuildScope, type BuildScopeInput, type BuildUse,
} from "@/lib/api";

/* Build Scope — the TNCDBR development-potential calculator, tuned for the Chennai mental
 * model: plot area in sq.ft / Grounds, road width as tap presets, and a live recalculation so
 * there is no "compute" button. Ground elevation and NOC triggers arrive from the scored
 * location (prefill); only AAI/airport parameters are left as an optional advanced step.
 */

/** Values carried over from the active scored location. `key` is the lat,lng signature so the
 *  panel re-seeds only when the user actually scores a new point, never on every re-render. */
export interface BuildScopePrefill {
  key: string;
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

type AreaUnit = "sqft" | "ground" | "sqm";
const UNITS: { id: AreaUnit; label: string }[] = [
  { id: "sqft", label: "sq.ft" }, { id: "ground", label: "Grounds" }, { id: "sqm", label: "m²" },
];
const SQFT_M2 = 0.092903;      // 1 sq.ft in m²
const GROUND_SQFT = 2400;      // 1 Ground = 2400 sq.ft (Chennai)

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
  if (unit === "sqm") return v;
  if (unit === "ground") return v * GROUND_SQFT * SQFT_M2;
  return v * SQFT_M2;
}

/** Helper line showing the area in the two units the user did NOT pick. */
function areaHelper(v: number | null, unit: AreaUnit): string {
  if (v == null || v <= 0) return "";
  const sqm = toSqm(v, unit);
  const sqft = sqm / SQFT_M2;
  const grounds = sqft / GROUND_SQFT;
  const parts: string[] = [];
  if (unit !== "ground") parts.push(`${grounds.toFixed(grounds < 10 ? 1 : 0)} Ground`);
  if (unit !== "sqm") parts.push(`${Math.round(sqm)} m²`);
  if (unit !== "sqft") parts.push(`${Math.round(sqft).toLocaleString()} sq.ft`);
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

  return (
    <div className="mt-4 space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label="Max FSI (with premium)" value={s.fsi.max_with_premium.toFixed(2)}
              sub={`Normal ${s.fsi.normal} + premium ${s.fsi.premium_added}`} />
        <Stat label="Max built-up" value={`${Math.round(s.built_up_area_sqm.at_premium_fsi).toLocaleString()} m²`}
              sub={`${Math.round(s.built_up_area_sqm.at_normal_fsi).toLocaleString()} m² at normal FSI`} />
        <Stat label="Ground coverage" value={`${Math.round(s.ground_coverage.fraction * 100)}%`}
              sub={`${Math.round(s.ground_coverage.max_footprint_sqm).toLocaleString()} m² footprint`} />
        <Stat label="Net permissible height"
              value={netH != null ? `${netH} m` : "—"}
              sub={netH != null ? `capped by ${s.height.constrained_by}` : "add AAI PTE below"} />
        <Stat label="Setbacks" value={`${s.setbacks.front_m} / ${s.setbacks.side1_m} / ${s.setbacks.rear_m} m`}
              sub={`front / side / rear · ${s.setbacks.regime}`} />
        <Stat label="Parking" value={`${s.parking.car_equivalent_spaces} ECS`}
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
  const [use, setUse] = useState<BuildUse>("residential");
  const [unit, setUnit] = useState<AreaUnit>("sqft");
  const [area, setArea] = useState("2400");   // 1 Ground — a familiar Chennai default
  const [road, setRoad] = useState("12");
  const [height, setHeight] = useState("");
  const [pte, setPte] = useState("");
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
    };
  }, [area, unit, road, use, height, pte, ground, flags]);

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
        Indicative development potential (TNCDBR) — FSI, setbacks, height caps, NOCs and a
        downloadable layout. Updates live; verify with the planning authority.
      </p>

      {surveyBadge && (
        <span className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-[var(--plane)]
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
              {UNITS.map((u) => (
                <button key={u.id} onClick={() => setUnit(u.id)}
                        className={`rounded-md px-2 py-0.5 text-[12px] font-medium transition ${
                          unit === u.id ? "bg-[var(--surface)] text-[var(--ink)] shadow-sm"
                                        : "text-[var(--ink-muted)]"}`}>
                  {u.label}
                </button>
              ))}
            </div>
          </div>
          <input inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)}
                 className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                            px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]" />
          <span className="mt-0.5 block text-[11.5px] text-[var(--ink-muted)]">{areaHelper(num(area), unit)}</span>
        </div>

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
            Advanced height &amp; airport NOC parameters
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
                <span className="text-[12px] text-[var(--ink-2)]">AAI top elevation PTE (m AMSL)</span>
                <input inputMode="decimal" value={pte} onChange={(e) => setPte(e.target.value)}
                       placeholder="from AAI NOCAS — for airport height cap"
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
