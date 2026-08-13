import { cn } from "./cn";
import { toStyle } from "../../utils/toStyle";

export interface AvatarProps {
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function colorFromIdentity(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  const hue = Math.abs(hash) % 360;
  return `oklch(0.55 0.12 ${hue})`;
}

export function Avatar({ name, size = "md", className }: AvatarProps) {
  return (
    <span
      className={cn("ui-avatar", `ui-avatar--${size}`, className)}
      style={toStyle({
        background: `${colorFromIdentity(name)}22`,
        color: colorFromIdentity(name),
      })}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}
