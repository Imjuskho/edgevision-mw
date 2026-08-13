import { useState, useCallback } from "react";
import { studioApi } from "../services/api";
import type { InstanceMask, RoadSegAnnotation } from "../types";

interface UseRoadSegmentationReturn {
  isSegmenting: boolean;
  instances: InstanceMask[];
  annotations: RoadSegAnnotation[];
  error: string | null;
  segmentViaApi: (imageId: string) => Promise<InstanceMask[]>;
  acceptInstance: (id: string) => void;
  rejectInstance: (id: string) => void;
  acceptAll: () => void;
  rejectAll: () => void;
  setAnnotations: (anns: RoadSegAnnotation[]) => void;
  clearInstances: () => void;
}

let annotationIdCounter = 0;

function nextAnnotationId(): string {
  annotationIdCounter += 1;
  return `road_ann_${annotationIdCounter}_${Date.now()}`;
}

export function useRoadSegmentation(): UseRoadSegmentationReturn {
  const [isSegmenting, setIsSegmenting] = useState(false);
  const [instances, setInstances] = useState<InstanceMask[]>([]);
  const [annotations, setAnnotations] = useState<RoadSegAnnotation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const segmentViaApi = useCallback(async (imageId: string): Promise<InstanceMask[]> => {
    setIsSegmenting(true);
    setError(null);
    try {
      const resp = await studioApi.segmentRoad(imageId);
      const result = resp.data as { instances: InstanceMask[] };
      setInstances(result.instances);
      const anns: RoadSegAnnotation[] = result.instances.map((inst) => ({
        id: nextAnnotationId(),
        class_id: inst.class_id,
        class_name: inst.class_name,
        confidence: inst.confidence,
        polygon: inst.polygon ?? [],
        accepted: true,
      }));
      setAnnotations(anns);
      return result.instances;
    } catch (err) {
      const axiosDetail =
        typeof err === "object" &&
        err !== null &&
        "response" in err &&
        typeof (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
          ? (err as { response: { data: { detail: string } } }).response.data.detail
          : null;
      const msg =
        axiosDetail ??
        (err instanceof Error ? err.message : "Road segmentation API call failed");
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsSegmenting(false);
    }
  }, []);

  const acceptInstance = useCallback((id: string) => {
    setAnnotations((prev) =>
      prev.map((a) => (a.id === id ? { ...a, accepted: true } : a))
    );
  }, []);

  const rejectInstance = useCallback((id: string) => {
    setAnnotations((prev) =>
      prev.map((a) => (a.id === id ? { ...a, accepted: false } : a))
    );
  }, []);

  const acceptAll = useCallback(() => {
    setAnnotations((prev) => prev.map((a) => ({ ...a, accepted: true })));
  }, []);

  const rejectAll = useCallback(() => {
    setAnnotations((prev) => prev.map((a) => ({ ...a, accepted: false })));
  }, []);

  const clearInstances = useCallback(() => {
    setInstances([]);
    setAnnotations([]);
    annotationIdCounter = 0;
  }, []);

  return {
    isSegmenting,
    instances,
    annotations,
    error,
    segmentViaApi,
    acceptInstance,
    rejectInstance,
    acceptAll,
    rejectAll,
    setAnnotations,
    clearInstances,
  };
}
