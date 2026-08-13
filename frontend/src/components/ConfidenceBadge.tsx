import { useI18n } from "../i18n";
import { BAND_CLASS } from "../lib/format";
import type { RiskAssessment } from "../types";

export function ConfidenceBadge({ risk }: { risk: RiskAssessment }) {
  const { t } = useI18n();
  const explanation = {
    high: t("confidence.high"),
    medium: t("confidence.medium"),
    low: t("confidence.low"),
  }[risk.band];

  return (
    <span
      title={explanation}
      className={`text-xs font-semibold px-2 py-1 rounded-full ring-1 ${BAND_CLASS[risk.band] ?? ""}`}
    >
      {t("card.confidence", { score: risk.confidence })}
    </span>
  );
}
