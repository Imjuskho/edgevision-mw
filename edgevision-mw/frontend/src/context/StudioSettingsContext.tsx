import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { View } from "../routes/paths";
import { useAuth } from "../hooks/useAuth";
import { studioApi } from "../services/api";
import { canManageOperationalSettings, canUseExpertFeatures } from "../utils/roles";

const STORAGE_KEY = "studio_settings_v2";
const SYNC_DEBOUNCE_MS = 800;

export type StudioThemePreference = "system" | "dark" | "light" | "high-contrast";
export type StudioTheme = "dark" | "light" | "high-contrast";

export interface StudioFeatureFlags {
  liveAnnotate: boolean;
  training: boolean;
  export: boolean;
  fleet: boolean;
  roadAnalysis: boolean;
  agriAnalysis: boolean;
  dedup: boolean;
  roadTaxonomy: boolean;
  agriTaxonomy: boolean;
  healthDashboard: boolean;
}

export interface PersonalSettings {
  theme: StudioThemePreference;
  showDashboardHealth: boolean;
  expertMode: boolean;
  compactSidebar: boolean;
  reducedMotion: boolean;
  lowDataMode: boolean;
  sidebarCollapsed: boolean;
  defaultZoom: number;
  onboardingComplete: boolean;
}

export interface OperationalSettings {
  features: StudioFeatureFlags;
  dedupDefaultThreshold: number;
  dedupDefaultMethods: string[];
}

export interface StudioSettings {
  personal: PersonalSettings;
  operational: OperationalSettings;
}

const DEFAULT_FEATURES: StudioFeatureFlags = {
  liveAnnotate: true,
  training: true,
  export: true,
  fleet: true,
  roadAnalysis: true,
  agriAnalysis: true,
  dedup: true,
  roadTaxonomy: true,
  agriTaxonomy: true,
  healthDashboard: true,
};

export const DEFAULT_SETTINGS: StudioSettings = {
  personal: {
    theme: "dark",
    showDashboardHealth: true,
    expertMode: false,
    compactSidebar: false,
    reducedMotion: false,
    lowDataMode: false,
    sidebarCollapsed: false,
    defaultZoom: 1,
    onboardingComplete: false,
  },
  operational: {
    features: { ...DEFAULT_FEATURES },
    dedupDefaultThreshold: 0.92,
    dedupDefaultMethods: ["phash", "clip"],
  },
};

const VIEW_FEATURE: Partial<Record<View, keyof StudioFeatureFlags>> = {
  liveAnnotate: "liveAnnotate",
  training: "training",
  export: "export",
  fleet: "fleet",
  roadAnalysis: "roadAnalysis",
  agriAnalysis: "agriAnalysis",
  dedup: "dedup",
  roadTaxonomy: "roadTaxonomy",
  agriTaxonomy: "agriTaxonomy",
  health: "healthDashboard",
};

function loadLocalSettings(): StudioSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<StudioSettings>;
    return {
      personal: { ...DEFAULT_SETTINGS.personal, ...parsed.personal },
      operational: {
        ...DEFAULT_SETTINGS.operational,
        ...parsed.operational,
        features: {
          ...DEFAULT_SETTINGS.operational.features,
          ...parsed.operational?.features,
        },
      },
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function persistLocal(settings: StudioSettings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // ignore quota errors
  }
}

function resolveTheme(preference: StudioThemePreference): StudioTheme {
  if (preference === "system") {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  return preference;
}

function applyDomEffects(settings: StudioSettings) {
  const root = document.documentElement;
  const resolved = resolveTheme(settings.personal.theme);
  root.setAttribute("data-theme", resolved);
  root.classList.toggle("reduced-motion", settings.personal.reducedMotion);
  root.classList.toggle("compact-sidebar", settings.personal.compactSidebar);
  root.classList.toggle("sidebar-collapsed", settings.personal.sidebarCollapsed);
  root.classList.toggle("low-data", settings.personal.lowDataMode);
}

interface StudioSettingsContextValue {
  settings: StudioSettings;
  resolvedTheme: StudioTheme;
  syncStatus: "idle" | "syncing" | "error" | "offline";
  updatePersonal: (patch: Partial<PersonalSettings>) => void;
  updateOperational: (patch: Partial<OperationalSettings>) => void;
  setFeature: (key: keyof StudioFeatureFlags, enabled: boolean) => void;
  resetSettings: () => void;
  completeOnboarding: () => void;
  isViewEnabled: (view: View) => boolean;
  /** Flat accessors for backward compatibility */
  expertMode: boolean;
  showDashboardHealth: boolean;
}

const StudioSettingsContext = createContext<StudioSettingsContextValue | null>(null);

export function StudioSettingsProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const [settings, setSettings] = useState<StudioSettings>(() => {
    const loaded = loadLocalSettings();
    // Migrate legacy theme values
    const theme = loaded.personal.theme as string;
    if (theme !== "system" && theme !== "dark" && theme !== "light" && theme !== "high-contrast") {
      loaded.personal.theme = "dark";
    }
    return loaded;
  });
  const [resolvedTheme, setResolvedTheme] = useState<StudioTheme>(() =>
    resolveTheme(loadLocalSettings().personal.theme),
  );
  const [syncStatus, setSyncStatus] = useState<"idle" | "syncing" | "error" | "offline">("idle");
  const syncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPatch = useRef<Partial<{ personal: PersonalSettings; operational: OperationalSettings }>>({});

  useEffect(() => {
    applyDomEffects(settings);
    persistLocal(settings);
    setResolvedTheme(resolveTheme(settings.personal.theme));
  }, [settings]);

  useEffect(() => {
    if (settings.personal.theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => {
      applyDomEffects(settings);
      setResolvedTheme(resolveTheme("system"));
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [settings]);

  // Load from backend when user authenticates
  useEffect(() => {
    if (!isAuthenticated || !user) return;
    let cancelled = false;
    (async () => {
      try {
        const resp = await studioApi.getUserSettings();
        if (cancelled) return;
        const remote = resp.data as StudioSettings & { personal: PersonalSettings; operational: OperationalSettings };
        setSettings({
          personal: { ...DEFAULT_SETTINGS.personal, ...remote.personal },
          operational: {
            ...DEFAULT_SETTINGS.operational,
            ...remote.operational,
            features: {
              ...DEFAULT_SETTINGS.operational.features,
              ...remote.operational?.features,
            },
          },
        });
        setSyncStatus("idle");
      } catch {
        if (!cancelled) setSyncStatus("offline");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user?.id]);

  const flushSync = useCallback(async () => {
    if (!isAuthenticated) return;
    const patch = pendingPatch.current;
    if (!Object.keys(patch).length) return;
    pendingPatch.current = {};
    setSyncStatus("syncing");
    try {
      await studioApi.patchUserSettings(patch);
      setSyncStatus("idle");
    } catch {
      setSyncStatus("error");
      pendingPatch.current = { ...pendingPatch.current, ...patch };
    }
  }, [isAuthenticated]);

  const scheduleSync = useCallback(
    (patch: Partial<{ personal: PersonalSettings; operational: OperationalSettings }>) => {
      pendingPatch.current = {
        personal: { ...pendingPatch.current.personal, ...patch.personal } as PersonalSettings | undefined,
        operational: { ...pendingPatch.current.operational, ...patch.operational } as OperationalSettings | undefined,
      };
      if (syncTimer.current) clearTimeout(syncTimer.current);
      syncTimer.current = setTimeout(() => void flushSync(), SYNC_DEBOUNCE_MS);
    },
    [flushSync],
  );

  const updatePersonal = useCallback(
    (patch: Partial<PersonalSettings>) => {
      setSettings((prev) => {
        const next = { ...prev, personal: { ...prev.personal, ...patch } };
        scheduleSync({ personal: next.personal });
        return next;
      });
    },
    [scheduleSync],
  );

  const updateOperational = useCallback(
    (patch: Partial<OperationalSettings>) => {
      if (!canManageOperationalSettings(user?.role)) return;
      setSettings((prev) => {
        const next: StudioSettings = {
          ...prev,
          operational: {
            ...prev.operational,
            ...patch,
            features: patch.features
              ? { ...prev.operational.features, ...patch.features }
              : prev.operational.features,
          },
        };
        scheduleSync({ operational: next.operational });
        return next;
      });
    },
    [scheduleSync, user?.role],
  );

  const setFeature = useCallback(
    (key: keyof StudioFeatureFlags, enabled: boolean) => {
      setSettings((prev) => {
        const next: StudioSettings = {
          ...prev,
          operational: {
            ...prev.operational,
            features: { ...prev.operational.features, [key]: enabled },
          },
        };
        scheduleSync({ operational: next.operational });
        return next;
      });
    },
    [scheduleSync],
  );

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
    scheduleSync({ personal: DEFAULT_SETTINGS.personal, operational: DEFAULT_SETTINGS.operational });
  }, [scheduleSync]);

  const completeOnboarding = useCallback(() => {
    updatePersonal({ onboardingComplete: true });
  }, [updatePersonal]);

  const isViewEnabled = useCallback(
    (view: View) => {
      const feature = VIEW_FEATURE[view];
      if (!feature) return true;
      return settings.operational.features[feature];
    },
    [settings.operational.features],
  );

  const expertMode =
    settings.personal.expertMode && canUseExpertFeatures(user?.role);

  const value = useMemo(
    () => ({
      settings,
      resolvedTheme,
      syncStatus,
      updatePersonal,
      updateOperational,
      setFeature,
      resetSettings,
      completeOnboarding,
      isViewEnabled,
      expertMode,
      showDashboardHealth: settings.personal.showDashboardHealth,
    }),
    [
      settings,
      resolvedTheme,
      syncStatus,
      updatePersonal,
      updateOperational,
      setFeature,
      resetSettings,
      completeOnboarding,
      isViewEnabled,
      expertMode,
    ],
  );

  return <StudioSettingsContext.Provider value={value}>{children}</StudioSettingsContext.Provider>;
}

export function useStudioSettings() {
  const ctx = useContext(StudioSettingsContext);
  if (!ctx) throw new Error("useStudioSettings must be used within StudioSettingsProvider");
  return ctx;
}

export { DEFAULT_SETTINGS as DEFAULT_STUDIO_SETTINGS, VIEW_FEATURE };
