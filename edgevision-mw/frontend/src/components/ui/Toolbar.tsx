import type { ReactNode } from "react";
import { cn } from "./cn";

export interface ToolbarProps {
  label?: string;
  count?: number;
  countLabel?: string;
  search?: ReactNode;
  filters?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function Toolbar({ label, count, countLabel, search, filters, actions, className }: ToolbarProps) {
  return (
    <div className={cn("ui-toolbar", className)}>
      {(label || count !== undefined) && (
        <div className="ui-toolbar__meta">
          {label && <span className="ui-toolbar__label">{label}</span>}
          {count !== undefined && (
            <span className="ui-toolbar__count">{countLabel ?? count}</span>
          )}
        </div>
      )}
      {search && <div className="ui-toolbar__search">{search}</div>}
      {filters && <div className="ui-toolbar__filters">{filters}</div>}
      {actions && <div className="ui-toolbar__actions">{actions}</div>}
    </div>
  );
}
