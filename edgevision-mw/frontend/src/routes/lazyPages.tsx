import { lazy } from "react";

export const LazyAnnotationPage = lazy(() => import("../pages/AnnotationPage"));
export const LazySegmentPage = lazy(() => import("../pages/SegmentPage"));
export const LazyNodeManagementPage = lazy(() => import("../pages/NodeManagementPage"));
export const LazyAgriAnalysisPage = lazy(() => import("../pages/AgriAnalysisPage"));
export const LazyAgriTaxonomyPage = lazy(() => import("../pages/AgriTaxonomyPage"));
export const LazyUploadPage = lazy(() => import("../pages/UploadPage"));
export const LazyQueuePage = lazy(() => import("../pages/QueuePage"));
export const LazyAdminAssignPage = lazy(() => import("../pages/AdminAssignPage"));
export const LazyReviewPage = lazy(() => import("../pages/ReviewPage"));
export const LazyRoadAnalysisPage = lazy(() => import("../pages/RoadAnalysisPage"));
export const LazyRoadTaxonomyPage = lazy(() => import("../pages/RoadTaxonomyPage"));
export const LazyTrainingPage = lazy(() => import("../pages/TrainingPage"));
export const LazyDatasetBrowser = lazy(() => import("../pages/DatasetBrowser"));
export const LazyLiveAnnotatePage = lazy(() => import("../pages/LiveAnnotatePage"));
export const LazyHealthDashboard = lazy(() =>
  import("../components/HealthDashboard/HealthDashboard").then((m) => ({
    default: m.HealthDashboard,
  })),
);
export const LazyDedupPanel = lazy(() =>
  import("../components/DedupPanel/DedupPanel").then((m) => ({ default: m.DedupPanel })),
);
export const LazyNotFoundPage = lazy(() => import("../pages/NotFoundPage"));
export const LazySettingsPage = lazy(() => import("../pages/SettingsPage"));
export const LazyExportPreview = lazy(() =>
  import("../components/ExportPreview/ExportPreview").then((m) => ({
    default: m.ExportPreview,
  })),
);
export const LazyOperatorDashboardPage = lazy(() => import("../pages/OperatorDashboardPage"));
export const LazyBuyerDashboardPage = lazy(() => import("../pages/BuyerDashboardPage"));
export const LazyMarketplacePage = lazy(() => import("../pages/MarketplacePage"));
export const LazySubjectPortalPage = lazy(() => import("../pages/SubjectPortalPage"));
