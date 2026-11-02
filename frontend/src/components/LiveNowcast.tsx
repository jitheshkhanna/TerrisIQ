"use client";

import { useEffect, useState } from "react";
import { nowcast, type Nowcast, type NowcastStatus } from "@/lib/api";

/* The live strip: rain falling now x this place's flood susceptibility. It refreshes on its
 * own and hides itself when the live feed is unavailable, so it never breaks the card. */

const STYLE: Record<Exclude<NowcastStatus, "unavailable">, string> = {
  active: "var(--critical)",
  likely: "var(--serious)",
  watch: "var(--warning)",
  clear: "var(--good)",
};

function agoLabel(ms: number) {
  const m = Math.floor((Date.now() - ms) / 60000);
  if (m < 1) return "just now";
  if (m === 1) return "1 min ago";
  if (m < 60) return `${m} min ago`;
  return "over an hour ago";
}

export default function LiveNowcast({ lat, lng, floodLevel }:
  { lat: number; lng: number; floodLevel: number }) {
  const [data, setData] = useState<Nowcast | null>(null);
  const [fetchedAt, setFetchedAt] = useState(0);
  const [, tick] = useState(0);

  useEffect(() => {
    let alive = true;
    setData(null); // clear while the new place loads so a stale strip never lingers
    const load = () =>
      nowcast(lat, lng, floodLevel).then((d) => {
        if (!alive) return;
        setData(d);
        setFetchedAt(Date.now());
      });
    load();
    const refresh = setInterval(load, 5 * 60 * 1000); // re-poll the live feed
    const clock = setInterval(() => tick((n) => n + 1), 30 * 1000); // re-render "x min ago"
    return () => {
      alive = false;
      clearInterval(refresh);
      clearInterval(clock);
    };
  }, [lat, lng, floodLevel]);

  if (!data || data.status === "unavailable" || !data.headline) return null;
  const color = STYLE[data.status];

  return (
    <div
      className="rise mt-3 flex items-center gap-3 rounded-2xl border px-3.5 py-2.5"
      style={{
        background: `color-mix(in srgb, ${color} 9%, var(--surface))`,
        borderColor: `color-mix(in srgb, ${color} 28%, transparent)`,
      }}
      role="status"
      aria-live="polite"
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
          style={{ background: color }}
          aria-hidden
        />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold uppercase tracking-[0.08em]" style={{ color }}>
            Live
          </span>
          <span className="text-[11.5px] text-[var(--ink-muted)]">· updated {agoLabel(fetchedAt)}</span>
        </div>
        <p className="mt-0.5 text-[13.5px] font-medium leading-snug text-[var(--ink)]">
          {data.headline}
        </p>
      </div>
    </div>
  );
}
