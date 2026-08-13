import { useEffect, useRef, useState } from "react";
import { LogOut, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Avatar } from "./Avatar";
import { Badge } from "./Badge";
import { cn } from "./cn";

export interface ProfileMenuProps {
  name: string;
  email?: string;
  role: string;
  onSettings: () => void;
  onLogout: () => void;
  className?: string;
}

export function ProfileMenu({ name, email, role, onSettings, onLogout, className }: ProfileMenuProps) {
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
    <div className={cn("ui-relative", className)} ref={ref}>
      <button
        type="button"
        className="ui-btn ui-btn--ghost ui-profile-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Avatar name={name} size="sm" />
        <span className="text-body-sm ui-profile-name">{name}</span>
      </button>
      {open && (
        <div className="ui-popover ui-popover--profile" role="menu">
          <div className="ui-profile-header">
            <div className="ui-profile-name-bold">{name}</div>
            {email && <div className="text-caption">{email}</div>}
            <div className="ui-profile-role">
              <Badge variant="info">{role}</Badge>
            </div>
          </div>
          <button type="button" className="ui-menu-item" role="menuitem" onClick={() => { onSettings(); setOpen(false); }}>
            <Settings size={16} /> {t("nav.settings", "Settings")}
          </button>
          <button type="button" className="ui-menu-item ui-menu-item--danger" role="menuitem" onClick={() => { onLogout(); setOpen(false); }}>
            <LogOut size={16} /> {t("nav.logout", "Logout")}
          </button>
        </div>
      )}
    </div>
  );
}
