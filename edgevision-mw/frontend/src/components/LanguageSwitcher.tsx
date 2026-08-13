import { useTranslation } from "react-i18next";
import { Select } from "./ui";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ny", label: "Chichewa" },
] as const;

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const current = i18n.language.startsWith("ny") ? "ny" : "en";

  return (
    <Select
      value={current}
      options={LANGUAGES.map(({ code, label }) => ({ value: code, label }))}
      onChange={(lng) => {
        void i18n.changeLanguage(lng);
        localStorage.setItem("studio_language", lng);
        document.documentElement.lang = lng;
      }}
      aria-label={t("app.language", "Language")}
    />
  );
}
