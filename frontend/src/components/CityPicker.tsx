"use client";

import type { City } from "@/lib/api";

interface Props {
  cities: City[];
  value: City;
  onChange: (city: City) => void;
}

/** Lives inside the search bar, to its left: pick the city, then search within it.
 *  A native select on purpose - the most reliable control on a phone, and it works with
 *  every screen reader without custom keyboard handling. */
export default function CityPicker({ cities, value, onChange }: Props) {
  return (
    <div className="relative flex h-[54px] shrink-0 items-center border-r border-[var(--hairline)]">
      <label htmlFor="city" className="sr-only">
        City
      </label>
      <select
        id="city"
        value={value.slug}
        onChange={(e) => {
          const next = cities.find((c) => c.slug === e.target.value);
          if (next) onChange(next);
        }}
        className="h-full cursor-pointer appearance-none rounded-l-2xl bg-transparent pl-4 pr-8
                   text-[15px] font-semibold text-[var(--ink)] focus:outline-none"
      >
        {cities.map((c) => (
          <option key={c.slug} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
      <svg
        viewBox="0 0 12 12"
        className="pointer-events-none absolute right-3 h-3 w-3 text-[var(--ink-muted)]"
        aria-hidden
      >
        <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none"
              strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
