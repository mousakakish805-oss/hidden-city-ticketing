import { useI18n } from "../i18n";
import { SEVERITY_CLASS } from "../lib/format";
import type { Disclaimer } from "../types";

interface Props {
  disclaimer: Disclaimer | null;
  accepted: boolean;
  onAccept: () => void;
  onBack: () => void;
}

const SEVERITY_ORDER = ["critical", "warning", "info"] as const;

/**
 * The rules and risks, as a full page rather than only a modal.
 *
 * The modal exists to *block* results until the critical rules are ticked.
 * This page exists to be read properly, linked to, and returned to — which the
 * modal cannot do, because dismissing it loses your place and it is only
 * reachable mid-search.
 */
export function RulesPage({ disclaimer, accepted, onAccept, onBack }: Props) {
  const { t } = useI18n();

  if (!disclaimer) {
    return <p className="text-sm text-ink-faint">{t("rules.loading")}</p>;
  }

  const grouped = SEVERITY_ORDER.map((severity) => ({
    severity,
    rules: disclaimer.rules.filter((rule) => rule.severity === severity),
  })).filter((group) => group.rules.length > 0);

  return (
    <div className="space-y-8 pb-10">
      <header className="space-y-3 max-w-3xl">
        <h1 className="text-2xl font-bold">{disclaimer.title}</h1>
        <p className="text-ink-muted leading-relaxed">{disclaimer.summary}</p>
        <p className="text-sm text-ink-faint">
          {t("rules.version", { version: disclaimer.version })}
        </p>
      </header>

      {/* How the technique works, before the rules about doing it safely.
          A list of prohibitions makes little sense without the mechanism. */}
      <section className="rounded-2xl bg-surface ring-1 ring-line p-5 max-w-3xl">
        <h2 className="font-bold mb-2">{t("rules.howTitle")}</h2>
        <p className="text-sm text-ink-muted leading-relaxed">{t("rules.howBody")}</p>
        <div
          dir="ltr"
          className="mt-4 rounded-xl bg-surface-2 ring-1 ring-line p-4 font-mono text-sm
                     flex flex-wrap items-center gap-2"
        >
          <span className="font-bold">AMM</span>
          <span className="text-ink-faint">&rarr;</span>
          <span className="font-bold text-positive bg-positive-soft ring-1 ring-positive-line rounded px-1.5">
            IST
          </span>
          <span className="text-ink-faint">&#8669;</span>
          <span className="line-through text-ink-faint">SKP</span>
          <span className="ms-3 font-sans text-xs text-ink-faint not-italic">
            {t("rules.diagramNote")}
          </span>
        </div>
      </section>

      {grouped.map((group) => (
        <section key={group.severity} className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">
            {t(`rules.group.${group.severity}` as "rules.group.critical")}
          </h2>

          {group.rules.map((rule, index) => (
            <article
              key={rule.code}
              className={`rounded-xl border p-5 ${SEVERITY_CLASS[rule.severity] ?? ""}`}
            >
              <div className="flex items-baseline gap-3">
                <span className="text-sm font-bold tabular-nums opacity-60 shrink-0">
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-bold">{rule.title}</h3>
                  <p className="mt-1.5 text-sm text-ink-muted leading-relaxed">{rule.body}</p>
                  {rule.required && (
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wider">
                      {t("rules.mustAccept")}
                    </p>
                  )}
                </div>
              </div>
            </article>
          ))}
        </section>
      ))}

      <section className="rounded-2xl bg-surface ring-1 ring-line p-5 max-w-3xl">
        <h2 className="font-bold mb-2">{t("rules.checklistTitle")}</h2>
        <ol className="space-y-2 text-sm text-ink-muted list-decimal ms-5">
          {["one", "two", "three", "four", "five"].map((step) => (
            <li key={step}>{t(`rules.checklist.${step}` as "rules.checklist.one")}</li>
          ))}
        </ol>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        {accepted ? (
          <span className="inline-flex items-center gap-2 rounded-lg bg-positive-soft
                           text-positive ring-1 ring-positive-line px-4 py-2 text-sm font-semibold">
            {t("rules.alreadyAccepted")}
          </span>
        ) : (
          <button
            type="button"
            onClick={onAccept}
            className="rounded-lg bg-positive hover:opacity-90 px-5 py-2.5 font-semibold
                       text-accent-ink transition"
          >
            {t("rules.acceptAll")}
          </button>
        )}
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg ring-1 ring-line-strong px-5 py-2.5 font-semibold
                     text-ink-muted hover:text-ink transition"
        >
          {t("rules.back")}
        </button>
      </div>
    </div>
  );
}
