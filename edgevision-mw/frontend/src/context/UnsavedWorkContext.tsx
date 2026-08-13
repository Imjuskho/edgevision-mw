import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { flushSessionSync, getPendingSyncCount } from "../hooks/useOfflineSync";
import i18n from "../i18n";

interface UnsavedWorkContextValue {
  isDirty: boolean;
  setDirty: (dirty: boolean) => void;
  /** Returns true if navigation should proceed. */
  confirmLeaveIfNeeded: (sessionId?: string) => Promise<boolean>;
}

const UnsavedWorkContext = createContext<UnsavedWorkContextValue | null>(null);

export function UnsavedWorkProvider({ children }: { children: ReactNode }) {
  const [isDirty, setIsDirty] = useState(false);

  const setDirty = useCallback((dirty: boolean) => {
    setIsDirty(dirty);
  }, []);

  const confirmLeaveIfNeeded = useCallback(
    async (sessionId?: string): Promise<boolean> => {
      const pending = sessionId ? await getPendingSyncCount(sessionId) : 0;
      if (!isDirty && pending === 0) return true;

      let message: string;
      if (isDirty && pending > 0) {
        message = i18n.t("unsaved.both", { count: pending });
      } else if (isDirty) {
        message = i18n.t("unsaved.dirty");
      } else {
        message = i18n.t("unsaved.pending", { count: pending });
      }

      if (!window.confirm(message)) return false;

      if (sessionId && pending > 0 && navigator.onLine) {
        await flushSessionSync(sessionId);
      }

      setIsDirty(false);
      return true;
    },
    [isDirty],
  );

  const value = useMemo(
    () => ({ isDirty, setDirty, confirmLeaveIfNeeded }),
    [isDirty, setDirty, confirmLeaveIfNeeded],
  );

  return <UnsavedWorkContext.Provider value={value}>{children}</UnsavedWorkContext.Provider>;
}

export function useUnsavedWork(): UnsavedWorkContextValue {
  const ctx = useContext(UnsavedWorkContext);
  if (!ctx) throw new Error("useUnsavedWork must be used within UnsavedWorkProvider");
  return ctx;
}
