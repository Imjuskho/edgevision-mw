import type { ReactNode } from "react";
import { cn } from "./cn";

export type BadgeVariant = "default" | "success" | "warning" | "danger" | "info";

export interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  return (
    <span className={cn("ui-badge", variant !== "default" && `ui-badge--${variant}`, className)}>
      {children}
    </span>
  );
}
