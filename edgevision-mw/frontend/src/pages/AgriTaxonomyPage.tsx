import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";
import { AGRI_CROP_DISPLAY_NAMES, AGRI_HEALTH_DISPLAY_NAMES } from "../constants/agriTaxonomy";
import type { AgriClassInfo } from "../types";
import { toStyle } from "../utils/toStyle";
import { TaxonomyContextBanner } from "../components/TaxonomyContextBanner";
import { PageShell } from "../components/PageShell";

interface Props {
  datasetId?: string;
}

export default function AgriTaxonomyPage({ datasetId }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith("ny") ? "ny" : "en";
  const [cropClasses, setCropClasses] = useState<AgriClassInfo[]>([]);
  const [healthClasses, setHealthClasses] = useState<AgriClassInfo[]>([]);
  const [version, setVersion] = useState("");
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"crops" | "health">("crops");

  useEffect(() => {
    studioApi
      .getAgriClasses()
      .then((resp) => {
        const data = resp.data as { classes: (AgriClassInfo & { category?: string })[]; version: string };
        const crops = data.classes.filter((c) => c.category === "crop" || !c.category);
        const health = data.classes.filter((c) => c.category === "health");
        setCropClasses(crops.length > 0 ? crops : data.classes.slice(0, Math.ceil(data.classes.length / 2)));
        setHealthClasses(health);
        setVersion(data.version);
      })
      .catch(() => {
        // silent
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <PageShell accent="taxonomy" title={t("taxonomy.agriTitle")}>
        <div className="empty-state">{t("taxonomy.loading")}</div>
      </PageShell>
    );
  }

  const activeClasses = activeTab === "crops" ? cropClasses : healthClasses;

  return (
    <PageShell
      accent="taxonomy"
      title={t("taxonomy.agriTitle")}
      subtitle={t("taxonomy.agriSubtitle", "Crop types and plant health conditions for agriculture labeling.")}
      badge={version ? t("taxonomy.version", { version }) : undefined}
    >
      <TaxonomyContextBanner datasetId={datasetId} analysisView="agriAnalysis" taxonomyLabelKey="nav.agriTaxonomy" />

      <div className="agri-taxonomy-tabs">
        <button
          type="button"
          className={`agri-taxonomy-tab ${activeTab === "crops" ? "active" : ""}`}
          onClick={() => setActiveTab("crops")}
        >
          {t("taxonomy.cropTypes")} ({cropClasses.length})
        </button>
        <button
          type="button"
          className={`agri-taxonomy-tab ${activeTab === "health" ? "active" : ""}`}
          onClick={() => setActiveTab("health")}
        >
          {t("taxonomy.healthConditions")} ({healthClasses.length})
        </button>
      </div>

      <div className="agri-taxonomy-grid">
        {activeClasses.map((cls) => (
          <div key={cls.id} className="agri-taxonomy-card ui-panel">
            <div className="agri-taxonomy-color" style={toStyle({ backgroundColor: cls.color })} />
            <div className="agri-taxonomy-info">
              <div className="agri-taxonomy-name">
                {(activeTab === "crops" ? AGRI_CROP_DISPLAY_NAMES : AGRI_HEALTH_DISPLAY_NAMES)[cls.name]?.[lang] ?? cls.name}
              </div>
              <div className="agri-taxonomy-key">{cls.name}</div>
              <div className="agri-taxonomy-id">{t("taxonomy.classId", { id: cls.id })}</div>
              <div className="agri-taxonomy-desc">{cls.description}</div>
            </div>
          </div>
        ))}
      </div>
    </PageShell>
  );
}
