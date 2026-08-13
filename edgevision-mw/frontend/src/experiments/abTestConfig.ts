export interface Experiment {
  id: string;
  name: string;
  description: string;
  variants: Variant[];
  rolloutPercent: number;
  eligibleRoles: string[];
}

export interface Variant {
  id: string;
  name: string;
  config: Record<string, any>;
  weight: number;
}

export const EXPERIMENTS: Record<string, Experiment> = {
  ai_assist_mode: {
    id: 'ai_assist_mode',
    name: 'AI Assist Interaction Mode',
    description: 'Test click-to-segment vs full-image pre-label vs no AI',
    rolloutPercent: 100,
    eligibleRoles: ['annotator', 'senior_annotator'],
    variants: [
      {
        id: 'control',
        name: 'No AI Assist',
        config: { aiAssistEnabled: false, showPrelabels: false },
        weight: 20,
      },
      {
        id: 'full_image',
        name: 'Full Image Pre-label',
        config: { aiAssistEnabled: true, mode: 'full_image', showPrelabels: true },
        weight: 40,
      },
      {
        id: 'click_segment',
        name: 'Click-to-Segment',
        config: { aiAssistEnabled: true, mode: 'click_segment', showPrelabels: false },
        weight: 40,
      },
    ],
  },

  turbo_review_layout: {
    id: 'turbo_review_layout',
    name: 'Turbo Review Layout',
    description: 'Test single-image vs grid layout for QA review',
    rolloutPercent: 50,
    eligibleRoles: ['senior_annotator'],
    variants: [
      {
        id: 'single',
        name: 'Single Image Focus',
        config: { layout: 'single', thumbnailStrip: true },
        weight: 50,
      },
      {
        id: 'grid',
        name: 'Grid Gallery',
        config: { layout: 'grid', columns: 4 },
        weight: 50,
      },
    ],
  },
};

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash);
}

export function assignVariant(
  experimentId: string,
  userId: string
): Variant | null {
  const experiment = EXPERIMENTS[experimentId];
  if (!experiment) return null;

  const hash = hashString(`${experimentId}:${userId}`);
  const bucket = hash % 100;

  if (bucket >= experiment.rolloutPercent) return null;

  const totalWeight = experiment.variants.reduce((sum, v) => sum + v.weight, 0);
  let cumulative = 0;
  const variantBucket = hash % totalWeight;

  for (const variant of experiment.variants) {
    cumulative += variant.weight;
    if (variantBucket < cumulative) return variant;
  }

  return experiment.variants[0];
}

interface ExperimentEvent {
  experimentId: string;
  variantId: string;
  userId: string;
  eventType: 'exposed' | 'converted' | 'dismissed';
  metadata?: Record<string, any>;
  timestamp: string;
}

export function trackExperimentEvent(event: Omit<ExperimentEvent, 'timestamp'>): void {
  const fullEvent: ExperimentEvent = {
    ...event,
    timestamp: new Date().toISOString(),
  };

  const queue = JSON.parse(localStorage.getItem('experiment_events') || '[]');
  queue.push(fullEvent);
  localStorage.setItem('experiment_events', JSON.stringify(queue));

  if (queue.length >= 10) {
    flushExperimentEvents();
  }
}

async function flushExperimentEvents(): Promise<void> {
  const queue = JSON.parse(localStorage.getItem('experiment_events') || '[]');
  if (queue.length === 0) return;

  try {
    await fetch('/api/v1/analytics/experiments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('jwt')}`,
      },
      body: JSON.stringify({ events: queue }),
    });
    localStorage.setItem('experiment_events', '[]');
  } catch {
    // Keep in queue for retry
  }
}

window.addEventListener('beforeunload', () => {
  flushExperimentEvents();
});

import { useMemo, useCallback } from 'react';

export function useExperiment(experimentId: string, userId: string) {
  const variant = useMemo(() => assignVariant(experimentId, userId), [experimentId, userId]);

  const track = useCallback(
    (eventType: ExperimentEvent['eventType'], metadata?: Record<string, any>) => {
      if (!variant) return;
      trackExperimentEvent({
        experimentId,
        variantId: variant.id,
        userId,
        eventType,
        metadata,
      });
    },
    [variant, experimentId, userId]
  );

  return { variant, track };
}
