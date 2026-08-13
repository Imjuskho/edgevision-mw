import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Dataset } from "../../types";
import type { View } from "../../routes/paths";
import { buildPath } from "../../routes/paths";
import { Breadcrumbs, type BreadcrumbItem } from "../ui/Breadcrumbs";

interface UseBreadcrumbsArgs {
  view: View;
  datasetId: string;
  datasets: Dataset[];
  onNavigate: (path: string) => void;
}

export function useBreadcrumbs({ view, datasetId, datasets, onNavigate }: UseBreadcrumbsArgs) {
  const { t } = useTranslation();

  return useMemo(() => {
    if (view === "home" || !datasetId) return [];

    const ds = datasets.find((d) => (d.dataset_id || d.id) === datasetId);
    const dsName = ds?.name || datasetId;
    const items: BreadcrumbItem[] = [
      { label: t("nav.datasets", "Datasets"), onClick: () => onNavigate("/datasets") },
      { label: dsName, onClick: () => onNavigate(buildPath("home", { datasetId })) },
    ];

    items.push({ label: t(`views.${view}`, view) });

    return items;
  }, [view, datasetId, datasets, onNavigate, t]);
}

export function AppBreadcrumbs(props: UseBreadcrumbsArgs & { className?: string }) {
  const items = useBreadcrumbs(props);
  if (items.length === 0) return null;
  return <Breadcrumbs items={items} className={props.className} />;
}
