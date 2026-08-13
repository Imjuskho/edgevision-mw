import { type ReactNode } from "react";
import { Navigate, useParams } from "react-router-dom";

interface DatasetParamBridgeProps {
  children: (datasetId: string) => ReactNode;
}

/** Read :datasetId from the matched route (single source of truth for dataset-scoped pages). */
export function DatasetParamBridge({ children }: DatasetParamBridgeProps) {
  const { datasetId: rawDatasetId } = useParams<{ datasetId: string }>();
  const datasetId = rawDatasetId ? decodeURIComponent(rawDatasetId) : "";

  if (!datasetId) {
    return <Navigate to="/datasets" replace />;
  }

  return <>{children(datasetId)}</>;
}
