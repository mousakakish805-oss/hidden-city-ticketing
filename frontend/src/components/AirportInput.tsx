import { useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import type { Airport } from "../types";

interface Props {
  label: string;
  hint?: string;
  value: string;
  placeholder?: string;
  onChange: (iata: string) => void;
}

export function AirportInput({ label, hint, value, placeholder, onChange }: Props) {
  const [options, setOptions] = useState<Airport[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const blurTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    // Nothing is offered until a letter is typed. Focusing a field that
    // already reads "AMM" used to fire a search for "AMM" and drop a list
    // over the form before the visitor had asked for anything.
    if (!open || value.length === 0) {
      setOptions([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api
        .airports(value)
        .then((results) => {
          setOptions(results);
          setHighlighted(0);
        })
        .catch(() => setOptions([]));
    }, 150);
    return () => window.clearTimeout(timer);
  }, [value, open]);

  useEffect(() => () => window.clearTimeout(blurTimer.current), []);

  const choose = (airport: Airport) => {
    onChange(airport.iata);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || options.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + options.length) % options.length);
    } else if (event.key === "Enter") {
      const airport = options[highlighted];
      if (airport) {
        event.preventDefault();
        choose(airport);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <label className="block text-xs font-medium text-ink-muted mb-1.5">
        {label}
        {hint && <span className="ms-2 text-ink-faint">{hint}</span>}
      </label>
      <input
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        maxLength={3}
        // Track raw typing, not just picking a suggestion, so a typed code is
        // never silently ignored on submit.
        onChange={(event) => {
          onChange(event.target.value.toUpperCase());
          setOpen(true);
        }}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={onKeyDown}
        // IATA codes are Latin identifiers -- typing them must stay LTR even
        // when the rest of the page is right-to-left.
        dir="ltr"
        className="coupon w-full rounded bg-canvas border border-line px-3 py-2.5 text-lg font-semibold
                   tracking-wide focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                   placeholder:text-ink-faint placeholder:font-normal"
      />

      {open && options.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-30 mt-1 w-full max-h-64 overflow-auto rounded-lg bg-surface
                     ring-1 ring-line-strong shadow-2xl"
        >
          {options.map((airport, index) => (
            <li key={airport.iata} role="option" aria-selected={index === highlighted}>
              <button
                type="button"
                onMouseDown={() => choose(airport)}
                onMouseEnter={() => setHighlighted(index)}
                className={`w-full text-start px-3 py-2 flex items-baseline gap-2 ${
                  index === highlighted ? "bg-surface-2" : ""
                }`}
              >
                <span className="font-mono font-bold text-accent w-10" dir="ltr">
                  {airport.iata}
                </span>
                <span className="text-sm truncate">{airport.city}</span>
                <span className="text-xs text-ink-faint ms-auto shrink-0 ps-2">
                  {airport.country}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
