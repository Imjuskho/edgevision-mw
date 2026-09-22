import { useCallback, useEffect, useMemo, useState } from "react";
import { studioApi } from "../services/api";
import type { Dataset, ImageItem, NodeInfo } from "../types";

export type SearchResultKind = "dataset" | "node" | "image" | "action";

export interface GlobalSearchResult {
  id: string;
  kind: SearchResultKind;
  title: string;
  subtitle?: string;
  meta?: string;
  datasetId?: string;
}

interface UseGlobalSearchOptions {
  datasets: Dataset[];
  activeDatasetId?: string;
  debounceMs?: number;
}

export function useGlobalSearch({ datasets, activeDatasetId, debounceMs = 250 }: UseGlobalSearchOptions) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [remoteDatasets, setRemoteDatasets] = useState<Dataset[]>([]);
  const [nodes, setNodes] = useState<NodeInfo[]>([]);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [loading, setLoading] = useState(false);

  const [prevDebouncedQuery, setPrevDebouncedQuery] = useState(debouncedQuery);
  if (debouncedQuery !== prevDebouncedQuery) {
    setPrevDebouncedQuery(debouncedQuery);
    if (!debouncedQuery) {
      setRemoteDatasets([]);
      setNodes([]);
      setImages([]);
      setLoading(false);
    } else {
      setLoading(true);
    }
  }
  const [prevActiveDatasetId, setPrevActiveDatasetId] = useState(activeDatasetId);
  if (activeDatasetId !== prevActiveDatasetId) {
    setPrevActiveDatasetId(activeDatasetId);
    if (!activeDatasetId) setImages([]);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), debounceMs);
    return () => window.clearTimeout(timer);
  }, [query, debounceMs]);

  useEffect(() => {
    if (!debouncedQuery) return;

    let cancelled = false;

    (async () => {
      try {
        const q = debouncedQuery.toLowerCase();
        const localMatches = datasets.filter(
          (ds) =>
            ds.name?.toLowerCase().includes(q) ||
            ds.dataset_id?.toLowerCase().includes(q) ||
            ds.id?.toLowerCase().includes(q),
        );

        const requests: Promise<void>[] = [];

        requests.push(
          studioApi
            .listDatasets({ search: debouncedQuery, page_size: 20 })
            .then((resp) => {
              if (cancelled) return;
              const items = resp.data?.items ?? resp.data ?? [];
              setRemoteDatasets(Array.isArray(items) ? items : []);
            })
            .catch(() => {
              if (!cancelled) setRemoteDatasets(localMatches);
            }),
        );

        requests.push(
          studioApi
            .listNodes()
            .then((resp) => {
              if (cancelled) return;
              const list = (resp.data?.items ?? resp.data ?? []) as NodeInfo[];
              setNodes(
                (Array.isArray(list) ? list : []).filter(
                  (n) =>
                    n.node_id?.toLowerCase().includes(q) ||
                    n.district?.toLowerCase().includes(q) ||
                    n.category?.toLowerCase().includes(q),
                ),
              );
            })
            .catch(() => {
              if (!cancelled) setNodes([]);
            }),
        );

        if (activeDatasetId) {
          requests.push(
            studioApi
              .listImages(activeDatasetId, 1, 100)
              .then((resp) => {
                if (cancelled) return;
                const list = (resp.data?.images ?? resp.data ?? []) as ImageItem[];
                setImages(
                  (Array.isArray(list) ? list : []).filter(
                    (img) =>
                      String(img.index + 1).includes(q) ||
                      img.annotation_id?.toLowerCase().includes(q),
                  ),
                );
              })
              .catch(() => {
                if (!cancelled) setImages([]);
              }),
          );
        }

        await Promise.all(requests);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, datasets, activeDatasetId]);

  const results = useMemo((): GlobalSearchResult[] => {
    if (!debouncedQuery) return [];

    const seen = new Set<string>();
    const out: GlobalSearchResult[] = [];

    const add = (item: GlobalSearchResult) => {
      const key = `${item.kind}:${item.id}`;
      if (seen.has(key)) return;
      seen.add(key);
      out.push(item);
    };

    for (const ds of remoteDatasets) {
      add({
        id: ds.dataset_id || ds.id,
        kind: "dataset",
        title: ds.name || ds.dataset_id,
        subtitle: ds.dataset_id,
        meta: ds.status,
      });
    }

    for (const node of nodes.slice(0, 12)) {
      add({
        id: node.node_id,
        kind: "node",
        title: node.node_id,
        subtitle: `${node.district} · ${node.category}`,
        meta: node.status,
      });
    }

    for (const img of images.slice(0, 12)) {
      add({
        id: img.annotation_id,
        kind: "image",
        title: `Image ${img.index + 1}`,
        subtitle: img.annotation_id,
        meta: `#${img.index + 1}`,
        datasetId: activeDatasetId,
      });
    }

    return out;
  }, [debouncedQuery, remoteDatasets, nodes, images, activeDatasetId]);

  const clear = useCallback(() => {
    setQuery("");
    setDebouncedQuery("");
  }, []);

  return { query, setQuery, debouncedQuery, results, loading, clear };
}
