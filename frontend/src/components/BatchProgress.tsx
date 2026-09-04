import { useI18n } from "../i18n";
import { money } from "../lib/format";
import type { ProbeResult, SearchEvent } from "../types";

interface Props {
  events: SearchEvent[];
}

/** Live view of the fan-out: which onward markets have been priced so far. */
export function BatchProgress({ events }: Props) {
  const { t, locale } = useI18n();

  if (events.length === 0) {
    return (
      <div className="rounded-2xl bg-surface ring-1 ring-line p-5 animate-pulse">
        <p className="text-sm text-ink-faint">{t("progress.starting")}</p>
      </div>
    );
  }

  const probes = events.filter(
    (event): event is SearchEvent & { type: "probe_finished" } & ProbeResult =>
      event.type === "probe_finished",
  );
  const candidates = events.find((event) => event.type === "candidates");
  const baseline = events.find((event) => event.type === "baseline");
  const planned = candidates?.count ?? 0;
  const percent = planned ? Math.min(100, (probes.length / planned) * 100) : 0;

  return (
    <div className="rounded-2xl bg-surface ring-1 ring-line p-5 ">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-ink-muted">{t("progress.title")}</h3>
        <span className="text-sm text-ink-faint tabular-nums">
          {t("progress.probed", { done: probes.length, total: planned || "?" })}
        </span>
      </div>

      <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mb-4">
        <div
          className="h-full bg-accent transition-all duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>

      {baseline && (
        <p className="text-sm text-ink-muted mb-3">
          {t("progress.baseline", {
            price: money(baseline.price, baseline.currency, locale),
            count: baseline.offer_count,
          })}
        </p>
      )}

      <div className="flex flex-wrap gap-1.5" dir="ltr">
        {probes.map((probe, index) => (
          <span
            key={`${probe.destination}-${index}`}
            title={probe.error ?? (probe.from_cache ? t("progress.cached") : undefined)}
            className={`px-2 py-0.5 rounded text-xs font-mono ring-1 ${
              probe.error
                ? "bg-danger-soft text-danger ring-danger-line"
                : "bg-surface-2 text-ink-muted ring-line-strong"
            }`}
          >
            {probe.destination}
            {probe.min_price != null && (
              <span className="ms-1.5 text-positive">{Math.round(probe.min_price)}</span>
            )}
            {probe.from_cache && <span className="ms-1 text-ink-faint">&#183;</span>}
          </span>
        ))}
      </div>
    </div>
  );
}
