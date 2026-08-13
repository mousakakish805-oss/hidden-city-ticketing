import { LANGUAGES, useI18n } from "../i18n";

/** Two-language switch. Kept as visible buttons rather than a dropdown so the
 *  other language is always readable in its own script. */
export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();

  return (
    <div
      role="group"
      aria-label={t("header.language")}
      className="flex items-center rounded-full ring-1 ring-line-strong overflow-hidden"
    >
      {LANGUAGES.map((entry) => (
        <button
          key={entry.code}
          type="button"
          onClick={() => setLang(entry.code)}
          aria-pressed={lang === entry.code}
          className={`px-2.5 py-1 transition ${
            lang === entry.code
              ? "bg-ink text-canvas font-semibold"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {entry.name}
        </button>
      ))}
    </div>
  );
}
