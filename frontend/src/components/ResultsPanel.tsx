import { useI18n } from "../i18n";
import { dateTime, money } from "../lib/format";
import type { SearchResult } from "../types";
import { LegSection } from "./LegSection";

interface Props {
  result: SearchResult;
  /** Provider is the mock: every figure below is generated, not real. */
  syntheticData: boolean;
  disclaimerAccepted: boolean;
  onOpenDisclaimer: () => void;
}

export function ResultsPanel({
  result,
  syntheticData,
  disclaimerAccepted,
  onOpenDisclaimer,
}: Props) {
  const { t, locale } = useI18n();
  const isRoundTrip = result.trip_type === "round_trip" && result.inbound !== null;
  const totals = result.totals;

  return (
    <>
      {result.warnings.map((warning) => (
        <div
          key={warning}
          className="rounded-xl border border-warning-line bg-warning-soft text-warning px-4 py-3 text-sm"
        >
          {warning}
        </div>
      ))}

      {/* Trip total first: on a return trip the headline number is what both
          tickets cost together, not either leg on its own. */}
      {isRoundTrip && totals?.baseline != null && totals.best != null && (
        <section className="rounded-2xl bg-surface ring-1 ring-line p-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-ink-faint mb-1">
                {t("trip.totalNormal")}
              </p>
              <p className="text-2xl font-bold text-ink-muted line-through">
                {money(totals.baseline, totals.currency, locale)}
              </p>
            </div>
            <div className="text-end">
              <p className="text-xs uppercase tracking-wider text-positive mb-1">
                {t("trip.totalBest")}
              </p>
              <p className="text-3xl font-bold text-positive">
                {money(totals.best, totals.currency, locale)}
              </p>
            </div>
          </div>

          {totals.savings != null && totals.savings > 0 && (
            <p className="mt-3 text-sm font-semibold text-positive">
              {t("trip.totalSaving", {
                amount: money(totals.savings, totals.currency, locale),
              })}
              <span className="ms-2 font-normal text-ink-faint">
                {totals.legs_with_savings === 2
                  ? t("trip.savingsOnBoth")
                  : t("trip.savingsOnOneLeg")}
              </span>
            </p>
          )}
          {(totals.savings == null || totals.savings <= 0) && (
            <p className="mt-3 text-sm text-ink-faint">{t("trip.noSavings")}</p>
          )}

          {/* The single most important instruction on a return trip. */}
          <p className="mt-4 rounded-lg border border-danger-line bg-danger-soft text-danger px-3 py-2 text-sm">
            {t("trip.separateTickets")}
          </p>
        </section>
      )}

      <LegSection
        leg={result.outbound}
        showHeading={isRoundTrip}
        syntheticData={syntheticData}
        disclaimerAccepted={disclaimerAccepted}
        onOpenDisclaimer={onOpenDisclaimer}
      />

      {isRoundTrip && result.inbound && (
        <LegSection
          leg={result.inbound}
          showHeading
          syntheticData={syntheticData}
          disclaimerAccepted={disclaimerAccepted}
          onOpenDisclaimer={onOpenDisclaimer}
        />
      )}

      <p className="text-xs text-ink-faint pb-8">
        {t("footer.meta", {
          provider: result.provider,
          probes:
            result.outbound.probes.length + (result.inbound?.probes.length ?? 0),
          ms: result.duration_ms,
          time: dateTime(result.generated_at, locale),
        })}
      </p>
    </>
  );
}
