"use client";

import { useRef, useState } from "react";
import { parseDocument, type DocFields, type DocParseResult, type DocType } from "@/lib/api";

/* Consented Patta / EC / FMB upload. The user drops their own land document, ticks an explicit
 * consent box, and sees the extracted title fields. Privacy is front and centre: parsing uses
 * a vision model (an external service), so nothing is sent until consent is given, and the copy
 * says so. The backend stores nothing; see api/documents.py.
 */

const DOC_TYPES: { id: DocType; label: string }[] = [
  { id: "patta", label: "Patta / Chitta" },
  { id: "ec", label: "Encumbrance Cert." },
  { id: "sale_deed", label: "Sale deed" },
  { id: "tslr", label: "TSLR" },
  { id: "fmb", label: "FMB sketch" },
  { id: "other", label: "Other" },
];

const MAX_MB = 8;

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="text-[12px] text-[var(--ink-muted)]">{label}</span>
      <span className="text-right text-[13px] font-medium text-[var(--ink)]">{value}</span>
    </div>
  );
}

function Extracted({ fields }: { fields: DocFields }) {
  const names = (fields.owner_names ?? []).filter(Boolean);
  const survey = [fields.survey_number, fields.sub_division].filter(Boolean).join("/");
  const place = [fields.village, fields.taluk, fields.district].filter(Boolean).join(", ");
  const mortgages = fields.mortgages ?? [];
  const unreleased = mortgages.filter((m) => m?.created && !m?.released);

  return (
    <div className="rise mt-3">
      <div className="divide-y divide-[var(--hairline)]">
        {survey && <Field label="Survey number" value={survey} />}
        {names.length > 0 && <Field label="Owner(s)" value={names.join(", ")} />}
        {place && <Field label="Village / taluk / district" value={place} />}
        {fields.document_number && <Field label="Document no." value={String(fields.document_number)} />}
        {fields.execution_date && <Field label="Executed" value={String(fields.execution_date)} />}
        {fields.transaction_value_inr != null &&
          <Field label="Value" value={`₹${fields.transaction_value_inr}`} />}
      </div>

      {/* Encumbrance / mortgage flag — the EC due-diligence signal. */}
      {mortgages.length > 0 && (
        <div className="mt-3 flex items-start gap-2.5 rounded-xl border px-3 py-2.5"
             style={{
               background: `color-mix(in srgb, var(--${unreleased.length ? "critical" : "good"}) 8%, var(--surface))`,
               borderColor: `color-mix(in srgb, var(--${unreleased.length ? "critical" : "good"}) 26%, transparent)`,
             }}>
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full"
                style={{ background: `var(--${unreleased.length ? "critical" : "good"})` }} aria-hidden />
          <p className="text-[12.5px] leading-snug text-[var(--ink-2)]">
            {unreleased.length
              ? `${unreleased.length} mortgage(s) recorded without a release deed — a live encumbrance to verify with CERSAI and the EC.`
              : `${mortgages.length} mortgage(s) found, all showing a release.`}
          </p>
        </div>
      )}
    </div>
  );
}

export default function DocumentUploadPanel() {
  const [docType, setDocType] = useState<DocType>("patta");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<DocParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | null) => {
    setError(null);
    setRes(null);
    if (f && f.size > MAX_MB * 1024 * 1024) { setError(`File exceeds ${MAX_MB} MB.`); return; }
    setFile(f);
  };

  const submit = async () => {
    if (!file) { setError("Choose a PDF or image first."); return; }
    setBusy(true);
    setError(null);
    try {
      setRes(await parseDocument(file, docType, consent));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not parse the document.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-[var(--hairline)] bg-[var(--surface)] p-4 sm:p-5">
      <h2 className="text-[17px] font-semibold text-[var(--ink)]">Verify a document</h2>
      <p className="mt-0.5 text-[13px] text-[var(--ink-2)]">
        Upload your own Patta, EC or FMB to extract the survey number, owner and encumbrance
        chain. Your document is read only to produce this result and is not stored.
      </p>

      <div className="mt-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {DOC_TYPES.map((d) => (
            <button key={d.id} onClick={() => setDocType(d.id)}
                    className={`rounded-full px-3 py-1.5 text-[13px] font-medium transition ${
                      docType === d.id
                        ? "bg-[var(--ink)] text-[var(--surface)]"
                        : "bg-[var(--plane)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
              {d.label}
            </button>
          ))}
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0] ?? null); }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border
                      border-dashed px-4 py-6 text-center transition ${
                        drag ? "border-[var(--ink-2)] bg-[var(--plane)]" : "border-[var(--hairline)]"}`}
        >
          <input ref={inputRef} type="file" accept=".pdf,image/*" className="hidden"
                 onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          <p className="text-[14px] text-[var(--ink)]">
            {file ? file.name : "Drop a PDF or image, or click to choose"}
          </p>
          <p className="mt-0.5 text-[11.5px] text-[var(--ink-muted)]">PDF or image, up to {MAX_MB} MB</p>
        </div>

        {/* Consent */}
        <label className="flex items-start gap-2.5 text-[12.5px] leading-snug text-[var(--ink-2)]">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)}
                 className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--ink)]" />
          <span>
            I consent to this document being sent to the vision parser to extract its fields.
            Without consent, only an embedded text layer (if any) is read on the server.
          </span>
        </label>

        {error && <p className="text-[13px] text-[var(--critical)]">{error}</p>}

        <button onClick={submit} disabled={busy || !file}
                className="w-full rounded-lg bg-[var(--ink)] px-3 py-2.5 text-[14px] font-semibold
                           text-[var(--surface)] disabled:opacity-50">
          {busy ? "Reading…" : "Extract fields"}
        </button>
      </div>

      {res && (
        <div className="mt-2">
          {res.fields ? <Extracted fields={res.fields} /> : (
            res.text_excerpt ? (
              <p className="rise mt-3 whitespace-pre-wrap rounded-xl bg-[var(--plane)] p-3 text-[12px]
                            leading-relaxed text-[var(--ink-2)]">{res.text_excerpt.slice(0, 600)}</p>
            ) : null
          )}
          {res.note && <p className="mt-2 text-[12px] text-[var(--ink-muted)]">{res.note}</p>}
          <p className="mt-2 text-[11.5px] leading-snug text-[var(--ink-muted)]">{res.disclaimer}</p>
        </div>
      )}
    </section>
  );
}
