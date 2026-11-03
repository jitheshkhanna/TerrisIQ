"use client";

import { useState } from "react";
import { type Fact, type RiskResult, type RiskScore } from "@/lib/api";
import { gradeFill, gradeText, gradeTrack } from "@/lib/design";
import EvidenceDrawer from "@/components/EvidenceDrawer";

/* The card answers three questions in the order people ask them:
 *   1. Should I worry?        -> one verdict word and a 5-step meter
 *   2. About what?            -> three rows, each a level and a few short findings
 *   3. Can I trust this?      -> one small chip; the long explanations sit behind a toggle
 * Letter grades are gone from the screen: "B" never told anyone whether to worry.
 */

const SHORT_MEANING: Record<number, string> = {
  1: "No major red flags",
  2: "A few minor flags",
  3: "Some issues to check",
  4: "Serious issues found",
  5: "Major red flags",
};

const DEPTH_CHIP: Record<string, string> = {
  deep: "Full flood survey",
  moderate: "Partial data",
  baseline: "Limited data",
};

const LEVEL_WORD: Record<number, string> = {
  1: "Very low",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Very high",
};

function Meter({ level, grade, size = "lg" }: { level: number; grade: string; size?: "lg" | "sm" }) {
  const fill = gradeFill(grade);
  const track = gradeTrack(grade);
  const big = size === "lg";
  return (
    <div className={`flex items-end ${big ? "gap-1.5" : "gap-[3px]"}`} role="img"
         aria-label={`${LEVEL_WORD[level]} risk, ${level} of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className="rounded-[3px]"
          style={{
            width: big ? 22 : 6,
            height: big ? 8 + i * 5 : 6 + i * 2,
            background: i <= level ? fill : track,
          }}
        />
      ))}
    </div>
  );
}

const FACT_DOT: Record<string, string> = {
  high: "var(--critical)",
  medium: "var(--warning)",
  low: "var(--edge)",
  good: "var(--good)",
};

function Chip({ fact }: { fact: Fact }) {
  if (fact.level === "info") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed
                       border-[var(--edge)] px-2.5 py-1 text-[13px] text-[var(--ink-muted)]">
        <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
          <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <path d="M6 5.2v3M6 3.4v.1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        {fact.text}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--plane)] px-2.5 py-1
                     text-[13px] text-[var(--ink)]">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: FACT_DOT[fact.level] }}
            aria-hidden />
      {fact.text}
    </span>
  );
}

const ICONS: Record<string, React.ReactNode> = {
  // A plain water drop: the wave-plus-drop version read as a bell at 20px.
  flood: (
    <path d="M8 1.8C8 1.8 3.2 7.2 3.2 10.2a4.8 4.8 0 0 0 9.6 0C12.8 7.2 8 1.8 8 1.8Z"
          stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round" />
  ),
  contamination: (
    <path d="M6 2h4M6.5 2v4L3 12.5A1 1 0 0 0 3.9 14h8.2a1 1 0 0 0 .9-1.5L9.5 6V2M5 10h6"
          stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  ),
  scarcity: (
    <path d="M8 1.8v1.6M8 12.6v1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M1.8 8h1.6M12.6 8h1.6M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1M8 5.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6Z"
          stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
  ),
};

function Row({ kind, title, block }: { kind: string; title: string; block: RiskScore | null }) {
  const icon = (
    <svg viewBox="0 0 16 16" className="h-5 w-5 shrink-0 text-[var(--ink-2)]" aria-hidden>
      {ICONS[kind]}
    </svg>
  );

  if (!block) {
    return (
      <div className="flex items-center gap-3 py-3.5 opacity-70">
        {icon}
        <span className="flex-1 text-[15px] font-medium text-[var(--ink-2)]">{title}</span>
        <span className="text-[14px] text-[var(--ink-muted)]">No data</span>
      </div>
    );
  }

  // Info chips are data gaps, not risks: keep them, but after the findings.
  const facts = [...block.facts].sort((a, b) =>
    Number(a.level === "info") - Number(b.level === "info")).slice(0, 3);

  return (
    <div className="py-3.5">
      <div className="flex items-center gap-3">
        {icon}
        <span className="flex-1 text-[15px] font-medium text-[var(--ink)]">{title}</span>
        <span className="text-[14px] font-medium" style={{ color: gradeText(block.grade) }}>
          {LEVEL_WORD[block.level]}
        </span>
        <Meter level={block.level} grade={block.grade} size="sm" />
      </div>
      {facts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5 pl-8">
          {facts.map((f) => (
            <Chip key={f.text} fact={f} />
          ))}
        </div>
      )}
    </div>
  );
}

function Details({ result }: { result: RiskResult }) {
  const [open, setOpen] = useState(false);
  const sections: [string, RiskScore | null][] = [
    ["Flood", result.flood],
    ["Groundwater contamination", result.contamination],
    ["Water scarcity", result.scarcity],
  ];
  return (
    <div className="border-t border-[var(--hairline)] pt-2">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex min-h-[var(--tap)] w-full items-center justify-between text-[14px]
                   text-[var(--ink-2)] hover:text-[var(--ink)]"
      >
        {open ? "Hide details" : "See details"}
        <svg viewBox="0 0 12 12" className={`h-3 w-3 transition ${open ? "rotate-180" : ""}`} aria-hidden>
          <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="rise space-y-4 pb-2 text-[13px] leading-relaxed text-[var(--ink-2)]">
          <p>
            <span className="font-medium text-[var(--ink)]">{result.composite_score}/100</span>
            {" "}overall &middot; {result.confidence} confidence
          </p>
          {result.grade_floor_reason && <p>{result.grade_floor_reason}</p>}
          {result.evidence_ceiling_reason && <p>{result.evidence_ceiling_reason}</p>}
          {result.coverage_note && <p>{result.coverage_note}</p>}
          {sections.map(([name, block]) =>
            block ? (
              <div key={name}>
                <p className="font-medium text-[var(--ink)]">
                  {name} &middot; {block.score}/100
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-4">
                  {block.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
          <p className="text-[12px] text-[var(--ink-muted)]">
            {result.latitude.toFixed(5)}, {result.longitude.toFixed(5)}
          </p>
        </div>
      )}
    </div>
  );
}

export default function ScoreCard({ result }: { result: RiskResult }) {
  const admin = result.administrative;
  const adjusted = result.grade_floor_applied
    ? "Raised: one serious issue"
    : result.evidence_ceiling_applied
      ? "Capped: limited data here"
      : null;

  return (
    <div className="rise">
      {/* 1. Should I worry? */}
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[28px] font-semibold leading-tight tracking-tight"
             style={{ color: gradeText(result.composite_grade) }}>
            {result.verdict}
          </p>
          <p className="mt-0.5 text-[15px] text-[var(--ink-2)]">{SHORT_MEANING[result.level]}</p>
        </div>
        <Meter level={result.level} grade={result.composite_grade} />
      </div>

      {/* Where, and how much to trust it */}
      <p className="mt-4 truncate text-[15px] text-[var(--ink)]" title={result.address ?? undefined}>
        {result.address ?? "Dropped pin"}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="rounded-full bg-[var(--plane)] px-2.5 py-1 text-[13px] font-medium text-[var(--ink)]">
          {admin.inside_gcc ? admin.summary : "Outside city limits"}
          {admin.ward_is_official === false && admin.inside_gcc && " (approx.)"}
        </span>
        <span className="rounded-full border border-[var(--hairline)] px-2.5 py-1 text-[13px] text-[var(--ink-2)]">
          {DEPTH_CHIP[result.city.depth]}
        </span>
        {adjusted && (
          <span className="rounded-full border border-[var(--hairline)] px-2.5 py-1 text-[13px] text-[var(--ink-2)]">
            {adjusted}
          </span>
        )}
      </div>

      {/* Coastal regulation (CRZ) — only when the plot is near the coast. */}
      {result.crz && (() => {
        const danger = result.crz.band === "no-development";
        const c = danger ? "var(--critical)" : "var(--warning)";
        return (
          <div className="mt-3 flex items-start gap-2.5 rounded-xl border px-3 py-2.5"
               style={{ background: `color-mix(in srgb, ${c} 8%, var(--surface))`,
                        borderColor: `color-mix(in srgb, ${c} 26%, transparent)` }}>
            <svg viewBox="0 0 16 16" className="mt-0.5 h-4 w-4 shrink-0" style={{ color: c }} aria-hidden>
              <path d="M1 11c2-1.4 3-1.4 5 0s3 1.4 5 0 3-1.4 5 0M3 7.5 8 2l5 5.5"
                    stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round"
                    strokeLinejoin="round" />
            </svg>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-[var(--ink)]">Coastal regulation (CRZ)</p>
              <p className="mt-0.5 text-[12.5px] leading-snug text-[var(--ink-2)]">{result.crz.headline}</p>
              <p className="mt-0.5 text-[11.5px] leading-snug text-[var(--ink-muted)]">{result.crz.note}</p>
            </div>
          </div>
        );
      })()}

      {/* 2. About what? */}
      <div className="mt-3 divide-y divide-[var(--hairline)] border-t border-[var(--hairline)]">
        <Row kind="flood" title="Flooding" block={result.flood} />
        <Row kind="contamination" title="Water pollution" block={result.contamination} />
        <Row kind="scarcity" title="Water shortage" block={result.scarcity} />
      </div>

      {/* 3. Everything else, on request */}
      <Details result={result} />

      {/* 4. Engineering, cadastral & underwriting evidence — units + sources + live scenes */}
      <EvidenceDrawer result={result} />
    </div>
  );
}
