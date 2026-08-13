import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { buildPath, type View } from "../routes/paths";

interface Props {
  datasetId?: string;
  analysisView: View;
  taxonomyLabelKey: string;
}

/** Links global taxonomy reference pages back to dataset-scoped analysis when a dataset is active. */
export function TaxonomyContextBanner({ datasetId, analysisView, taxonomyLabelKey }: Props) {
  const { t } = useTranslation();

  if (datasetId) {
    return (
      <div className="taxonomy-context-banner">
        <span>{t("taxonomy.viewingGlobal", { name: t(taxonomyLabelKey) })}</span>
        <Link className="btn btn-sm" to={buildPath(analysisView, { datasetId })}>
          {t("taxonomy.openAnalysis", { datasetId })}
        </Link>
      </div>
    );
  }

  return (
    <div className="taxonomy-context-banner taxonomy-context-banner-muted">
      <span>{t("taxonomy.noDataset")}</span>
      <Link className="btn btn-sm" to="/datasets">
        {t("taxonomy.selectDataset")}
      </Link>
    </div>
  );
}
