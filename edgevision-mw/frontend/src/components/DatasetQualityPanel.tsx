import { useTranslation } from "react-i18next";
import { Badge } from "./ui";

interface DatasetQualityPanelProps {
  iaaScore?: number;
  piiScrubVerified?: boolean;
  consentCoveragePct?: number;
  sampleCount?: number;
  classes?: Record<string, number>;
  status?: string;
}

function tierLabel(status: string | undefined): { key: string; fallback: string; variant: "info" | "success" | "warning" | "danger" } {
  switch (status?.toLowerCase()) {
    case "for_sale":
    case "sold":
      return { key: "datasets.tierCurated", fallback: "Curated", variant: "success" };
    case "ready":
      return { key: "datasets.tierAnnotated", fallback: "Annotated", variant: "info" };
    case "building":
      return { key: "datasets.tierRaw", fallback: "Raw", variant: "warning" };
    default:
      return { key: "datasets.tierUnknown", fallback: status || "Unknown", variant: "default" as "info" };
  }
}

function iaaVariant(score: number): "success" | "warning" | "danger" {
  if (score >= 0.96) return "success";
  if (score >= 0.80) return "warning";
  return "danger";
}

function piiVariant(verified: boolean | undefined): "success" | "warning" | "danger" {
  if (verified === true) return "success";
  if (verified === false) return "warning";
  return "danger";
}

export function DatasetQualityPanel({
  iaaScore,
  piiScrubVerified,
  consentCoveragePct,
  sampleCount,
  classes,
  status,
}: DatasetQualityPanelProps) {
  const { t } = useTranslation();
  const tier = tierLabel(status);
  const classCount = classes ? Object.keys(classes).length : 0;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center" }}>
      {/* Tier */}
      <Badge variant={tier.variant}>
        {t(tier.key, tier.fallback)}
      </Badge>

      {/* IAA */}
      {iaaScore != null && iaaScore > 0 && (
        <Badge variant={iaaVariant(iaaScore)}>
          {t("datasets.iaa", "IAA")} {(iaaScore * 100).toFixed(0)}%
        </Badge>
      )}

      {/* PII */}
      <Badge variant={piiVariant(piiScrubVerified)}>
        {piiScrubVerified
          ? t("datasets.piiScrubbed", "PII Scrubbed")
          : t("datasets.piiPending", "PII Pending")}
      </Badge>

      {/* Consent */}
      {consentCoveragePct != null && consentCoveragePct > 0 && (
        <Badge variant={consentCoveragePct >= 80 ? "success" : "warning"}>
          {t("datasets.consent", "Consent")} {consentCoveragePct.toFixed(0)}%
        </Badge>
      )}

      {/* Class count */}
      {classCount > 0 && (
        <Badge variant="default">
          {t("datasets.classCount", "{{count}} classes", { count: classCount })}
        </Badge>
      )}

      {/* Sample count */}
      {sampleCount != null && sampleCount > 0 && (
        <Badge variant="default">
          {sampleCount.toLocaleString()} {t("datasets.images", "images")}
        </Badge>
      )}
    </div>
  );
}
