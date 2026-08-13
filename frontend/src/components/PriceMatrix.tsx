import { useI18n } from "../i18n";
import type { PriceMatrix as Matrix } from "../types";

/**
 * Ticketed destination x airline, cheapest fare in each cell.
 *
 * The argument the whole app is making, in one table: rows *below* the
 * highlighted target row are further away and cost less.
 */
export function PriceMatrix({ matrix }: { matrix: Matrix }) {
  const { t } = useI18n();
  if (matrix.rows.length === 0) return null;

  return (
    <section className="rounded-2xl bg-surface ring-1 ring-line p-5">
      <h2 className="font-semibold mb-1">{t("matrix.title")}</h2>
      <p className="text-sm text-ink-faint mb-4">{t("matrix.subtitle")}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-ink-faint text-xs uppercase tracking-wider">
              <th scope="col" className="text-start font-medium py-2 pe-4">
                {t("matrix.ticketedTo")}
              </th>
              {matrix.carriers.map((carrier) => (
                <th key={carrier} scope="col" className="text-end font-medium py-2 px-2 font-mono">
                  {carrier}
                </th>
              ))}
              <th scope="col" className="text-end font-medium py-2 ps-4">
                {t("matrix.best")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {matrix.rows.map((row) => (
              <tr key={row.iata} className={row.is_target ? "bg-accent-soft" : ""}>
                <th scope="row" className="text-start font-normal py-2 pe-4 whitespace-nowrap">
                  <span className="font-mono font-semibold">{row.iata}</span>
                  <span className="text-ink-faint ms-2">{row.city}</span>
                  {row.is_target && (
                    <span className="ms-2 text-[10px] uppercase tracking-wider text-accent font-semibold">
                      {t("matrix.yourTarget")}
                    </span>
                  )}
                </th>
                {row.prices.map((price, index) => (
                  <td
                    key={index}
                    className={`text-end py-2 px-2 tabular-nums ${
                      price == null
                        ? "text-ink-faint"
                        : price === row.cheapest
                          ? "text-positive font-semibold"
                          : "text-ink-muted"
                    }`}
                  >
                    {price == null ? "--" : Math.round(price)}
                  </td>
                ))}
                <td className="text-end py-2 ps-4 font-semibold tabular-nums">
                  {Math.round(row.cheapest)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
