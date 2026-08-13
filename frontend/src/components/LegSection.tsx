import { plural, useI18n } from "../i18n";
import { money, shortDate } from "../lib/format";
import type { LegResult } from "../types";
import { HiddenCityCard } from "./HiddenCityCard";
import { PriceMatrix } from "./PriceMatrix";
import { StandardOfferCard } from "./StandardOfferCard";

interface Props {
  leg: LegResult;
  /** Only shown for return trips; a one-way needs no direction heading. */
  showHeading: boolean;
  disclaimerAccepted: boolean;
  onOpenDisclaimer: () => void;
}

/** One direction of a trip: its savings, its normal fares, its price matrix. */
export function LegSection({ leg, showHeading, disclaimerAccepted, onOpenDisclaimer }: Props) {
  const { t, locale } = useI18n();
  const { hidden_city: hidden, baseline } = leg;
  const currency = baseline.currency;

  return (
    <section className="space-y-4">
      {showHeading && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-2">
          <h2 className="text-lg font-bold">
            {leg.leg === "outbound" ? t("trip.outbound") : t("trip.inbound")}
          </h2>
          <span className="text-sm text-ink-muted" dir="ltr">
            {leg.origin} &rarr; {leg.destination}
          </span>
          <span className="text-sm text-ink-faint">{shortDate(leg.departure_date, locale)}</span>
        </div>
      )}

      <div>
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
          <h3 className="font-bold">
            {hidden.count > 0
              ? plural(t, "results.opportunities", hidden.count)
              : t("results.noneTitle")}
          </h3>
          {hidden.best_savings != null && (
            <p className="text-sm text-positive font-semibold">
              {t("results.bestSaving", {
                amount: money(hidden.best_savings, currency, locale),
              })}
            </p>
          )}
        </div>

        {hidden.count === 0 ? (
          <div className="rounded-2xl bg-surface ring-1 ring-line p-6 text-ink-muted">
            <p>
              {t("results.noneBody", {
                city: leg.destination_airport.city,
                probes: leg.probes.length,
              })}
              {hidden.rejected_count > 0 && (
                <>
                  {" "}
                  {t("results.noneRejected", {
                    count: hidden.rejected_count,
                    target: leg.destination,
                  })}
                </>
              )}
            </p>
          </div>
        ) : !disclaimerAccepted ? (
          // The mandatory gate: savings are never rendered before the rules are read.
          <div className="rounded-2xl ring-1 ring-warning-line bg-warning-soft p-6 text-center">
            <p className="text-3xl mb-2" aria-hidden="true">
              &#128274;
            </p>
            <p className="font-semibold text-warning">
              {t("locked.title", {
                count: hidden.count,
                amount: money(hidden.best_savings, currency, locale),
              })}
            </p>
            <p className="text-sm text-ink-muted mt-2 max-w-lg mx-auto">{t("locked.body")}</p>
            <button
              type="button"
              onClick={onOpenDisclaimer}
              className="mt-4 rounded-lg bg-warning hover:opacity-90 px-5 py-2.5
                         font-semibold text-accent-ink"
            >
              {t("locked.button")}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {hidden.options.map((option) => (
              <HiddenCityCard
                key={`${option.ticketed_iata}-${option.offer.offer_id}`}
                option={option}
                currency={currency}
              />
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="font-bold mb-1">
          {t("standard.title", { city: leg.destination_airport.city })}
        </h3>
        <p className="text-sm text-ink-faint mb-3">
          {t("standard.subtitle", {
            count: baseline.offer_count,
            price: money(baseline.price, currency, locale),
          })}
        </p>
        <div className="space-y-2">
          {baseline.offers.slice(0, 6).map((offer) => (
            <StandardOfferCard
              key={offer.offer_id}
              offer={offer}
              currency={currency}
              isCheapest={offer.price_total === baseline.price}
            />
          ))}
        </div>
      </div>

      <PriceMatrix matrix={leg.price_matrix} />
    </section>
  );
}
