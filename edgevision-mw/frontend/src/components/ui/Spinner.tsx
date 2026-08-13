import { cn } from "./cn";

export interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <span
      className={cn(
        "ui-spinner",
        size === "sm" && "ui-spinner--sm",
        size === "lg" && "ui-spinner--lg",
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  );
}
