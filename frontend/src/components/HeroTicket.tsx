import { useI18n } from "../i18n";

/**
 * The hero: a boarding pass with its last coupon torn off.
 *
 * This is the product, not a picture of it. Hidden-city ticketing is the
 * single act of buying a ticket to a further city and not boarding the last
 * flight, and a page can either explain that in a paragraph or show it in one
 * object. The perforation is the argument — everything left of it is the
 * journey you take, everything right of it is what you paid for and abandon.
 *
 * Decorative, so it is hidden from screen readers; the heading and body text
 * beside it carry the same meaning in words.
 */
export function HeroTicket() {
  const { t } = useI18n();

  return (
    <div aria-hidden className="select-none">
      <div className="flex flex-col sm:flex-row items-stretch max-w-lg">
        {/* Flown: the part that behaves like an ordinary ticket. */}
        <div className="ticket animate-print flex-1 p-5">
          <p className="text-[11px] text-ink-faint">{t("hero.ticketTo")}</p>
          <p className="coupon text-3xl font-semibold tracking-tight mt-0.5">SCQ</p>

          <div className="coupon mt-5 flex items-baseline gap-2 text-sm">
            <span className="font-semibold">AMM</span>
            <span className="flex-1 border-t border-dashed border-line-strong" />
            <span className="font-semibold text-accent">MAD</span>
          </div>
          <p className="text-xs text-ink-muted mt-2">
            {t("hero.getOffAt")} <span className="coupon text-ink font-semibold">MAD</span>
          </p>

          <p className="mt-4 text-xs font-medium text-positive">{t("hero.stubFlown")}</p>
        </div>

        {/* The perforation, and the coupon beyond it. */}
        <div className="perf notch relative w-full h-3 sm:h-auto sm:w-3 shrink-0" />

        <div
          className="ticket animate-tear w-full sm:w-40 p-5 origin-top-left
                     border-dashed opacity-70"
        >
          <p className="coupon text-[11px] text-ink-faint">MAD</p>
          <p className="coupon text-lg font-semibold mt-0.5 line-through decoration-danger">
            BCN
          </p>
          <p className="coupon text-[11px] text-ink-faint mt-3">IB 1684</p>
          <p className="mt-4 text-xs font-medium text-danger">{t("hero.stubSkipped")}</p>
        </div>
      </div>
    </div>
  );
}
