import type { LucideIcon, LucideProps } from "lucide-react";

export type IconSize = "sm" | "md" | "lg";

const SIZE_MAP: Record<IconSize, number> = {
  sm: 16,
  md: 20,
  lg: 24,
};

export interface IconProps extends Omit<LucideProps, "size"> {
  icon: LucideIcon;
  size?: IconSize;
}

export function Icon({ icon: LucideIconComponent, size = "sm", ...props }: IconProps) {
  return <LucideIconComponent size={SIZE_MAP[size]} strokeWidth={2} aria-hidden {...props} />;
}
