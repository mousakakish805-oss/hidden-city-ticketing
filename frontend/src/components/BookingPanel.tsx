import { useI18n } from "../i18n";
import type { BookingGuidance } from "../types";

/**
 * Where to buy the fare.
 *
 * We send people to the airline's own site rather than deep-linking into its
 * booking flow: every carrier's search URL differs and those formats change
 * without notice, so a fabricated deep link breaks quietly. The instructions
 * carry the actual work — which route to search, one way, connecting where.
 *
 * This app never books anything; it only reports prices.
 */
export function BookingPanel({ booking }: { booking: BookingGuidance }) {
  const { t } = useI18n();

  return (
    <div className="mt-4 rounded-xl bg-surface-2 ring-1 ring-line p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider text-ink-faint font-semibold mb-1">
            {t("booking.title")}
          </p>
          <p className="text-sm text-ink-muted">{booking.instructions}</p>
          {booking.note && <p className="text-sm text-warning mt-1">{booking.note}</p>}
          <p className="text-xs text-ink-faint mt-1.5">{t("booking.note")}</p>
        </div>

        {booking.url && (
          <a
            href={booking.url}
            target="_blank"
            // noreferrer alongside noopener: the airline should not receive
            // this tool as the referrer.
            rel="noopener noreferrer"
            className="shrink-0 rounded-lg bg-ink hover:opacity-90 px-4 py-2 text-sm
                       font-semibold text-canvas transition"
          >
            {t("booking.openSite", { airline: booking.carrier_name })}
          </a>
        )}
      </div>
    </div>
  );
}
