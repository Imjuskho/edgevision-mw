import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "./cn";
import { IconButton } from "./IconButton";
import type { ToastType } from "./Toast.types";

export type { ToastType, ToastAction } from "./Toast.types";

interface ToastMessage {
  id: string;
  message: string;
  type: ToastType;
  action?: { label: string; onClick: () => void };
  durationMs: number;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, action?: { label: string; onClick: () => void }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_META: Record<ToastType, { label: string; Icon: typeof Info }> = {
  success: { label: "Success", Icon: CheckCircle2 },
  error: { label: "Error", Icon: XCircle },
  warning: { label: "Warning", Icon: AlertTriangle },
  info: { label: "Notice", Icon: Info },
};

const MAX_VISIBLE = 4;
const DEFAULT_DURATION = 4000;
const ACTION_DURATION = 8000;

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastMessage;
  onDismiss: (id: string) => void;
}) {
  const [progress, setProgress] = useState(100);
  const meta = TOAST_META[toast.type];

  useEffect(() => {
    const started = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const elapsed = now - started;
      const remaining = Math.max(0, 100 - (elapsed / toast.durationMs) * 100);
      setProgress(remaining);
      if (elapsed < toast.durationMs) {
        frame = requestAnimationFrame(tick);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [toast.durationMs, toast.id]);

  return (
    <div className={cn("ui-toast", `ui-toast--${toast.type}`)} role="alert">
      <div className={cn("ui-toast__icon", `ui-toast__icon--${toast.type}`)} aria-hidden="true">
        <meta.Icon size={18} strokeWidth={2} />
      </div>
      <div className="ui-toast__body">
        <p className="ui-toast__title">{meta.label}</p>
        <p className="ui-toast__message">{toast.message}</p>
        {toast.action && (
          <button
            type="button"
            className="ui-toast__action"
            onClick={() => {
              toast.action?.onClick();
              onDismiss(toast.id);
            }}
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <IconButton label="Dismiss notification" size="sm" className="ui-toast__close" onClick={() => onDismiss(toast.id)}>
        <X size={14} />
      </IconButton>
      <div className="ui-toast__progress" aria-hidden="true">
        <span className="ui-toast__progress-bar" style={{ "--progress": `${progress}%` } as React.CSSProperties} />
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timersRef = useRef<Map<string, number>>(new Map());

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info", action?: { label: string; onClick: () => void }) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const durationMs = action ? ACTION_DURATION : DEFAULT_DURATION;
      setToasts((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { id, message, type, action, durationMs }]);
      const timer = window.setTimeout(() => dismiss(id), durationMs);
      timersRef.current.set(id, timer);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-container" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
