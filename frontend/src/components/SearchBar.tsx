"use client";

import { useEffect, useRef, useState } from "react";
import { geocode, isShortMapLink, parseLocationInput, type GeocodeResult } from "@/lib/api";

interface Props {
  onSelect: (result: GeocodeResult) => void;
  /** Search is biased to the selected city, so "MG Road" finds the right one. */
  city?: string | null;
  placeholder?: string;
  /** Rendered at the left edge of the bar, e.g. the city picker. */
  leading?: React.ReactNode;
  /** GPS "check where I am" action; the pin button shows when the field is empty. */
  onUseLocation?: () => void;
  /** True while the GPS fix is in flight, so the pin button shows a spinner. */
  locating?: boolean;
}

// Category is a quiet label, not a colour-coded taxonomy. Colour on this screen is
// reserved for risk, so nothing here competes with the hazard ramp.

// Type-ahead hits the geocoder (LocationIQ) per keystroke, which has a rate limit and a
// quota, so we wait a beat and require ≥3 characters, and cache results per session to
// avoid repeat calls for the same query.
const DEBOUNCE_MS = 300;
const MIN_CHARS = 3;

export default function SearchBar({ onSelect, city, placeholder, leading, onUseLocation, locating }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLDivElement>(null);
  // Choosing a result writes its name into the input. Without this guard that change
  // re-triggers the search effect and the dropdown pops straight back open.
  const skipSearch = useRef(false);
  // Per-session geocode cache (key: city|lowercased query) so repeat/returning queries
  // don't re-hit the geocoder.
  const cache = useRef<Map<string, { results: GeocodeResult[]; expanded: string | null }>>(new Map());
  const listId = "place-suggestions";

  const reset = () => {
    setResults([]);
    setExpanded(null);
    setError(null);
    setOpen(false);
    setActive(-1);
  };

  const handleChange = (value: string) => {
    setQuery(value);
    if (value.trim().length < MIN_CHARS) reset();
  };

  const choose = (result: GeocodeResult) => {
    skipSearch.current = true;
    onSelect(result);
    setQuery(result.label);
    setResults([]);
    setExpanded(null);
    setOpen(false);
    setActive(-1);
  };

  useEffect(() => {
    if (skipSearch.current) {
      skipSearch.current = false;
      return;
    }
    const term = query.trim();
    if (term.length < MIN_CHARS) return;

    // Pasted a Google Maps link or bare lat,lng? Use the exact pin — skip the geocoder.
    const pinned = parseLocationInput(term);
    if (pinned) {
      setResults([pinned]);
      setExpanded(null);
      setError(null);
      setActive(0);
      setOpen(true);
      setBusy(false);
      return;
    }
    // A short share link hides its coordinates behind a redirect we can't follow here.
    if (isShortMapLink(term)) {
      reset();
      setError("Open the short link, then paste the full google.com/maps URL from the address bar.");
      return;
    }

    // Serve a cached result instantly — no geocoder call for a query we've already seen.
    const cacheKey = `${city ?? ""}|${term.toLowerCase()}`;
    const hit = cache.current.get(cacheKey);
    if (hit) {
      setResults(hit.results);
      setExpanded(hit.expanded);
      setActive(-1);
      setOpen(true);
      setError(hit.results.length === 0 ? "Nothing found. Try a locality, street or landmark." : null);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const body = await geocode(term, city, controller.signal);
        cache.current.set(cacheKey, { results: body.results, expanded: body.expanded });
        setResults(body.results);
        setExpanded(body.expanded);
        setActive(-1);
        setOpen(true);
        if (body.results.length === 0) {
          setError("Nothing found near Chennai. Try a locality, street or landmark.");
        }
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setBusy(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, city]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[active >= 0 ? active : 0]);
    }
  };

  return (
    <div ref={box} className="relative">
      <div className="floating relative flex items-center">
        {leading}
        <div className="relative flex min-w-0 flex-1 items-center">
        <svg
          className="pointer-events-none absolute left-3.5 h-[18px] w-[18px] text-[var(--ink-muted)]"
          viewBox="0 0 16 16" fill="none" aria-hidden
        >
          <circle cx="7" cy="7" r="4.6" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10.6 10.6 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder ?? "Bus stop, street, landmark, area"}
          aria-label="Search a bus stop, street, landmark or area"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          className="min-h-[54px] w-full min-w-0 rounded-2xl border border-transparent bg-transparent
                     py-3 pl-10 pr-12 text-[16px] text-[var(--ink)]
                     placeholder:text-[var(--ink-muted)] focus:outline-none"
        />
        <div className="absolute right-3 flex items-center gap-2">
          {(busy || locating) && (
            <span
              className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--hairline)]
                         border-t-[var(--ink-2)]"
              aria-label={locating ? "Finding your location" : "Searching"}
            />
          )}
          {query && !busy && (
            <button
              onClick={() => {
                setQuery("");
                reset();
              }}
              aria-label="Clear search"
              className="flex h-9 w-9 items-center justify-center text-[20px] leading-none
                         text-[var(--ink-muted)] transition hover:text-[var(--ink)]"
            >
              &times;
            </button>
          )}
          {!query && !busy && !locating && onUseLocation && (
            <button
              onClick={onUseLocation}
              aria-label="Use my current location"
              title="Use my current location"
              className="flex h-9 w-9 items-center justify-center text-[var(--ink-muted)]
                         transition hover:text-[var(--ink)]"
            >
              <svg viewBox="0 0 20 20" className="h-[19px] w-[19px]" fill="none" aria-hidden>
                <circle cx="10" cy="10" r="3.4" stroke="currentColor" strokeWidth="1.6" />
                <path d="M10 1.5v2.6M10 15.9v2.6M18.5 10h-2.6M4.1 10H1.5"
                      stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>
        </div>
      </div>

      {expanded && open && (
        <p className="mt-2 px-1 text-[13px] text-[var(--ink-muted)]">
          Looking for <span className="text-[var(--ink-2)]">{expanded}</span>
        </p>
      )}
      {error && <p className="mt-2 px-1 text-[14px] text-[var(--ink-2)]">{error}</p>}

      {open && results.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="floating quiet-scroll rise absolute z-20 mt-2 max-h-[46vh] w-full
                     overflow-auto py-1.5"
        >
          {results.map((result, index) => (
            <li key={`${result.latitude},${result.longitude},${result.label}`} role="option"
                aria-selected={index === active}>
              <button
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(result)}
                className={`flex min-h-[56px] w-full items-start justify-between gap-3 px-4 py-3
                            text-left transition-colors
                            ${index === active ? "bg-[var(--plane)]" : ""}`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[16px] font-medium text-[var(--ink)]">
                    {result.label}
                  </span>
                  {result.context && (
                    <span className="mt-0.5 block truncate text-[13px] text-[var(--ink-muted)]">
                      {result.context}
                    </span>
                  )}
                </span>
                <span className="eyebrow mt-1.5 shrink-0">{result.category}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
