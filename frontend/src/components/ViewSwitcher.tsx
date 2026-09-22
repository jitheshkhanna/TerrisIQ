"use client";

import * as ToggleGroup from "@radix-ui/react-toggle-group";
import { FLOOD_ORDER, FLOOD_RAMP, VIEWS, type MapView } from "@/lib/design";

interface Props {
  view: MapView;
  onChange: (view: MapView) => void;
  showWards: boolean;
  onWardsChange: (next: boolean) => void;
}

/** One question at a time.
 *
 *  Radix ToggleGroup rather than a hand-rolled row of buttons: it gives roving tabindex,
 *  arrow-key navigation and correct radio semantics for screen readers, which the
 *  checkbox panel this replaces never had.
 */
export default function ViewSwitcher({ view, onChange, showWards, onWardsChange }: Props) {
  const active = VIEWS.find((v) => v.id === view);

  return (
    <div className="floating p-2 sm:p-3">
      <p className="eyebrow mb-2 hidden sm:block">Show on map</p>

      <ToggleGroup.Root
        type="single"
        value={view}
        onValueChange={(value) => value && onChange(value as MapView)}
        aria-label="Choose what the map shows"
        className="grid grid-cols-4 gap-1 rounded-xl bg-[var(--plane)] p-1"
      >
        {VIEWS.map((option) => (
          <ToggleGroup.Item
            key={option.id}
            value={option.id}
            aria-label={`${option.label}. ${option.hint}`}
            className="flex min-h-[40px] items-center justify-center rounded-lg px-2 text-[14px]
                       font-medium text-[var(--ink-2)] transition
                       hover:text-[var(--ink)]
                       data-[state=on]:bg-[var(--surface)] data-[state=on]:text-[var(--ink)]
                       data-[state=on]:shadow-[0_1px_2px_rgba(11,11,11,0.12)]"
          >
            {option.label}
          </ToggleGroup.Item>
        ))}
      </ToggleGroup.Root>

      {active && (
        <p className="mt-2 hidden text-[13px] leading-snug text-[var(--ink-muted)] sm:block">
          {active.hint}
        </p>
      )}

      {view === "flood" && (
        <div className="mt-3 hidden border-t border-[var(--hairline)] pt-2.5 sm:block">
          <div className="flex h-2.5 overflow-hidden rounded-full">
            {FLOOD_ORDER.map((level) => (
              <span
                key={level}
                className="flex-1"
                style={{ background: FLOOD_RAMP[level] }}
                title={level}
              />
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[12px] text-[var(--ink-muted)]">
            <span>Low risk</span>
            <span>High risk</span>
          </div>
        </div>
      )}

      <label
        className="mt-3 hidden min-h-[var(--tap)] cursor-pointer items-center gap-2.5 border-t sm:flex
                   border-[var(--hairline)] pt-2.5 text-[14px] text-[var(--ink-2)]"
      >
        <input
          type="checkbox"
          checked={showWards}
          onChange={(e) => onWardsChange(e.target.checked)}
          className="h-[18px] w-[18px] accent-[var(--ink)]"
        />
        Ward boundaries
      </label>
    </div>
  );
}
