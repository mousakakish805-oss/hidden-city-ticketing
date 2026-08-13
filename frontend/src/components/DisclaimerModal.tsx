import { useEffect, useState } from "react";

import { useI18n } from "../i18n";
import { SEVERITY_CLASS } from "../lib/format";
import type { Disclaimer } from "../types";

interface Props {
  disclaimer: Disclaimer;
  onAccept: () => void;
  onDismiss: () => void;
}

/**
 * The mandatory operational-risk gate.
 *
 * Every rule marked `required` by the backend must be individually ticked
 * before the accept button enables -- a single "I agree" is too easy to click
 * past when getting it wrong voids the ticket.
 */
export function DisclaimerModal({ disclaimer, onAccept, onDismiss }: Props) {
  const { t } = useI18n();
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const ready = disclaimer.required_codes.every((code) => checked[code]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onDismiss]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="disclaimer-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--canvas)_55%,black)]/80 backdrop-blur-sm p-4"
      onClick={onDismiss}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl bg-surface
                   ring-1 ring-line-strong shadow-2xl"
      >
        <header className="p-6 border-b border-line shrink-0">
          <div className="flex items-start gap-3">
            <span className="text-2xl leading-none" aria-hidden="true">
              &#9888;
            </span>
            <div>
              <h2 id="disclaimer-title" className="text-xl font-bold">
                {disclaimer.title}
              </h2>
              <p className="mt-2 text-sm text-ink-muted leading-relaxed">{disclaimer.summary}</p>
            </div>
          </div>
        </header>

        <div className="overflow-y-auto p-6 space-y-3 min-h-0">
          {disclaimer.rules.map((rule) => (
            <div
              key={rule.code}
              className={`rounded-xl border p-4 ${SEVERITY_CLASS[rule.severity] ?? ""}`}
            >
              <label className={`flex gap-3 ${rule.required ? "cursor-pointer" : ""}`}>
                {rule.required && (
                  <input
                    type="checkbox"
                    checked={Boolean(checked[rule.code])}
                    onChange={(event) =>
                      setChecked((previous) => ({
                        ...previous,
                        [rule.code]: event.target.checked,
                      }))
                    }
                    className="mt-1 accent-[var(--positive)] size-4 shrink-0"
                  />
                )}
                <div className={rule.required ? "" : "ps-7"}>
                  <p className="font-semibold">{rule.title}</p>
                  <p className="mt-1 text-sm text-ink-muted leading-relaxed">{rule.body}</p>
                </div>
              </label>
            </div>
          ))}
        </div>

        <footer className="p-6 border-t border-line flex items-center justify-between gap-4 shrink-0">
          <p className="text-xs text-ink-faint">
            {t("modal.versionNote", {
              version: disclaimer.version,
              count: disclaimer.required_codes.length,
            })}
          </p>
          <button
            type="button"
            disabled={!ready}
            onClick={onAccept}
            className="rounded-lg bg-positive hover:opacity-90 disabled:bg-surface-2
                       disabled:text-ink-faint px-5 py-2.5 font-semibold text-accent-ink
                       transition shrink-0"
          >
            {t("modal.accept")}
          </button>
        </footer>
      </div>
    </div>
  );
}
