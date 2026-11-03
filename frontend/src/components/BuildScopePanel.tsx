"use client";

import { useState } from "react";
import {
  buildScope, downloadLayout, ulpinLookup,
  type BuildScope, type BuildScopeInput, type BuildUse, type UlpinResult,
} from "@/lib/api";

/* Build Scope — the TNCDBR development-potential calculator.
 * Pure-input, pure-output: no map or scored point needed, so it stands alone. Every number
 * carries the engine's `basis`; the panel never invents a figure the API did not return.
 */

const USES: { id: BuildUse; label: string }[] = [
  { id: "residential", label: "Residential" },
  { id: "commercial", label: "Commercial" },
  { id: "mixed", label: "Mixed use" },
  { id: "industrial", label: "Industrial" },
  { id: "institutional", label: "Institutional" },
  { id: "plotted_layout", label: "Plotted layout" },
];

function Num({ label, value, onChange, placeholder, hint }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; hint?: string;
}) {
  return (
    <label className="block">
      <span className="text-[13px] font-medium text-[var(--ink-2)]">{label}</span>
      <input
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                   px-3 py-2 text-[15px] text-[var(--ink)] outline-none
                   focus:border-[var(--ink-2)]"
      />
      {hint && <span className="mt-0.5 block text-[11.5px] text-[var(--ink-muted)]">{hint}</span>}
    </label>
  );
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

function num(v: string): number | null {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

function Results({ s, input }: { s: BuildScope; input: BuildScopeInput }) {
  const [dl, setDl] = useState<string | null>(null);
  const netH = s.height.net_permissible_m;
  const activeNocs = s.noc_checklist.filter((n) => n.required);

  const grab = async (fmt: "dxf" | "geojson") => {
    setDl(fmt);
    try {
      await downloadLayout(input, fmt);
    } catch {
      /* swallow — the button just re-enables */
    } finally {
      setDl(null);
    }
  };

  return (
    <div className="rise mt-4 space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label="Max FSI (with premium)" value={s.fsi.max_with_premium.toFixed(2)}
              sub={`Normal ${s.fsi.normal} + premium ${s.fsi.premium_added}`} />
        <Stat label="Max built-up" value={`${Math.round(s.built_up_area_sqm.at_premium_fsi).toLocaleString()} m²`}
              sub={`${Math.round(s.built_up_area_sqm.at_normal_fsi).toLocaleString()} m² at normal FSI`} />
        <Stat label="Ground coverage" value={`${Math.round(s.ground_coverage.fraction * 100)}%`}
              sub={`${Math.round(s.ground_coverage.max_footprint_sqm).toLocaleString()} m² footprint`} />
        <Stat label="Net permissible height"
              value={netH != null ? `${netH} m` : "—"}
              sub={netH != null ? `capped by ${s.height.constrained_by}` : "add AAI PTE + ground elev."} />
        <Stat label="Setbacks" value={`${s.setbacks.front_m} / ${s.setbacks.side1_m} / ${s.setbacks.rear_m} m`}
              sub={`front / side / rear · ${s.setbacks.regime}`} />
        <Stat label="Parking" value={`${s.parking.car_equivalent_spaces} ECS`}
              sub={s.yield.approx_dwelling_units != null ? `~${s.yield.approx_dwelling_units} units` : s.osr.required ? `OSR ${s.osr.area_sqm} m²` : "car-equiv. spaces"} />
      </div>

      {/* NOC checklist */}
      <div>
        <p className="text-[13px] font-semibold text-[var(--ink)]">Clearances to obtain</p>
        {activeNocs.length === 0 ? (
          <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
            No clearances triggered by these inputs. Spatial NOCs (CRZ, lake, heritage) depend
            on the plot location — declare them to check.
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

      {/* Layout export */}
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

function UlpinField() {
  const [code, setCode] = useState("");
  const [res, setRes] = useState<UlpinResult | null>(null);
  const [busy, setBusy] = useState(false);

  const look = async () => {
    if (!code.trim()) return;
    setBusy(true);
    try {
      setRes(await ulpinLookup(code.trim()));
    } catch {
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-dashed border-[var(--hairline)] p-3">
      <p className="text-[13px] font-medium text-[var(--ink-2)]">Survey number / ULPIN (optional)</p>
      <div className="mt-1.5 flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && look()}
          placeholder="e.g. 33CHN0014502B0"
          className="min-w-0 flex-1 rounded-lg border border-[var(--hairline)] bg-[var(--surface)]
                     px-3 py-2 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--ink-2)]"
        />
        <button onClick={look} disabled={busy}
                className="rounded-lg bg-[var(--ink)] px-3 py-2 text-[13px] font-medium
                           text-[var(--surface)] disabled:opacity-50">
          {busy ? "…" : "Check"}
        </button>
      </div>
      {res && (
        <p className="mt-2 text-[12px] leading-snug text-[var(--ink-muted)]">{res.message}</p>
      )}
    </div>
  );
}

export default function BuildScopePanel() {
  const [use, setUse] = useState<BuildUse>("residential");
  const [area, setArea] = useState("");
  const [road, setRoad] = useState("");
  const [height, setHeight] = useState("");
  const [pte, setPte] = useState("");
  const [ground, setGround] = useState("");
  const [result, setResult] = useState<BuildScope | null>(null);
  const [lastInput, setLastInput] = useState<BuildScopeInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    const a = num(area), r = num(road);
    if (a == null || a <= 0) { setError("Enter a plot area in m²."); return; }
    if (r == null || r < 0) { setError("Enter the abutting road width in m."); return; }
    const input: BuildScopeInput = {
      plot_area_sqm: a, road_width_m: r, use,
      proposed_height_m: num(height), pte_amsl_m: num(pte), ground_elev_amsl_m: num(ground),
    };
    setError(null);
    setBusy(true);
    try {
      const res = await buildScope(input);
      setResult(res.scope);
      setLastInput(input);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not compute.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-[var(--hairline)] bg-[var(--surface)] p-4 sm:p-5">
      <h2 className="text-[17px] font-semibold text-[var(--ink)]">Build Scope</h2>
      <p className="mt-0.5 text-[13px] text-[var(--ink-2)]">
        Indicative development potential (TNCDBR) — FSI, setbacks, height caps, NOCs and a
        downloadable layout. Screening estimate; verify with the planning authority.
      </p>

      <div className="mt-4 space-y-3">
        <UlpinField />

        <div>
          <span className="text-[13px] font-medium text-[var(--ink-2)]">Intended use</span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {USES.map((u) => (
              <button key={u.id} onClick={() => setUse(u.id)}
                      className={`rounded-full px-3 py-1.5 text-[13px] font-medium transition ${
                        use === u.id
                          ? "bg-[var(--ink)] text-[var(--surface)]"
                          : "bg-[var(--plane)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
                {u.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Num label="Plot area (m²)" value={area} onChange={setArea} placeholder="1200" />
          <Num label="Road width (m)" value={road} onChange={setRoad} placeholder="18"
               hint="drives premium FSI" />
          <Num label="Proposed height (m)" value={height} onChange={setHeight} placeholder="optional" />
          <div />
          <Num label="AAI top elev. PTE (m AMSL)" value={pte} onChange={setPte} placeholder="optional"
               hint="from AAI NOCAS" />
          <Num label="Ground elev. (m AMSL)" value={ground} onChange={setGround} placeholder="optional"
               hint="net height = PTE − ground" />
        </div>

        {error && <p className="text-[13px] text-[var(--critical)]">{error}</p>}

        <button onClick={run} disabled={busy}
                className="w-full rounded-lg bg-[var(--ink)] px-3 py-2.5 text-[14px] font-semibold
                           text-[var(--surface)] disabled:opacity-50">
          {busy ? "Computing…" : "Compute development potential"}
        </button>
      </div>

      {result && lastInput && <Results s={result} input={lastInput} />}
    </section>
  );
}
