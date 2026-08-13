import { Monitor, Moon, Sun, Contrast } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStudioSettings, type StudioThemePreference } from "../../context/StudioSettingsContext";
import { IconButton } from "./IconButton";

const CYCLE: StudioThemePreference[] = ["system", "dark", "light", "high-contrast"];

const ICONS = {
  system: Monitor,
  dark: Moon,
  light: Sun,
  "high-contrast": Contrast,
} as const;

export function ThemeToggle() {
  const { t } = useTranslation();
  const { settings, updatePersonal, resolvedTheme } = useStudioSettings();
  const current = settings.personal.theme;
  const Icon = ICONS[current];

  const cycle = () => {
    const idx = CYCLE.indexOf(current);
    const next = CYCLE[(idx + 1) % CYCLE.length];
    updatePersonal({ theme: next });
  };

  return (
    <IconButton
      label={t("settings.theme", "Theme") + `: ${t(`settings.theme_${resolvedTheme}`, resolvedTheme)}`}
      onClick={cycle}
    >
      <Icon size={18} />
    </IconButton>
  );
}
