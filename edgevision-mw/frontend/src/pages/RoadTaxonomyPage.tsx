import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";
import { ROAD_CLASS_DISPLAY_NAMES } from "../constants/roadTaxonomy";
import type { RoadClassInfo } from "../types";
import { toStyle } from "../utils/toStyle";
import { TaxonomyContextBanner } from "../components/TaxonomyContextBanner";
import { PageShell } from "../components/PageShell";

interface Props {
  datasetId?: string;
}

export default function RoadTaxonomyPage({ datasetId }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith("ny") ? "ny" : "en";
  const [classes, setClasses] = useState<RoadClassInfo[]>([]);
  const [version, setVersion] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    studioApi
      .getRoadClasses()
      .then((resp) => {
        const data = resp.data as { classes: RoadClassInfo[]; version: string };
        setClasses(data.classes);
        setVersion(data.version);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <PageShell accent="taxonomy" title={t("taxonomy.roadTitle")}>
        <div className="empty-state">{t("taxonomy.loading")}</div>
      </PageShell>
    );
  }

  if (loadError) {
    return (
      <PageShell accent="taxonomy" title={t("taxonomy.roadTitle")}>
        <div className="empty-state error-notice"><p>{t("taxonomy.loadFailed")}</p></div>
      </PageShell>
    );
  }

  return (
    <PageShell
      accent="taxonomy"
      title={t("taxonomy.roadTitle")}
      subtitle={t("taxonomy.roadSubtitle", "Reference labels for road condition and surface classes.")}
      badge={version ? t("taxonomy.version", { version }) : undefined}
    >
      <TaxonomyContextBanner datasetId={datasetId} analysisView="roadAnalysis" taxonomyLabelKey="nav.roadTaxonomy" />

      {classes.length === 0 && (
        <div className="road-taxonomy-empty ui-panel">
          <p>{t("taxonomy.roadEmpty")}</p>
        </div>
      )}

      <div className="road-taxonomy-grid">
        {classes.map((cls) => (
          <div key={cls.id} className="road-taxonomy-card ui-panel">
            <div className="road-taxonomy-color" style={toStyle({ backgroundColor: cls.color })} />
            <div className="road-taxonomy-info">
              <div className="road-taxonomy-name">
                {ROAD_CLASS_DISPLAY_NAMES[cls.name]?.[lang] ?? cls.name}
              </div>
              <div className="road-taxonomy-key">{cls.name}</div>
              <div className="road-taxonomy-id">{t("taxonomy.classId", { id: cls.id })}</div>
              <div className="road-taxonomy-desc">{cls.description}</div>
            </div>
          </div>
        ))}
      </div>
    </PageShell>
  );
}
