import { useEffect, useRef, useState } from "react";
import { Wifi, WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "./cn";

export interface ConnectionPillProps {
  isOnline: boolean;
  pendingSync?: number;
  onSync?: () => void;
  lowData?: boolean;
  onToggleLowData?: () => void;
  className?: string;
}

export function ConnectionPill({
  isOnline,
  pendingSync = 0,
  onSync,
  lowData,
  onToggleLowData,
  className,
}: ConnectionPillProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className={cn("ui-relative", className)}>
      <button
        type="button"
        className={cn("ui-connection-pill", !isOnline && "ui-connection-pill--offline")}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="ui-connection-pill__dot" aria-hidden />
        {isOnline ? t("nav.online", "Online") : t("nav.offline", "Offline")}
        {pendingSync > 0 && ` · ${pendingSync}`}
        {isOnline ? <Wifi size={14} aria-hidden /> : <WifiOff size={14} aria-hidden />}
      </button>
      {open && (
        <div className="ui-popover ui-popover--connection">
          {pendingSync > 0 && onSync && (
            <button type="button" className="ui-menu-item" onClick={() => { onSync(); setOpen(false); }}>
              {t("sync.syncNow", "Sync now")} ({pendingSync})
            </button>
          )}
          {onToggleLowData && (
            <button type="button" className="ui-menu-item" onClick={() => { onToggleLowData(); setOpen(false); }}>
              {lowData ? t("settings.lowDataOff", "Disable low data mode") : t("settings.lowDataOn", "Enable low data mode")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
