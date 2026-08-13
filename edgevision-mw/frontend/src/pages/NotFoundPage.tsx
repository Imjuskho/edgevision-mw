import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <div className="page-shell not-found-page">
      <div className="empty-state not-found-inner">
        <h1 className="not-found-title">{t("errors.notFoundTitle")}</h1>
        <p className="not-found-message">{t("errors.notFoundMessage")}</p>
        <Link className="btn btn-primary" to="/">
          {t("errors.notFoundHome")}
        </Link>
      </div>
    </div>
  );
}
