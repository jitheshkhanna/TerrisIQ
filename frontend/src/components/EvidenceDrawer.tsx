"use client";

import { useEffect, useState } from "react";
import { fetchScenes, type RiskResult, type Scene } from "@/lib/api";

/* "Engineering, Cadastral & Underwriting Evidence" drawer.
 * Re-exposes what we already computed with explicit units and a source for every line, and
 * is HONEST about the gaps: metrics we don't yet produce (InSAR subsidence in m/yr, SAR flood
 * recurrence %) are labelled as the Phase-B orbital pipeline, not faked. The satellite
 * provenance list is real — live STAC granule IDs and timestamps for this point.
 */

const LEVEL_WORD: Record<number, string> = {
  1: "Very low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very high",
};

function Line({ label, value, source }: { label: string; value: string; source: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-[var(--ink)]">{label}</p>
        <p className="text-[11.5px] text-[var(--ink-muted)]">{source}</p>
      </div>
      <p className="shrink-0 text-[13px] text-[var(--ink-2)]">{value}</p>
    </div>
  );
}

function Scenes({ lat, lng }: { lat: number; lng: number }) {
  const [scenes, setScenes] = useState<Scene[] | null>(null);

  useEffect(() => {
    let live = true;
    fetchScenes(lat, lng).then((s) => live && setScenes(s));
    return () => { live = false; };
  }, [lat, lng]);

  if (scenes === null) {
    return <p className="text-[12px] text-[var(--ink-muted)]">Loading satellite coverage…</p>;
  }
  if (scenes.length === 0) {
    return (
      <p className="text-[12px] text-[var(--ink-muted)]">
        No public scene list available right now. Pixel products (NISAR/OPERA/InSAR) are Phase B.
      </p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {scenes.map((s, i) => (
        <li key={s.granule_id ?? i} className="text-[12px] text-[var(--ink-2)]">
          <span className="font-medium text-[var(--ink)]">{s.platform ?? s.collection}</span>
          {s.datetime ? ` · ${s.datetime.slice(0, 10)}` : ""}
          {s.cloud_cover_pct != null ? ` · ${s.cloud_cover_pct}% cloud` : ""}
          <span className="block truncate text-[11px] text-[var(--ink-muted)]" title={s.granule_id ?? ""}>
            {s.granule_id}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function EvidenceDrawer({ result }: { result: RiskResult }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 border-t border-[var(--hairline)] pt-2">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex min-h-[var(--tap)] w-full items-center justify-between text-[14px]
                   text-[var(--ink-2)] hover:text-[var(--ink)]"
      >
        {open ? "Hide engineering evidence" : "Engineering & underwriting evidence"}
        <svg viewBox="0 0 12 12" className={`h-3 w-3 transition ${open ? "rotate-180" : ""}`} aria-hidden>
          <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="rise space-y-4 pb-2">
          <div className="divide-y divide-[var(--hairline)]">
            <Line label="Flood susceptibility"
                  value={`${LEVEL_WORD[result.flood.level]} (lvl ${result.flood.level}/5)`}
                  source={result.flood.confidence === "high"
                    ? "GCC flood inundation survey + SRTM terrain"
                    : "SRTM 30 m terrain + OpenStreetMap proxies"} />
            {result.scarcity && (
              <Line label="Water scarcity"
                    value={`${LEVEL_WORD[result.scarcity.level]} (lvl ${result.scarcity.level}/5)`}
                    source="CGWB groundwater block assessment" />
            )}
            {result.contamination && (
              <Line label="Contamination proximity"
                    value={`${LEVEL_WORD[result.contamination.level]} (lvl ${result.contamination.level}/5)`}
                    source="CPCB clusters + OSM industrial land use" />
            )}
            {result.crz && (
              <Line label="Coastal regulation (CRZ)"
                    value={`~${result.crz.distance_m} m to coast`}
                    source="OSM coastline proxy — verify against CZMP" />
            )}
            <Line label="Subsidence velocity (LOS)" value="Phase B"
                  source="12-day NISAR/Sentinel-1 InSAR (MintPy) — orbital pipeline pending" />
            <Line label="SAR flood recurrence Φ" value="Phase B"
                  source="OPERA DSWx / NISAR GCOV stack — orbital pipeline pending" />
          </div>

          <div>
            <p className="text-[13px] font-semibold text-[var(--ink)]">Satellite coverage (live)</p>
            <p className="mb-2 text-[11.5px] text-[var(--ink-muted)]">
              Real scenes covering this point, newest first — granule ID, sensor and date.
            </p>
            <Scenes lat={result.latitude} lng={result.longitude} />
          </div>

          <p className="text-[11.5px] leading-snug text-[var(--ink-muted)]">
            Sensor-to-ground-truth: screening fuses open terrain, survey and OSM layers with
            ground stations (CPCB/CGWB). Orbital radar metrics (NISAR/OPERA/InSAR) come online
            in Phase B. Every figure above cites its source; none are estimated beyond it.
          </p>
        </div>
      )}
    </div>
  );
}
