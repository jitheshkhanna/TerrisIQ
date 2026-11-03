"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ScoreCard from "@/components/ScoreCard";
import BuildScopePanel, { type BuildScopePrefill } from "@/components/BuildScopePanel";
import DocumentUploadPanel from "@/components/DocumentUploadPanel";
import LiveNowcast from "@/components/LiveNowcast";
import SearchBar from "@/components/SearchBar";
import ViewSwitcher from "@/components/ViewSwitcher";
import ChatPanel from "@/components/ChatPanel";
import {
  assessRisk,
  fullLabel,
  listCities,
  reportUrl,
  reverseGeocode,
  type City,
  type RiskResult,
} from "@/lib/api";
import type { MapView } from "@/lib/design";

// MapLibre touches window on import, so it must not be server-rendered.
const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-[var(--plane)]" />,
});

// A couple of recognisable places per city, so the empty state is never a blank map.
const EXAMPLES: Record<string, { label: string; lat: number; lng: number }[]> = {
  chennai: [
    { label: "Velachery", lat: 12.9783, lng: 80.2209 },
    { label: "Manali", lat: 13.1647, lng: 80.2587 },
    { label: "Pallikaranai", lat: 12.94, lng: 80.21 },
  ],
  bengaluru: [
    { label: "Koramangala", lat: 12.9352, lng: 77.6245 },
    { label: "Bellandur", lat: 12.9304, lng: 77.6784 },
    { label: "Yelahanka", lat: 13.1007, lng: 77.5963 },
  ],
  hyderabad: [
    { label: "Hitec City", lat: 17.4435, lng: 78.3772 },
    { label: "Kukatpally", lat: 17.4948, lng: 78.3996 },
    { label: "Abids", lat: 17.3891, lng: 78.4761 },
  ],
  mumbai: [
    { label: "Dadar", lat: 19.0176, lng: 72.8448 },
    { label: "Andheri", lat: 19.1197, lng: 72.8468 },
    { label: "Kurla", lat: 19.0726, lng: 72.8845 },
  ],
  delhi: [
    { label: "Dwarka", lat: 28.5921, lng: 77.046 },
    { label: "Yamuna Vihar", lat: 28.6942, lng: 77.2732 },
    { label: "Saket", lat: 28.5245, lng: 77.2066 },
  ],
  pune: [
    { label: "Kothrud", lat: 18.5074, lng: 73.8077 },
    { label: "Hadapsar", lat: 18.5089, lng: 73.926 },
    { label: "Baner", lat: 18.5642, lng: 73.7769 },
  ],
  kolkata: [
    { label: "Salt Lake", lat: 22.5867, lng: 88.4172 },
    { label: "Behala", lat: 22.4989, lng: 88.3197 },
    { label: "Tollygunge", lat: 22.4948, lng: 88.3464 },
  ],
  ahmedabad: [
    { label: "Maninagar", lat: 22.9962, lng: 72.6017 },
    { label: "Bopal", lat: 23.0323, lng: 72.4692 },
    { label: "Naranpura", lat: 23.0562, lng: 72.5613 },
  ],
};

export default function Home() {
  const [cities, setCities] = useState<City[]>([]);
  const [city, setCity] = useState<City | null>(null);
  const [marker, setMarker] = useState<{ lat: number; lng: number } | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number; lng: number; zoom?: number } | null>(null);
  const [result, setResult] = useState<RiskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<MapView>("flood");
  const [showWards, setShowWards] = useState(false);
  const [showViews, setShowViews] = useState(true);
  const [locating, setLocating] = useState(false);
  // Ensures the ?lat&lng deep link (opened from the browser extension) scores only once.
  const deepLinkRef = useRef(false);

  // Carry the scored location into Build Scope: ground elevation (G) and the NOC triggers the
  // spatial engine already knows about (CRZ coast, waterbody, storm drain). Memoised so the
  // panel re-seeds only when the point changes, not on every render.
  const buildPrefill = useMemo<BuildScopePrefill | undefined>(() => {
    if (!result) return undefined;
    const d = result.flood?.details as {
      elevation?: { elevation_m?: number };
      waterbody?: { nearest_waterbody_m?: number };
      drainage?: { nearest_drain_m?: number };
    } | undefined;
    const elev = d?.elevation?.elevation_m;
    const wb = d?.waterbody?.nearest_waterbody_m;
    const drain = d?.drainage?.nearest_drain_m;
    const flags: Record<string, boolean> = {};
    const triggers: string[] = [];
    if (result.crz) { flags.near_coast = true; triggers.push(`CRZ ~${result.crz.distance_m} m to coast`); }
    if (typeof wb === "number" && wb <= 50) { flags.near_water_body = true; triggers.push(`Water body ${wb} m`); }
    if (typeof drain === "number" && drain <= 50) { flags.near_storm_drain = true; triggers.push(`Storm drain ${drain} m`); }
    return {
      key: `${result.latitude.toFixed(5)},${result.longitude.toFixed(5)}`,
      groundElevM: typeof elev === "number" ? elev : null,
      cityName: result.city?.name ?? null,
      flags, triggers,
    };
  }, [result]);

  useEffect(() => {
    listCities()
      .then((list) => {
        setCities(list);

        // Deep link: /?lat=&lng=&city= — how the Terris browser extension hands a place
        // over to the full web app. Accept latitude/longitude as aliases too.
        const params = new URLSearchParams(window.location.search);
        const lat = parseFloat(params.get("lat") ?? params.get("latitude") ?? "");
        const lng = parseFloat(params.get("lng") ?? params.get("longitude") ?? "");
        const slug = params.get("city");
        const hasPoint = Number.isFinite(lat) && Number.isFinite(lng);
        const inBbox = (c: City) =>
          lat >= c.bbox.lat_min && lat <= c.bbox.lat_max &&
          lng >= c.bbox.lng_min && lng <= c.bbox.lng_max;
        const linked =
          (slug ? list.find((c) => c.slug === slug) : undefined) ??
          (hasPoint ? list.find(inBbox) : undefined) ??
          null;

        setCity((current) => current ?? linked ?? list[0] ?? null);

        if (!deepLinkRef.current && hasPoint) {
          deepLinkRef.current = true;
          setFlyTo({ lat, lng, zoom: 15 });
          score(lat, lng, null, slug ?? linked?.slug ?? null);
        }
      })
      .catch(() => setError("Could not load the list of cities."));
    // Run once on mount; `score` is stable for this one-shot deep-link hand-off.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const score = useCallback(async (lat: number, lng: number, label?: string | null,
                                   slug?: string | null) => {
    setMarker({ lat, lng });
    setLoading(true);
    setError(null);
    try {
      // Score first, then fill in the address. A slow geocoder must never hold up the
      // number the user actually came for.
      const assessment = await assessRisk(lat, lng, label ?? null, slug ?? city?.slug ?? null);
      setResult(assessment);
      // Let the map follow the scored place: adopt its city when it differs (a US point
      // returns a "us" pseudo-city centred on the point, so the map leaves India for it;
      // scoring back in India adopts the India city again).
      if (assessment.city && assessment.city.slug !== city?.slug) setCity(assessment.city);
      if (!label) {
        const resolved = await reverseGeocode(lat, lng);
        if (resolved) setResult((prev) => (prev ? { ...prev, address: resolved } : prev));
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The scoring service did not answer. Try again in a moment.",
      );
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [city]);

  const useMyLocation = useCallback((silent = false) => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      if (!silent) setError("Location isn't available on this device. Search an address instead.");
      return;
    }
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        // Snap to the covered city the point falls in, so the score uses the right data.
        const match =
          cities.find(
            (c) =>
              latitude >= c.bbox.lat_min && latitude <= c.bbox.lat_max &&
              longitude >= c.bbox.lng_min && longitude <= c.bbox.lng_max,
          ) ?? null;
        if (match && match.slug !== city?.slug) setCity(match);
        setFlyTo({ lat: latitude, lng: longitude, zoom: 15 });
        score(latitude, longitude, null, match?.slug ?? city?.slug ?? null);
        setLocating(false);
      },
      (err) => {
        setLocating(false);
        if (silent) return; // auto-locate on landing: deny quietly, just show the default city
        setError(
          err.code === err.PERMISSION_DENIED
            ? "Location permission denied. Search an address or tap the map instead."
            : "Couldn't get your location. Search an address or tap the map instead.",
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }, [cities, city, score]);

  // Land -> jump to the visitor's own location, like a maps app. Skipped when a ?lat&lng
  // deep link already picked the place. US points now score too (FEMA), India via the city.
  const autoLocatedRef = useRef(false);
  useEffect(() => {
    if (autoLocatedRef.current || cities.length === 0) return;
    autoLocatedRef.current = true;
    const p = new URLSearchParams(window.location.search);
    const hasPoint =
      Number.isFinite(parseFloat(p.get("lat") ?? p.get("latitude") ?? "")) &&
      Number.isFinite(parseFloat(p.get("lng") ?? p.get("longitude") ?? ""));
    if (!hasPoint) useMyLocation(true);
  }, [cities, useMyLocation]);

  // Mobile bottom sheet with iOS-style snap: PEEK (map dominant, data peeking) <-> FULL
  // (data over the map). The grabber follows the finger, then snaps on release.
  const PEEK_DVH = 80; // collapsed: 80% map, 20% data peeking
  const FULL_DVH = 8;
  const [sheetExpanded, setSheetExpanded] = useState(false);
  const [sheetDragTop, setSheetDragTop] = useState<number | null>(null);
  const sheetDrag = useRef<{ y: number; top: number; moved: number } | null>(null);
  const sheetTop = sheetDragTop ?? (sheetExpanded ? FULL_DVH : PEEK_DVH);
  const onSheetDown = (e: React.PointerEvent) => {
    sheetDrag.current = { y: e.clientY, top: sheetTop, moved: 0 };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onSheetMove = (e: React.PointerEvent) => {
    const d = sheetDrag.current;
    if (!d) return;
    d.moved = Math.max(d.moved, Math.abs(e.clientY - d.y));
    const dvh = ((e.clientY - d.y) / window.innerHeight) * 100;
    setSheetDragTop(Math.max(FULL_DVH, Math.min(PEEK_DVH, d.top + dvh)));
  };
  const onSheetUp = () => {
    const d = sheetDrag.current;
    if (!d) return;
    if (d.moved < 6) setSheetExpanded((v) => !v); // a tap on the grabber toggles
    else setSheetExpanded((sheetDragTop ?? d.top) < (PEEK_DVH + FULL_DVH) / 2);
    setSheetDragTop(null);
    sheetDrag.current = null;
  };

  const examples = (city && EXAMPLES[city.slug]) || [];

  const panel = (
    <>
      <SearchBar
        city={city?.slug}
        placeholder="Search a place in India or the US, or paste a Maps link"
        onUseLocation={() => useMyLocation(false)}
        locating={locating}
        onSelect={(found) => {
          setFlyTo({ lat: found.latitude, lng: found.longitude });
          score(found.latitude, found.longitude, fullLabel(found));
        }}
      />

      {!result && !loading && !error && (
        <div className="card mt-3 p-5">
          <p className="text-[16px] leading-relaxed text-[var(--ink-2)]">
            Check flooding, water pollution and water shortage for any plot.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {examples.map((example) => (
              <button
                key={example.label}
                onClick={() => {
                  setFlyTo({ lat: example.lat, lng: example.lng });
                  score(example.lat, example.lng, `${example.label}, ${city?.name ?? ""}`);
                }}
                className="min-h-[var(--tap)] rounded-full border border-[var(--edge)] px-4
                           text-[15px] text-[var(--ink-2)] transition hover:border-[var(--ink)]
                           hover:text-[var(--ink)]"
              >
                {example.label}
              </button>
            ))}
          </div>
          <p className="mt-4 text-[14px] text-[var(--ink-muted)]">Or tap the map.</p>
        </div>
      )}

      {loading && (
        <div className="card mt-3 p-5" aria-live="polite" aria-busy="true">
          <span className="sr-only">Scoring this location</span>
          <div className="h-3.5 w-28 animate-pulse rounded bg-[var(--hairline)]" />
          <div className="mt-3.5 h-12 w-36 animate-pulse rounded bg-[var(--hairline)]" />
          <div className="mt-5 space-y-2.5">
            <div className="h-2.5 w-full animate-pulse rounded bg-[var(--hairline)]" />
            <div className="h-2.5 w-full animate-pulse rounded bg-[var(--hairline)]" />
            <div className="h-2.5 w-2/3 animate-pulse rounded bg-[var(--hairline)]" />
          </div>
        </div>
      )}

      {error && (
        <div className="card mt-3 p-5" role="alert">
          <p className="text-[15px] leading-relaxed text-[var(--ink-2)]">{error}</p>
        </div>
      )}

      {!loading && result && result.flood && (
        <LiveNowcast lat={result.latitude} lng={result.longitude} floodLevel={result.flood.level}
                     region={[result.city.name, result.city.state].filter(Boolean).join(",")} />
      )}

      {!loading && result && (
        <div className="card mt-3 p-5">
          <ScoreCard result={result} />
        </div>
      )}

      {!loading && result && (
        <div className="mt-3">
          <BuildScopePanel prefill={buildPrefill} />
        </div>
      )}

      {!loading && result && (
        <div className="mt-3">
          <DocumentUploadPanel />
        </div>
      )}

      <ChatPanel
        result={result}
        onLocation={(lat, lng, label) => {
          setFlyTo({ lat, lng, zoom: 15 });
          score(lat, lng, label);
        }}
      />

      <footer className="mt-3 px-1 pb-2 text-[12px] leading-relaxed text-[var(--ink-muted)]">
        <p>Screening only. Verify before you buy.</p>
        {/* Moved off the map to keep it clean; OSM (ODbL) and OpenMapTiles require it. */}
        <p className="mt-0.5">
          Map ©{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer"
             className="underline underline-offset-2 hover:text-[var(--ink-2)]">
            OpenStreetMap
          </a>
          {" "}·{" "}
          <a href="https://openmaptiles.org/" target="_blank" rel="noreferrer"
             className="underline underline-offset-2 hover:text-[var(--ink-2)]">
            OpenMapTiles
          </a>
          {" "}·{" "}
          <a href="https://openfreemap.org/" target="_blank" rel="noreferrer"
             className="underline underline-offset-2 hover:text-[var(--ink-2)]">
            OpenFreeMap
          </a>
        </p>
      </footer>
    </>
  );

  // Pinned report button — rendered OUTSIDE the scroll area so the panel content scrolls
  // above it only, never under it. Orange (the 10% accent), dark ink on top.
  const actionBar = !loading && result ? (
    <a
      href={reportUrl(result.latitude, result.longitude, result.address, result.city.slug)}
      target="_blank"
      rel="noreferrer"
      className="flex min-h-[52px] w-full items-center justify-center rounded-xl
                 bg-[var(--accent)] px-4 text-[16px] font-semibold text-[var(--accent-ink)]
                 shadow-[0_12px_30px_-10px_rgba(245,124,0,0.5)]
                 transition hover:bg-[var(--accent-strong)] active:scale-[0.99]"
    >
      Download report
    </a>
  ) : null;

  // A soft fade at the bottom of the scroll area cues that there is more below (Law of
  // continuity) without a "scroll down" label.
  const scrollFade: React.CSSProperties = {
    WebkitMaskImage: "linear-gradient(to bottom, #000 calc(100% - 26px), transparent)",
    maskImage: "linear-gradient(to bottom, #000 calc(100% - 26px), transparent)",
  };

  if (!city) {
    return (
      <main className="fixed inset-0 grid place-items-center bg-[var(--plane)]">
        <p className="text-[15px] text-[var(--ink-2)]">
          {error ?? "Loading cities..."}
        </p>
      </main>
    );
  }

  return (
    <main className="fixed inset-0 overflow-hidden bg-[var(--plane)]">
      <div className="absolute inset-0">
        <MapView
          city={city}
          marker={marker}
          onPick={score}
          view={view}
          showWards={showWards}
          flyTo={flyTo}
          activeWard={result?.administrative.ward ?? null}
          padding={{ left: 420, bottom: 0 }}
        />
      </div>

      {/* Logo stands on its own, top-left. */}
      <header className="pointer-events-none absolute left-0 right-0 top-0 z-30 flex items-start
                         px-4 pt-4 lg:px-6 lg:pt-5">
        <div className="floating pointer-events-auto flex items-center gap-2 px-2.5 py-1.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.png" alt="" aria-hidden className="h-6 w-6" />
          <span className="text-[15px] font-semibold tracking-tight text-[var(--ink)]">TerrisIQ</span>
        </div>
      </header>

      {/* Map-layers control, top-right, open by default. Hidden for US points: those hazard
          layers are Chennai's, with no US equivalent (FEMA is a point lookup, not a tile). */}
      {city?.slug !== "us" && (
        <div className="absolute right-4 top-4 z-30 flex flex-col items-end gap-2 lg:right-6 lg:top-5">
          <button
            onClick={() => setShowViews(!showViews)}
            aria-expanded={showViews}
            className="floating flex min-h-[var(--tap)] items-center gap-2 px-4 text-[15px]
                       font-medium text-[var(--ink-2)] transition hover:text-[var(--ink)]"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden>
              <path d="M8 1.8 14.5 5 8 8.2 1.5 5 8 1.8Z M2.6 8.2 8 10.9l5.4-2.7 M2.6 11.2 8 13.9l5.4-2.7"
                    stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Map
          </button>
          {showViews && (
            <div className="rise w-[260px] sm:w-[280px]">
              <ViewSwitcher
                view={view}
                onChange={setView}
                showWards={showWards}
                onWardsChange={setShowWards}
              />
            </div>
          )}
        </div>
      )}

      {/* Desktop: a floating column over the map; the report button is pinned below the scroll. */}
      <div className="absolute bottom-5 left-6 top-16 z-20 hidden w-[400px] flex-col lg:flex">
        <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto pr-1"
             style={actionBar ? scrollFade : undefined}>
          {panel}
        </div>
        {actionBar && <div className="mt-2 pr-1">{actionBar}</div>}
      </div>

      {/* Mobile: a draggable bottom sheet. Grabber drags map-dominant <-> data-over-map and
          snaps; the report button stays pinned, with content fading under it. */}
      <div className="absolute inset-x-0 bottom-0 z-20 flex flex-col overflow-hidden
                      rounded-t-3xl border-t border-[var(--ring)] bg-[var(--plane)]
                      shadow-[0_-10px_30px_-14px_rgba(11,11,11,0.22)] lg:hidden"
           style={{ top: `${sheetTop}dvh`,
                    transition: sheetDragTop === null ? "top .32s cubic-bezier(.4,0,.2,1)" : "none" }}>
        <div onPointerDown={onSheetDown} onPointerMove={onSheetMove} onPointerUp={onSheetUp}
             onPointerCancel={onSheetUp}
             className="flex-none touch-none cursor-grab pb-1 pt-3 active:cursor-grabbing"
             role="button" aria-label="Drag to expand or collapse the panel">
          <div className="mx-auto h-1.5 w-10 rounded-full bg-[var(--edge)]" aria-hidden />
        </div>
        <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-1"
             style={actionBar ? scrollFade : undefined}>
          {panel}
        </div>
        {actionBar && (
          <div className="flex-none border-t border-[var(--hairline)] bg-[var(--plane)] px-4 pb-5 pt-3">
            {actionBar}
          </div>
        )}
      </div>
    </main>
  );
}
