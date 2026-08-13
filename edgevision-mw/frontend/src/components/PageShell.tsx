import type { ReactNode } from "react";

export type PageAccent =
  | "labeling"
  | "data"
  | "quality"
  | "analysis"
  | "fleet"
  | "settings"
  | "export"
  | "training"
  | "health"
  | "taxonomy"
  | "segment";

interface PageShellProps {
  accent: PageAccent;
  title: string;
  subtitle?: string;
  badge?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  fullWidth?: boolean;
}

export function PageShell({
  accent,
  title,
  subtitle,
  badge,
  actions,
  children,
  className = "",
  fullWidth = false,
}: PageShellProps) {
  return (
    <div className={`page-shell page-accent--${accent}${fullWidth ? " page-shell--full" : ""} ${className}`.trim()}>
      <header className="page-accent-header">
        <div className="page-accent-header-text">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {badge && <span className="page-accent-badge">{badge}</span>}
        {actions && <div className="page-accent-actions">{actions}</div>}
      </header>
      <div className="page-accent-body">{children}</div>
    </div>
  );
}
