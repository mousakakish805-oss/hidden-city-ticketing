import { useI18n } from "../i18n";
import type { Theme } from "../hooks/useTheme";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

/** Single button rather than a two-option group: with exactly two themes,
 *  showing the one you would switch *to* is less to read and less to click. */
export function ThemeToggle({ theme, onToggle }: Props) {
  const { t } = useI18n();
  const goingDark = theme === "light";

  return (
    <button
      type="button"
      onClick={onToggle}
      title={goingDark ? t("theme.toDark") : t("theme.toLight")}
      aria-label={goingDark ? t("theme.toDark") : t("theme.toLight")}
      className="grid place-items-center size-7 rounded-full ring-1 ring-line-strong
                 text-ink-muted hover:text-ink transition"
    >
      <span aria-hidden="true" className="text-sm leading-none">
        {goingDark ? "◓" : "◒"}
      </span>
    </button>
  );
}
