/** Presentation helpers shared across components.
 *
 *  Everything user-visible takes a `locale`, so the same number renders
 *  correctly under either language. Airport codes, flight numbers and times
 *  are deliberately *not* localised — they are identifiers, and travellers
 *  match them against boarding passes and airline sites.
 */

export function money(
  value: number | null | undefined,
  currency = "USD",
  locale = "en",
): string {
  if (value == null) return "--";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function number(value: number, locale = "en"): string {
  return new Intl.NumberFormat(locale).format(value);
}

export function timeOfDay(iso: string, locale = "en"): string {
  return new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

export function shortDate(iso: string, locale = "en"): string {
  return new Date(iso).toLocaleDateString(locale, { month: "short", day: "numeric" });
}

export function dateTime(iso: string, locale = "en"): string {
  return new Date(iso).toLocaleString(locale);
}

export function minutesLabel(minutes: number | null, locale = "en"): string {
  if (minutes == null) return "--";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const h = number(hours, locale);
  const m = number(rest, locale);
  return hours ? `${h}h ${m.padStart(2, "0")}m` : `${m}m`;
}

function toDateInput(date: Date): string {
  const offsetMinutes = date.getTimezoneOffset();
  return new Date(date.getTime() - offsetMinutes * 60_000).toISOString().slice(0, 10);
}

/** Date input value N days from today, in the local timezone. */
export function dateInDays(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return toDateInput(date);
}

/** Shift a `YYYY-MM-DD` value by N days, staying in the local timezone. */
export function addDays(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return toDateInput(date);
}

/** Semantic tokens only — see index.css. Never hardcode a colour here, or the
 *  light and dark themes drift apart one component at a time. */
export const SEVERITY_CLASS: Record<string, string> = {
  critical: "border-danger-line bg-danger-soft text-danger",
  warning: "border-warning-line bg-warning-soft text-warning",
  info: "border-accent-line bg-accent-soft text-accent",
};

export const BAND_CLASS: Record<string, string> = {
  high: "text-positive bg-positive-soft ring-positive-line",
  medium: "text-warning bg-warning-soft ring-warning-line",
  low: "text-danger bg-danger-soft ring-danger-line",
};
