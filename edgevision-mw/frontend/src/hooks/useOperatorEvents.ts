import { useState, useEffect, useRef, useCallback } from "react";
import api from "../services/api";

export interface PerceptionEvent {
  id: string;
  event_type: string;
  rule_id: string;
  rule_name: string;
  track_id: number | null;
  class_name: string | null;
  taxonomy_label: string | null;
  confidence: number;
  bbox: number[] | null;
  started_at: string | null;
  triggered_at: string;
  duration_seconds: number | null;
  clip_frames: number;
  auto_save: boolean;
  dataset_id: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
}

interface PerceptionEventPage {
  items: PerceptionEvent[];
  total: number;
  limit: number;
  offset: number;
}

interface UseOperatorEventsOptions {
  pollIntervalMs?: number;
  limit?: number;
  eventTypes?: string[];
}

export function useOperatorEvents({
  pollIntervalMs = 5000,
  limit = 30,
  eventTypes,
}: UseOperatorEventsOptions = {}) {
  const [events, setEvents] = useState<PerceptionEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastSeenIdRef = useRef<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const fetchEvents = useCallback(async () => {
    try {
      const params: Record<string, string | number> = { limit, offset: 0 };
      if (eventTypes && eventTypes.length > 0) {
        params.event_type = eventTypes[0];
      }
      const res = await api.get<PerceptionEventPage>("/annotations/events", { params });
      const data = res.data;
      setEvents(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load events";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [limit, eventTypes]);

  useEffect(() => {
    fetchEvents();
    intervalRef.current = setInterval(fetchEvents, pollIntervalMs);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchEvents, pollIntervalMs]);

  const newCount = events.filter(
    (e) => lastSeenIdRef.current === null || e.id > lastSeenIdRef.current,
  ).length;

  const markSeen = useCallback(() => {
    if (events.length > 0) {
      lastSeenIdRef.current = events[0].id;
    }
  }, [events]);

  const refresh = useCallback(() => {
    setLoading(true);
    fetchEvents();
  }, [fetchEvents]);

  return { events, total, loading, error, newCount, markSeen, refresh };
}

export function useOperatorStats() {
  const [stats, setStats] = useState<{
    total_events: number;
    events_today: number;
    active_tracks: number;
    rules_loaded: number;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchStats = async () => {
      try {
        const res = await api.get<PerceptionEventPage>("/annotations/events", {
          params: { limit: 1, offset: 0 },
        });
        if (!cancelled) {
          setStats({
            total_events: res.data.total,
            events_today: res.data.total,
            active_tracks: 0,
            rules_loaded: 5,
          });
        }
      } catch {
        if (!cancelled) setStats(null);
      }
    };
    fetchStats();
    return () => { cancelled = true; };
  }, []);

  return stats;
}
