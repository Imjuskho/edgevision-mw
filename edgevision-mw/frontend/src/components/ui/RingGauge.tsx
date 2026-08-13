import { cn } from "./cn";
import { toStyle } from "../../utils/toStyle";

export interface RingGaugeProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  label?: string;
  className?: string;
}

export function RingGauge({
  value,
  size = 80,
  strokeWidth = 6,
  color = "var(--accent-blue)",
  label,
  className,
}: RingGaugeProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(100, Math.max(0, value)) / 100) * circumference;

  const sizeClass = size === 56 ? "ui-ring-gauge--sm" : size === 80 ? "ui-ring-gauge--md" : size === 120 ? "ui-ring-gauge--lg" : undefined;

  return (
    <div
      className={cn("ui-ring-gauge", sizeClass, className)}
      style={sizeClass ? undefined : toStyle({ width: size, height: size })}
    >
      <svg width={size} height={size} aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border-default)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="ui-ring-gauge__label">{label ?? `${Math.round(value)}%`}</span>
    </div>
  );
}
