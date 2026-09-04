/**
 * Every currency the visitor can price a trip in.
 *
 * The list is not curated and not hard-coded. `Intl.supportedValuesOf` gives
 * the browser's full ISO 4217 set and `Intl.DisplayNames` names each one in
 * the active language, so this file stays correct as currencies are added,
 * renamed or redenominated, and needs no second entry per language.
 *
 * The backend accepts any three-letter code, and the code is passed straight
 * through to the flight provider, so fares come back quoted in it rather than
 * converted afterwards — a converted price would drift from what the airline
 * actually charges.
 *
 * FALLBACK is only reached on a browser without `Intl.supportedValuesOf`.
 * It is not a preference list; it is the smallest set that keeps the picker
 * usable if the real one cannot be built.
 */

const FALLBACK = [
  "USD", "EUR", "GBP", "JOD", "SAR", "AED", "QAR", "KWD", "BHD", "OMR",
  "EGP", "TRY", "ILS", "LBP", "IQD", "CHF", "CAD", "AUD", "NZD", "JPY",
  "CNY", "INR", "PKR", "RUB", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
  "ZAR", "MAD", "TND", "DZD", "NGN", "KES", "THB", "SGD", "MYR", "IDR",
  "PHP", "KRW", "HKD", "BRL", "MXN", "ARS", "CLP", "COP",
];

export const DEFAULT_CURRENCY = "USD";

/** Every ISO 4217 code this browser knows, or FALLBACK if it cannot say. */
export function allCurrencyCodes(): string[] {
  try {
    const supported = Intl.supportedValuesOf("currency");
    if (supported.length) return [...supported];
  } catch {
    // Older browser, or an implementation without the "currency" key.
  }
  return FALLBACK;
}

/** "USD" -> "US Dollar" / "دولار أمريكي". Falls back to the code itself. */
export function currencyName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "currency" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export interface CurrencyOption {
  code: string;
  label: string;
}

/**
 * The picker's options, sorted by name in the reader's own language.
 *
 * Sorted with `Intl.Collator` rather than a plain string compare, because
 * neither Arabic names nor accented Latin ones order correctly under a
 * code-unit sort.
 */
export function currencyOptions(locale: string): CurrencyOption[] {
  const collator = new Intl.Collator(locale);
  return allCurrencyCodes()
    .map((code) => ({ code, label: `${code} ${currencyName(code, locale)}` }))
    .sort((a, b) => collator.compare(a.label, b.label));
}
