import type { ReactNode } from "react";
import { cn } from "./cn";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  delta?: string;
  deltaDirection?: "up" | "down";
  sparkline?: ReactNode;
  className?: string;
}

export function StatCard({ label, value, delta, deltaDirection, sparkline, className }: StatCardProps) {
  return (
    <div className={cn("ui-stat-card", className)}>
      <div className="ui-stat-card__label">{label}</div>
      <div className="ui-stat-card__value">{value}</div>
      {delta && (
        <div className={cn("ui-stat-card__delta", deltaDirection && `ui-stat-card__delta--${deltaDirection}`)}>
          {delta}
        </div>
      )}
      {sparkline}
    </div>
  );
}
