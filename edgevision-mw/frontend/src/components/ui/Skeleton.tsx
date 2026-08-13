import { cn } from "./cn";
import { toStyle } from "../../utils/toStyle";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  variant?: "rect" | "text" | "circle";
  shimmer?: boolean;
  className?: string;
}

export function Skeleton({ width, height, variant = "rect", shimmer = true, className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "ui-skeleton",
        variant === "text" && "ui-skeleton--text",
        variant === "circle" && "ui-skeleton--circle",
        shimmer && "ui-skeleton--shimmer skeleton-shimmer",
        className,
      )}
      style={toStyle({
        width,
        height,
      })}
      aria-hidden
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="ui-skeleton-card">
      <Skeleton height={120} />
      <Skeleton variant="text" width="60%" />
      <Skeleton variant="text" width="40%" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="ui-skeleton-table">
      <Skeleton height={36} />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={44} />
      ))}
    </div>
  );
}
