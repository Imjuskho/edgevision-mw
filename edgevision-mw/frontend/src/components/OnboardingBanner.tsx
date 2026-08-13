import { useTranslation } from "react-i18next";
import { useStudioSettings } from "../context/StudioSettingsContext";
import { isAnnotatorRole } from "../utils/roles";
import { useAuth } from "../hooks/useAuth";

export function OnboardingBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { settings, completeOnboarding } = useStudioSettings();

  if (!isAnnotatorRole(user?.role)) return null;
  if (settings.personal.onboardingComplete) return null;

  return (
    <div className="onboarding-banner" role="region" aria-label={t("onboarding.title", "Getting started")}>
      <div className="onboarding-banner-content">
        <h2>{t("onboarding.title", "Welcome to EdgeVision Studio")}</h2>
        <p>
          {t(
            "onboarding.annotatorBody",
            "Your workspace is focused on labeling and data tasks. Pick a dataset from the sidebar, open your queue, and start annotating.",
          )}
        </p>
        <ol className="onboarding-steps">
          <li>{t("onboarding.step1", "Select a dataset in the sidebar")}</li>
          <li>{t("onboarding.step2", "Open Queue or Annotate to start work")}</li>
          <li>{t("onboarding.step3", "Save often — offline sync keeps your progress safe")}</li>
        </ol>
      </div>
      <button type="button" className="btn btn-primary onboarding-dismiss" onClick={completeOnboarding}>
        {t("onboarding.dismiss", "Got it")}
      </button>
    </div>
  );
}
