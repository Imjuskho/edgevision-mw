import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStudioSettings } from "../context/StudioSettingsContext";
import { useAuth } from "../hooks/useAuth";
import { Tour } from "./ui/Tour";
import { roleSupportsTourTrack } from "../utils/homePersona";

interface RawTourStep {
  id: string;
  target?: string;
  titleKey: string;
  bodyKey: string;
}

const TOUR_STEPS: Record<string, RawTourStep[]> = {
  ANNOTATOR: [
    { id: "sidebar", target: "[data-tour='sidebar']", titleKey: "tour.annotator.sidebarTitle", bodyKey: "tour.annotator.sidebarBody" },
    { id: "annotate", target: "[data-tour='nav-annotate']", titleKey: "tour.annotator.annotateTitle", bodyKey: "tour.annotator.annotateBody" },
    { id: "shortcuts", target: "[data-tour='topbar']", titleKey: "tour.annotator.shortcutsTitle", bodyKey: "tour.annotator.shortcutsBody" },
    { id: "save", target: "[data-tour='topbar']", titleKey: "tour.annotator.saveTitle", bodyKey: "tour.annotator.saveBody" },
  ],
  OPERATOR: [
    { id: "fleet", target: "[data-tour='nav-fleet']", titleKey: "tour.operator.fleetTitle", bodyKey: "tour.operator.fleetBody" },
    { id: "upload", target: "[data-tour='nav-upload']", titleKey: "tour.operator.uploadTitle", bodyKey: "tour.operator.uploadBody" },
    { id: "export", target: "[data-tour='nav-export']", titleKey: "tour.operator.exportTitle", bodyKey: "tour.operator.exportBody" },
  ],
  QA: [
    { id: "review", target: "[data-tour='nav-review']", titleKey: "tour.qa.reviewTitle", bodyKey: "tour.qa.reviewBody" },
    { id: "dedup", target: "[data-tour='nav-dedup']", titleKey: "tour.qa.dedupTitle", bodyKey: "tour.qa.dedupBody" },
    { id: "health", target: "[data-tour='nav-health']", titleKey: "tour.qa.healthTitle", bodyKey: "tour.qa.healthBody" },
  ],
  ADMIN: [
    { id: "review", target: "[data-tour='nav-review']", titleKey: "tour.qa.reviewTitle", bodyKey: "tour.qa.reviewBody" },
    { id: "assign", target: "[data-tour='nav-assign']", titleKey: "tour.admin.assignTitle", bodyKey: "tour.admin.assignBody" },
    { id: "export", target: "[data-tour='nav-export']", titleKey: "tour.qa.exportTitle", bodyKey: "tour.qa.exportBody" },
  ],
  FIELD_TECH: [
    { id: "fleet", target: "[data-tour='nav-fleet']", titleKey: "tour.field.fleetTitle", bodyKey: "tour.field.fleetBody" },
    { id: "datasets", target: "[data-tour='nav-datasets']", titleKey: "tour.field.datasetsTitle", bodyKey: "tour.field.datasetsBody" },
  ],
};

export function RoleAwareTour() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { settings, completeOnboarding } = useStudioSettings();
  const [stepIndex, setStepIndex] = useState(0);

  const track = roleSupportsTourTrack(user?.role);
  const rawSteps = TOUR_STEPS[track] ?? TOUR_STEPS.ANNOTATOR;
  const steps = useMemo(
    () =>
      rawSteps.map((step) => ({
        ...step,
        title: t(step.titleKey),
        body: t(step.bodyKey),
      })),
    [rawSteps, t],
  );

  const open = !settings.personal.onboardingComplete;

  const finish = () => {
    completeOnboarding();
    setStepIndex(0);
  };

  return (
    <Tour
      open={open}
      steps={steps}
      stepIndex={stepIndex}
      onNext={() => setStepIndex((i) => Math.min(i + 1, steps.length - 1))}
      onPrev={() => setStepIndex((i) => Math.max(i - 1, 0))}
      onSkip={finish}
      onFinish={finish}
    />
  );
}
