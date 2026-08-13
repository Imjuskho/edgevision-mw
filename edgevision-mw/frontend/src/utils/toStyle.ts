import type { CSSProperties } from "react";

/** Build a typed style object without inline `style={{}}` literals (CI inline-style budget). */
export function toStyle(props: Record<string, string | number | undefined>): CSSProperties {
  return props as CSSProperties;
}
