import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import type { Dataset } from "../types";
import { buildPath, type View } from "./paths";
import { AdminRoute, RoleRoute } from "./AdminRoute";
import { SessionGate } from "./SessionGate";
import { DatasetParamBridge } from "./DatasetParamBridge";
import {
  LazyAdminAssignPage,
  LazyAgriAnalysisPage,
  LazyAgriTaxonomyPage,
  LazyAnnotationPage,
  LazyBuyerDashboardPage,
  LazyDatasetBrowser,
  LazyDedupPanel,
  LazyExportPreview,
  LazyHealthDashboard,
  LazyLiveAnnotatePage,
  LazyNodeManagementPage,
  LazyNotFoundPage,
  LazyOperatorDashboardPage,
  LazyQueuePage,
  LazyReviewPage,
  LazyRoadAnalysisPage,
  LazyRoadTaxonomyPage,
  LazySegmentPage,
  LazySettingsPage,
  LazySubjectPortalPage,
  LazyTrainingPage,
  LazyUploadPage,
  LazyMarketplacePage,
} from "./lazyPages";
import { TurboReview } from "../components/TurboReview/TurboReview";

export interface AppRoutesProps {
  datasetId: string;
  imageIndex: number;
  setImageIndex: (idx: number) => void;
  datasets: Dataset[];
  datasetsLoading: boolean;
  datasetsPage: number;
  datasetsPages: number;
  datasetsTotal: number;
  datasetsError: boolean;
  loadDatasets: (
    page?: number,
    append?: boolean,
    filters?: { search?: string; status?: string },
  ) => Promise<void>;
  refreshDatasets: (filters?: { search?: string; status?: string }) => void;
  loadMoreDatasets: () => Promise<void>;
  handleSelectDataset: (dsId: string) => void;
  onSessionReady: (sessionId: string, datasetId: string) => void;
  loadHealth: () => Promise<void>;
  homeContent: React.ReactNode;
}

export function AppRoutes({
  datasetId,
  imageIndex,
  setImageIndex,
  datasets,
  datasetsLoading,
  datasetsPage,
  datasetsPages,
  datasetsTotal,
  datasetsError,
  loadDatasets,
  refreshDatasets,
  loadMoreDatasets,
  handleSelectDataset,
  onSessionReady,
  loadHealth,
  homeContent,
}: AppRoutesProps) {
  const navigate = useNavigate();

  const navigateDatasetView = (view: View) => {
    navigate(buildPath(view, { datasetId: datasetId || undefined }));
  };

  return (
    <Routes>
      <Route path="/" element={homeContent} />

      <Route
        path="/datasets"
        element={
          <LazyDatasetBrowser
            datasets={datasets}
            loading={datasetsLoading}
            error={datasetsError}
            selectedId={datasetId}
            onSelect={handleSelectDataset}
            onRefresh={refreshDatasets}
            onLoadMore={loadMoreDatasets}
            hasMore={datasetsPage < datasetsPages}
            totalCount={datasetsTotal}
            currentPage={datasetsPage}
          />
        }
      />

      <Route path="/datasets/:datasetId" element={homeContent} />

      <Route
        path="/datasets/:datasetId/annotate"
        element={
          <SessionGate onSessionReady={onSessionReady}>
            {({ sessionId, datasetId: dsId }) => (
              <LazyAnnotationPage
                sessionId={sessionId}
                datasetId={dsId}
                imageIndex={imageIndex}
                onNavigate={setImageIndex}
                onSaved={loadHealth}
                onGoToUpload={() => navigateDatasetView("upload")}
              />
            )}
          </SessionGate>
        }
      />

      <Route
        path="/datasets/:datasetId/agri-annotate"
        element={
          <SessionGate onSessionReady={onSessionReady}>
            {({ sessionId, datasetId: dsId }) => (
              <LazyAnnotationPage
                sessionId={sessionId}
                datasetId={dsId}
                imageIndex={imageIndex}
                onNavigate={setImageIndex}
                onSaved={loadHealth}
                onGoToUpload={() => navigateDatasetView("upload")}
                taxonomyContext="agri"
              />
            )}
          </SessionGate>
        }
      />

      <Route
        path="/datasets/:datasetId/segment"
        element={
          <SessionGate onSessionReady={onSessionReady}>
            {({ sessionId, datasetId: dsId }) => (
              <LazySegmentPage
                sessionId={sessionId}
                datasetId={dsId}
                imageIndex={imageIndex}
                onSaved={loadHealth}
                onNavigate={setImageIndex}
              />
            )}
          </SessionGate>
        }
      />

      <Route
        path="/datasets/:datasetId/upload"
        element={
          <DatasetParamBridge>
            {(dsId) => (
              <LazyUploadPage
                datasetId={dsId}
                onUploaded={() => {
                  loadHealth();
                  loadDatasets();
                }}
              />
            )}
          </DatasetParamBridge>
        }
      />
      <Route
        path="/datasets/:datasetId/health"
        element={
          <DatasetParamBridge>
            {(dsId) => (
              <LazyHealthDashboard
                datasetId={dsId}
                onNavigate={(path) => {
                  if (path.includes("dedup")) navigate(buildPath("dedup", { datasetId: dsId }));
                  else if (path.includes("export")) navigate(buildPath("export", { datasetId: dsId }));
                }}
              />
            )}
          </DatasetParamBridge>
        }
      />
      <Route
        path="/datasets/:datasetId/dedup"
        element={
          <RoleRoute view="dedup">
            <DatasetParamBridge>
              {(dsId) => (
                <LazyDedupPanel
                  datasetId={dsId}
                  onNavigate={() => navigate(buildPath("health", { datasetId: dsId }))}
                />
              )}
            </DatasetParamBridge>
          </RoleRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/export"
        element={
          <RoleRoute view="export">
            <DatasetParamBridge>{(dsId) => <LazyExportPreview datasetId={dsId} />}</DatasetParamBridge>
          </RoleRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/road-analysis"
        element={
          <RoleRoute view="roadAnalysis">
            <DatasetParamBridge>{(dsId) => <LazyRoadAnalysisPage datasetId={dsId} />}</DatasetParamBridge>
          </RoleRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/agri-analysis"
        element={
          <RoleRoute view="agriAnalysis">
            <DatasetParamBridge>{(dsId) => <LazyAgriAnalysisPage datasetId={dsId} />}</DatasetParamBridge>
          </RoleRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/training"
        element={
          <RoleRoute view="training">
            <DatasetParamBridge>{(dsId) => <LazyTrainingPage datasetId={dsId} />}</DatasetParamBridge>
          </RoleRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/live-annotate"
        element={
          <DatasetParamBridge>
            {(dsId) => (
              <LazyLiveAnnotatePage
                datasetId={dsId}
                onSaved={() => {
                  loadHealth();
                  loadDatasets();
                }}
                onNavigateToAnnotate={(idx) => {
                  setImageIndex(idx);
                  navigate(buildPath("annotate", { datasetId: dsId }));
                }}
              />
            )}
          </DatasetParamBridge>
        }
      />

      <Route
        path="/queue"
        element={
          <LazyQueuePage
            onStartAnnotation={(dsId) => {
              navigate(buildPath("annotate", { datasetId: dsId }));
            }}
          />
        }
      />
      <Route
        path="/assign"
        element={
          <AdminRoute>
            <LazyAdminAssignPage />
          </AdminRoute>
        }
      />
      <Route
        path="/review"
        element={
          <AdminRoute>
            <LazyReviewPage />
          </AdminRoute>
        }
      />
      <Route
        path="/datasets/:datasetId/review/fast"
        element={
          <AdminRoute>
            <SessionGate onSessionReady={onSessionReady}>
              {({ sessionId, datasetId: dsId }) => (
                <div className="page-shell review-page">
                  <TurboReview
                    sessionId={sessionId}
                    datasetId={dsId}
                    onOpenInStudio={(idx) => {
                      setImageIndex(idx);
                      navigate(buildPath("annotate", { datasetId: dsId }));
                    }}
                  />
                </div>
              )}
            </SessionGate>
          </AdminRoute>
        }
      />
      <Route path="/road-taxonomy" element={<LazyRoadTaxonomyPage datasetId={datasetId} />} />
      <Route path="/agri-taxonomy" element={<LazyAgriTaxonomyPage datasetId={datasetId} />} />

      <Route path="/nodes" element={<RoleRoute view="fleet"><LazyNodeManagementPage /></RoleRoute>} />
      <Route path="/nodes/:nodeId" element={<RoleRoute view="fleet"><LazyNodeManagementPage /></RoleRoute>} />
      <Route path="/settings" element={<LazySettingsPage />} />

      {/* D1: Operator Console */}
      <Route path="/operator" element={<LazyOperatorDashboardPage />} />
      <Route path="/operator/dashboard" element={<LazyOperatorDashboardPage />} />

      {/* D2: Buyer Dashboard */}
      <Route path="/buyer" element={<LazyBuyerDashboardPage />} />
      <Route path="/buyer/dashboard" element={<LazyBuyerDashboardPage />} />

      {/* D2b: Marketplace */}
      <Route path="/marketplace" element={<LazyMarketplacePage />} />

      {/* D3: Subject Portal */}
      <Route path="/subject/:subjectHash" element={<LazySubjectPortalPage />} />

      <Route path="/annotate" element={<Navigate to="/datasets" replace />} />
      <Route path="/agri-annotate" element={<Navigate to="/datasets" replace />} />
      <Route path="/segment" element={<Navigate to="/datasets" replace />} />
      <Route path="/upload" element={<Navigate to="/datasets" replace />} />
      <Route path="/health" element={<Navigate to="/datasets" replace />} />
      <Route path="/dedup" element={<Navigate to="/datasets" replace />} />
      <Route path="/export" element={<Navigate to="/datasets" replace />} />
      <Route path="/road-analysis" element={<Navigate to="/datasets" replace />} />
      <Route path="/agri-analysis" element={<Navigate to="/datasets" replace />} />
      <Route path="/training" element={<Navigate to="/datasets" replace />} />
      <Route path="/live-annotate" element={<Navigate to="/datasets" replace />} />
      <Route path="/review/fast" element={<Navigate to="/datasets" replace />} />

      <Route path="*" element={<LazyNotFoundPage />} />
    </Routes>
  );
}
