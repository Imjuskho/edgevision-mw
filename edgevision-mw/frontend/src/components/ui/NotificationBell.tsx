import { useEffect, useRef, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "./Badge";
import { cn } from "./cn";
import { IconButton } from "./IconButton";

export interface Notification {
  id: string;
  title: string;
  body?: string;
  read: boolean;
  timestamp: string;
}

export interface NotificationBellProps {
  notifications: Notification[];
  onMarkRead: (id: string) => void;
  onMarkAllRead?: () => void;
  className?: string;
}

function formatRelativeTime(value: string, locale: string) {
  const rtf = new Intl.RelativeTimeFormat(locale.startsWith("ny") ? "ny-MW" : "en", { numeric: "auto" });
  const diffMs = Date.now() - new Date(value).getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (Math.abs(diffDays) >= 1) return rtf.format(-diffDays, "day");
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  if (Math.abs(diffHours) >= 1) return rtf.format(-diffHours, "hour");
  const diffMinutes = Math.round(diffMs / (1000 * 60));
  return rtf.format(-diffMinutes, "minute");
}

export function NotificationBell({ notifications, onMarkRead, onMarkAllRead, className }: NotificationBellProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className={cn("ui-notif-bell", className)} ref={ref}>
      <IconButton
        label={t("notifications.title", "Notifications")}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Bell size={18} />
      </IconButton>
      {unread > 0 && (
        <span className="ui-notif-dot" aria-hidden>
          {unread > 9 ? "9+" : unread}
        </span>
      )}
      {open && (
        <div
          className="ui-notif-popover ui-popover"
          role="menu"
          aria-label={t("notifications.title", "Notifications")}
        >
          <div className="ui-notif-popover__header">
            <div className="ui-notif-popover__title-row">
              <span className="ui-notif-popover__title">{t("notifications.title", "Notifications")}</span>
              {unread > 0 && <Badge variant="info">{unread}</Badge>}
            </div>
            {onMarkAllRead && unread > 0 && (
              <button
                type="button"
                className="ui-notif-popover__action"
                onClick={() => {
                  onMarkAllRead();
                }}
              >
                <CheckCheck size={14} aria-hidden />
                {t("notifications.markAllRead", "Mark all read")}
              </button>
            )}
          </div>
          <div className="ui-notif-popover__list">
            {notifications.length === 0 ? (
              <div className="ui-notif-popover__empty">
                <Bell size={24} strokeWidth={1.5} aria-hidden />
                <p>{t("notifications.empty", "No notifications yet")}</p>
              </div>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  role="menuitem"
                  className={cn("ui-notif-row", !n.read && "ui-notif-row--unread")}
                  onClick={() => onMarkRead(n.id)}
                >
                  {!n.read && <span className="ui-notif-row__dot" aria-hidden />}
                  <div className={cn("ui-notif-row__content", n.read && "ui-notif-row__content--read")}>
                    <span className="ui-notif-row__title">{n.title}</span>
                    {n.body && <span className="ui-notif-row__body">{n.body}</span>}
                    <time className="ui-notif-row__time" dateTime={n.timestamp}>
                      {formatRelativeTime(n.timestamp, i18n.language)}
                    </time>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
