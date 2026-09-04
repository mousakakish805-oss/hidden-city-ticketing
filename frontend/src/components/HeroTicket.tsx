import { useI18n } from "../i18n";

/**
 * The hero: one boarding pass, perforated, whose last coupon goes unused.
 *
 * This is the product rather than a picture of it. Hidden-city ticketing is
 * the single act of buying a ticket to a further city and not boarding the
 * last flight, and a page can either explain that in a paragraph or show it
 * in one object. The perforation is the argument: left of it is the journey
 * you take, right of it is what you paid for and abandon.
 *
 * It is one card, not two. An earlier version separated the halves with a gap
 * and drew half-circle notches over the join; against a black canvas the
 * notches rendered as floating rings and the whole thing read as broken. A
 * ticket is one piece of paper until somebody tears it.
 *
 * Decorative, so it is hidden from assistive technology -- the heading and
 * body text beside it carry the same meaning in words.
 */
export function HeroTicket() {
  const { t } = useI18n();

  return (
    <div aria-hidden className="ticket select-none flex w-full max-w-md md:w-[26rem] md:shrink-0">
      {/* Flown. */}
      <div className="flex-1 p-5 min-w-0">
        <p className="text-[11px] text-ink-faint">{t("hero.ticketTo")}</p>
        <p className="coupon text-3xl font-semibold tracking-tight mt-0.5">SCQ</p>

        <div className="coupon mt-6 flex items-baseline gap-2 text-sm">
          <span className="font-semibold">AMM</span>
          <span className="flex-1 border-t border-line-strong" />
          <span className="font-semibold text-accent">MAD</span>
        </div>
        <p className="text-xs text-ink-muted mt-2">
          {t("hero.getOffAt")} <span className="coupon font-semibold text-ink">MAD</span>
        </p>

        <p className="mt-5 text-xs font-medium text-positive">{t("hero.stubFlown")}</p>
      </div>

      {/* Abandoned, across the perforation. */}
      <div className="abandoned w-32 sm:w-36 shrink-0 p-5
                   border-s border-dashed border-line-strong">
        <p className="coupon text-[11px] text-ink-faint">MAD</p>
        <p className="coupon text-lg font-semibold mt-0.5 line-through decoration-danger decoration-2">
          BCN
        </p>
        <p className="coupon text-[11px] text-ink-faint mt-4">IB 1684</p>
        <p className="mt-5 text-xs font-medium text-danger">{t("hero.stubSkipped")}</p>
      </div>
    </div>
  );
}
