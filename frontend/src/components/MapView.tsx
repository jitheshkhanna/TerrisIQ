"use client";

import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { ALL_DATA_LAYERS, FLOOD_RAMP, MAP, VIEW_LAYERS, type MapView } from "@/lib/design";
import type { City } from "@/lib/api";

export const CHENNAI_CENTER: [number, number] = [80.2707, 13.0827];

interface Props {
  city: City;
  marker: { lat: number; lng: number } | null;
  onPick: (lat: number, lng: number) => void;
  view: MapView;
  showWards: boolean;
  flyTo: { lat: number; lng: number; zoom?: number } | null;
  /** Ward number of the current result, outlined on the map. */
  activeWard: string | null;
  padding?: { left: number; bottom: number };
}

// Positron: a desaturated basemap. Roads and labels recede to grey so the hazard ramp
// is the only saturated thing on screen, which is the whole point of the map.
const BASEMAP = "https://tiles.openfreemap.org/styles/positron";

// MapLibre parses tiles in a module Web Worker. Turbopack cannot resolve that worker
// chunk ("chunk path empty but not in a worker"), which kills the worker and leaves a
// blank canvas. Serving it from public/ bypasses the bundler; scripts/copy-maplibre-
// worker.mjs keeps the copy current via npm predev/prebuild.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

// Layer ids are stable across cities; only the URL changes, so switching city swaps
// the data in place rather than rebuilding the map.
const SOURCE_IDS = [
  "zones", "wards", "flood_zones", "waterbodies", "industrial_osm",
  "swd", "flood_hotspots", "dumpsites", "low_lying",
] as const;

const REMOTE: Record<string, string> = {
  industrial_osm: "industrial",
};

function layerUrl(slug: string, id: string) {
  return `/api/v1/layers/${slug}/${REMOTE[id] ?? id}`;
}

export default function MapView({
  city,
  marker,
  onPick,
  view,
  showWards,
  flyTo,
  activeWard,
  padding,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markerEl = useRef<Marker | null>(null);
  const ready = useRef(false);
  const onPickRef = useRef(onPick);
  const cityRef = useRef(city);
  const viewRef = useRef(view);
  const wardsRef = useRef(showWards);
  useEffect(() => {
    onPickRef.current = onPick;
    cityRef.current = city;
    viewRef.current = view;
    wardsRef.current = showWards;
  }, [onPick, city, view, showWards]);

  useEffect(() => {
    if (map.current || !container.current) return;
    const node = container.current;

    // MapLibre fixes its transform at construction. Built against a zero-size container
    // it decides no tiles are needed and never revisits that: the canvas can be resized
    // afterwards and the map still renders nothing but our own GeoJSON, with every
    // source reporting "loaded". So wait until the container has real dimensions before
    // constructing anything. This also covers a map mounted inside a hidden tab.
    let cancelled = false;
    let sizeWatcher: ResizeObserver | null = null;
    let teardown: (() => void) | null = null;

    const start = () => {
      if (cancelled || map.current) return;

    const instance = new MapLibreMap({
        container: node,
        style: BASEMAP,
        // Read through the ref: the map is built once, and the effect below moves it
        // when the city changes. Referencing the prop here would make this effect
        // reactive and rebuild the whole map on every switch.
        center: [cityRef.current.centre.lng, cityRef.current.centre.lat],
        zoom: 10.8,
        maxBounds: [
          [cityRef.current.bbox.lng_min - 0.35, cityRef.current.bbox.lat_min - 0.35],
          [cityRef.current.bbox.lng_max + 0.35, cityRef.current.bbox.lat_max + 0.35],
        ],
        // The attribution bar is off the map to keep it clean. OpenStreetMap (ODbL) and
        // OpenMapTiles still require credit, which the panel footer carries.
        attributionControl: false,
      });
      map.current = instance;

      instance.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
      instance.addControl(new ScaleControl({ maxWidth: 96, unit: "metric" }), "bottom-left");

      instance.on("error", (event) => {
        // Surfaced in development only: MapLibre emits errors for ordinary things like a
        // missing tile, and a noisy console in production hides real problems.
        if (process.env.NODE_ENV !== "production") {
          const message = (event as unknown as { error?: Error })?.error?.message ?? String(event);
          console.warn("[map]", message);
        }
      });

      const applyVisibility = () => {
        if (!instance.getLayer("flood_zones-fill")) return;
        const on = new Set(VIEW_LAYERS[viewRef.current]);
        for (const id of ALL_DATA_LAYERS) {
          if (instance.getLayer(id)) {
            instance.setLayoutProperty(id, "visibility", on.has(id) ? "visible" : "none");
          }
        }
        for (const id of ["wards-line", "zones-line"]) {
          if (instance.getLayer(id)) {
            instance.setLayoutProperty(id, "visibility", wardsRef.current ? "visible" : "none");
          }
        }
      };

      const addOurLayers = () => {
        // Adding sources while the style is still parsing leaves the basemap in a state
        // where it never requests a single tile: the map shows our GeoJSON and nothing
        // underneath it. Wait for a fully loaded style, every time.
        if (!instance.isStyleLoaded()) return;
        if (instance.getLayer("flood_zones-fill")) return; // already set up
        try {
        for (const id of SOURCE_IDS) {
          instance.addSource(id, { type: "geojson", data: layerUrl(cityRef.current.slug, id) });
        }

        // Hazard sits directly on the basemap, under every line and label.
        instance.addLayer({
          id: "flood_zones-fill",
          type: "fill",
          source: "flood_zones",
          paint: {
            "fill-color": [
              "match",
              ["get", "CATEGORY"],
              "Very Low", FLOOD_RAMP["Very Low"],
              "Low", FLOOD_RAMP.Low,
              "Moderate", FLOOD_RAMP.Moderate,
              "High", FLOOD_RAMP.High,
              "Very High", FLOOD_RAMP["Very High"],
              "transparent",
            ],
            "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.55, 13, 0.4, 16, 0.24],
          },
        });

        instance.addLayer({
          id: "low_lying-fill",
          type: "fill",
          source: "low_lying",
          paint: { "fill-color": FLOOD_RAMP.High, "fill-opacity": 0.42 },
        });

        instance.addLayer({
          id: "waterbodies-fill",
          type: "fill",
          source: "waterbodies",
          paint: { "fill-color": MAP.water, "fill-opacity": 0.45 },
        });
        instance.addLayer({
          id: "waterbodies-line",
          type: "line",
          source: "waterbodies",
          paint: { "line-color": MAP.waterLine, "line-width": 1.2 },
        });

        instance.addLayer({
          id: "industrial_osm-fill",
          type: "fill",
          source: "industrial_osm",
          paint: { "fill-color": MAP.industrial, "fill-opacity": 0.4 },
        });

        // Condition is the useful signal, so failing drains read differently from working
        // ones rather than every drain looking the same.
        instance.addLayer({
          id: "swd-line",
          type: "line",
          source: "swd",
          paint: {
            "line-color": ["case", ["==", ["get", "STATUS"], "Bad"], MAP.drainBad, MAP.drain],
            "line-width": ["case", ["==", ["get", "STATUS"], "Bad"], 1.6, 0.7],
            "line-opacity": 0.8,
          },
        });

        instance.addLayer({
          id: "zones-line",
          type: "line",
          source: "zones",
          paint: { "line-color": MAP.wardLine, "line-width": 1, "line-opacity": 0.22 },
        });
        instance.addLayer({
          id: "wards-line",
          type: "line",
          source: "wards",
          paint: { "line-color": MAP.wardLine, "line-width": 0.5, "line-opacity": 0.11 },
        });

        // The ward containing the current result, drawn on top.
        instance.addLayer({
          id: "wards-active",
          type: "line",
          source: "wards",
          filter: ["==", ["get", "name"], "__none__"],
          paint: { "line-color": MAP.wardLine, "line-width": 2, "line-opacity": 0.85 },
        });
        instance.addLayer({
          id: "wards-active-fill",
          type: "fill",
          source: "wards",
          filter: ["==", ["get", "name"], "__none__"],
          paint: { "fill-color": MAP.wardLine, "fill-opacity": 0.05 },
        });

        instance.addLayer({
          id: "flood_hotspots-circle",
          type: "circle",
          source: "flood_hotspots",
          paint: {
            "circle-radius": 4.5,
            "circle-color": MAP.hotspot,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          },
        });

        instance.addLayer({
          id: "dumpsites-circle",
          type: "circle",
          source: "dumpsites",
          paint: {
            "circle-radius": 6,
            "circle-color": MAP.dumpsite,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });

          ready.current = true;
          applyVisibility();
          instance.getCanvas().style.cursor = "crosshair";
          // The canvas is sized at construction, which can happen a frame before the
          // container has its final size. Without this the map paints into a small corner
          // and the rest of the screen stays white.
          instance.resize();
        } catch (err) {
          // A throw here leaves the basemap up with none of our layers on it, which is
          // easy to mistake for "the data did not load".
          console.error("[map] could not add data layers", err);
        }
      };

      // Waiting only on "load" is a race we lose: with React's development double-mount the
      // style can already be parsed by the time the second instance attaches its handler,
      // and the event never fires again. The map then shows the basemap and none of our
      // data, silently. Check first, subscribe second.
      if (instance.isStyleLoaded()) addOurLayers();
      else instance.once("load", addOurLayers);
      instance.on("styledata", addOurLayers);

      instance.on("click", (event: MapMouseEvent) => {
        onPickRef.current(event.lngLat.lat, event.lngLat.lng);
      });

      // MapLibre sizes its canvas once at construction. If the container is laid out or
      // resized afterwards — a phone rotating, a window resize, the panel crossing the
      // desktop breakpoint, or the map mounting before layout settles — the canvas keeps
      // the old size and the map renders into a corner with white around it. Watch the
      // container and tell the map to catch up.
      const observer = new ResizeObserver(() => instance.resize());
      observer.observe(node);
      // Belt and braces: the observer's first callback can land after the initial paint.
      const raf = requestAnimationFrame(() => instance.resize());
      const settle = setTimeout(() => instance.resize(), 250);

      // React runs mount/unmount/mount in development. If anything in here throws — and
      // remove() can, on a map torn down mid-load — the refs below never get cleared, the
      // second mount sees a non-null map.current and returns early, and the map left in
      // the DOM is the one we already destroyed. That is the whole white-screen failure,
      // so every step is isolated and the refs are cleared unconditionally.
      teardown = () => {
        cancelAnimationFrame(raf);
        clearTimeout(settle);
        try {
          observer.disconnect();
        } catch {
          /* observer already gone */
        }
        try {
          instance.remove();
        } catch {
          /* map was mid-load; nothing left to clean up */
        }
        map.current = null;
        ready.current = false;
      };
    };

    if (node.clientWidth > 0 && node.clientHeight > 0) {
      start();
    } else {
      sizeWatcher = new ResizeObserver(() => {
        if (node.clientWidth > 0 && node.clientHeight > 0) {
          sizeWatcher?.disconnect();
          sizeWatcher = null;
          start();
        }
      });
      sizeWatcher.observe(node);
    }

    // React runs mount/unmount/mount in development. Every step is isolated and the refs
    // are cleared unconditionally: if remove() throws on a map torn down mid-load, a
    // non-null map.current makes the second mount bail out and leaves a dead map on screen.
    return () => {
      cancelled = true;
      sizeWatcher?.disconnect();
      teardown?.();
    };
  }, []);

  // Exactly one view's layers are on at a time; everything else is switched off.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (!instance.getLayer("flood_zones-fill")) return;
      const on = new Set(VIEW_LAYERS[view]);
      for (const id of ALL_DATA_LAYERS) {
        if (instance.getLayer(id)) {
          instance.setLayoutProperty(id, "visibility", on.has(id) ? "visible" : "none");
        }
      }
      for (const id of ["wards-line", "zones-line"]) {
        if (instance.getLayer(id)) {
          instance.setLayoutProperty(id, "visibility", showWards ? "visible" : "none");
        }
      }
    };
    apply();
    // Layers may not exist yet on first render; catch up when they appear.
    instance.once("idle", apply);
  }, [view, showWards]);

  // City switch: repoint every source and move the camera, without tearing the map down.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      for (const id of SOURCE_IDS) {
        const src = instance.getSource(id);
        if (src && "setData" in src) {
          (src as unknown as { setData: (d: string) => void }).setData(layerUrl(city.slug, id));
        }
      }
      instance.setMaxBounds([
        [city.bbox.lng_min - 0.35, city.bbox.lat_min - 0.35],
        [city.bbox.lng_max + 0.35, city.bbox.lat_max + 0.35],
      ]);
      instance.jumpTo({ center: [city.centre.lng, city.centre.lat], zoom: 10.8 });
    };
    if (ready.current) apply();
    else instance.once("idle", apply);
    // Primitives, not the bbox/centre objects: those are fresh on every render and
    // would repoint every source on each one.
  }, [city.slug, city.bbox.lat_min, city.bbox.lng_min, city.bbox.lat_max,
      city.bbox.lng_max, city.centre.lat, city.centre.lng]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      const value = activeWard ?? "__none__";
      for (const id of ["wards-active", "wards-active-fill"]) {
        if (instance.getLayer(id)) {
          instance.setFilter(id, ["==", ["get", "name"], value]);
        }
      }
    };
    if (ready.current) apply();
    else instance.once("idle", apply);
  }, [activeWard]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (!marker) {
      markerEl.current?.remove();
      markerEl.current = null;
      return;
    }
    if (!markerEl.current) {
      const el = document.createElement("div");
      el.style.cssText =
        "width:16px;height:16px;border-radius:50%;background:#0b0b0b;" +
        "border:3px solid #fcfcfb;box-shadow:0 2px 8px rgba(11,11,11,.35);cursor:pointer";
      markerEl.current = new Marker({ element: el });
    }
    markerEl.current.setLngLat([marker.lng, marker.lat]).addTo(instance);
  }, [marker]);

  useEffect(() => {
    if (!flyTo || !map.current) return;
    // A point outside the city (e.g. a US address scored from FEMA) is unreachable while
    // maxBounds is locked to the city. Release the lock so the camera can travel there.
    const b = cityRef.current.bbox;
    const outside = flyTo.lat < b.lat_min || flyTo.lat > b.lat_max ||
                    flyTo.lng < b.lng_min || flyTo.lng > b.lng_max;
    if (outside) map.current.setMaxBounds(null);
    map.current.flyTo({
      center: [flyTo.lng, flyTo.lat],
      zoom: flyTo.zoom ?? 14.5,
      duration: 900,
      essential: true,
      // Keep the pin clear of the floating panels rather than under them.
      padding: {
        left: padding?.left ?? 0,
        bottom: padding?.bottom ?? 0,
        top: 0,
        right: 0,
      },
    });
  }, [flyTo, padding?.left, padding?.bottom]);

  return <div ref={container} className="h-full w-full" />;
}
