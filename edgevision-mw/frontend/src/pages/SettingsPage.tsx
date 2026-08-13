import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import {
  DEFAULT_STUDIO_SETTINGS,
  useStudioSettings,
  type StudioFeatureFlags,
} from "../context/StudioSettingsContext";
import { Switch } from "../components/ui";
import { canManageOperationalSettings, isAdminRole } from "../utils/roles";
import { useAuth } from "../hooks/useAuth";
import { AuditLogPanel } from "../components/AuditLogPanel";

const FEATURE_KEYS: (keyof StudioFeatureFlags)[] = [
  "liveAnnotate",
  "training",
  "export",
  "fleet",
  "roadAnalysis",
  "agriAnalysis",
  "dedup",
  "healthDashboard",
  "roadTaxonomy",
  "agriTaxonomy",
];

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`settings-toggle-row${disabled ? " settings-toggle-row--disabled" : ""}`}>
      <div className="settings-toggle-copy">
        <span className="settings-toggle-label">{label}</span>
        {description && <span className="settings-toggle-desc">{description}</span>}
      </div>
      <Switch checked={checked} onChange={onChange} disabled={disabled} />
    </label>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const {
    settings,
    syncStatus,
    updatePersonal,
    setFeature,
    updateOperational,
    resetSettings,
    expertMode,
  } = useStudioSettings();
  const isAdmin = canManageOperationalSettings(user?.role);
  const showAudit = isAdminRole(user?.role);
  const { personal, operational } = settings;

  const syncLabel =
    syncStatus === "syncing"
      ? t("settings.syncing", "Syncing…")
      : syncStatus === "error"
        ? t("settings.syncError", "Sync failed — saved locally")
        : syncStatus === "offline"
          ? t("settings.syncOffline", "Offline — using local copy")
          : t("settings.synced", "Synced to your account");

  return (
    <PageShell
      accent="settings"
      title={t("settings.title", "Settings")}
      subtitle={
        isAdmin
          ? t("settings.subtitleAdmin", "Personal preferences and operational controls for the workspace.")
          : t("settings.subtitlePersonal", "Your display and workflow preferences.")
      }
      actions={<span className={`settings-sync-badge settings-sync-badge--${syncStatus}`}>{syncLabel}</span>}
    >
      <div className="settings-grid">
        <section className="settings-panel">
          <h2>{t("settings.personalTitle", "Personal preferences")}</h2>
          <p className="settings-panel-desc">
            {t("settings.personalDesc", "Theme, motion, and layout — synced across your devices.")}
          </p>
          <div className="settings-toggle-list">
            <ToggleRow
              label={t("settings.lowDataOn", "Low data mode")}
              description={t("settings.lowDataDesc", "Smaller thumbnails and fewer animations on slow links.")}
              checked={personal.lowDataMode}
              onChange={(v) => updatePersonal({ lowDataMode: v })}
            />
            <ToggleRow
              label={t("settings.showDashboardHealth", "Show health on dashboard")}
              description={t("settings.showDashboardHealthDesc", "Display dataset health rings on the home dashboard.")}
              checked={personal.showDashboardHealth}
              onChange={(v) => updatePersonal({ showDashboardHealth: v })}
            />
            <ToggleRow
              label={t("settings.expertMode", "Expert mode")}
              description={t("settings.expertModeDesc", "Advanced dedup thresholds, fleet commands, review batch actions, and tuning options.")}
              checked={personal.expertMode}
              onChange={(v) => updatePersonal({ expertMode: v })}
            />
            <ToggleRow
              label={t("settings.compactSidebar", "Compact sidebar")}
              description={t("settings.compactSidebarDesc", "Tighter navigation for smaller screens.")}
              checked={personal.compactSidebar}
              onChange={(v) => updatePersonal({ compactSidebar: v })}
            />
            <ToggleRow
              label={t("settings.reducedMotion", "Reduce motion")}
              description={t("settings.reducedMotionDesc", "Minimize animations and transitions.")}
              checked={personal.reducedMotion}
              onChange={(v) => updatePersonal({ reducedMotion: v })}
            />
          </div>
        </section>

        {isAdmin && (
          <section className="settings-panel">
            <h2>{t("settings.operationalTitle", "Operational settings")}</h2>
            <p className="settings-panel-desc">
              {t("settings.operationalDesc", "Admin-only — controls which modules appear for all users. Changes are audited.")}
            </p>
            <div className="settings-toggle-list">
              {FEATURE_KEYS.map((key) => (
                <ToggleRow
                  key={key}
                  label={t(`settings.features.${key}`, key)}
                  description={t(`settings.features.${key}Desc`, "")}
                  checked={operational.features[key]}
                  onChange={(v) => setFeature(key, v)}
                />
              ))}
            </div>
            {expertMode && (
              <div className="settings-expert-block">
                <h3>{t("settings.dedupDefaults", "Dedup defaults")}</h3>
                <label className="settings-field">
                  <span>{t("settings.dedupThreshold", "Similarity threshold")}</span>
                  <input
                    type="range"
                    min={0.8}
                    max={0.99}
                    step={0.01}
                    value={operational.dedupDefaultThreshold}
                    onChange={(e) =>
                      updateOperational({ dedupDefaultThreshold: parseFloat(e.target.value) })
                    }
                  />
                  <span>{(operational.dedupDefaultThreshold * 100).toFixed(0)}%</span>
                </label>
              </div>
            )}
          </section>
        )}

        {showAudit && <AuditLogPanel />}

        <section className="settings-panel settings-panel--muted">
          <h2>{t("settings.resetTitle", "Reset")}</h2>
          <p className="settings-panel-desc">
            {t("settings.resetDesc", "Restore defaults. Language preference is unchanged.")}
          </p>
          <button type="button" className="btn" onClick={resetSettings}>
            {t("settings.resetButton", "Reset to defaults")}
          </button>
          <p className="settings-footnote">
            {t("settings.storageNote", "Preferences sync to your account; local storage is used as a fallback.")}
          </p>
        </section>
      </div>
    </PageShell>
  );
}

export { DEFAULT_STUDIO_SETTINGS as DEFAULT_SETTINGS };
