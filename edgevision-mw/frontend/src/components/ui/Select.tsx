import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "./cn";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchable?: boolean;
  "aria-label"?: string;
  className?: string;
}

export function Select({
  value,
  options,
  onChange,
  // i18n: callers should pass a translated placeholder string
  placeholder = "Select…",
  searchable = false,
  "aria-label": ariaLabel,
  className,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  const filtered = searchable
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className={cn("ui-relative", className)}>
      <button
        type="button"
        className="ui-select-trigger ui-select-trigger-inner"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{selected?.label ?? placeholder}</span>
        <ChevronDown size={16} aria-hidden />
      </button>
      {open && (
        <div className="ui-popover ui-popover--select" role="listbox">
          {searchable && (
            <input
              className="ui-input ui-select-filter"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              // i18n: callers should pass a translated placeholder via the component API
              placeholder="Filter…"
              autoFocus
            />
          )}
          {filtered.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="option"
              aria-selected={opt.value === value}
              className={cn("ui-menu-item", opt.value === value && "ui-menu-item--active")}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
                setQuery("");
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  side?: "left" | "right";
  children: ReactNode;
}

export function Drawer({ open, onClose, side = "right", children }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="ui-drawer-backdrop" onClick={onClose} role="presentation" />
      <div className={cn("ui-drawer-panel", side === "left" && "ui-drawer-panel--left")}>{children}</div>
    </>
  );
}
