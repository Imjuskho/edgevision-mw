import { cn } from "./cn";

export interface ProgressBarProps {
  value: number;
  max?: number;
  className?: string;
  "aria-label"?: string;
}

export function ProgressBar({ value, max = 100, className, "aria-label": ariaLabel }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div
      className={cn("ui-progress", className)}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={ariaLabel}
    >
      <div className="ui-progress__bar" style={{ "--progress": `${pct}%` } as React.CSSProperties} />
    </div>
  );
}
